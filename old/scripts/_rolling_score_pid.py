"""
ローリング複合スコア + 正規化 + PID制御シミュレーション

Score(t) = EV × PF × √N × Omega × Tail × RecentFactor × CostTol
           ────────────────────────────────────────────────────────
                              1 + MaxDD

設計:
  - 30トレードのローリング窓で毎トレード更新
  - RecentFactor: 窓内後半10件 / 前半20件のEV比（下限0.3）
  - IS期間のスコア分布からTF横断で正規化（0〜100）
  - OOSに同じ正規化を適用してPID入力とする

PID:
  目標値 = 50
  誤差 = 50 - 現在の正規化スコア
  lot_multiplier = clip(1.0 + Kp×e + Ki×∑e + Kd×Δe, 0.1, 2.0)
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.rcParams["font.family"] = "Yu Gothic"
import matplotlib.pyplot as plt
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR   = Path("data/dukascopy")
PIP        = 0.01; ENTRY_COST = 0.2; SW = 20
IS_START   = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START  = "2024-01-01"; OOS_END   = "2025-01-01"

ROLL_WIN   = 30    # ローリング窓（トレード数）
RECENT_K   = 0.33  # 窓内の「直近」割合（後半33%）
COST_PIPS  = ENTRY_COST

PID_TARGET = 50.0
PID_KP     = 0.012
PID_KI     = 0.003
PID_KD     = 0.005

# ロット制御の下限・上限・閾値
LOT_MIN       = 0.1   # ロット最小倍率（完全停止ではなく最小継続）
LOT_MAX       = 2.0   # ロット最大倍率
LOT_STOP_THR  = 20.0  # 正規化スコアがこれ以下 → 完全停止（0×）
LOT_FULL_THR  = 70.0  # 正規化スコアがこれ以上 → フルロット以上許可

TF_CONFIGS = {
    "5min":  dict(rule="5min",  rb=12, rp=10, mh=5,  color="#3498db"),
    "30min": dict(rule="30min", rb=6,  rp=15, mh=3,  color="#e67e22"),
    "1h":    dict(rule="1h",    rb=4,  rp=25, mh=2,  color="#2ecc71"),
}

OUT_PDF = Path("rolling_score_pid.pdf")

# ── データ準備 ────────────────────────────────────────────────────────────────
dfs5 = {p: pd.read_parquet(DATA_DIR/f"{p}_5min.parquet")
        for p in PAIRS if (DATA_DIR/f"{p}_5min.parquet").exists()}
rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
st   = currency_strength(rd)
sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())
df5  = dfs5["USDJPY"]


def resample(rule):
    if rule == "5min": return df5, sd5.reindex(df5.index)
    df = df5.resample(rule, label="left", closed="left").agg(
        Open=("Open","first"), High=("High","max"),
        Low=("Low","min"), Close=("Close","last"), Volume=("Volume","sum")
    ).dropna(subset=["Open"])
    sd = sd5.resample(rule, label="left", closed="left").last().reindex(df.index)
    return df, sd


def make_sig(df, sd, rb, rp):
    c = df["Close"]
    rh = c.shift(1).rolling(rb).max()
    rl = c.shift(1).rolling(rb).min()
    ir = (rh-rl) <= rp * PIP
    s  = sd.reindex(df.index)
    return pd.DataFrame({"c":c,"o":df["Open"],
                         "ls":ir&(c>rh)&(s>0),
                         "ss":ir&(c<rl)&(s<0),
                         "rm":(rh+rl)/2})


def run_bt(sig, mh):
    """バックテスト: (pnl_array, entry_time_array) を返す"""
    c=sig["c"].values; o=sig["o"].values; rm=sig["rm"].values
    ls=sig["ls"].values; ss=sig["ss"].values; idx=sig.index; n=len(sig)
    pnls=[]; times=[]; inT=False; d=0; ep=sp=0.0; eb=-1
    for i in range(1,n-1):
        if not inT:
            if ls[i-1]:   d=1;  ep=o[i]+ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
            elif ss[i-1]: d=-1; ep=o[i]-ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
        else:
            held=i-eb; unr=(c[i]-ep)*d/PIP; xp=None
            if d==1  and c[i]<=sp: xp=sp
            elif d==-1 and c[i]>=sp: xp=sp
            elif held>=mh and unr>0:
                if d==1  and c[i]<c[i-1]: xp=c[i]
                elif d==-1 and c[i]>c[i-1]: xp=c[i]
            if xp is not None:
                pnls.append((xp-ep)*d/PIP); times.append(idx[i])
                inT=False; d=0
    return np.array(pnls), pd.DatetimeIndex(times)


# ── スコア計算（1ウィンドウ分） ───────────────────────────────────────────────
def score_window(p: np.ndarray) -> float:
    if len(p) < 5: return 0.0
    w=p[p>0]; l=p[p<=0]; n=len(p)

    ev = p.mean()
    if ev <= 0: return 0.0

    pf = w.sum()/abs(l.sum()) if len(l)>0 and l.sum()!=0 else 5.0
    if pf <= 1.0: return 0.0

    sqrt_n = np.sqrt(n)

    # Omega（閾値=0）
    gains  = np.sum(np.maximum(p, 0))
    losses = np.sum(np.maximum(-p, 0))
    omega  = gains/losses if losses>0 else 5.0

    # Tail Ratio
    p95 = np.percentile(p, 95)
    p05 = np.percentile(p, 5)
    tail = abs(p95/p05) if p05!=0 else 5.0

    # RecentFactor（窓後半 vs 前半）
    split = max(1, int(n * (1 - RECENT_K)))
    ev_old = p[:split].mean() if split>0 else ev
    ev_new = p[split:].mean() if split<n else ev
    if ev_old > 0:
        rf = np.clip(ev_new / ev_old, 0.3, 3.0)
    else:
        rf = 0.3 if ev_new >= 0 else 0.0

    # CostTolerance
    cost_tol = np.clip(ev / COST_PIPS, 0.0, 50.0)

    # MaxDD
    eq   = np.cumsum(p)
    peak = np.maximum.accumulate(np.maximum(eq, 0))
    mdd  = abs((eq-peak).min())

    return (ev * pf * sqrt_n * omega * tail * rf * cost_tol) / (1 + mdd)


# ── ローリングスコア系列 ──────────────────────────────────────────────────────
def rolling_scores(pnls: np.ndarray, times: pd.DatetimeIndex) -> pd.Series:
    scores = []
    for i in range(len(pnls)):
        start = max(0, i - ROLL_WIN + 1)
        s = score_window(pnls[start:i+1])
        scores.append(s)
    return pd.Series(scores, index=times)


# ── 正規化（IS期間の分布を基準） ─────────────────────────────────────────────
def normalize_with_params(s: pd.Series, lo: float, hi: float) -> pd.Series:
    if hi == lo: return pd.Series(50.0, index=s.index)
    return ((s - lo) / (hi - lo) * 100).clip(0, 100)


# ── PIDシミュレーション ───────────────────────────────────────────────────────
def pid_sim(norm_scores: pd.Series, target=PID_TARGET,
            kp=PID_KP, ki=PID_KI, kd=PID_KD) -> pd.Series:
    """
    PID制御 + 閾値による強制停止・上限制御

    スコア < LOT_STOP_THR  → 強制停止（0×）
    スコア < 30             → 最小ロット（LOT_MIN）
    スコア 30〜70           → PID出力でロット調整
    スコア > LOT_FULL_THR  → フルロット以上許可（上限LOT_MAX）
    """
    integral = 0.0
    prev_err = 0.0
    lots = []
    for s in norm_scores:
        # 強制停止域
        if s <= LOT_STOP_THR:
            lots.append(0.0)
            integral = 0.0   # 積分リセット（ウィンドアップ防止）
            prev_err = 0.0
            continue

        err      = target - s
        integral = np.clip(integral + err, -200, 200)
        deriv    = err - prev_err
        u        = kp*err + ki*integral + kd*deriv
        lot      = np.clip(1.0 + u, LOT_MIN, LOT_MAX)

        # 下限ガード: スコア30未満はLOT_MINに固定
        if s < 30:
            lot = LOT_MIN

        lots.append(lot)
        prev_err = err
    return pd.Series(lots, index=norm_scores.index)


# ── メイン ────────────────────────────────────────────────────────────────────
print("ローリングスコア計算中...")

raw_series  = {}   # TF → raw rolling score series（IS+OOS全期間）
is_raw      = {}   # TF → IS期間のrawスコア

for tf, cfg in TF_CONFIGS.items():
    df, sd = resample(cfg["rule"])
    full_sig = make_sig(df, sd, cfg["rb"], cfg["rp"])
    pnls_all, times_all = run_bt(full_sig, cfg["mh"])

    # タイムゾーン統一
    tz = times_all.tz
    is_end_ts  = pd.Timestamp(IS_END,  tz=tz)
    oos_st_ts  = pd.Timestamp(OOS_START, tz=tz)
    oos_en_ts  = pd.Timestamp(OOS_END,   tz=tz)
    is_mask    = times_all < is_end_ts
    oos_mask   = (times_all >= oos_st_ts) & (times_all <= oos_en_ts)

    # 全期間でローリングスコアを計算
    rs = rolling_scores(pnls_all, times_all)
    raw_series[tf] = rs
    is_raw[tf]     = rs[is_mask]
    print(f"  {tf}: 全{len(pnls_all)}件  IS={is_mask.sum()}件  OOS={oos_mask.sum()}件")

# IS期間の全TF横断でパーセンタイルを基準に正規化
all_is_vals = np.concatenate([v.values for v in is_raw.values()])
all_is_vals = all_is_vals[np.isfinite(all_is_vals) & (all_is_vals > 0)]
NORM_LO = np.percentile(all_is_vals, 5)
NORM_HI = np.percentile(all_is_vals, 95)
print(f"\n正規化範囲（IS p5〜p95）: {NORM_LO:.3f} 〜 {NORM_HI:.3f}")

# 正規化・PID
norm_series = {}
pid_series  = {}
for tf in TF_CONFIGS:
    ns = normalize_with_params(raw_series[tf], NORM_LO, NORM_HI)
    norm_series[tf] = ns
    pid_series[tf]  = pid_sim(ns)

# ── 数値サマリー ──────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print("  ローリングスコア統計（正規化後 0〜100）")
print(f"{'='*65}")
print(f"  {'TF':>5} | {'IS 平均':>8} {'IS 中央':>8} {'IS min':>7} {'IS max':>7} "
      f"| {'OOS 平均':>9} {'OOS 中央':>9}")
print("  " + "-"*65)
for tf in TF_CONFIGS:
    ns     = norm_series[tf]
    tz2    = ns.index.tz
    is_ts  = pd.Timestamp(IS_START,  tz=tz2)
    ie_ts  = pd.Timestamp(IS_END,    tz=tz2)
    os_ts  = pd.Timestamp(OOS_START, tz=tz2)
    oe_ts  = pd.Timestamp(OOS_END,   tz=tz2)
    is_s   = ns[(ns.index >= is_ts) & (ns.index < ie_ts)]
    oos_s  = ns[(ns.index >= os_ts) & (ns.index <= oe_ts)]
    print(f"  {tf:>5} | {is_s.mean():>8.1f} {is_s.median():>8.1f} "
          f"{is_s.min():>7.1f} {is_s.max():>7.1f} | "
          f"{oos_s.mean():>9.1f} {oos_s.median():>9.1f}")

print(f"\n  PID設定: target={PID_TARGET}  Kp={PID_KP}  Ki={PID_KI}  Kd={PID_KD}")
print(f"\n  ロット倍率統計（PID出力）")
print(f"  {'TF':>5} | {'IS 平均':>8} {'IS min':>7} {'IS max':>7} "
      f"| {'OOS 平均':>9} {'OOS min':>9} {'OOS max':>9}")
print("  " + "-"*65)
for tf in TF_CONFIGS:
    ps  = pid_series[tf]
    tz3 = ps.index.tz
    is_ts=pd.Timestamp(IS_START,tz=tz3); ie_ts=pd.Timestamp(IS_END,tz=tz3)
    os_ts=pd.Timestamp(OOS_START,tz=tz3); oe_ts=pd.Timestamp(OOS_END,tz=tz3)
    is_p  = ps[(ps.index >= is_ts) & (ps.index < ie_ts)]
    oos_p = ps[(ps.index >= os_ts) & (ps.index <= oe_ts)]
    print(f"  {tf:>5} | {is_p.mean():>8.2f} {is_p.min():>7.2f} {is_p.max():>7.2f} | "
          f"{oos_p.mean():>9.2f} {oos_p.min():>9.2f} {oos_p.max():>9.2f}")

# ── グラフ ────────────────────────────────────────────────────────────────────
print("\nグラフ生成中...")
fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True,
                          facecolor="#1a1a2e")
fig.suptitle("USDJPY レンジブレイク 3戦略 ローリングスコア・PID制御",
             fontsize=13, color="white", y=0.98)

# IS/OOS境界
tz_plot  = norm_series["5min"].index.tz
boundary = pd.Timestamp(IS_END, tz=tz_plot)

for ax in axes:
    ax.set_facecolor("#16213e")
    ax.axvline(boundary, color="#e74c3c", linewidth=1.2,
               linestyle="--", alpha=0.8, label="IS/OOS境界")
    tz_b = boundary.tz
    ax.axvspan(pd.Timestamp(IS_START, tz=tz_b), boundary, alpha=0.07, color="#3498db")
    ax.axvspan(boundary, pd.Timestamp(OOS_END, tz=tz_b), alpha=0.07, color="#e67e22")

# Panel 1: 生スコア（対数）
ax1 = axes[0]
for tf, cfg in TF_CONFIGS.items():
    rs = raw_series[tf]
    rs_plot = rs[(rs.index >= pd.Timestamp(IS_START, tz=tz_plot)) &
                 (rs.index <= pd.Timestamp(OOS_END,  tz=tz_plot))]
    rs_log  = np.log1p(rs_plot.clip(lower=0))
    ax1.plot(rs_plot.index, rs_log, color=cfg["color"],
             linewidth=0.8, alpha=0.8, label=tf)
ax1.set_ylabel("Raw Score (log1p)", color="white", fontsize=10)
ax1.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
           labelcolor="white", framealpha=0.7)
ax1.tick_params(colors="white"); ax1.yaxis.label.set_color("white")
for spine in ax1.spines.values(): spine.set_edgecolor("#444")
ax1.set_title("① 生スコア（対数）", color="#aaa", fontsize=10, loc="left")

# Panel 2: 正規化スコア + 目標線
ax2 = axes[1]
ax2.axhline(PID_TARGET, color="#f1c40f", linewidth=1.0,
            linestyle=":", alpha=0.9, label=f"目標値 {PID_TARGET}")
ax2.axhline(70, color="#2ecc71", linewidth=0.6, linestyle=":", alpha=0.5)
ax2.axhline(30, color="#e74c3c", linewidth=0.6, linestyle=":", alpha=0.5)
for tf, cfg in TF_CONFIGS.items():
    ns = norm_series[tf]
    ns_plot = ns[(ns.index >= pd.Timestamp(IS_START, tz=tz_plot)) &
                 (ns.index <= pd.Timestamp(OOS_END,  tz=tz_plot))]
    ax2.plot(ns_plot.index, ns_plot, color=cfg["color"],
             linewidth=0.9, alpha=0.85, label=tf)
    # 週次平均を太線で
    ns_w = ns_plot.resample("W").mean()
    ax2.plot(ns_w.index, ns_w, color=cfg["color"],
             linewidth=2.0, alpha=0.6)
ax2.set_ylim(-5, 105)
ax2.set_ylabel("正規化スコア (0〜100)", color="white", fontsize=10)
ax2.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
           labelcolor="white", framealpha=0.7)
ax2.tick_params(colors="white")
for spine in ax2.spines.values(): spine.set_edgecolor("#444")
ax2.set_title("② 正規化スコア（細線:全トレード / 太線:週次平均）", color="#aaa", fontsize=10, loc="left")
ax2.text(pd.Timestamp("2022-02-01"), 72, "フルロット域(>70)", color="#2ecc71", fontsize=7, alpha=0.7)
ax2.text(pd.Timestamp("2022-02-01"), 32, "縮小域(<30)", color="#e74c3c", fontsize=7, alpha=0.7)

# Panel 3: PIDロット倍率
ax3 = axes[2]
ax3.axhline(1.0, color="#aaa", linewidth=0.8, linestyle=":", alpha=0.7)
for tf, cfg in TF_CONFIGS.items():
    ps = pid_series[tf]
    ps_plot = ps[(ps.index >= pd.Timestamp(IS_START, tz=tz_plot)) &
                 (ps.index <= pd.Timestamp(OOS_END,  tz=tz_plot))]
    ps_w = ps_plot.resample("W").mean()
    ax3.fill_between(ps_w.index, 1.0, ps_w,
                     alpha=0.25, color=cfg["color"])
    ax3.plot(ps_w.index, ps_w, color=cfg["color"],
             linewidth=1.8, label=tf)
ax3.set_ylim(0.0, 2.2)
ax3.set_ylabel("ロット倍率 (×)", color="white", fontsize=10)
ax3.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
           labelcolor="white", framealpha=0.7)
ax3.tick_params(colors="white")
ax3.set_xlabel("日付", color="white", fontsize=10)
for spine in ax3.spines.values(): spine.set_edgecolor("#444")
ax3.set_title(f"③ PIDロット倍率（週次・Kp={PID_KP} Ki={PID_KI} Kd={PID_KD}）",
              color="#aaa", fontsize=10, loc="left")

# 凡例

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(OUT_PDF, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close()
print(f"保存: {OUT_PDF.resolve()}")
print("完了")
