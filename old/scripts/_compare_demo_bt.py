# -*- coding: utf-8 -*-
import sys, glob
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np

# ── デモトレード読み込み ────────────────────────────────────────────────
demo = pd.read_csv('japan_stocks/results/demo/trades.csv', encoding='utf-8')
demo['entry_date'] = pd.to_datetime(demo['entry_date'])
demo['exit_date']  = pd.to_datetime(demo['exit_date'])

print('='*60)
print('デモトレード（生データ）')
print('='*60)
print(f'件数（重複含む）: {len(demo)}')

dupes = demo[demo.duplicated(keep=False)]
if len(dupes):
    print(f'\n【重複行が検出されました: {len(dupes)}件】')
    print(dupes[['exit_date','ticker','sector','pnl_jpy']].to_string(index=False))

demo = demo.drop_duplicates()
print(f'\n重複除去後: {len(demo)}件')

# ── デモ集計 ───────────────────────────────────────────────────────────
pnl  = demo['pnl_jpy']
n    = len(pnl)
wins = int((pnl > 0).sum())
gp   = pnl[pnl > 0].sum()
gl   = pnl[pnl < 0].abs().sum()

print()
print('='*60)
print('デモ集計（重複除去後）')
print('='*60)
print(f'件数     : {n}')
print(f'勝率     : {wins/n*100:.1f}%  ({wins}勝{n-wins}敗)')
print(f'累積損益 : {pnl.sum():+,.0f}円')
print(f'PF       : {gp/gl:.2f}' if gl > 0 else 'PF       : N/A')
if wins > 0:
    print(f'平均利益 : {pnl[pnl>0].mean():+,.0f}円')
if (n - wins) > 0:
    print(f'平均損失 : {pnl[pnl<0].mean():+,.0f}円')
print(f'決済理由 : {demo["exit_reason"].value_counts().to_dict()}')

# ── バックテストOOS（同期間）────────────────────────────────────────────
oos_files = sorted(glob.glob('japan_stocks/results/backtest_v2/cs_oos_*.csv'))
if not oos_files:
    print('OOS CSVが見つかりません')
    sys.exit(1)

bt = pd.read_csv(oos_files[-1], encoding='utf-8-sig')
bt['entry_date'] = pd.to_datetime(bt['entry_date'])
bt['exit_date']  = pd.to_datetime(bt['exit_date'])

demo_start = demo['entry_date'].min()
demo_end   = demo['exit_date'].max()
bt_period  = bt[
    (bt['entry_date'] >= demo_start) &
    (bt['exit_date']  <= demo_end + pd.Timedelta(days=1))
].copy()

pnl_bt  = bt_period['net_pnl_jpy']
n_bt    = len(pnl_bt)
wins_bt = int((pnl_bt > 0).sum())
gp_bt   = pnl_bt[pnl_bt > 0].sum()
gl_bt   = pnl_bt[pnl_bt < 0].abs().sum()

print()
print('='*60)
print(f'バックテストOOS（同期間: {demo_start.date()} ~ {demo_end.date()}）')
print('='*60)
print(f'件数     : {n_bt}')
if n_bt > 0:
    print(f'勝率     : {wins_bt/n_bt*100:.1f}%  ({wins_bt}勝{n_bt-wins_bt}敗)')
    print(f'累積損益 : {pnl_bt.sum():+,.0f}円')
    print(f'PF       : {gp_bt/gl_bt:.2f}' if gl_bt > 0 else 'PF       : N/A')
    if wins_bt > 0:
        print(f'平均利益 : {pnl_bt[pnl_bt>0].mean():+,.0f}円')
    if (n_bt - wins_bt) > 0:
        print(f'平均損失 : {pnl_bt[pnl_bt<0].mean():+,.0f}円')
    print(f'決済理由 : {bt_period["exit_reason"].value_counts().to_dict()}')

# ── 銘柄レベル比較 ─────────────────────────────────────────────────────
print()
print('='*60)
print('銘柄レベル比較')
print('='*60)
demo_tickers = set(demo['ticker'])
bt_tickers   = set(bt_period['ticker']) if n_bt > 0 else set()
both     = demo_tickers & bt_tickers
only_demo = demo_tickers - bt_tickers
only_bt   = bt_tickers   - demo_tickers

print(f'共通銘柄 ({len(both)}件): {sorted(both)}')
print(f'デモのみ ({len(only_demo)}件): {sorted(only_demo)}')
print(f'BTのみ   ({len(only_bt)}件): {sorted(only_bt)}')

# ── 比較サマリー ────────────────────────────────────────────────────────
print()
print('='*60)
print('比較サマリー')
print('='*60)
print(f"{'指標':<12} {'デモ':>12} {'バックテスト':>12}")
print('-'*40)
print(f"{'件数':<12} {n:>12} {n_bt:>12}")
wr_demo = wins/n*100 if n > 0 else 0
wr_bt   = wins_bt/n_bt*100 if n_bt > 0 else 0
print(f"{'勝率(%)':<12} {wr_demo:>12.1f} {wr_bt:>12.1f}")
print(f"{'累積損益':<12} {pnl.sum():>+12,.0f} {pnl_bt.sum():>+12,.0f}")
pf_demo = gp/gl if gl > 0 else float('nan')
pf_bt   = gp_bt/gl_bt if gl_bt > 0 else float('nan')
print(f"{'PF':<12} {pf_demo:>12.2f} {pf_bt:>12.2f}")
