"""
Market state classifier.

States:
  TREND          — large strength diff AND ACF > 0  → follow momentum
  MEAN_REVERSION — small strength diff AND ACF < 0  → fade extremes
  NO_TRADE       — ambiguous; skip

classify_pair() is a pure function; MarketClassifier wraps it for a full dataset.
"""
from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

from .config import (
    ACF_REVERSION_MAX,
    ACF_TREND_MIN,
    ACF_WINDOW,
    BB_WINDOW,
    ATR_WINDOW,
    PAIR_CURRENCIES,
    STRENGTH_DIFF_THRESHOLD,
)
from .features import (
    acf_lag1,
    atr,
    bollinger_bands,
    currency_strength,
    log_returns,
)


class MarketState(str, Enum):
    TREND = "TREND"
    MEAN_REVERSION = "MEAN_REVERSION"
    NO_TRADE = "NO_TRADE"


# ── Single-bar classification ─────────────────────────────────────────────────

def classify_bar(strength_diff: float, acf: float) -> MarketState:
    """
    Classify one bar given scalar strength_diff and acf.

    Trend        : large diff AND ACF positive  → momentum continuing
    Mean Reversion: large diff AND ACF negative  → strong move reverting
    Chop         : small diff OR  ACF near zero  → no directional edge
    """
    if np.isnan(strength_diff) or np.isnan(acf):
        return MarketState.NO_TRADE

    large_diff = abs(strength_diff) >= STRENGTH_DIFF_THRESHOLD

    if large_diff and acf >= ACF_TREND_MIN:
        return MarketState.TREND
    if large_diff and acf <= ACF_REVERSION_MAX:   # 強弱差が大 + ACF負 → 平均回帰
        return MarketState.MEAN_REVERSION
    return MarketState.NO_TRADE   # 強弱差が小、またはACFが中立 → Chop


# ── Full dataset classifier ───────────────────────────────────────────────────

class MarketClassifier:
    """
    Computes features and classifies each bar for all pairs.

    Usage:
        clf = MarketClassifier(price_data)
        states_df  = clf.states          # DataFrame[pair → MarketState]
        current    = clf.current_state() # {pair: MarketState} for latest bar
    """

    def __init__(self, price_data: dict[str, pd.DataFrame]):
        self.price_data = price_data
        self._build()

    # ── Internal construction ─────────────────────────────────────────────────

    def _build(self):
        # Per-pair log returns
        self.returns: dict[str, pd.Series] = {
            pair: log_returns(df["Close"])
            for pair, df in self.price_data.items()
        }

        # Currency strength (DataFrame: index=time, col=currency)
        self.strength: pd.DataFrame = currency_strength(self.returns)

        # Per-pair ACF series
        self.acf: dict[str, pd.Series] = {
            pair: acf_lag1(ret, ACF_WINDOW)
            for pair, ret in self.returns.items()
        }

        # Per-pair BB (sigma=1 for trend, sigma=3 for reversion)
        self.bb1: dict[str, pd.DataFrame] = {
            pair: bollinger_bands(df["Close"], BB_WINDOW, 1.0)
            for pair, df in self.price_data.items()
        }
        self.bb3: dict[str, pd.DataFrame] = {
            pair: bollinger_bands(df["Close"], BB_WINDOW, 3.0)
            for pair, df in self.price_data.items()
        }

        # ATR
        self.atr_: dict[str, pd.Series] = {
            pair: atr(df["High"], df["Low"], df["Close"], ATR_WINDOW)
            for pair, df in self.price_data.items()
        }

        # Classification
        self.states: pd.DataFrame = self._classify_all()

    def _strength_diff(self, pair: str) -> pd.Series:
        base, quote = PAIR_CURRENCIES.get(pair, (None, None))
        if base is None or base not in self.strength or quote not in self.strength:
            idx = self.returns[pair].index
            return pd.Series(np.nan, index=idx, name=pair)
        return (self.strength[base] - self.strength[quote]).rename(pair)

    def _classify_all(self) -> pd.DataFrame:
        out = {}
        for pair in self.returns:
            sd = self._strength_diff(pair)
            ac = self.acf[pair]
            # Align on common index
            aligned = pd.DataFrame({"sd": sd, "ac": ac}).dropna(how="all")
            states = pd.Series(
                [classify_bar(row.sd, row.ac) for row in aligned.itertuples()],
                index=aligned.index,
                name=pair,
                dtype=object,
            )
            out[pair] = states
        return pd.DataFrame(out)

    # ── Public API ────────────────────────────────────────────────────────────

    def current_state(self) -> dict[str, MarketState]:
        """Returns the latest known classification for each pair (ffill for sparse indices)."""
        last = self.states.ffill().iloc[-1]
        return {pair: MarketState(v) for pair, v in last.items() if pd.notna(v)}

    @property
    def latest_strength(self) -> pd.Series:
        """Latest known currency strength for each currency (ffill for sparse indices)."""
        return self.strength.ffill().iloc[-1]

    def state_counts(self) -> pd.DataFrame:
        """Count of TREND / MEAN_REVERSION / NO_TRADE per pair over full history."""
        return self.states.apply(lambda col: col.value_counts()).T.fillna(0).astype(int)

    def strength_diff(self, pair: str) -> pd.Series:
        return self._strength_diff(pair)
