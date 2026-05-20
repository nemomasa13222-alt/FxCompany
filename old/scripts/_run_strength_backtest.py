# -*- coding: utf-8 -*-
"""
通貨強弱 × ブレイクダウン バックテスト
────────────────────────────────────────────────────────────────
エントリー : ブレイク確定 → 次足 Open でショート
SL        : ATR(14) × 1.0 上 / 0.5%資金ルールでロット逆算
TP        : トレーリングストップ（初期SL幅でトレール）
最大保有   : 48本（4時間）→ 時間切れは Close で決済
IS        : 2022-01-01 〜 2023-12-31
OOS       : 2024-01-01 〜 2024-12-31
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
OUT_DIR  = BASE / "docs" / "strength_break"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── パラメータ ──────────────────────────────────────────────
CAPITAL         = 1_000_000   # 資金（円）
RISK_PCT        = 0.005       # SLリスク 0.5%
PIP_VALUE       = 100         # 円/pip/lot（DMMFXミニロット）
PIP_SIZE        = 0.01        # USDJPY の 1pip = 0.01円
ATR_PERIOD      = 14          # SL距離算出用 ATR
MAX_HOLD        = 48          # 最大保有本数（48本=4時間）
STRENGTH_WINDOW = 24
Q_THRESHOLD     = 0.10        # 強弱差下位10%

IS_START  = "2022-01-01"
IS_END    = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END   = "2024-12-31"

JST = pd.Timedelta(hours=9)
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
print(f"共通バー数: {len(common_idx):,}")

# ── 通貨強弱スコア ──────────────────────────────────────────
pair_logret = {
    p: np.log(df["Close"] / df["Close"].shift(STRENGTH_WINDOW))
    for p, df in dfs.items()
}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt     = {c: 0 for c in CURRENCIES}
for pair, (b, q) in PAIR_CURRENCIES.items():
    if pair not in pair_logret: continue
    r = pair_logret[pair]
    raw_str[b] += r; raw_str[q] -= r
    cnt[b]     += 1; cnt[q]     += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]

strength_diff = pd.DataFrame(raw_str)["USD"] - pd.DataFrame(raw_str)["JPY"]
q_thresh      = strength_diff.quantile(Q_THRESHOLD)

# ── ATR 算出 ────────────────────────────────────────────────
hi, lo, cl_prev = usdjpy["High"], usdjpy["Low"], usdjpy["Close"].shift(1)
tr  = pd.concat([hi - lo, (hi - cl_prev).abs(), (lo - cl_prev).abs()], axis=1).max(axis=1)
atr = tr.rolling(ATR_PERIOD).mean()

# ── シグナル ────────────────────────────────────────────────
signal_mask = (
    (usdjpy["Low"]  < usdjpy["Low"].shift(1)) &   # ブレイクダウン
    (strength_diff <= q_thresh) &                   # 強弱差極大
    strength_diff.notna() &
    atr.notna()
)

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

# ── バックテスト ────────────────────────────────────────────
print("バックテスト実行中...")

def run_backtest(mask):
    """シグナル一覧を受け取り、トレード結果を返す"""
    signal_positions = np.where(mask)[0]
    records = []

    for sig_pos in signal_positions:
        entry_pos = sig_pos + 1
        if entry_pos >= len(usdjpy): continue

        entry_bar   = usdjpy.index[entry_pos]
        entry_price = usdjpy["Open"].iloc[entry_pos]
        atr_val     = atr.iloc[sig_pos]

        if atr_val <= 0 or np.isnan(atr_val): continue

        # SL距離 & ロットサイズ
        sl_dist  = atr_val                          # price units
        sl_price = entry_price + sl_dist            # short: stop above
        sl_pips  = sl_dist / PIP_SIZE
        if sl_pips <= 0: continue
        lot_size = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

        # 保有シミュレーション
        lowest_low  = entry_price
        trail_stop  = sl_price                      # 初期SL = entry + ATR
        exit_price  = None
        exit_reason = "time"
        hold_bars   = 0

        for h in range(1, MAX_HOLD + 1):
            bar_pos = entry_pos + h
            if bar_pos >= len(usdjpy): break

            bar_high  = usdjpy["High"].iloc[bar_pos]
            bar_low   = usdjpy["Low"].iloc[bar_pos]
            bar_close = usdjpy["Close"].iloc[bar_pos]
            hold_bars = h

            # ストップヒット確認（バー内High がストップ以上）
            if bar_high >= trail_stop:
                exit_price  = trail_stop
                exit_reason = "stop"
                break

            # トレール更新（新安値でトレールを引き下げ）
            if bar_low < lowest_low:
                lowest_low  = bar_low
                new_trail   = lowest_low + sl_dist
                trail_stop  = min(trail_stop, new_trail)  # 下方向のみ更新

        if exit_price is None:
            # 時間切れ決済
            ep = entry_pos + hold_bars
            if ep >= len(usdjpy): continue
            exit_price  = usdjpy["Close"].iloc[ep]
            exit_reason = "time"

        # P&L 計算（ショート: entry高 - exit低 = 利益）
        pnl_price = entry_price - exit_price
        pnl_pips  = pnl_price / PIP_SIZE
        pnl_yen   = pnl_pips * PIP_VALUE * lot_size
        r_mult    = pnl_yen / (CAPITAL * RISK_PCT)  # R倍率

        sig_bar  = usdjpy.index[sig_pos]
        records.append({
            "signal_bar":  sig_bar,
            "entry_bar":   entry_bar,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "sl_dist":     sl_dist,
            "lot_size":    lot_size,
            "hold_bars":   hold_bars,
            "exit_reason": exit_reason,
            "pnl_pips":    pnl_pips,
            "pnl_yen":     pnl_yen,
            "r_mult":      r_mult,
            "session":     sess_series.get(sig_bar, "不明"),
            "jst_hour":    (sig_bar + JST).hour,
        })

    return pd.DataFrame(records)

# IS / OOS
is_mask  = signal_mask & (common_idx >= IS_START)  & (common_idx <= IS_END)
oos_mask = signal_mask & (common_idx >= OOS_START) & (common_idx <= OOS_END)

df_is  = run_backtest(is_mask)
df_oos = run_backtest(oos_mask)

df_is["period"]  = "IS"
df_oos["period"] = "OOS"
df_all = pd.concat([df_is, df_oos], ignore_index=True)
df_all.to_csv(OUT_DIR / "backtest_trades.csv", index=False, encoding="utf-8-sig")

# ── 集計関数 ────────────────────────────────────────────────
def summarize(df, label=""):
    if len(df) == 0:
        return {}
    wins   = df[df["pnl_yen"] > 0]
    losses = df[df["pnl_yen"] <= 0]
    gp = wins["pnl_yen"].sum()
    gl = losses["pnl_yen"].abs().sum()
    pf = gp / gl if gl > 0 else float("inf")
    cum = df["pnl_yen"].cumsum()
    dd  = (cum.cummax() - cum).max()
    return {
        "label":    label,
        "n":        len(df),
        "wins":     len(wins),
        "losses":   len(losses),
        "win_rate": len(wins)/len(df)*100,
        "total_pnl":df["pnl_yen"].sum(),
        "avg_pnl":  df["pnl_yen"].mean(),
        "avg_r":    df["r_mult"].mean(),
        "pf":       pf,
        "max_dd":   dd,
        "skew_r":   stats.skew(df["r_mult"]),
    }

# ── コンソール出力 ──────────────────────────────────────────
print("\n" + "="*70)
print("  IS期間 全体")
s = summarize(df_is, "IS全体")
print(f"  件数:{s['n']:,}  勝率:{s['win_rate']:.1f}%  PF:{s['pf']:.2f}  "
      f"損益:{s['total_pnl']:+,.0f}円  MaxDD:{s['max_dd']:,.0f}円  "
      f"Skew(R):{s['skew_r']:+.3f}")

print("\n  IS期間 セッション別")
print(f"  {'セッション':18s} {'n':>5s}  {'勝率%':>6s}  {'PF':>5s}  "
      f"{'損益(円)':>10s}  {'MaxDD':>10s}  {'平均R':>7s}")
print("-"*70)

sess_rows = []
for sess_name, *_ in SESSIONS:
    sub = df_is[df_is["session"]==sess_name]
    if len(sub) < 5: continue
    sv = summarize(sub, sess_name)
    tag = "★" if sv["pf"] >= 1.2 and sv["avg_r"] > 0 else "  "
    print(f"  {tag}{sess_name:16s} {sv['n']:5,}  {sv['win_rate']:6.1f}  "
          f"{sv['pf']:5.2f}  {sv['total_pnl']:+10,.0f}  "
          f"{sv['max_dd']:10,.0f}  {sv['avg_r']:+7.4f}")
    sv["session"] = sess_name
    sess_rows.append(sv)

print("\n  OOS期間 全体")
so = summarize(df_oos, "OOS全体")
print(f"  件数:{so['n']:,}  勝率:{so['win_rate']:.1f}%  PF:{so['pf']:.2f}  "
      f"損益:{so['total_pnl']:+,.0f}円  MaxDD:{so['max_dd']:,.0f}円  "
      f"Skew(R):{so['skew_r']:+.3f}")

print("\n  OOS期間 セッション別")
print("-"*70)
for sess_name, *_ in SESSIONS:
    sub = df_oos[df_oos["session"]==sess_name]
    if len(sub) < 5: continue
    sv = summarize(sub, sess_name)
    tag = "★" if sv["pf"] >= 1.2 and sv["avg_r"] > 0 else "  "
    print(f"  {tag}{sess_name:16s} {sv['n']:5,}  {sv['win_rate']:6.1f}  "
          f"{sv['pf']:5.2f}  {sv['total_pnl']:+10,.0f}  "
          f"{sv['max_dd']:10,.0f}  {sv['avg_r']:+7.4f}")

# ── 図1: 累積損益曲線 IS / OOS ──────────────────────────────
print("\n図描画中...")
fig, axes = plt.subplots(2, 1, figsize=(16, 10))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("累積損益曲線  ─  通貨強弱×ブレイクダウン ショート\n"
             f"SL: 資金0.5%  /  TP: トレーリング(ATR×1.0)  /  最大{MAX_HOLD}本",
             fontsize=12, fontweight="bold")

for ax, (df_p, period_label) in zip(axes, [
    (df_is,  f"IS ({IS_START} 〜 {IS_END})"),
    (df_oos, f"OOS ({OOS_START} 〜 {OOS_END})"),
]):
    ax.set_facecolor("#f8f9fa")
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)

    # 全体
    if len(df_p) > 0:
        cum = df_p["pnl_yen"].cumsum()
        ax.plot(range(len(cum)), cum.values, color="#2c3e50", lw=2.0,
                label=f"全セッション  {df_p['pnl_yen'].sum():+,.0f}円  "
                      f"n={len(df_p)}")

    # セッション別
    for sess_name, _, _, color in SESSIONS:
        sub = df_p[df_p["session"]==sess_name].copy()
        if len(sub) < 5: continue
        cum_s = sub["pnl_yen"].cumsum()
        ax.plot(range(len(cum_s)), cum_s.values, color=color, lw=1.3,
                alpha=0.75, ls="--",
                label=f"{sess_name.split()[0]}  {sub['pnl_yen'].sum():+,.0f}円  "
                      f"n={len(sub)}")

    ax.set_title(period_label, fontsize=10, fontweight="bold")
    ax.set_xlabel("トレード番号", fontsize=8)
    ax.set_ylabel("累積損益 (円)", fontsize=8)
    ax.legend(fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

plt.tight_layout()
fig.savefig(OUT_DIR/"bt_pnl_curve.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 図2: R倍率分布 セッション別（IS） ──────────────────────
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"IS期間  R倍率分布  ─  セッション別\n"
             f"（R=1.0 → 資金0.5%分の利益 / R=-1.0 → SL到達）",
             fontsize=12, fontweight="bold")

for ax, (sess_name, _, _, color) in zip(axes.flat, SESSIONS):
    ax.set_facecolor("#f8f9fa")
    ax.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6)
    sub = df_is[df_is["session"]==sess_name]
    if len(sub) < 10:
        ax.set_title(f"{sess_name}  (データ不足)", fontsize=9)
        continue

    sv = summarize(sub)
    r = sub["r_mult"]
    lo, hi = np.percentile(r, [1, 99])
    ax.hist(r.clip(lo, hi), bins=60, density=True, color=color,
            alpha=0.65, edgecolor="none")
    try:
        kde = stats.gaussian_kde(r.clip(lo, hi), bw_method=0.3)
        xs  = np.linspace(lo, hi, 300)
        ax.plot(xs, kde(xs), color=color, lw=2.0)
    except Exception:
        pass

    ax.axvline(r.mean(), color="black", lw=1.2, ls=":", label=f"平均 {r.mean():+.3f}R")
    ax.set_title(
        f"{sess_name}  n={len(sub)}  勝率{sv['win_rate']:.1f}%  "
        f"PF {sv['pf']:.2f}  avgR {sv['avg_r']:+.4f}",
        fontsize=9, fontweight="bold"
    )
    ax.set_xlabel("R倍率", fontsize=8)
    ax.set_ylabel("確率密度", fontsize=8)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
fig.savefig(OUT_DIR/"bt_r_dist.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 図3: セッション別 PF / 損益 棒グラフ（IS vs OOS） ─────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("セッション別指標比較  IS vs OOS", fontsize=12, fontweight="bold")

sess_names = [s[0] for s in SESSIONS]
colors     = [s[3] for s in SESSIONS]
x = np.arange(len(sess_names))

for ax, (metric, ylabel) in zip(axes, [
    ("pf",        "Profit Factor"),
    ("total_pnl", "総損益 (円)"),
    ("win_rate",  "勝率 (%)"),
]):
    is_vals, oos_vals = [], []
    for sess_name in sess_names:
        si = summarize(df_is[df_is["session"]==sess_name])
        so = summarize(df_oos[df_oos["session"]==sess_name])
        is_vals.append(si.get(metric, 0))
        oos_vals.append(so.get(metric, 0))

    ax.set_facecolor("#f8f9fa")
    if metric == "pf":
        ax.axhline(1.0, color="#e74c3c", lw=1.0, ls="--", alpha=0.7, label="PF=1.0")
    if metric == "win_rate":
        ax.axhline(50, color="#e74c3c", lw=1.0, ls="--", alpha=0.7)

    bars_is  = ax.bar(x - 0.2, is_vals,  0.35, label="IS",  color=colors, alpha=0.8)
    bars_oos = ax.bar(x + 0.2, oos_vals, 0.35, label="OOS", color=colors, alpha=0.45,
                      edgecolor=[c for c in colors], linewidth=1.2)

    ax.set_xticks(x)
    ax.set_xticklabels([s.split()[0] for s in sess_names], fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(ylabel, fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    if metric == "total_pnl":
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

plt.tight_layout()
fig.savefig(OUT_DIR/"bt_session_compare.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終サマリー ────────────────────────────────────────────
print("\n" + "="*70)
print("  最終サマリー（IS × セッション別）")
print("="*70)
print(f"  資金: {CAPITAL:,}円  リスク: {RISK_PCT*100:.1f}%/trade  "
      f"ATR({ATR_PERIOD})  最大保有: {MAX_HOLD}本")
print(f"  強弱フィルター: USD-JPY差 下位{int(Q_THRESHOLD*100)}%")
print()
for sv in sess_rows:
    verdict = "★ 採用候補" if sv.get("pf",0) >= 1.2 else "△ 要検討" if sv.get("pf",0) >= 1.0 else "✗"
    print(f"  {sv['session']:18s}  PF:{sv['pf']:.2f}  "
          f"勝率:{sv['win_rate']:.1f}%  損益:{sv['total_pnl']:+,.0f}円  "
          f"DD:{sv['max_dd']:,.0f}円  avgR:{sv['avg_r']:+.4f}  {verdict}")

print(f"\n保存先: {OUT_DIR}")
print("完了")
