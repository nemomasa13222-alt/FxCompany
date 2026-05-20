# -*- coding: utf-8 -*-
"""
Phase 2: ファットテール・リバーサル バックテスト
IS期間（2022-2023）

戦略ルール:
  [シグナル] 5分足の |対数リターン| > IS期間の上位X% 閾値
  [Entry1]   翌足（Bar1）のOpen でエントリー
  [Entry2]   Bar1も下落（Close<Open）なら Bar1終値で追加エントリー
  [TP]       各エントリーの下落幅 × Fib23.6% を上乗せした価格
  [SL]       各エントリーで資金の1%損失となるロット計算、SL距離=下落幅と同値
  [MAX_HOLD] 5本以内に決済されなければ成行クローズ

実行: python _run_fat_tail_backtest.py
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "fat_tail_backtest"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
IS_START   = "2022-01-01"; IS_END = "2023-12-31"
PAIRS      = ["GBPUSD", "AUDUSD"]
PIP        = {"GBPUSD": 0.0001, "AUDUSD": 0.0001}
CAPITAL    = 1_000_000   # 円（バックテスト用）
RISK_PCT   = 0.005       # 1エントリーあたりの損失上限 = 資金の0.5%
FIB_TP     = 0.500       # エグジット水準: Fib50%
MAX_HOLD   = 5           # 最大保有バー数
THRESHOLDS = [0.01]      # 上位1%固定

try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except: pass

def load_5min(pair):
    f = DATA_DIR / f"{pair}_5min.parquet"
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    df = df[(df.index >= IS_START) & (df.index <= IS_END)]
    return df[["Open","High","Low","Close"]].dropna()

def run_backtest(pair: str, threshold: float):
    df   = load_5min(pair)
    pip  = PIP[pair]
    log_ret = np.log(df["Close"] / df["Open"])
    abs_ret = log_ret.abs()
    cut  = float(abs_ret.quantile(1 - threshold))

    records = []
    i = 0
    n = len(df)
    while i < n - MAX_HOLD - 2:
        # ─── シグナル検出
        ret0 = log_ret.iloc[i]
        if abs_ret.iloc[i] <= cut:
            i += 1; continue

        direction = "buy" if ret0 < 0 else "sell"  # 下落→買い / 上昇→売り
        bar0 = df.iloc[i]
        # 下落幅（pips）
        move0 = (bar0["Open"] - bar0["Close"]) / pip  # > 0 for down
        if direction == "sell":
            move0 = (bar0["Close"] - bar0["Open"]) / pip
        if move0 <= 0:
            i += 1; continue

        # ─── Entry 1: 翌足Open
        if i + 1 >= n: break
        bar1     = df.iloc[i + 1]
        e1_price = bar1["Open"]
        sl_dist1 = move0 * pip   # SL距離 = 下落幅と同値（price単位）
        sl1      = e1_price - sl_dist1 if direction=="buy" else e1_price + sl_dist1
        tp1      = e1_price + FIB_TP * move0 * pip if direction=="buy" \
                   else e1_price - FIB_TP * move0 * pip
        lot1     = (CAPITAL * RISK_PCT) / (move0 * PIP.get(pair, 0.0001) * 10_000)
        # (lot1 × move0pip × pip_val[10000per lot]) = CAPITAL×RISK_PCT

        # ─── Entry 2の確認（Bar1が終値 < 始値）
        bar1_falls = bar1["Close"] < bar1["Open"] if direction=="buy" \
                     else bar1["Close"] > bar1["Open"]
        has_e2    = False
        e2_price  = sl2 = tp2 = lot2 = 0.0
        if bar1_falls:
            move1    = (bar1["Open"] - bar1["Close"]) / pip if direction=="buy" \
                       else (bar1["Close"] - bar1["Open"]) / pip
            if move1 > 0:
                has_e2   = True
                e2_price = bar1["Close"]
                sl_dist2 = move1 * pip
                sl2      = e2_price - sl_dist2 if direction=="buy" else e2_price + sl_dist2
                tp2      = e2_price + FIB_TP * move1 * pip if direction=="buy" \
                           else e2_price - FIB_TP * move1 * pip
                lot2     = (CAPITAL * RISK_PCT) / (move1 * PIP.get(pair, 0.0001) * 10_000)

        # ─── バー追跡（Bar2から MAX_HOLD 本以内）
        start_bar = i + 2  # Bar2 から追跡開始
        pnl1 = pnl2 = 0.0
        e1_closed = e2_closed = False
        exit_bar  = min(start_bar + MAX_HOLD, n - 1)

        for j in range(start_bar, min(start_bar + MAX_HOLD, n)):
            bar = df.iloc[j]
            if direction == "buy":
                # SL判定（安値がSLを下回る）
                if not e1_closed and bar["Low"] <= sl1:
                    pnl1 = -(CAPITAL * RISK_PCT); e1_closed = True
                if has_e2 and not e2_closed and bar["Low"] <= sl2:
                    pnl2 = -(CAPITAL * RISK_PCT); e2_closed = True
                # TP判定（高値がTPを上回る）
                if not e1_closed and bar["High"] >= tp1:
                    pnl1 = FIB_TP * move0 * pip * lot1 * 10_000; e1_closed = True
                if has_e2 and not e2_closed and bar["High"] >= tp2:
                    pnl2 = FIB_TP * move1 * pip * lot2 * 10_000; e2_closed = True
            else:  # sell
                if not e1_closed and bar["High"] >= sl1:
                    pnl1 = -(CAPITAL * RISK_PCT); e1_closed = True
                if has_e2 and not e2_closed and bar["High"] >= sl2:
                    pnl2 = -(CAPITAL * RISK_PCT); e2_closed = True
                if not e1_closed and bar["Low"] <= tp1:
                    pnl1 = FIB_TP * move0 * pip * lot1 * 10_000; e1_closed = True
                if has_e2 and not e2_closed and bar["Low"] <= tp2:
                    pnl2 = FIB_TP * move1 * pip * lot2 * 10_000; e2_closed = True
            if e1_closed and (not has_e2 or e2_closed):
                exit_bar = j; break

        # 未決済は成行クローズ（exit_barの終値）
        exit_close = df.iloc[exit_bar]["Close"]
        if not e1_closed:
            if direction == "buy":
                pnl1 = (exit_close - e1_price) / pip * pip * lot1 * 10_000
            else:
                pnl1 = (e1_price - exit_close) / pip * pip * lot1 * 10_000
        if has_e2 and not e2_closed:
            if direction == "buy":
                pnl2 = (exit_close - e2_price) / pip * pip * lot2 * 10_000
            else:
                pnl2 = (e2_price - exit_close) / pip * pip * lot2 * 10_000

        total_pnl = pnl1 + pnl2
        records.append({
            "datetime":  df.index[i],
            "direction": direction,
            "move0_pip": round(move0, 1),
            "has_e2":    has_e2,
            "pnl1":      round(pnl1, 0),
            "pnl2":      round(pnl2, 0),
            "pnl_total": round(total_pnl, 0),
        })
        i = exit_bar + 1  # 次のシグナルは決済後から探す

    return pd.DataFrame(records)

# ════════════════════════════════════════════════════════
# サーベイ実行
# ════════════════════════════════════════════════════════
all_summary = []

for pair in PAIRS:
    print(f"\n{'='*65}")
    print(f"  {pair} — ファットテール・リバーサル バックテスト")
    print(f"{'='*65}")
    print(f"  {'閾値':>5} {'件数':>6} {'勝率':>7} {'PF':>7} "
          f"{'損益万':>8} {'MaxDD%':>8} {'2回目%':>8}")
    print(f"  {'-'*60}")

    pair_results = []
    for thr in THRESHOLDS:
        df_tr = run_backtest(pair, thr)
        if len(df_tr) == 0:
            print(f"  {thr*100:4.0f}%  (データなし)"); continue

        pnl  = df_tr["pnl_total"]
        wins = (pnl > 0).sum(); n = len(pnl)
        gp   = pnl[pnl>0].sum(); gl = pnl[pnl<=0].abs().sum()
        pf   = gp/gl if gl>0 else float("inf")
        cum  = pnl.cumsum()
        dd   = (cum.cummax() - cum).max() / CAPITAL * 100
        e2r  = df_tr["has_e2"].mean() * 100

        print(f"  {thr*100:4.0f}%  {n:6d}  {wins/n*100:6.1f}%  "
              f"{pf:6.3f}  {pnl.sum()/10000:+7.1f}  {dd:7.1f}%  {e2r:7.1f}%")

        pair_results.append({
            "pair": pair, "threshold": thr,
            "n": n, "win_rate": round(wins/n*100,1),
            "pf": round(pf,3), "pnl_man": round(pnl.sum()/10000,1),
            "max_dd_pct": round(dd,1), "e2_rate": round(e2r,1),
        })
        all_summary.append(pair_results[-1])

        # 月次PnL
        df_tr["month"] = df_tr["datetime"].dt.to_period("M")
        monthly = df_tr.groupby("month")["pnl_total"].sum()
        df_tr.to_csv(OUT_DIR / f"{pair}_{int(thr*100)}pct_trades.csv",
                     index=False, encoding="utf-8-sig")

    # ── 累積PnLグラフ（閾値別比較）
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"{pair} IS期間 ファットテール・リバーサル 累積損益", fontsize=11)
    colors = ["#2980b9","#27ae60","#e74c3c","#8e44ad"]
    for ax_i, ax in enumerate(axes):
        for t_i, thr in enumerate(THRESHOLDS):
            f_csv = OUT_DIR / f"{pair}_{int(thr*100)}pct_trades.csv"
            if not f_csv.exists(): continue
            d = pd.read_csv(f_csv, encoding="utf-8-sig")
            if len(d)==0: continue
            cum = d["pnl_total"].cumsum()
            ax.plot(cum.values, color=colors[t_i], lw=1.5,
                    label=f"閾値{thr*100:.0f}% ({len(d)}件)")
        ax.axhline(0, color="#333", lw=0.8, ls="--")
        ax.set_title("累積損益（円）" if ax_i==0 else "累積損益（万円）")
        if ax_i==1: ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v,_:f"{v/10000:.0f}万"))
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{int(v):,}"))
    plt.tight_layout()
    plt.savefig(OUT_DIR / f"{pair}_cumulative_pnl.png", dpi=130, bbox_inches="tight")
    plt.close()

# ── サマリーCSV
pd.DataFrame(all_summary).to_csv(OUT_DIR/"summary.csv",
                                  index=False, encoding="utf-8-sig")

print(f"\n{'='*65}")
print("総括サマリー（IS期間）")
print(f"{'='*65}")
print(f"{'ペア':>8} {'閾値':>5} {'件数':>6} {'勝率':>7} "
      f"{'PF':>7} {'損益万':>8} {'MaxDD%':>8}")
print(f"{'-'*60}")
for r in sorted(all_summary, key=lambda x: -x["pf"]):
    print(f"{r['pair']:>8}  {r['threshold']*100:3.0f}%  {r['n']:6d}  "
          f"{r['win_rate']:6.1f}%  {r['pf']:6.3f}  "
          f"{r['pnl_man']:+7.1f}  {r['max_dd_pct']:7.1f}%")
print(f"\n保存先: {OUT_DIR}")
print("完了")
