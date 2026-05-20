# -*- coding: utf-8 -*-
"""
USD/JPY デュアルストラテジー統合バックテスト  IS期間（2022-2023）
─────────────────────────────────────────────────────────────
戦略A（順張り）: NY  21-03JST + 強弱差Q10 + BreakDown + ac12>0.15 → SHORT
戦略B（逆張り）: 東京 09-15JST + 強弱差Q10 + BreakDown + ac12<0.00 → LONG

共通条件:
  強弱差 = USDスコア − JPYスコア（直近24本の12ペアから算出）
  BreakDown: 現在足Low < 前足Low
  エントリー: 次足Open / SL: ATR(14)×1.0, 資金0.5%リスク / TP: トレーリング
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
OUT_DIR  = BASE / "docs" / "usdjpy_dual"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── パラメータ ──────────────────────────────────────────────
IS_START  = "2022-01-01"
IS_END    = "2023-12-31"
STRENGTH_WINDOW = 24
Q_THRESHOLD     = 0.10      # 強弱差下位10%
JST             = pd.Timedelta(hours=9)
CAPITAL         = 1_000_000
RISK_PCT        = 0.005     # SLリスク0.5%
PIP_VALUE       = 100       # 円/pip/lot（USDJPY）
PIP_SIZE        = 0.01
ATR_PERIOD      = 14
MAX_HOLD        = 48        # 最大保有48本（4時間）
AC_WINDOW       = 12

# ── 戦略定義 ────────────────────────────────────────────────
STRATEGIES = {
    "A_SHORT": {
        "label":     "戦略A 順張りショート",
        "direction": "short",
        "session_h": (21, 3),   # 21:00〜03:00 JST
        "ac_cond":   "gt",      # ac > threshold
        "ac_thr":    0.15,
        "color":     "#2980b9",
    },
    "B_LONG": {
        "label":     "戦略B 逆張りロング",
        "direction": "long",
        "session_h": (9, 15),   # 09:00〜15:00 JST
        "ac_cond":   "lt",      # ac < threshold
        "ac_thr":    0.00,
        "color":     "#e74c3c",
    },
}

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
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
usdjpy = dfs["USDJPY"].copy()
is_idx = (common_idx >= IS_START) & (common_idx <= IS_END)

# ── 通貨強弱 & 強弱差 ──────────────────────────────────────
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]; raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]

strength_diff = pd.DataFrame(raw_str)["USD"] - pd.DataFrame(raw_str)["JPY"]
q10 = strength_diff.quantile(Q_THRESHOLD)

# ── ATR・自己相関 ────────────────────────────────────────────
hi,lo,cl = usdjpy["High"], usdjpy["Low"], usdjpy["Close"].shift(1)
tr  = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
atr = tr.rolling(ATR_PERIOD).mean()

ret = np.log(usdjpy["Close"]/usdjpy["Close"].shift(1))
def rolling_ac(series, window):
    arr = series.values; res = np.full(len(arr), np.nan)
    for i in range(window-1, len(arr)):
        x = arr[i-window+1:i+1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-1],x[1:])
        res[i] = c[0,1]
    return pd.Series(res, index=series.index)
ac = rolling_ac(ret, AC_WINDOW)

# ── JST時刻 ─────────────────────────────────────────────────
jst_hour = (common_idx + JST).hour

def in_session(hour_series, s, e):
    if s < e:
        return (hour_series >= s) & (hour_series < e)
    else:
        return (hour_series >= s) | (hour_series < e)

# ── ベースシグナル（強弱差Q10 + BreakDown） ─────────────────
breakdown = (
    (usdjpy["Low"] < usdjpy["Low"].shift(1)) &
    (strength_diff <= q10) &
    strength_diff.notna()
)

# ── バックテスト関数 ─────────────────────────────────────────
def run_bt(mask, direction, strat_label):
    positions = np.where(mask)[0]
    records = []
    for sp in positions:
        ep = sp + 1
        if ep >= len(usdjpy): continue
        entry_bar   = usdjpy.index[ep]
        entry_price = usdjpy["Open"].iloc[ep]
        atr_val     = atr.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue

        sl_dist = atr_val
        sl_pips = sl_dist / PIP_SIZE
        if sl_pips <= 0: continue
        lot_sz  = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

        if direction == "short":
            best = entry_price; trail = entry_price + sl_dist
            exit_p = None; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep+h
                if bp >= len(usdjpy): break
                bh = usdjpy["High"].iloc[bp]; bl = usdjpy["Low"].iloc[bp]; held = h
                if bh >= trail: exit_p = trail; break
                if bl < best: best = bl; trail = min(trail, best + sl_dist)
            if exit_p is None:
                fp = ep+held
                if fp < len(usdjpy): exit_p = usdjpy["Close"].iloc[fp]
                else: continue
            pnl = (entry_price - exit_p) / PIP_SIZE * PIP_VALUE * lot_sz
        else:
            best = entry_price; trail = entry_price - sl_dist
            exit_p = None; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep+h
                if bp >= len(usdjpy): break
                bh = usdjpy["High"].iloc[bp]; bl = usdjpy["Low"].iloc[bp]; held = h
                if bl <= trail: exit_p = trail; break
                if bh > best: best = bh; trail = max(trail, best - sl_dist)
            if exit_p is None:
                fp = ep+held
                if fp < len(usdjpy): exit_p = usdjpy["Close"].iloc[fp]
                else: continue
            pnl = (exit_p - entry_price) / PIP_SIZE * PIP_VALUE * lot_sz

        r_mult = pnl / (CAPITAL * RISK_PCT)
        sig_bar = usdjpy.index[sp]
        records.append({
            "strategy": strat_label,
            "signal_bar": sig_bar,
            "entry_bar":  entry_bar,
            "entry_price":entry_price,
            "exit_price": exit_p,
            "pnl_yen":    pnl,
            "r_mult":     r_mult,
            "hold_bars":  held,
            "jst_hour":   (sig_bar + JST).hour,
        })
    return pd.DataFrame(records)

# ── 各戦略シグナル生成 & バックテスト ────────────────────────
dfs_bt = {}
for key, cfg in STRATEGIES.items():
    s, e = cfg["session_h"]
    sess_mask  = in_session(pd.Series(jst_hour, index=common_idx), s, e)
    ac_mask    = (ac > cfg["ac_thr"]) if cfg["ac_cond"]=="gt" else (ac < cfg["ac_thr"])
    final_mask = breakdown & is_idx & sess_mask & ac_mask & ac.notna()
    df_bt = run_bt(final_mask, cfg["direction"], cfg["label"])
    dfs_bt[key] = df_bt
    print(f"  {cfg['label']}: {len(df_bt)}件")

df_combined = pd.concat(dfs_bt.values(), ignore_index=True)
df_combined.sort_values("signal_bar", inplace=True)
df_combined.to_csv(OUT_DIR/"trades.csv", index=False, encoding="utf-8-sig")

# ── 集計 ────────────────────────────────────────────────────
def summarize(df):
    if len(df) == 0: return {}
    wins = df[df["pnl_yen"]>0]; losses = df[df["pnl_yen"]<=0]
    gp = wins["pnl_yen"].sum(); gl = losses["pnl_yen"].abs().sum()
    pf = gp/gl if gl>0 else float("inf")
    cum = df["pnl_yen"].cumsum()
    dd  = (cum.cummax()-cum).max()
    return {
        "n": len(df), "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins)/len(df)*100,
        "total_pnl": df["pnl_yen"].sum(),
        "pf": pf, "avg_r": df["r_mult"].mean(),
        "skew_r": stats.skew(df["r_mult"]),
        "max_dd": dd,
        "dd_pct": dd/CAPITAL*100,
    }

print("\n" + "="*70)
print("  IS期間バックテスト結果（2022-2023）")
print("="*70)

sv_A = summarize(dfs_bt["A_SHORT"])
sv_B = summarize(dfs_bt["B_LONG"])
sv_C = summarize(df_combined)

rows = [
    ("戦略A 順張りショート（NY）",   sv_A),
    ("戦略B 逆張りロング（東京）",    sv_B),
    ("統合システム（A+B合計）",       sv_C),
]
print(f"\n  {'':28s} {'n':>5s}  {'勝率%':>6s}  {'PF':>5s}  {'損益(円)':>11s}  {'MaxDD':>9s}  {'DD%':>5s}  {'avgR':>7s}")
print("-"*88)
for label, sv in rows:
    if not sv: continue
    tag = "★" if sv["pf"]>=1.2 else "  "
    print(f"  {tag}{label:26s} {sv['n']:5,}  {sv['win_rate']:6.1f}  {sv['pf']:5.2f}  "
          f"{sv['total_pnl']:+11,.0f}  {sv['max_dd']:9,.0f}  {sv['dd_pct']:5.1f}  {sv['avg_r']:+7.4f}")

# 月別集計
print("\n  月別損益（統合）")
print(f"  {'月':>8s}  {'A損益':>10s}  {'B損益':>10s}  {'合計':>10s}  {'n':>4s}")
print("-"*55)
df_combined["month"] = pd.to_datetime(df_combined["signal_bar"]).dt.to_period("M")
df_combined["strat_key"] = df_combined["strategy"].map(
    {v["label"]: k for k,v in STRATEGIES.items()})

monthly = df_combined.groupby("month").agg(
    total=("pnl_yen","sum"), n=("pnl_yen","count")).reset_index()
for _, row in monthly.iterrows():
    sub = df_combined[df_combined["month"]==row["month"]]
    a_pnl = sub[sub["strat_key"]=="A_SHORT"]["pnl_yen"].sum()
    b_pnl = sub[sub["strat_key"]=="B_LONG"]["pnl_yen"].sum()
    tag = "+" if row["total"]>=0 else "-"
    print(f"  {str(row['month']):>8s}  {a_pnl:+10,.0f}  {b_pnl:+10,.0f}  "
          f"{row['total']:+10,.0f}  {row['n']:4.0f}")

# ── 可視化 ──────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 18))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(
    "USD/JPY デュアルストラテジー統合システム  ─  IS期間（2022-2023）\n"
    "戦略A: 順張りショート（NY 21-03JST / ac>0.15）  ＋  "
    "戦略B: 逆張りロング（東京 09-15JST / ac<0.00）",
    fontsize=13, fontweight="bold", y=0.98
)
gs = fig.add_gridspec(3, 2, hspace=0.4, wspace=0.3)

# ① 累積P&L（3戦略重ね）
ax1 = fig.add_subplot(gs[0, :])
ax1.set_facecolor("#f8f9fa")
ax1.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)

for key, cfg in STRATEGIES.items():
    df_p = dfs_bt[key]
    if len(df_p) == 0: continue
    sv  = summarize(df_p)
    cum = df_p["pnl_yen"].cumsum()
    ax1.plot(range(len(cum)), cum.values, color=cfg["color"], lw=2.2,
             label=f"{cfg['label']}  PF={sv['pf']:.2f}  {sv['total_pnl']:+,.0f}円  "
                   f"n={sv['n']}  DD={sv['max_dd']:,.0f}円")

# 統合（累積）
if len(df_combined)>0:
    cum_c = df_combined["pnl_yen"].cumsum()
    ax1.plot(range(len(cum_c)), cum_c.values, color="#2c3e50", lw=2.8, ls="--",
             label=f"統合合計  PF={sv_C['pf']:.2f}  {sv_C['total_pnl']:+,.0f}円  "
                   f"n={sv_C['n']}  DD={sv_C['max_dd']:,.0f}円")

ax1.set_title("累積損益曲線", fontsize=11, fontweight="bold")
ax1.set_xlabel("トレード番号", fontsize=9)
ax1.set_ylabel("累積損益 (円)", fontsize=9)
ax1.legend(fontsize=9, framealpha=0.9)
ax1.grid(axis="y", alpha=0.3)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# ② 月別棒グラフ（A/B積み上げ）
ax2 = fig.add_subplot(gs[1, :])
ax2.set_facecolor("#f8f9fa")
ax2.axhline(0, color="#333", lw=0.8)
months = monthly["month"].astype(str).tolist()
x = np.arange(len(months))

a_vals = [df_combined[(df_combined["month"]==m) & (df_combined["strat_key"]=="A_SHORT")]["pnl_yen"].sum()
          for m in monthly["month"]]
b_vals = [df_combined[(df_combined["month"]==m) & (df_combined["strat_key"]=="B_LONG")]["pnl_yen"].sum()
          for m in monthly["month"]]

ax2.bar(x, a_vals, 0.5, label="戦略A ショート", color=STRATEGIES["A_SHORT"]["color"], alpha=0.8)
ax2.bar(x, b_vals, 0.5, bottom=a_vals, label="戦略B ロング",
        color=STRATEGIES["B_LONG"]["color"], alpha=0.8)
ax2.set_title("月別損益（A+B 積み上げ）", fontsize=11, fontweight="bold")
ax2.set_xticks(x); ax2.set_xticklabels(months, rotation=45, fontsize=8)
ax2.set_ylabel("損益 (円)", fontsize=9)
ax2.legend(fontsize=9)
ax2.grid(axis="y", alpha=0.3)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# ③④ R倍率分布（戦略別）
for ax, (key, cfg) in zip(
    [fig.add_subplot(gs[2,0]), fig.add_subplot(gs[2,1])],
    STRATEGIES.items()
):
    ax.set_facecolor("#f8f9fa")
    ax.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6)
    df_p = dfs_bt[key]; sv = summarize(df_p)
    if len(df_p) < 10:
        ax.set_title(f"{cfg['label']} (データ不足)", fontsize=9)
        continue
    r = df_p["r_mult"]
    lo, hi = np.percentile(r,[1,99])
    ax.hist(r.clip(lo,hi), bins=60, density=True,
            color=cfg["color"], alpha=0.65, edgecolor="none")
    try:
        kde=stats.gaussian_kde(r.clip(lo,hi),bw_method=0.3)
        xs=np.linspace(lo,hi,300); ax.plot(xs,kde(xs),color=cfg["color"],lw=2.0)
    except: pass
    ax.axvline(r.mean(), color="black", lw=1.2, ls=":", label=f"平均 {r.mean():+.3f}R")
    ax.set_title(
        f"{cfg['label']}\n"
        f"n={sv['n']}  勝率{sv['win_rate']:.1f}%  PF {sv['pf']:.2f}  "
        f"avgR {sv['avg_r']:+.4f}  DD {sv['max_dd']:,.0f}円",
        fontsize=9, fontweight="bold"
    )
    ax.set_xlabel("R倍率 (1R = 資金0.5%)", fontsize=8)
    ax.set_ylabel("確率密度", fontsize=8)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

plt.savefig(OUT_DIR/"dual_system_is.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終サマリー ────────────────────────────────────────────
print("\n" + "="*70)
print("  最終サマリー")
print("="*70)
print(f"""
  資金:   {CAPITAL:,}円   リスク/トレード: {RISK_PCT*100:.1f}%
  期間:   {IS_START} 〜 {IS_END}

  戦略A（順張りショート）  NYセッション 21-03JST
    PF={sv_A.get('pf',0):.2f}  勝率={sv_A.get('win_rate',0):.1f}%
    損益={sv_A.get('total_pnl',0):+,.0f}円  MaxDD={sv_A.get('max_dd',0):,.0f}円({sv_A.get('dd_pct',0):.1f}%)
    n={sv_A.get('n',0)}

  戦略B（逆張りロング）  東京セッション 09-15JST
    PF={sv_B.get('pf',0):.2f}  勝率={sv_B.get('win_rate',0):.1f}%
    損益={sv_B.get('total_pnl',0):+,.0f}円  MaxDD={sv_B.get('max_dd',0):,.0f}円({sv_B.get('dd_pct',0):.1f}%)
    n={sv_B.get('n',0)}

  統合システム（A+B）
    PF={sv_C.get('pf',0):.2f}  勝率={sv_C.get('win_rate',0):.1f}%
    損益={sv_C.get('total_pnl',0):+,.0f}円  MaxDD={sv_C.get('max_dd',0):,.0f}円({sv_C.get('dd_pct',0):.1f}%)
    n={sv_C.get('n',0)}  週次勝率=（月次グラフ参照）
""")
print(f"保存先: {OUT_DIR}")
print("完了")
