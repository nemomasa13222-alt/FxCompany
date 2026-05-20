# -*- coding: utf-8 -*-
"""
EURJPY 通貨強弱 × 自己相関スキャルピング戦略
IS+OOS フルバックテスト
───────────────────────────────────────────────────────────────
確定パラメータ:
  Q_EXTREME=0.03（強弱差 下位3%）
  AC_MIN=0.10（自己相関係数 ≥0.10、セッション別方向）
  スプレッド=0.5pip（DMM FX）
  Capital=1,000,000 / Risk=0.5%/trade
  IS: 2022-2023 / OOS: 2024

出力: docs/eurjpy/bt_eurjpy.csv
      docs/eurjpy/pnl_is.png
      docs/eurjpy/pnl_oos.png
      docs/eurjpy/pnl_cumulative.png
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats

# ── フォント ───────────────────────────────────────────────────
FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

# ── パス設定 ──────────────────────────────────────────────────
BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "eurjpy"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 確定パラメータ ─────────────────────────────────────────────
IS_START  = "2022-01-01"
IS_END    = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END   = "2024-12-31"

Q_EXTREME       = 0.03    # 強弱差 下位3%（IS期間で計算）
AC_MIN          = 0.10    # 自己相関係数 閾値
STRENGTH_WINDOW = 24      # 強弱スコアの計算ウィンドウ（5min×24=2時間）
AC_WINDOW       = 12      # 自己相関ウィンドウ（5min×12=1時間）
H_HOLD          = 6       # 保有バー数（5min×6=30分）
MAX_HOLD        = 48      # 最大保有バー数

SPREAD_PIPS = 0.5         # スプレッド (pip)
PIP_VALUE   = 100         # 1lot×1pip=100円
PIP_SIZE    = 0.01        # EURJPY 1pip=0.01
CAPITAL     = 1_000_000   # 初期資金
RISK_PCT    = 0.005       # 1トレードリスク 0.5%
ATR_PERIOD  = 14

JST = pd.Timedelta(hours=9)

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# EURJPYセッション別プレイブック（direction: +1=LONG, -1=SHORT, 0=skip）
# プレイブック（docs/strategy_judgment/playbook.csv）より
SESSIONS = [
    # △long（弱シグナル）はスキップ — プレイブック上▼SHORT/▲LONGのみ採用
    ("欧州 15-21JST", 15, 21, -1, "Q10+ac>0",  "#27ae60"),  # ▼SHORT（主力）
    ("NY   21-03JST", 21,  3, +1, "Q10+ac<0",  "#2980b9"),  # ▲LONG（主力）
]

# ── データ読込 ─────────────────────────────────────────────────
print("データ読込中 (全12ペア)...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists():
        print(f"  !! {pair} が見つかりません")
        continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]
    print(f"  {pair}: {len(df):,} bars  {df.index[0]} → {df.index[-1]}")

# 共通インデックス（全期間）
common_idx = dfs["EURJPY"].index
for p in dfs:
    common_idx = common_idx.intersection(dfs[p].index)
for p in dfs:
    dfs[p] = dfs[p].reindex(common_idx)

eurjpy = dfs["EURJPY"]
print(f"\n共通インデックス: {len(common_idx):,} bars  {common_idx[0]} → {common_idx[-1]}")

# ── 通貨強弱スコア ─────────────────────────────────────────────
print("\n通貨強弱スコア計算中...")
pair_lr = {p: np.log(df["Close"] / df["Close"].shift(STRENGTH_WINDOW))
           for p, df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair, (b, q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]
    raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]

str_df = pd.DataFrame(raw_str)
# EURJPY の通貨強弱差 = EUR強弱 - JPY強弱
eur_jpy_diff = str_df["EUR"] - str_df["JPY"]

# ── IS期間の分位点で閾値確定（先読みなし）─────────────────────
is_mask  = (common_idx >= IS_START) & (common_idx <= IS_END)
oos_mask = (common_idx >= OOS_START) & (common_idx <= OOS_END)

q_thresh_is = eur_jpy_diff[is_mask].quantile(Q_EXTREME)
print(f"IS期間の強弱差 Q{Q_EXTREME*100:.0f}% 閾値: {q_thresh_is:.6f}")

# ── 自己相関（ローリング）──────────────────────────────────────
print("自己相関計算中...")
returns_ej = np.log(eurjpy["Close"] / eurjpy["Close"].shift(1))

def rolling_autocorr(series, window, lag=1):
    arr = series.values
    result = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        x = arr[i - window + 1: i + 1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-lag], x[lag:])
        result[i] = c[0, 1]
    return pd.Series(result, index=series.index)

ac = rolling_autocorr(returns_ej, AC_WINDOW)
print(f"  自己相関 計算完了  有効値: {ac.notna().sum():,}")

# ── セッション割り当て ─────────────────────────────────────────
jst_hour = (common_idx + JST).hour

def get_sess_idx(h):
    for name, s, e, *_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]

sess_s = pd.Series([get_sess_idx(h) for h in jst_hour], index=common_idx)

# ── ベースシグナル（強弱差 Q_EXTREME以下） ─────────────────────
base_signal = (eur_jpy_diff <= q_thresh_is) & eur_jpy_diff.notna()

# ── ATR計算 ────────────────────────────────────────────────────
hi_s  = eurjpy["High"]
lo_s  = eurjpy["Low"]
cl_prev = eurjpy["Close"].shift(1)
tr  = pd.concat([(hi_s - lo_s), (hi_s - cl_prev).abs(), (lo_s - cl_prev).abs()],
                axis=1).max(axis=1)
atr = tr.rolling(ATR_PERIOD).mean()

# ── バックテスト関数 ───────────────────────────────────────────
def run_backtest_session(period_mask):
    """
    全セッションのシグナルを走査してトレードログを生成
    - 欧州(15-21JST): SHORT。強弱差Q3% + ac>0.10 → ショートエントリー
    - NY(21-03JST): LONG。強弱差Q3% + ac<-0.10 → ロングエントリー
    - 東京・深夜: LONG（弱シグナル）。強弱差Q3% + ac<-0.10
    """
    records = []
    spread_cost = SPREAD_PIPS * PIP_SIZE  # スプレッドコスト（価格単位）

    for sess_name, s_h, e_h, direction, flt, _ in SESSIONS:
        sess_mask = sess_s == sess_name

        # 自己相関フィルター（direction=+1はac<-AC_MIN, direction=-1はac>+AC_MIN）
        if direction == -1:  # SHORT
            ac_filter = (ac > AC_MIN) & ac.notna()
        else:  # LONG
            ac_filter = (ac < -AC_MIN) & ac.notna()

        signal_mask = base_signal & sess_mask & ac_filter & period_mask

        sig_positions = np.where(signal_mask)[0]
        for sig_pos in sig_positions:
            ep = sig_pos + 1
            if ep >= len(eurjpy): continue

            entry_bar   = eurjpy.index[ep]
            entry_open  = eurjpy["Open"].iloc[ep]
            atr_val     = atr.iloc[sig_pos]
            if atr_val <= 0 or np.isnan(atr_val): continue

            # エントリー価格（スプレッド考慮）
            if direction == -1:   # SHORT: 売りはBid = Open - spread/2
                entry_price = entry_open - spread_cost / 2
                sl_price    = entry_price + atr_val
            else:                 # LONG:  買いはAsk = Open + spread/2
                entry_price = entry_open + spread_cost / 2
                sl_price    = entry_price - atr_val

            sl_pips = atr_val / PIP_SIZE
            if sl_pips <= 0: continue
            lot_size = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

            # トレイリングストップ（保有期間: MAX_HOLDバーまで）
            exit_price = None
            exit_reason = "time"
            held = 0
            trail_stop = sl_price

            if direction == -1:  # SHORT
                best_price = entry_price   # 最安値（LOW方向）
                for h in range(1, MAX_HOLD + 1):
                    bp = ep + h
                    if bp >= len(eurjpy): break
                    b_high = eurjpy["High"].iloc[bp]
                    b_low  = eurjpy["Low"].iloc[bp]
                    held = h
                    if b_high >= trail_stop:
                        exit_price = trail_stop
                        exit_reason = "stop"
                        break
                    if b_low < best_price:
                        best_price = b_low
                        trail_stop = min(trail_stop, best_price + atr_val)
            else:  # LONG
                best_price = entry_price   # 最高値（HIGH方向）
                for h in range(1, MAX_HOLD + 1):
                    bp = ep + h
                    if bp >= len(eurjpy): break
                    b_high = eurjpy["High"].iloc[bp]
                    b_low  = eurjpy["Low"].iloc[bp]
                    held = h
                    if b_low <= trail_stop:
                        exit_price = trail_stop
                        exit_reason = "stop"
                        break
                    if b_high > best_price:
                        best_price = b_high
                        trail_stop = max(trail_stop, best_price - atr_val)

            if exit_price is None:
                fp = ep + held
                if fp >= len(eurjpy): continue
                exit_price = eurjpy["Close"].iloc[fp]
                exit_reason = "time"

            # 決済時もスプレッドコスト
            if direction == -1:  # SHORT: 買い戻しはAsk
                exit_price_adj = exit_price + spread_cost / 2
                pnl_pips = (entry_price - exit_price_adj) / PIP_SIZE
            else:  # LONG: 売りはBid
                exit_price_adj = exit_price - spread_cost / 2
                pnl_pips = (exit_price_adj - entry_price) / PIP_SIZE

            pnl_yen = pnl_pips * PIP_VALUE * lot_size
            r_mult  = pnl_yen / (CAPITAL * RISK_PCT)

            exit_bar = eurjpy.index[ep + held] if (ep + held) < len(eurjpy) else eurjpy.index[-1]
            sig_bar  = eurjpy.index[sig_pos]

            records.append({
                "signal_dt":   sig_bar,
                "entry_dt":    entry_bar,
                "exit_dt":     exit_bar,
                "session":     sess_name,
                "direction":   "SHORT" if direction == -1 else "LONG",
                "filter":      flt,
                "entry_price": round(entry_price, 5),
                "exit_price":  round(exit_price_adj, 5),
                "sl_price":    round(sl_price, 5),
                "lot_size":    round(lot_size, 2),
                "held_bars":   held,
                "exit_reason": exit_reason,
                "pnl_pips":    round(pnl_pips, 2),
                "pnl_yen":     round(pnl_yen, 0),
                "r_mult":      round(r_mult, 3),
                "atr_val":     round(atr_val, 5),
                "eur_jpy_diff":round(eur_jpy_diff.iloc[sig_pos], 6),
                "ac_val":      round(ac.iloc[sig_pos], 4),
            })

    df_rec = pd.DataFrame(records)
    if len(df_rec) > 0:
        df_rec = df_rec.sort_values("entry_dt").reset_index(drop=True)
    return df_rec

# ── IS バックテスト ─────────────────────────────────────────────
print("\n=== IS バックテスト (2022-2023) ===")
df_is = run_backtest_session(is_mask)
print(f"  トレード数: {len(df_is)}")
if len(df_is) > 0:
    wins = (df_is["pnl_yen"] > 0).sum()
    total_pnl = df_is["pnl_yen"].sum()
    gross_profit = df_is.loc[df_is["pnl_yen"]>0,"pnl_yen"].sum()
    gross_loss   = df_is.loc[df_is["pnl_yen"]<0,"pnl_yen"].abs().sum()
    pf_is = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    cumsum_is = df_is["pnl_yen"].cumsum()
    running_max = cumsum_is.cummax()
    dd_is = ((running_max - cumsum_is) / CAPITAL * 100).max()
    print(f"  勝率:     {wins/len(df_is)*100:.1f}%")
    print(f"  PF:       {pf_is:.3f}")
    print(f"  累積損益: {total_pnl/10000:.1f}万円")
    print(f"  最大DD:   {dd_is:.1f}%")
    df_is["period"] = "IS"

# ── OOS バックテスト ────────────────────────────────────────────
print("\n=== OOS バックテスト (2024) ===")
df_oos = run_backtest_session(oos_mask)
print(f"  トレード数: {len(df_oos)}")
if len(df_oos) > 0:
    wins_o = (df_oos["pnl_yen"] > 0).sum()
    total_pnl_o = df_oos["pnl_yen"].sum()
    gross_profit_o = df_oos.loc[df_oos["pnl_yen"]>0,"pnl_yen"].sum()
    gross_loss_o   = df_oos.loc[df_oos["pnl_yen"]<0,"pnl_yen"].abs().sum()
    pf_oos = gross_profit_o / gross_loss_o if gross_loss_o > 0 else float("inf")
    cumsum_oos = df_oos["pnl_yen"].cumsum()
    running_max_o = cumsum_oos.cummax()
    dd_oos = ((running_max_o - cumsum_oos) / CAPITAL * 100).max()
    print(f"  勝率:     {wins_o/len(df_oos)*100:.1f}%")
    print(f"  PF:       {pf_oos:.3f}")
    print(f"  累積損益: {total_pnl_o/10000:.1f}万円")
    print(f"  最大DD:   {dd_oos:.1f}%")
    df_oos["period"] = "OOS"

# ── 全期間CSV保存 ───────────────────────────────────────────────
df_all_trades = pd.concat([df_is, df_oos], ignore_index=True)
csv_path = OUT_DIR / "bt_eurjpy.csv"
df_all_trades.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"\n全トレードCSV保存: {csv_path}  ({len(df_all_trades)} rows)")

# ── 月次PnL集計 ────────────────────────────────────────────────
def monthly_pnl(df):
    if len(df) == 0: return pd.Series(dtype=float)
    df2 = df.copy()
    df2["entry_dt"] = pd.to_datetime(df2["entry_dt"])
    df2["month"] = df2["entry_dt"].dt.to_period("M")
    return df2.groupby("month")["pnl_yen"].sum()

monthly_is  = monthly_pnl(df_is)
monthly_oos = monthly_pnl(df_oos)

# ── 図1: IS期間 月次PnL ─────────────────────────────────────────
print("\n図1: IS期間 月次PnL描画中...")
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#fafafa")
ax.set_facecolor("#f8f9fa")
colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in monthly_is.values]
bars = ax.bar(range(len(monthly_is)), monthly_is.values / 10000,
              color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
ax.set_xticks(range(len(monthly_is)))
ax.set_xticklabels([str(p) for p in monthly_is.index], rotation=45, ha="right", fontsize=8)
ax.axhline(0, color="#333", lw=0.8)
ax.set_xlabel("月", fontsize=10)
ax.set_ylabel("損益 (万円)", fontsize=10)
ax.set_title(f"IS期間（2022-2023）月次PnL  合計: {monthly_is.sum()/10000:.1f}万円  "
             f"PF: {pf_is:.3f}  DD: {dd_is:.1f}%",
             fontsize=11, fontweight="bold")
ax.grid(axis="y", alpha=0.4)
for bar, val in zip(bars, monthly_is.values):
    if abs(val) > 500:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05 * (1 if val >= 0 else -1),
                f"{val/10000:.1f}", ha="center", va="bottom" if val >= 0 else "top",
                fontsize=7, color="#333")
plt.tight_layout()
fig.savefig(OUT_DIR / "pnl_is.png", dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: {OUT_DIR/'pnl_is.png'}")

# ── 図2: OOS期間 月次PnL ────────────────────────────────────────
print("図2: OOS期間 月次PnL描画中...")
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("#fafafa")
ax.set_facecolor("#f8f9fa")
colors_o = ["#2ecc71" if v >= 0 else "#e74c3c" for v in monthly_oos.values]
bars_o = ax.bar(range(len(monthly_oos)), monthly_oos.values / 10000,
                color=colors_o, alpha=0.85, edgecolor="white", linewidth=0.5)
ax.set_xticks(range(len(monthly_oos)))
ax.set_xticklabels([str(p) for p in monthly_oos.index], rotation=45, ha="right", fontsize=8)
ax.axhline(0, color="#333", lw=0.8)
ax.set_xlabel("月", fontsize=10)
ax.set_ylabel("損益 (万円)", fontsize=10)
ax.set_title(f"OOS期間（2024）月次PnL  合計: {monthly_oos.sum()/10000:.1f}万円  "
             f"PF: {pf_oos:.3f}  DD: {dd_oos:.1f}%",
             fontsize=11, fontweight="bold")
ax.grid(axis="y", alpha=0.4)
for bar, val in zip(bars_o, monthly_oos.values):
    if abs(val) > 300:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02 * (1 if val >= 0 else -1),
                f"{val/10000:.1f}", ha="center", va="bottom" if val >= 0 else "top",
                fontsize=7.5, color="#333")
plt.tight_layout()
fig.savefig(OUT_DIR / "pnl_oos.png", dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: {OUT_DIR/'pnl_oos.png'}")

# ── 図3: IS+OOS 累積損益チャート ────────────────────────────────
print("図3: IS+OOS累積損益チャート描画中...")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios":[3,1]})
fig.patch.set_facecolor("#fafafa")

# 累積損益
cumsum_is_all  = df_is["pnl_yen"].cumsum() if len(df_is) > 0 else pd.Series([0])
cumsum_oos_all = df_oos["pnl_yen"].cumsum() if len(df_oos) > 0 else pd.Series([0])

is_dates  = pd.to_datetime(df_is["entry_dt"])  if len(df_is)  > 0 else pd.Series()
oos_dates = pd.to_datetime(df_oos["entry_dt"]) if len(df_oos) > 0 else pd.Series()

ax1.set_facecolor("#f8f9fa")
if len(df_is) > 0:
    ax1.plot(is_dates, cumsum_is_all / 10000, color="#2980b9", lw=1.8,
             label=f"IS 2022-2023  +{df_is['pnl_yen'].sum()/10000:.1f}万円  PF={pf_is:.3f}  DD={dd_is:.1f}%")
    ax1.fill_between(is_dates, 0, cumsum_is_all / 10000, alpha=0.12, color="#2980b9")

if len(df_oos) > 0:
    oos_offset = df_is["pnl_yen"].sum() / 10000 if len(df_is) > 0 else 0
    ax1.plot(oos_dates, (cumsum_oos_all + df_is["pnl_yen"].sum()) / 10000,
             color="#e67e22", lw=1.8, ls="-",
             label=f"OOS 2024  +{df_oos['pnl_yen'].sum()/10000:.1f}万円  PF={pf_oos:.3f}  DD={dd_oos:.1f}%")
    ax1.fill_between(oos_dates, oos_offset,
                     (cumsum_oos_all + df_is["pnl_yen"].sum()) / 10000,
                     alpha=0.12, color="#e67e22")

if len(df_oos) > 0 and len(df_is) > 0:
    ax1.axvline(oos_dates.iloc[0], color="#e74c3c", lw=1.5, ls="--", alpha=0.8,
                label="OOS開始 2024-01-01")

ax1.axhline(0, color="#333", lw=0.8)
ax1.set_ylabel("累積損益 (万円)", fontsize=10)
total_all = (df_is["pnl_yen"].sum() + df_oos["pnl_yen"].sum()) / 10000
ax1.set_title(f"EURJPY 通貨強弱×自己相関戦略  IS+OOS 累積損益\n"
              f"Q_EXTREME={Q_EXTREME*100:.0f}% / AC≥{AC_MIN} / スプレッド{SPREAD_PIPS}pip  "
              f"合計: +{total_all:.1f}万円",
              fontsize=12, fontweight="bold")
ax1.legend(fontsize=9, framealpha=0.95)
ax1.grid(axis="y", alpha=0.4)

# 下段: ドローダウン
ax2.set_facecolor("#f8f9fa")
if len(df_all_trades) > 0:
    cumsum_all = df_all_trades["pnl_yen"].cumsum()
    running_max_all = cumsum_all.cummax()
    dd_series = (running_max_all - cumsum_all) / CAPITAL * 100
    all_dates = pd.to_datetime(df_all_trades["entry_dt"])
    ax2.fill_between(all_dates, 0, -dd_series, color="#e74c3c", alpha=0.5)
    ax2.axhline(0, color="#333", lw=0.8)
    ax2.set_ylabel("DD (%)", fontsize=9)
    ax2.set_xlabel("日付", fontsize=10)
    ax2.set_ylim(-max(dd_series.max() * 1.3, 5), 1)
    ax2.grid(axis="y", alpha=0.3)

plt.tight_layout()
fig.savefig(OUT_DIR / "pnl_cumulative.png", dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: {OUT_DIR/'pnl_cumulative.png'}")

# ── セッション別成績集計 ────────────────────────────────────────
print("\n=== セッション別成績 ===")
for period, df_p in [("IS", df_is), ("OOS", df_oos)]:
    print(f"\n{period}期間:")
    for sess_name, *_ in SESSIONS:
        sub = df_p[df_p["session"] == sess_name] if len(df_p) > 0 else pd.DataFrame()
        if len(sub) == 0:
            print(f"  {sess_name}: データなし")
            continue
        wins_s = (sub["pnl_yen"] > 0).sum()
        gp = sub.loc[sub["pnl_yen"]>0,"pnl_yen"].sum()
        gl = sub.loc[sub["pnl_yen"]<0,"pnl_yen"].abs().sum()
        pf_s = gp / gl if gl > 0 else float("inf")
        print(f"  {sess_name}: n={len(sub):3d}  勝率={wins_s/len(sub)*100:5.1f}%  "
              f"PF={pf_s:.3f}  損益={sub['pnl_yen'].sum()/10000:+.1f}万")

# ── 結果保存（KPI集計CSVも出力）────────────────────────────────
kpi = {
    "is_trades": len(df_is),
    "is_winrate": round((df_is["pnl_yen"]>0).sum()/len(df_is)*100, 1) if len(df_is) > 0 else 0,
    "is_pf":     round(pf_is, 3),
    "is_pnl_man":round(df_is["pnl_yen"].sum()/10000, 1) if len(df_is) > 0 else 0,
    "is_dd":     round(dd_is, 1) if len(df_is) > 0 else 0,
    "oos_trades":len(df_oos),
    "oos_winrate":round((df_oos["pnl_yen"]>0).sum()/len(df_oos)*100, 1) if len(df_oos) > 0 else 0,
    "oos_pf":    round(pf_oos, 3),
    "oos_pnl_man":round(df_oos["pnl_yen"].sum()/10000, 1) if len(df_oos) > 0 else 0,
    "oos_dd":    round(dd_oos, 1) if len(df_oos) > 0 else 0,
    "q_thresh":  round(q_thresh_is, 6),
    "q_extreme": Q_EXTREME,
    "ac_min":    AC_MIN,
    "spread_pips": SPREAD_PIPS,
}
pd.Series(kpi).to_json(OUT_DIR / "kpi.json")
print(f"\nKPI保存: {OUT_DIR/'kpi.json'}")
print("\n=== 完了 ===")
