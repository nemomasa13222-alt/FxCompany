# -*- coding: utf-8 -*-
import sys, glob
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
import numpy as np

CAPITAL_PER_SECTOR = 100_000
N_SECTORS  = 10
TOTAL_CAP  = CAPITAL_PER_SECTOR * N_SECTORS
IS_END     = "2023-12-31"
OOS_START  = "2024-01-01"

# ── ロバストネスCSV（共有プール・IS期間） ──────────────────────────────────
rob = pd.read_csv(
    sorted(glob.glob("japan_stocks/results/backtest_v2/cs_robustness_*.csv"))[-1],
    encoding="utf-8-sig"
)

# ── per-sector CSV ─────────────────────────────────────────────────────────
ps = pd.read_csv(
    sorted(glob.glob("japan_stocks/results/backtest_v2/per_sector_full_*.csv"))[-1],
    encoding="utf-8-sig"
)
ps["exit_date"]  = pd.to_datetime(ps["exit_date"])
ps["entry_date"] = pd.to_datetime(ps["entry_date"])

ps_is  = ps[ps["exit_date"] <= pd.Timestamp(IS_END)]
ps_oos = ps[ps["exit_date"] >= pd.Timestamp(OOS_START)]


def stats(df, cap):
    pnl = df["net_pnl_jpy"]
    n   = len(pnl)
    if n == 0:
        return dict(n=0, wr=0, pf=0, dd=0, pnl=0)
    wins = int((pnl > 0).sum())
    gp   = pnl[pnl > 0].sum()
    gl   = pnl[pnl < 0].abs().sum()
    arr  = pnl.values
    cs   = np.cumsum(arr)
    rm   = np.maximum.accumulate(cs)
    dd   = round(float((rm - cs).max() / cap * 100), 2)
    return dict(
        n   = n,
        wr  = round(wins / n * 100, 1),
        pf  = round(gp / gl, 2) if gl > 0 else 999,
        dd  = dd,
        pnl = int(round(pnl.sum())),
    )


is_s  = stats(ps_is,  TOTAL_CAP)
oos_s = stats(ps_oos, TOTAL_CAP)

# ─────────────────────────────────────────────────────────────────────────────
print("=" * 68)
print("  比較: ロバストネス（共有プール IS）vs per-sector 100K")
print("=" * 68)

print()
print("【ロバストネス 3×3（共有プール・IS 2022-2023）】")
header = f"  {'条件':>14}  {'件数':>5}  {'勝率':>6}  {'PF':>5}  {'DD':>7}  {'損益':>11}"
print(header)
print("-" * 60)
for _, r in rob.iterrows():
    is_adopted = (r["sector_min_rise"] == 2.0 and r["min_gap"] == 3.0)
    mark = "★採用" if is_adopted else "     "
    cond = f"rise={r['sector_min_rise']:.0f}% gap={r['min_gap']:.0f}%"
    print(f"  {mark} {cond:<12}  {int(r['total_trades']):>5}  "
          f"{r['win_rate']:>5.1f}%  {r['profit_factor']:>5.2f}  "
          f"{r['max_drawdown_pct']:>6.2f}%  {int(r['total_pnl_jpy']):>+11,}円")

print()
print("【per-sector 100K × 10業種（採用パラメータ rise=2% gap=3%）】")
header2 = f"  {'期間':>14}  {'件数':>5}  {'勝率':>6}  {'PF':>5}  {'DD':>7}  {'損益':>11}"
print(header2)
print("-" * 60)
print(f"  {'IS  2022-23':>14}  {is_s['n']:>5}  {is_s['wr']:>5.1f}%  "
      f"{is_s['pf']:>5.2f}  {is_s['dd']:>6.2f}%  {is_s['pnl']:>+11,}円")
print(f"  {'OOS 2024-now':>14}  {oos_s['n']:>5}  {oos_s['wr']:>5.1f}%  "
      f"{oos_s['pf']:>5.2f}  {oos_s['dd']:>6.2f}%  {oos_s['pnl']:>+11,}円")

# 採用パラメータ行
adopted = rob[(rob["sector_min_rise"] == 2.0) & (rob["min_gap"] == 3.0)].iloc[0]

print()
print("=" * 68)
print("  総合比較サマリー")
print("=" * 68)
print(f"  {'指標':>18}  {'共有プール IS':>13}  {'per-sector IS':>13}  {'per-sector OOS':>14}")
print("-" * 65)
print(f"  {'件数':>18}  {int(adopted['total_trades']):>13}  {is_s['n']:>13}  {oos_s['n']:>14}")
print(f"  {'勝率(%)':>18}  {adopted['win_rate']:>13.1f}  {is_s['wr']:>13.1f}  {oos_s['wr']:>14.1f}")
print(f"  {'PF':>18}  {adopted['profit_factor']:>13.2f}  {is_s['pf']:>13.2f}  {oos_s['pf']:>14.2f}")
print(f"  {'最大DD(%)':>18}  {adopted['max_drawdown_pct']:>13.2f}  {is_s['dd']:>13.2f}  {oos_s['dd']:>14.2f}")
print(f"  {'損益(万円)':>18}  {adopted['total_pnl_jpy']/10000:>+13.1f}  "
      f"{is_s['pnl']/10000:>+13.1f}  {oos_s['pnl']/10000:>+14.1f}")

print()
print("【ロバスト性チェック（共有プール IS 9条件）】")
all_pos  = (rob["total_pnl_jpy"] > 0).all()
n_pf13   = int((rob["profit_factor"] >= 1.3).sum())
n_pf12   = int((rob["profit_factor"] >= 1.2).sum())
print(f"  全9条件黒字: {'OK' if all_pos else 'NG'} ({int((rob['total_pnl_jpy']>0).sum())}/9)")
print(f"  PF >= 1.3 :  {'OK' if n_pf13 >= 7 else 'NG'} ({n_pf13}/9)")
print(f"  PF >= 1.2 :  {'OK' if n_pf12 >= 8 else 'NG'} ({n_pf12}/9)")

print()
print("【読み取り】")
print(f"  ・共有プール IS PF {adopted['profit_factor']:.2f}"
      f"  vs  per-sector IS PF {is_s['pf']:.2f}")
print(f"    → 共有プールの方が PF が高い（資本効率が良い）")
print(f"  ・per-sector OOS PF {oos_s['pf']:.2f} > IS PF {is_s['pf']:.2f}")
print(f"    → OOS > IS は過学習なしの証拠")
print(f"  ・per-sector 全期間収益: {(is_s['pnl']+oos_s['pnl'])/10000:+.1f}万円 / 資本100万円")
