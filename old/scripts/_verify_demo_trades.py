# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
import numpy as np
import yfinance as yf

RISK_PCT      = 0.5
STOP_DIST_PCT = 1.5
ROUND_TRIP    = 0.002
INITIAL_CAP   = 1_000_000

trades = pd.read_csv('japan_stocks/results/demo/trades.csv')

# 実際の市場データ取得
tickers = trades['ticker'].unique().tolist()
hist = {}
for t in tickers:
    try:
        df = yf.download(t, start='2026-05-06', end='2026-05-16', interval='1d', progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        hist[t] = df
    except Exception as e:
        print(f"  {t} 取得失敗: {e}")

print('=' * 100)
print(f"{'#':<3} {'銘柄':<10} {'E日':<6} {'記録EP':<8} {'実Open':<8} {'記録XP':<8} {'実Close':<8} {'株数':>5} {'計算株数':>6} {'記録損益':>9} {'再計算PnL':>9} {'差分':>7} {'判定'}")
print('-' * 100)

capital = INITIAL_CAP
issues = []
total_recalc = 0

for i, row in trades.iterrows():
    t      = row['ticker']
    edate  = pd.Timestamp(row['entry_date'])
    xdate  = pd.Timestamp(row['exit_date'])
    ep     = row['entry_price']
    xp     = row['exit_price']
    sh     = int(row['shares'])
    reason = row['exit_reason']
    rec_pnl = int(row['pnl_jpy'])

    # 実際のopen/close取得
    actual_open = actual_close = np.nan
    if t in hist:
        df = hist[t]
        erow = df[df.index.normalize() == edate]
        xrow = df[df.index.normalize() == xdate]
        if not erow.empty:
            actual_open = float(erow['Open'].iloc[0])
        if not xrow.empty:
            actual_close = float(xrow['Close'].iloc[0])

    # 株数再計算（エントリー時の資本）
    risk_amt    = capital * RISK_PCT / 100
    stop_jpy    = ep * STOP_DIST_PCT / 100
    calc_shares = int(risk_amt / stop_jpy) if stop_jpy > 0 else 0

    # 損益再計算（記録されている entry/exit/shares で再計算）
    gross    = (xp - ep) * sh
    cost     = ep * sh * ROUND_TRIP
    calc_pnl = round(gross - cost)
    diff     = calc_pnl - rec_pnl

    # 判定フラグ
    flags = []
    if not np.isnan(actual_open) and abs(ep - actual_open) > 5:
        flags.append(f"EP誤差:{actual_open:.0f}")
    if abs(calc_shares - sh) > 1:
        flags.append(f"株数:{sh}→{calc_shares}")
    if abs(diff) > 5:
        flags.append(f"損益差{diff:+.0f}円")

    flag_str = " / ".join(flags) if flags else "✓"

    print(f"{i+1:<3} {t:<10} {str(edate.date())[-5:]:<6} "
          f"{ep:<8.1f} {actual_open:<8.1f} {xp:<8.1f} {actual_close:<8.1f} "
          f"{sh:>5} {calc_shares:>6} {rec_pnl:>9,} {calc_pnl:>9,} {diff:>+7,}  {flag_str}")

    if flags:
        issues.append((t, flags))

    total_recalc += calc_pnl
    capital += calc_pnl

print('=' * 100)
print(f"\n【再計算サマリー】")
print(f"  累積損益（再計算）: {total_recalc:+,.0f}円")
print(f"  最終資本（再計算）: {capital:,.0f}円")
print(f"  初期資本:           {INITIAL_CAP:,.0f}円")
print(f"  収益率:             {total_recalc/INITIAL_CAP*100:+.2f}%")

print()
if issues:
    print("[要確認項目]")
    for t, f in issues:
        print(f"  {t}: {' / '.join(f)}")
else:
    print("[全トレード検証OK]")
