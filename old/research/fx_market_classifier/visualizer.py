"""
Visualization — market state heatmap, currency strength, pair detail chart.
All functions return matplotlib Figure objects (caller decides show/save).
"""
from __future__ import annotations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .classifier import MarketState

# State → numeric value for imshow
_STATE_NUM = {MarketState.TREND: 1, MarketState.MEAN_REVERSION: -1, MarketState.NO_TRADE: 0}
_STATE_COLOR = {
    MarketState.TREND: "#2196F3",
    MarketState.MEAN_REVERSION: "#FF9800",
    MarketState.NO_TRADE: "#BDBDBD",
}


def _xticks(index: pd.DatetimeIndex, n: int = 8) -> tuple[list[int], list[str]]:
    step = max(1, len(index) // n)
    pos = list(range(0, len(index), step))
    labels = [str(index[p])[:16] for p in pos]
    return pos, labels


# ── Heatmap: all pairs × time ──────────────────────────────────────────────

def plot_heatmap(
    states: pd.DataFrame,
    last_n: int = 288,   # 288 bars ≈ 1 day of 5-min
    figsize: tuple = (18, 6),
) -> plt.Figure:
    """
    Rows = currency pairs, columns = time.
    Blue=TREND, Orange=MEAN_REVERSION, Gray=NO_TRADE.
    """
    recent = states.tail(last_n)
    numeric = recent.apply(lambda col: col.map(_STATE_NUM)).fillna(0)

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(
        numeric.T.values,
        aspect="auto",
        cmap=plt.cm.RdYlBu,
        vmin=-1,
        vmax=1,
        interpolation="none",
    )

    ax.set_yticks(range(len(recent.columns)))
    ax.set_yticklabels(recent.columns, fontsize=9)

    pos, labels = _xticks(recent.index)
    ax.set_xticks(pos)
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=7)

    legend_patches = [
        mpatches.Patch(color=_STATE_COLOR[s], label=s.value)
        for s in [MarketState.TREND, MarketState.MEAN_REVERSION, MarketState.NO_TRADE]
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8)
    ax.set_title(f"Market State Heatmap — last {last_n} bars (5-min)", fontsize=11)
    fig.tight_layout()
    return fig


# ── Currency strength over time ────────────────────────────────────────────

def plot_strength(
    strength: pd.DataFrame,
    last_n: int = 288,
    figsize: tuple = (14, 4),
) -> plt.Figure:
    recent = strength.tail(last_n)
    fig, ax = plt.subplots(figsize=figsize)
    for col in recent.columns:
        ax.plot(range(len(recent)), recent[col].values, label=col, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.5, linestyle="--")
    ax.legend(fontsize=8, ncol=4)
    pos, labels = _xticks(recent.index)
    ax.set_xticks(pos)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)
    ax.set_title(f"Currency Strength (log-return avg, last {last_n} bars)", fontsize=11)
    ax.set_ylabel("Strength (log units)")
    fig.tight_layout()
    return fig


# ── Pair detail: price + BB, ACF, strength diff ────────────────────────────

