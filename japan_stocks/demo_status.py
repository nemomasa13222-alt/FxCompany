# -*- coding: utf-8 -*-
"""
デモ環境 リアルタイム損益確認
いつでも実行可能。保有ポジションの現在値を取得して含み損益を表示する。

実行: python japan_stocks/demo_status.py
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime
import json
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import data as dt

DEMO_DIR   = Path(__file__).parent / "results" / "demo"
STATE_FILE = DEMO_DIR / "state.json"
PNL_FILE   = DEMO_DIR / "pnl_history.csv"
TRADES_FILE= DEMO_DIR / "trades.csv"

INITIAL_CAPITAL = 1_000_000
STOP_DIST_PCT   = 1.5


def fetch_latest_price(ticker: str) -> float | None:
    try:
        df = dt.fetch(ticker, start="2026-01-01", use_cache=False)
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None


def main():
    if not STATE_FILE.exists():
        print("state.json が見つかりません。demo_signal.py を先に実行してください。")
        return

    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*62}")
    print(f"  デモ運用 リアルタイム損益  {now}")
    print(f"  最終自動更新: {state.get('last_run', '未実行')}")
    print(f"{'='*62}")

    capital    = state["capital"]
    unrealized = 0.0
    positions  = state.get("positions", [])

    if positions:
        print(f"\n  ── 保有ポジション ({len(positions)}件) ─────────────────────────")
        print(f"  {'銘柄':<10} {'業種':<14} {'取得値':>8} {'現在値':>8} {'損益':>10} {'%':>7} {'stop':>8} {'日数':>4}")
        print(f"  {'-'*74}")

        for pos in positions:
            ticker     = pos["ticker"]
            entry      = pos["entry_price"]
            shares     = pos["shares"]
            stop       = pos["stop_price"]
            days       = pos.get("days_held", 0)
            sector_short = pos["sector"][:8]

            # 最新値を取得（キャッシュ優先、なければライブ）
            current = fetch_latest_price(ticker)
            if current is None:
                current = entry
                price_str = f"{'--':>8}"
            else:
                price_str = f"{current:>8,.0f}"

            pnl_pos  = (current - entry) * shares
            pnl_pct  = (current / entry - 1) * 100 if entry > 0 else 0
            unrealized += pnl_pos
            sign = "+" if pnl_pos >= 0 else ""

            pnl_color_start = ""
            pnl_color_end   = ""

            print(f"  {ticker:<10} {sector_short:<14} {entry:>8,.0f} "
                  f"{price_str} {sign}{pnl_pos:>9,.0f} {pnl_pct:>+6.1f}% "
                  f"{stop:>8,.0f} {days:>3}日")
        print()

    pending = state.get("pending", [])
    if pending:
        print(f"  ── 明日 寄り候補 ({len(pending)}件) ───────────────────────────")
        for p in pending:
            print(f"  {p['ticker']:<10} ({p['sector']:<12})  "
                  f"引け{p['signal_close']:,.0f}円  gap={p['gap_pct']:.1f}%  corr={p['corr']:.2f}")
        print()

    total_equity  = capital + unrealized
    realized_pnl  = state.get("total_realized_pnl", 0)
    peak          = state.get("peak_capital", INITIAL_CAPITAL)
    dd_pct        = max(0.0, (peak - total_equity) / peak * 100) if peak > 0 else 0.0
    ret_pct       = (total_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    trade_count   = state.get("trade_count", 0)

    sign_r = "+" if ret_pct >= 0 else ""
    sign_u = "+" if unrealized >= 0 else ""
    sign_p = "+" if realized_pnl >= 0 else ""

    print(f"  ── 損益サマリー ──────────────────────────────────────────")
    print(f"  資産評価額   : {total_equity:>12,.0f}円  ({sign_r}{ret_pct:.2f}% 初期比)")
    print(f"  実現損益     : {sign_p}{realized_pnl:>11,.0f}円")
    print(f"  含み損益     : {sign_u}{unrealized:>11,.0f}円")
    print(f"  最大DD       : {dd_pct:.1f}%")
    print(f"  累計トレード : {trade_count}件")

    # 日次推移（最新5日）
    if PNL_FILE.exists():
        pnl_df = pd.read_csv(PNL_FILE, encoding="utf-8-sig")
        if len(pnl_df) > 0:
            recent = pnl_df.tail(5)
            print(f"\n  ── 直近推移（最新{len(recent)}日） ──────────────────────────")
            print(f"  {'日付':<12} {'評価額':>12} {'リターン':>8} {'DD':>6} {'保有':>4} {'決済':>4}")
            for _, row in recent.iterrows():
                sign_row = "+" if row["return_pct"] >= 0 else ""
                print(f"  {row['date']:<12} {row['total_equity']:>12,.0f} "
                      f"{sign_row}{row['return_pct']:>6.2f}% {row['max_dd_pct']:>5.1f}% "
                      f"{int(row['open_positions']):>4} {int(row['trades_today']):>4}")

    # 決済済みトレード（最新5件）
    if TRADES_FILE.exists():
        trades_df = pd.read_csv(TRADES_FILE, encoding="utf-8-sig")
        if len(trades_df) > 0:
            recent_t = trades_df.tail(5)
            print(f"\n  ── 直近決済トレード（最新{len(recent_t)}件） ──────────────────")
            print(f"  {'銘柄':<10} {'決済日':<12} {'理由':<6} {'損益':>10} {'%':>7} {'日数':>4}")
            for _, row in recent_t.iterrows():
                sign_t = "+" if row["pnl_jpy"] >= 0 else ""
                print(f"  {row['ticker']:<10} {row['exit_date']:<12} "
                      f"{row['exit_reason']:<6} {sign_t}{row['pnl_jpy']:>9,.0f} "
                      f"{row['return_pct']:>+6.2f}% {int(row['days_held']):>3}日")

    print(f"\n{'='*62}\n")


if __name__ == "__main__":
    main()
