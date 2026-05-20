"""
Market State Classifier — entry point.

Usage:
  python -m fx_market_classifier.main                   # fetch + classify + show charts
  python -m fx_market_classifier.main --backtest        # also run backtest
  python -m fx_market_classifier.main --pair USDJPY     # detail chart for one pair
"""
from __future__ import annotations

import argparse
import sys

import matplotlib.pyplot as plt

from .backtest import BacktestConfig, BacktestEngine
from .classifier import MarketClassifier, MarketState
from .data_fetcher import fetch_ohlcv
from .visualizer import (
    plot_heatmap,
    plot_pair_detail,
    plot_state_ratio,
    plot_strength,
)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="FX Market State Classifier")
    parser.add_argument("--backtest", action="store_true", help="Run backtest after classification")
    parser.add_argument("--pair", default=None, help="Show detail chart for one pair (e.g. USDJPY)")
    parser.add_argument("--days", type=int, default=50, help="Lookback days for data fetch")
    parser.add_argument("--save", action="store_true", help="Save charts as PNG instead of showing")
    args = parser.parse_args(argv)

    # ── 1. Data ───────────────────────────────────────────────────────────────
    print("Fetching 5-min FX data...")
    price_data = fetch_ohlcv(lookback_days=args.days)
    if not price_data:
        print("No data available. Check your internet connection.")
        sys.exit(1)

    # ── 2. Classify ───────────────────────────────────────────────────────────
    print("Computing features and classifying...")
    clf = MarketClassifier(price_data)

    print("\n-- Current Market State --")
    current = clf.current_state()
    for pair, state in current.items():
        marker = "[T]" if state == MarketState.TREND else "[M]" if state == MarketState.MEAN_REVERSION else "[-]"
        print(f"  {marker}  {pair:<10} {state.value}")

    print("\n-- State Counts (full history) --")
    print(clf.state_counts().to_string())

    # ── 3. Visualize ─────────────────────────────────────────────────────────
    figures = []

    fig_heat = plot_heatmap(clf.states)
    figures.append(("market_state_heatmap", fig_heat))

    fig_strength = plot_strength(clf.strength)
    figures.append(("currency_strength", fig_strength))

    fig_ratio = plot_state_ratio(clf.states)
    figures.append(("state_ratio", fig_ratio))

    if args.pair:
        pair = args.pair.upper()
        if pair in clf.states.columns:
            from .config import PAIR_CURRENCIES
            base, quote = PAIR_CURRENCIES[pair]
            sd = clf.strength_diff(pair)
            fig_detail = plot_pair_detail(
                pair=pair,
                price_df=price_data[pair],
                acf_series=clf.acf[pair],
                strength_diff=sd,
                state_series=clf.states[pair],
                bb1=clf.bb1[pair],
                bb3=clf.bb3[pair],
            )
            figures.append((f"detail_{pair}", fig_detail))
        else:
            print(f"[warn] Pair {pair} not in data. Skipping detail chart.")

    if args.save:
        for name, fig in figures:
            path = f"{name}.png"
            fig.savefig(path, dpi=120, bbox_inches="tight")
            print(f"Saved: {path}")
    else:
        plt.show()

    # ── 4. Backtest (optional) ────────────────────────────────────────────────
    if args.backtest:
        print("\n-- Backtest --")
        engine = BacktestEngine(clf, BacktestConfig())
        trades_df = engine.run()

        if trades_df.empty:
            print("  No trades generated.")
            return

        m = engine.metrics()
        print(f"  Trades         : {m['total_trades']}")
        print(f"  Win rate       : {m['win_rate']:.1%}")
        print(f"  Avg PnL        : {m['avg_pnl_pct']:.4f}%")
        print(f"  Total PnL      : {m['total_pnl_pct']:.4f}%")
        print(f"  Profit factor  : {m['profit_factor']:.2f}")
        print(f"  Max DD         : {m['max_dd_pct']:.4f}%")
        print(f"  Partial exits  : {m.get('partial_exit_hits', 0)} trades hit 3sigma")

        print("\n-- By Strategy --")
        print(engine.metrics_by_strategy().to_string())

        trades_df.to_csv("backtest_trades.csv", index=False)
        print("\nSaved: backtest_trades.csv")


if __name__ == "__main__":
    main()
