"""
期待値（EV）ベース PID制御

制御設計:
  制御対象 : 30トレード ローリングEV（pips/トレード）
  正規化   : norm_EV = rolling_EV / target_EV  （1.0 = IS平均と同等）
  目標値   : 1.0（正規化後）
  誤差     : 1.0 - norm_EV

  ロット倍率 = clip(1.0 + Kp×e + Ki×Σe + Kd×Δe, 0.0, 2.0)

  強制停止 : rolling_EV < 0              → ロット 0.0（積分もリセット）
  下限域   : norm_EV < 0.5               → ロット 0.3（最小継続）
  通常域   : norm_EV 0.5〜1.5            → PID制御
  上昇域   : norm_EV > 1.5               → ロット 2.0（上限）

TF別 IS target EV:
  5min  : +1.164 pips
  30min : +5.344 pips
  1h    : +7.480 pips
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.rcParams["font.family"] = "Yu Gothic"
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR  = Path("data/dukascopy")
PIP       = 0.01; ENTRY_COST = 0.2; SW = 20
IS_START  = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START = "2024-01-01"; OOS_END   = "2025-01-01"

ROLL_WIN = 100      # ローリング窓（トレード数）
PID_KP   = 0.5     # P: norm_EVの0.1ずれで5%ロット変化
PID_KI   = 0.05    # I: 累積ずれが効いてくる
PID_KD   = 0.1     # D: EV悪化速度に先手

LOT_MIN  = 0.3     # 下限域のロット（EV正だが低い時）
LOT_MAX  = 2.0
LOT_STOP = 0.0     # EV負の時（強制停止）

TF_CONFIGS = {
    "5min":  dict(rule="5min",  rb=12, rp=10, mh=5,  color="#3498db", target_ev=1.164),
    "30min": dict(rule="30min", rb=6,  rp=15, mh=3,  color="#e67e22", target_ev=5.344),
    "1h":    dict(rule="1h",    rb=4,  rp=25, mh=2,  color="#2ecc71", target_ev=7.480),
}

OUT_PDF = Path("ev_pid_w100.pdf")

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
    c=sig["c"].values; o=sig["o"].values; rm=sig["rm"].values
    ls=sig["ls"].values; ss=sig["ss"].values; idx=sig.index; n=len(sig)
    pnls=[]; times=[]; inT=False; d=0; ep=sp=0.0; eb=-1
    for i in range(1, n-1):
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


# ── ローリングEV ──────────────────────────────────────────────────────────────
def rolling_ev(pnls, times, window=ROLL_WIN):
    evs = []
    for i in range(len(pnls)):
        start = max(0, i - window + 1)
        evs.append(pnls[start:i+1].mean())
    return pd.Series(evs, index=times)


# ── PIDシミュレーション ───────────────────────────────────────────────────────
def pid_sim(ev_series: pd.Series, target_ev: float) -> tuple[pd.Series, pd.Series]:
    """
    Returns: (lot_series, norm_ev_series)
    """
    integral = 0.0
    prev_err = 0.0
    lots = []
    norm_evs = []

    for ev in ev_series:
        norm = ev / target_ev   # 正規化EV（1.0 = 目標）

        # ── 強制停止 ──
        if ev <= 0:
            lots.append(LOT_STOP)
            norm_evs.append(norm)
            integral = 0.0      # 積分ウィンドアップリセット
            prev_err = 0.0
            continue

        # ── PID ──
        err      = 1.0 - norm           # 目標1.0との誤差
        integral = np.clip(integral + err, -10.0, 10.0)
        deriv    = err - prev_err
        u        = PID_KP*err + PID_KI*integral + PID_KD*deriv

        lot = np.clip(1.0 + u, LOT_MIN if norm < 0.5 else 0.0, LOT_MAX)

        # 下限域（EV正だが目標の50%未満）は最小ロットに固定
        if norm < 0.5:
            lot = LOT_MIN

        lots.append(lot)
        norm_evs.append(norm)
        prev_err = err

    return (pd.Series(lots,     index=ev_series.index),
            pd.Series(norm_evs, index=ev_series.index))


# ── メイン ────────────────────────────────────────────────────────────────────
print("=" * 60)
print("  EV ベース PID制御シミュレーション")
print(f"  ローリング窓: {ROLL_WIN}トレード")
print(f"  Kp={PID_KP}  Ki={PID_KI}  Kd={PID_KD}")
print("=" * 60)

results = {}

for tf, cfg in TF_CONFIGS.items():
    df, sd = resample(cfg["rule"])
    sig    = make_sig(df, sd, cfg["rb"], cfg["rp"])
    pnls, times = run_bt(sig, cfg["mh"])

    ev_all        = rolling_ev(pnls, times)
    lot_all, norm = pid_sim(ev_all, cfg["target_ev"])

    tz = times.tz
    is_ts  = pd.Timestamp(IS_START,  tz=tz)
    ie_ts  = pd.Timestamp(IS_END,    tz=tz)
    os_ts  = pd.Timestamp(OOS_START, tz=tz)
    oe_ts  = pd.Timestamp(OOS_END,   tz=tz)

    is_mask  = (times >= is_ts)  & (times < ie_ts)
    oos_mask = (times >= os_ts)  & (times <= oe_ts)

    results[tf] = dict(
        pnls=pnls, times=times,
        ev_all=ev_all, lot_all=lot_all, norm_all=norm,
        is_mask=is_mask, oos_mask=oos_mask,
        target_ev=cfg["target_ev"],
    )

    # ── 統計表示 ──────────────────────────────────────────────────────────────
    for label, mask in [("IS", is_mask), ("OOS", oos_mask)]:
        ev_s  = ev_all[mask]
        lot_s = lot_all[mask]
        p_s   = pnls[mask]

        # PID適用後の実効損益 = pnl × lot（前のトレードのロットを使う）
        lot_arr = lot_s.values
        lots_prev = np.roll(lot_arr, 1); lots_prev[0] = 1.0
        eff_pnl = p_s * lots_prev

        n_stop = (lot_s == 0.0).sum()
        n_min  = (lot_s == LOT_MIN).sum()

        print(f"\n  [{tf} {label}]  N={mask.sum():,}件  target_EV={cfg['target_ev']:.3f}p")
        print(f"    ローリングEV: 平均{ev_s.mean():+.3f}p  中央{ev_s.median():+.3f}p"
              f"  min{ev_s.min():+.3f}p  max{ev_s.max():+.3f}p")
        print(f"    ロット倍率:   平均{lot_s.mean():.2f}×  停止{n_stop}件({n_stop/len(lot_s)*100:.0f}%)"
              f"  最小{n_min}件")
        print(f"    実効損益(EV調整後): {eff_pnl.sum():+.1f}p"
              f"  vs 固定1.0×: {p_s.sum():+.1f}p"
              f"  差: {eff_pnl.sum()-p_s.sum():+.1f}p")


# ── グラフ ────────────────────────────────────────────────────────────────────
print("\nグラフ生成中...")

with PdfPages(OUT_PDF) as pdf:
    fig, axes = plt.subplots(3, 1, figsize=(18, 12), sharex=True,
                              facecolor="#1a1a2e")
    fig.suptitle("USDJPY レンジブレイク 3戦略  EV-PID制御  ローリング30トレード",
                 fontsize=13, color="white", y=0.99)

    tz_p = results["5min"]["times"].tz
    is_s = pd.Timestamp(IS_START,  tz=tz_p)
    ie_s = pd.Timestamp(IS_END,    tz=tz_p)
    os_s = pd.Timestamp(OOS_START, tz=tz_p)
    oe_s = pd.Timestamp(OOS_END,   tz=tz_p)

    # ① ローリングEV（実値 pips）
    ax1 = axes[0]
    ax1.set_facecolor("#16213e")
    ax1.axhline(0, color="#e74c3c", linewidth=1.0, linestyle="--", alpha=0.8)
    ax1.axvline(ie_s, color="#f1c40f", linewidth=1.2, linestyle="--", alpha=0.7)
    ax1.axvspan(is_s, ie_s, alpha=0.07, color="#3498db")
    ax1.axvspan(ie_s, oe_s, alpha=0.07, color="#e67e22")
    for tf, cfg in TF_CONFIGS.items():
        r  = results[tf]
        ev = r["ev_all"]
        ev_plot = ev[(ev.index >= is_s) & (ev.index <= oe_s)]
        ev_w    = ev_plot.resample("W").mean()
        ax1.plot(ev_w.index, ev_w, color=cfg["color"], linewidth=1.8,
                 alpha=0.85, label=f"{tf}  target={cfg['target_ev']:.2f}p")
        ax1.axhline(cfg["target_ev"], color=cfg["color"],
                    linewidth=0.6, linestyle=":", alpha=0.5)
    ax1.set_ylabel("ローリングEV (pips)", color="white", fontsize=10)
    ax1.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
               labelcolor="white", framealpha=0.8)
    ax1.tick_params(colors="white")
    for s in ax1.spines.values(): s.set_edgecolor("#444")
    ax1.set_title("① ローリングEV（週次平均・点線=IS目標値）", color="#aaa",
                  fontsize=10, loc="left")

    # ② 正規化EV（1.0 = 目標）
    ax2 = axes[1]
    ax2.set_facecolor("#16213e")
    ax2.axhline(1.0, color="#f1c40f", linewidth=1.2, linestyle="--",
                alpha=0.9, label="目標 (1.0)")
    ax2.axhline(1.5, color="#2ecc71", linewidth=0.6, linestyle=":", alpha=0.5)
    ax2.axhline(0.5, color="#e74c3c", linewidth=0.6, linestyle=":", alpha=0.5)
    ax2.axhline(0.0, color="#e74c3c", linewidth=1.0, linestyle="-", alpha=0.5)
    ax2.axvline(ie_s, color="#f1c40f", linewidth=1.2, linestyle="--", alpha=0.7)
    ax2.axvspan(is_s, ie_s, alpha=0.07, color="#3498db")
    ax2.axvspan(ie_s, oe_s, alpha=0.07, color="#e67e22")
    for tf, cfg in TF_CONFIGS.items():
        r    = results[tf]
        norm = r["norm_all"]
        nm_plot = norm[(norm.index >= is_s) & (norm.index <= oe_s)]
        nm_w    = nm_plot.resample("W").mean()
        ax2.plot(nm_w.index, nm_w, color=cfg["color"], linewidth=1.8,
                 alpha=0.85, label=tf)
    ax2.set_ylim(-0.5, 2.5)
    ax2.set_ylabel("正規化EV (×目標)", color="white", fontsize=10)
    ax2.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
               labelcolor="white", framealpha=0.8)
    ax2.tick_params(colors="white")
    for s in ax2.spines.values(): s.set_edgecolor("#444")
    ax2.text(is_s + pd.Timedelta(days=20), 1.55, ">1.5 → ロット2×上限",
             color="#2ecc71", fontsize=7, alpha=0.7)
    ax2.text(is_s + pd.Timedelta(days=20), 0.55, "<0.5 → 最小ロット0.3×",
             color="#e74c3c", fontsize=7, alpha=0.7)
    ax2.text(is_s + pd.Timedelta(days=20), 0.05, "<0 → 強制停止",
             color="#e74c3c", fontsize=8, alpha=0.9)
    ax2.set_title("② 正規化EV（rolling_EV ÷ target_EV）", color="#aaa",
                  fontsize=10, loc="left")

    # ③ PIDロット倍率
    ax3 = axes[2]
    ax3.set_facecolor("#16213e")
    ax3.axhline(1.0, color="#aaa", linewidth=0.8, linestyle=":", alpha=0.6)
    ax3.axhline(LOT_MIN, color="#e74c3c", linewidth=0.6,
                linestyle=":", alpha=0.5, label=f"下限 {LOT_MIN}×")
    ax3.axhline(LOT_MAX, color="#2ecc71", linewidth=0.6,
                linestyle=":", alpha=0.5, label=f"上限 {LOT_MAX}×")
    ax3.axvline(ie_s, color="#f1c40f", linewidth=1.2, linestyle="--", alpha=0.7)
    ax3.axvspan(is_s, ie_s, alpha=0.07, color="#3498db")
    ax3.axvspan(ie_s, oe_s, alpha=0.07, color="#e67e22")
    for tf, cfg in TF_CONFIGS.items():
        r   = results[tf]
        lot = r["lot_all"]
        lt_plot = lot[(lot.index >= is_s) & (lot.index <= oe_s)]
        lt_w    = lt_plot.resample("W").mean()
        ax3.fill_between(lt_w.index, LOT_MIN, lt_w,
                         alpha=0.2, color=cfg["color"])
        ax3.plot(lt_w.index, lt_w, color=cfg["color"],
                 linewidth=1.8, label=tf)
    ax3.set_ylim(-0.1, 2.3)
    ax3.set_ylabel("ロット倍率 (×)", color="white", fontsize=10)
    ax3.set_xlabel("日付", color="white", fontsize=10)
    ax3.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e",
               labelcolor="white", framealpha=0.8)
    ax3.tick_params(colors="white")
    for s in ax3.spines.values(): s.set_edgecolor("#444")
    ax3.set_title(f"③ PIDロット倍率（週次・Kp={PID_KP} Ki={PID_KI} Kd={PID_KD}）",
                  color="#aaa", fontsize=10, loc="left")

    plt.tight_layout(rect=[0, 0, 1, 0.98])
    pdf.savefig(fig, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

print(f"保存: {OUT_PDF.resolve()}")
print("完了")
