# -*- coding: utf-8 -*-
"""
自己相関フィルター × ブレイクダウン  IS期間解析
─────────────────────────────────────────────────────────────
仮説: 5分足リターンの自己相関(lag=1)が正 → 下げモメンタムが持続
     → ブレイクダウン後に次足も下になりやすい

確認項目:
  1. 自己相関の分布（時間帯・セッション別）
  2. 閾値別の期待値・歪度変化（ウィンドウ × threshold マトリックス）
  3. 最良パラメータでのバックテスト（IS期間）
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats
from pathlib import Path

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "strength_break" / "autocorr"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── パラメータ ──────────────────────────────────────────────
IS_START  = "2022-01-01"
IS_END    = "2023-12-31"
STRENGTH_WINDOW = 24
Q_THRESHOLD     = 0.10
JST             = pd.Timedelta(hours=9)
CAPITAL         = 1_000_000
RISK_PCT        = 0.005
PIP_VALUE       = 100
PIP_SIZE        = 0.01
ATR_PERIOD      = 14
MAX_HOLD        = 48

# 自己相関パラメータ候補
AC_WINDOWS     = [12, 24, 48]          # ウィンドウ（本数）
AC_THRESHOLDS  = [0.0, 0.05, 0.10, 0.15]  # 閾値

HORIZONS = [1, 3, 6, 12, 24]

SESSIONS = [
    ("東京 09-15JST",  9, 15, "#f39c12"),
    ("欧州 15-21JST", 15, 21, "#27ae60"),
    ("NY   21-03JST", 21,  3, "#2980b9"),
    ("深夜 03-09JST",  3,  9, "#8e44ad"),
]

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# ── データ読込 ──────────────────────────────────────────────
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for pair in dfs:
    common_idx = common_idx.intersection(dfs[pair].index)
for pair in dfs:
    dfs[pair] = dfs[pair].reindex(common_idx)

usdjpy = dfs["USDJPY"].copy()
is_mask_idx = (common_idx >= IS_START) & (common_idx <= IS_END)

# ── 通貨強弱 ────────────────────────────────────────────────
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p, df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair, (b, q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]; raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]

strength_diff = pd.DataFrame(raw_str)["USD"] - pd.DataFrame(raw_str)["JPY"]
q_thresh = strength_diff.quantile(Q_THRESHOLD)

# ── ベースシグナル ──────────────────────────────────────────
base_signal = (
    (usdjpy["Low"] < usdjpy["Low"].shift(1)) &
    (strength_diff <= q_thresh) &
    strength_diff.notna()
)

# ── 自己相関算出 ────────────────────────────────────────────
print("自己相関算出中...")
returns = np.log(usdjpy["Close"] / usdjpy["Close"].shift(1))

def rolling_autocorr(series, window, lag=1):
    """ローリング lag-1 自己相関"""
    arr = series.values
    result = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        x = arr[i - window + 1: i + 1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-lag], x[lag:])
        result[i] = c[0, 1]
    return pd.Series(result, index=series.index)

autocorr_series = {}
for w in AC_WINDOWS:
    print(f"  window={w}本...")
    autocorr_series[w] = rolling_autocorr(returns, w)

# ── セッション割り当て ──────────────────────────────────────
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name, s, e, _ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return "深夜 03-09JST"

sess_series = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# ── 先行リターン ────────────────────────────────────────────
entry_price = usdjpy["Open"].shift(-1)
future_ret  = {h: np.log(usdjpy["Close"].shift(-h) / entry_price) for h in HORIZONS}

# ── 図1: 自己相関の分布（ウィンドウ別・IS期間） ─────────────
print("図1: 自己相関分布...")
fig, axes = plt.subplots(1, len(AC_WINDOWS), figsize=(18, 5), sharey=True)
fig.patch.set_facecolor("#fafafa")
fig.suptitle("5分足リターン 自己相関(lag=1) 分布  ─  IS期間\n"
             "（正 = 下げモメンタム持続、負 = 反転しやすい）",
             fontsize=12, fontweight="bold")

for ax, w in zip(axes, AC_WINDOWS):
    ax.set_facecolor("#f8f9fa")
    ac = autocorr_series[w][is_mask_idx].dropna()
    ax.hist(ac, bins=80, density=True, color="#3498db", alpha=0.6, edgecolor="none")
    try:
        kde = stats.gaussian_kde(ac, bw_method=0.2)
        xs = np.linspace(ac.min(), ac.max(), 300)
        ax.plot(xs, kde(xs), color="#2980b9", lw=2)
    except Exception:
        pass
    ax.axvline(0,   color="#e74c3c", lw=1.2, ls="--", label="0.0")
    ax.axvline(0.05,color="#f39c12", lw=1.0, ls=":", label="0.05")
    ax.axvline(0.10,color="#27ae60", lw=1.0, ls=":", label="0.10")
    pos_rate = (ac > 0).mean() * 100
    ax.set_title(f"ウィンドウ {w}本 ({w*5}分)\n"
                 f"平均={ac.mean():.4f}  正の割合={pos_rate:.1f}%",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("自己相関係数", fontsize=8)
    if w == AC_WINDOWS[0]: ax.set_ylabel("確率密度", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
fig.savefig(OUT_DIR/"ac_distribution.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 図2: ウィンドウ × 閾値 ヒートマップ（6本後 Mean & Skew） ─
print("図2: パラメータマトリックス...")
H_FOCUS = 6
rows_scan = []
for w in AC_WINDOWS:
    ac = autocorr_series[w]
    for thr in AC_THRESHOLDS:
        mask = base_signal & is_mask_idx & (ac > thr) & ac.notna()
        r = future_ret[H_FOCUS][mask].dropna()
        n = len(r)
        rows_scan.append({
            "window": w, "threshold": thr, "n": n,
            "mean":   r.mean() * 100 if n >= 30 else np.nan,
            "skew":   stats.skew(r)   if n >= 30 else np.nan,
            "neg_rt": (r < 0).mean() * 100 if n >= 30 else np.nan,
        })

df_scan = pd.DataFrame(rows_scan)
df_scan.to_csv(OUT_DIR/"param_scan.csv", index=False, encoding="utf-8-sig")

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"ウィンドウ × 閾値 マトリックス  ─  IS期間 / {H_FOCUS}本後({H_FOCUS*5}分後)\n"
             "（ベース: 強弱差Q10 + ブレイクダウン + 自己相関フィルター）",
             fontsize=11, fontweight="bold")

for ax, (col, label, cmap) in zip(axes, [
    ("mean",   "期待値 (%)",  "RdYlGn_r"),
    ("skew",   "歪度 (Skew)", "RdYlGn_r"),
    ("neg_rt", "下落率 (%)",  "RdYlGn"),
]):
    pivot = df_scan.pivot(index="threshold", columns="window", values=col)
    n_piv = df_scan.pivot(index="threshold", columns="window", values="n")
    vmax  = pivot.abs().max().max()
    center = 50 if col == "neg_rt" else 0
    im = ax.imshow(pivot.values, cmap=cmap, aspect="auto",
                   vmin=center - vmax, vmax=center + vmax)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    ax.set_xticks(range(len(AC_WINDOWS)))
    ax.set_xticklabels([f"{w}本\n({w*5}分)" for w in AC_WINDOWS], fontsize=8)
    ax.set_yticks(range(len(AC_THRESHOLDS)))
    ax.set_yticklabels([f">{thr:.2f}" for thr in AC_THRESHOLDS], fontsize=8)
    ax.set_title(label, fontsize=10, fontweight="bold")
    ax.set_xlabel("自己相関ウィンドウ", fontsize=8)
    ax.set_ylabel("自己相関閾値", fontsize=8)
    for i, thr in enumerate(AC_THRESHOLDS):
        for j, w in enumerate(AC_WINDOWS):
            val = pivot.iloc[i, j]
            n   = n_piv.iloc[i, j]
            if not np.isnan(val):
                fmt = "+.3f" if col != "neg_rt" else ".1f"
                ax.text(j, i, f"{val:{fmt}}\nn={int(n):,}",
                        ha="center", va="center", fontsize=7.5,
                        color="white" if abs(val - center) > vmax * 0.55 else "black")

plt.tight_layout()
fig.savefig(OUT_DIR/"param_matrix.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── コンソール：全horizon サマリー ───────────────────────────
print("\n" + "="*65)
print("  ウィンドウ × 閾値 × horizon サマリー（IS期間）")
print("="*65)
print(f"  {'window':>6s} {'thr':>5s} {'H':>4s}  {'Mean%':>8s}  {'Skew':>7s}  {'下落率':>7s}  {'n':>5s}")
print("-"*65)
for w in AC_WINDOWS:
    ac = autocorr_series[w]
    for thr in AC_THRESHOLDS:
        mask = base_signal & is_mask_idx & (ac > thr) & ac.notna()
        for h in HORIZONS:
            r = future_ret[h][mask].dropna()
            if len(r) < 30: continue
            tag = "★" if r.mean() < 0 and stats.skew(r) < -0.5 else "  "
            print(f"  {tag}{w:>5d}本 {thr:>4.2f} {h:>3d}本  "
                  f"{r.mean()*100:+8.4f}  {stats.skew(r):+7.3f}  "
                  f"{(r<0).mean()*100:>7.1f}  {len(r):5,}")
    print()

# ── 最良組み合わせを自動選定 ────────────────────────────────
best_row = df_scan.dropna().sort_values("mean").iloc[0]
best_w   = int(best_row["window"])
best_thr = best_row["threshold"]
print(f"\n【IS最良組み合わせ（期待値最小）】")
print(f"  ウィンドウ={best_w}本  閾値={best_thr:.2f}  "
      f"Mean={best_row['mean']:+.4f}%  Skew={best_row['skew']:+.3f}  "
      f"下落率={best_row['neg_rt']:.1f}%  n={int(best_row['n']):,}")

# ── バックテスト（最良パラメータ × IS × 全セッション） ───────
print(f"\nバックテスト（w={best_w}, thr={best_thr}）...")

hi, lo_s, cl_prev = usdjpy["High"], usdjpy["Low"], usdjpy["Close"].shift(1)
tr  = pd.concat([hi-lo_s, (hi-cl_prev).abs(), (lo_s-cl_prev).abs()], axis=1).max(axis=1)
atr = tr.rolling(ATR_PERIOD).mean()

best_ac = autocorr_series[best_w]
final_signal = base_signal & is_mask_idx & (best_ac > best_thr) & best_ac.notna()

def run_backtest(mask):
    positions = np.where(mask)[0]
    records = []
    for sig_pos in positions:
        ep = sig_pos + 1
        if ep >= len(usdjpy): continue
        entry_bar   = usdjpy.index[ep]
        entry_price = usdjpy["Open"].iloc[ep]
        atr_val     = atr.iloc[sig_pos]
        if atr_val <= 0 or np.isnan(atr_val): continue

        sl_dist  = atr_val
        sl_price = entry_price + sl_dist
        sl_pips  = sl_dist / PIP_SIZE
        if sl_pips <= 0: continue
        lot_size = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

        lowest   = entry_price
        trail    = sl_price
        exit_p   = None
        reason   = "time"
        held     = 0

        for h in range(1, MAX_HOLD + 1):
            bp = ep + h
            if bp >= len(usdjpy): break
            bh = usdjpy["High"].iloc[bp]
            bl = usdjpy["Low"].iloc[bp]
            held = h
            if bh >= trail:
                exit_p = trail; reason = "stop"; break
            if bl < lowest:
                lowest = bl
                trail  = min(trail, lowest + sl_dist)

        if exit_p is None:
            fp = ep + held
            if fp >= len(usdjpy): continue
            exit_p = usdjpy["Close"].iloc[fp]
            reason = "time"

        pnl_yen = (entry_price - exit_p) / PIP_SIZE * PIP_VALUE * lot_size
        r_mult  = pnl_yen / (CAPITAL * RISK_PCT)
        sig_bar = usdjpy.index[sig_pos]

        records.append({
            "signal_bar": sig_bar, "entry_bar": entry_bar,
            "entry_price": entry_price, "exit_price": exit_p,
            "pnl_yen": pnl_yen, "r_mult": r_mult,
            "hold_bars": held, "exit_reason": reason,
            "session": sess_series.get(sig_bar, "不明"),
            "autocorr": best_ac.get(sig_bar, np.nan),
        })
    return pd.DataFrame(records)

df_bt = run_backtest(final_signal)
df_bt.to_csv(OUT_DIR/"backtest_trades_ac.csv", index=False, encoding="utf-8-sig")

def summarize(df):
    if len(df) == 0: return {}
    wins = df[df["pnl_yen"] > 0]; losses = df[df["pnl_yen"] <= 0]
    gp = wins["pnl_yen"].sum(); gl = losses["pnl_yen"].abs().sum()
    pf = gp / gl if gl > 0 else float("inf")
    cum = df["pnl_yen"].cumsum()
    return {"n": len(df), "win_rate": len(wins)/len(df)*100,
            "pf": pf, "total_pnl": df["pnl_yen"].sum(),
            "avg_r": df["r_mult"].mean(), "skew_r": stats.skew(df["r_mult"]),
            "max_dd": (cum.cummax() - cum).max()}

print("\n" + "="*70)
print(f"  IS バックテスト結果  (自己相関 w={best_w}本 thr>{best_thr:.2f})")
print("="*70)
sv = summarize(df_bt)
print(f"  全体: n={sv['n']:,}  勝率={sv['win_rate']:.1f}%  PF={sv['pf']:.2f}  "
      f"損益={sv['total_pnl']:+,.0f}円  MaxDD={sv['max_dd']:,.0f}円")

print(f"\n  {'セッション':18s} {'n':>5s}  {'勝率%':>6s}  {'PF':>5s}  "
      f"{'損益(円)':>10s}  {'MaxDD':>9s}  {'avgR':>7s}")
print("-"*70)

for sess_name, *_ in SESSIONS:
    sub = df_bt[df_bt["session"]==sess_name]
    if len(sub) < 5: continue
    sv2 = summarize(sub)
    tag = "★" if sv2["pf"] >= 1.2 and sv2["avg_r"] > 0 else "  "
    print(f"  {tag}{sess_name:16s} {sv2['n']:5,}  {sv2['win_rate']:6.1f}  "
          f"{sv2['pf']:5.2f}  {sv2['total_pnl']:+10,.0f}  "
          f"{sv2['max_dd']:9,.0f}  {sv2['avg_r']:+7.4f}")

# ── 図3: フィルター別 損益曲線比較 ─────────────────────────
print("\n図3: 損益曲線比較...")
fig, axes = plt.subplots(1, 2, figsize=(18, 7))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"IS期間  自己相関フィルター効果  (ウィンドウ={best_w}本)\n"
             f"SL: 資金0.5%  TP: トレーリング(ATR×1.0)  最大{MAX_HOLD}本",
             fontsize=12, fontweight="bold")

# 左: フィルター段階別 P&L曲線
ax = axes[0]
ax.set_facecolor("#f8f9fa")
ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)

def run_simple_bt(mask):
    df = run_backtest(mask)
    return df

base_bt = run_simple_bt(base_signal & is_mask_idx)
ac0_bt  = run_simple_bt(base_signal & is_mask_idx & (autocorr_series[best_w] >  0.0)  & autocorr_series[best_w].notna())
ac_bt   = run_simple_bt(final_signal)

for df_p, label, color, lw in [
    (base_bt, f"ベース（強弱Q10+BreakDown）  PF={summarize(base_bt).get('pf',0):.2f}", "#95a5a6", 1.5),
    (ac0_bt,  f"+ 自己相関>0.0               PF={summarize(ac0_bt).get('pf',0):.2f}",  "#3498db", 1.8),
    (ac_bt,   f"+ 自己相関>{best_thr:.2f} (最良)  PF={summarize(ac_bt).get('pf',0):.2f}",  "#e74c3c", 2.2),
]:
    if len(df_p) == 0: continue
    cum = df_p["pnl_yen"].cumsum()
    ax.plot(range(len(cum)), cum.values, color=color, lw=lw,
            label=f"{label}  n={len(df_p):,}")

ax.set_title("フィルター段階別 累積損益", fontsize=10, fontweight="bold")
ax.set_xlabel("トレード番号", fontsize=8)
ax.set_ylabel("累積損益 (円)", fontsize=8)
ax.legend(fontsize=8, framealpha=0.9)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# 右: セッション別 P&L（自己相関フィルター適用後）
ax = axes[1]
ax.set_facecolor("#f8f9fa")
ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)

for sess_name, _, _, color in SESSIONS:
    sub = df_bt[df_bt["session"]==sess_name]
    if len(sub) < 5: continue
    cum = sub["pnl_yen"].cumsum()
    sv2 = summarize(sub)
    ax.plot(range(len(cum)), cum.values, color=color, lw=1.8,
            label=f"{sess_name.split()[0]}  PF={sv2['pf']:.2f}  "
                  f"{sv2['total_pnl']:+,.0f}円  n={sv2['n']}")

ax.set_title(f"自己相関フィルター適用後 セッション別 累積損益\n"
             f"(w={best_w}本, thr>{best_thr:.2f})",
             fontsize=10, fontweight="bold")
ax.set_xlabel("トレード番号", fontsize=8)
ax.set_ylabel("累積損益 (円)", fontsize=8)
ax.legend(fontsize=8, framealpha=0.9)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

plt.tight_layout()
fig.savefig(OUT_DIR/"ac_backtest.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

print(f"\n保存先: {OUT_DIR}")
print("完了")
