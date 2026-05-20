"""
Feature calculations: log returns, currency strength, ACF, BB, ATR.
All functions are stateless and return pd.Series / pd.DataFrame.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ACF_WINDOW, ATR_WINDOW, BB_WINDOW, CURRENCIES, PAIR_CURRENCIES


# ── Log returns ──────────────────────────────────────────────────────────────

def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


# ── Currency strength ─────────────────────────────────────────────────────────

def currency_strength(
    returns_dict: dict[str, pd.Series],
    pair_currencies: dict[str, tuple[str, str]] | None = None,
    currencies: list[str] | None = None,
) -> pd.DataFrame:
    """
    Strength of each currency = simple average of its signed contributions.

    For pair USDJPY: USD gets +ret, JPY gets −ret (base=+1, quote=−1).
    Strength is expressed in log-return units (dimensionless, not %).

    Returns DataFrame with one column per currency, index = price timestamps.
    """
    if pair_currencies is None:
        pair_currencies = PAIR_CURRENCIES
    if currencies is None:
        currencies = CURRENCIES

    # Align all return series to a common index
    common = pd.DataFrame({p: s for p, s in returns_dict.items()})

    contrib: dict[str, list[pd.Series]] = {c: [] for c in currencies}
    for pair, (base, quote) in pair_currencies.items():
        if pair not in common.columns:
            continue
        ret = common[pair]
        contrib[base].append(ret)
        contrib[quote].append(-ret)

    strength: dict[str, pd.Series] = {}
    for ccy, series_list in contrib.items():
        if not series_list:
            continue
        strength[ccy] = sum(series_list) / len(series_list)

    return pd.DataFrame(strength)


# ── ACF (lag=1) ───────────────────────────────────────────────────────────────

def acf_lag1(returns: pd.Series, window: int = ACF_WINDOW) -> pd.Series:
    """
    Rolling autocorrelation at lag 1 over `window` bars.
    Equivalent to: corr(r_t, r_{t-1}) over the last `window` observations.
    """
    lagged = returns.shift(1)
    return returns.rolling(window).corr(lagged).rename("acf_lag1")


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def bollinger_bands(
    close: pd.Series,
    window: int = BB_WINDOW,
    sigma: float = 2.0,
) -> pd.DataFrame:
    mid = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=1)
    return pd.DataFrame(
        {"upper": mid + sigma * std, "mid": mid, "lower": mid - sigma * std},
        index=close.index,
    )


# ── ATR ───────────────────────────────────────────────────────────────────────

def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = ATR_WINDOW,
) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=window, adjust=False).mean().rename("atr")


# ── Convenience: compute all features for one pair ───────────────────────────

def pair_features(
    df: pd.DataFrame,
    returns_dict: dict[str, pd.Series],
    pair: str,
    acf_window: int = ACF_WINDOW,
    bb_window: int = BB_WINDOW,
    bb_sigma_trend: float = 1.0,
    bb_sigma_rev: float = 3.0,
    atr_window: int = ATR_WINDOW,
) -> dict:
    ret = returns_dict[pair]
    strength = currency_strength(returns_dict)
    base, quote = PAIR_CURRENCIES[pair]
    strength_diff = strength[base] - strength[quote] if (base in strength and quote in strength) else pd.Series(np.nan, index=ret.index)

    return {
        "returns": ret,
        "acf": acf_lag1(ret, acf_window),
        "strength_diff": strength_diff,
        "bb_trend": bollinger_bands(df["Close"], bb_window, bb_sigma_trend),
        "bb_rev": bollinger_bands(df["Close"], bb_window, bb_sigma_rev),
        "atr": atr(df["High"], df["Low"], df["Close"], atr_window),
    }