def plot_pair_detail(
    pair: str,
    price_df: pd.DataFrame,
    acf_series: pd.Series,
    strength_diff: pd.Series,
    state_series: pd.Series,
    bb1: pd.DataFrame,
    bb3: pd.DataFrame,
    last_n: int = 288,
    figsize: tuple = (16, 10),
) -> plt.Figure:
    """Three-panel chart for one pair."""
    sl = slice(-last_n, None)
    close = price_df["Close"].iloc[sl]
    acf = acf_series.iloc[sl]
    sd = strength_diff.iloc[sl]
    states = state_series.iloc[sl]
    b1 = bb1.iloc[sl]
    b3 = bb3.iloc[sl]
    xs = range(len(close))

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=figsize, sharex=False)

    # ── Panel 1: Price + BB ────────────────────────────────────────────────
    ax1.plot(xs, close.values, color="black", linewidth=0.8, label="Close")
    ax1.plot(xs, b1["upper"].values, color="#2196F3", linewidth=0.6, linestyle="--", label="BB 1σ")
    ax1.plot(xs, b1["lower"].values, color="#2196F3", linewidth=0.6, linestyle="--")
    ax1.plot(xs, b3["upper"].values, color="#FF9800", linewidth=0.6, linestyle=":", label="BB 3σ")
    ax1.plot(xs, b3["lower"].values, color="#FF9800", linewidth=0.6, linestyle=":")
    ax1.plot(xs, b1["mid"].values, color="#9E9E9E", linewidth=0.5, linestyle="-")

    # Background shading by state
    import math as _math
    for i, state in enumerate(states.values):
        try:
            ms    = MarketState(state) if (state and not (isinstance(state, float) and _math.isnan(state))) else MarketState.NO_TRADE
            color = _STATE_COLOR.get(ms, "#BDBDBD")
        except (ValueError, TypeError):
            color = "#BDBDBD"
        ax1.axvspan(i - 0.5, i + 0.5, alpha=0.12, color=color, linewidth=0)

    ax1.legend(fontsize=7, loc="upper left")
    ax1.set_title(f"{pair} — Price with Bollinger Bands (1σ blue, 3σ orange)", fontsize=10)
    ax1.set_ylabel("Price")

    # ── Panel 2: ACF ──────────────────────────────────────────────────────
    ax2.plot(xs, acf.values, color="#673AB7", linewidth=0.9)
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.axhline(0.05, color="#2196F3", linewidth=0.6, linestyle="--", label="trend min (0.05)")
    ax2.axhline(-0.05, color="#FF9800", linewidth=0.6, linestyle="--", label="rev max (−0.05)")
    ax2.fill_between(xs, acf.values, 0,
                     where=np.array(acf.values, dtype=float) > 0,
                     alpha=0.15, color="#2196F3")
    ax2.fill_between(xs, acf.values, 0,
                     where=np.array(acf.values, dtype=float) < 0,
                     alpha=0.15, color="#FF9800")
    ax2.legend(fontsize=7)
    ax2.set_title("ACF lag=1 (rolling 100 bars)", fontsize=10)
    ax2.set_ylabel("ACF")

    # ── Panel 3: Strength diff ────────────────────────────────────────────
    base, quote = pair[:3], pair[3:]
    ax3.plot(xs, sd.values, color="#E91E63", linewidth=0.9)
    ax3.axhline(0, color="black", linewidth=0.5)
    ax3.axhline(0.0008, color="#2196F3", linewidth=0.6, linestyle="--", label="threshold ±0.0008")
    ax3.axhline(-0.0008, color="#2196F3", linewidth=0.6, linestyle="--")
    ax3.fill_between(xs, sd.values, 0, alpha=0.15, color="#E91E63")
    ax3.legend(fontsize=7)
    ax3.set_title(f"Strength Diff: {base} − {quote}", fontsize=10)
    ax3.set_ylabel("Log-return diff")

    # Shared x-ticks on bottom panel only
    pos, labels = _xticks(close.index)
    ax3.set_xticks(pos)
    ax3.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)

    fig.suptitle(f"Pair Detail: {pair}", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return fig


# ── State ratio bar chart ──────────────────────────────────────────────────

def plot_state_ratio(
    states: pd.DataFrame,
    figsize: tuple = (12, 5),
) -> plt.Figure:
    """Stacked bar: % of time in each state per pair."""
    counts = states.apply(lambda col: col.value_counts(normalize=True) * 100)
    counts = counts.T.fillna(0)
    for s in [MarketState.TREND.value, MarketState.MEAN_REVERSION.value, MarketState.NO_TRADE.value]:
        if s not in counts:
            counts[s] = 0.0

    fig, ax = plt.subplots(figsize=figsize)
    bottom = np.zeros(len(counts))
    for state, color in [
        (MarketState.TREND.value, "#2196F3"),
        (MarketState.MEAN_REVERSION.value, "#FF9800"),
        (MarketState.NO_TRADE.value, "#BDBDBD"),
    ]:
        vals = counts[state].values
        ax.bar(counts.index, vals, bottom=bottom, color=color, label=state)
        bottom += vals

    ax.set_ylabel("% of bars")
    ax.set_title("State Distribution per Pair (full history)", fontsize=11)
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig
