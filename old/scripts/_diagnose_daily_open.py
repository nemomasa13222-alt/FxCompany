# -*- coding: utf-8 -*-
import sys; sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import warnings; warnings.filterwarnings('ignore')
from fx_market_classifier.data_fetcher import fetch_ohlcv
from fx_market_classifier.daily_open_engine import DailyOpenEngine, DailyOpenConfig

data = fetch_ohlcv(lookback_days=55)

print('=== 0コスト検証 ===')
for entry, exit_t in [(0.1, 0.05), (0.2, 0.05), (0.3, 0.10)]:
    cfg = DailyOpenConfig(entry_threshold=entry, exit_threshold=exit_t,
                          spread_cost_pct=0.0, stop_loss_pct=1.5, time_limit_bars=60)
    eng = DailyOpenEngine(data, cfg)
    eng.run()
    m = eng.metrics()
    if m:
        pf_s = f"{m['pf']:.3f}" if m['pf'] < 99 else "inf"
        print(f"  entry={entry}% exit={exit_t}%  T={m['trades']}  "
              f"win={m['win_rate']*100:.1f}%  PF={pf_s}  total={m['total_pnl']:+.2f}%")

print()
print('=== エグジット理由（entry=0.1%, exit=0.05%, コストあり）===')
cfg = DailyOpenConfig(entry_threshold=0.1, exit_threshold=0.05, stop_loss_pct=1.5)
eng = DailyOpenEngine(data, cfg)
df  = eng.run()
if not df.empty:
    print(df['exit_reason'].value_counts().to_string())
    print()
    print('Case別:')
    print(df['case_type'].value_counts().to_string())
    print()
    print('方向別:')
    print(df['direction'].value_counts().to_string())
    print()
    print('ペア別 (capital_pnl合計):')
    pair_stats = df.groupby('pair').agg(
        T=('capital_pnl', 'count'),
        win=('capital_pnl', lambda x: (x > 0).mean()),
        total=('capital_pnl', 'sum')
    ).sort_values('total', ascending=False)
    print(pair_stats.round(3).to_string())
    print()
    print('stop vs spread_reduced の勝率比較:')
    for reason in ['stop', 'spread_reduced', 'time_limit', 'day_end']:
        sub = df[df['exit_reason'] == reason]
        if not sub.empty:
            wr = (sub['capital_pnl'] > 0).mean()
            avg = sub['capital_pnl'].mean()
            print(f"  {reason:<16} N={len(sub):4d}  win={wr*100:.1f}%  avg={avg:+.4f}%")
