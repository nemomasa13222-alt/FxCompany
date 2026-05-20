"""
Data fetcher — yfinance 5-min OHLCV for FX pairs.

Limitations:
  - yfinance 5-min data: ~55 days lookback maximum
  - For longer IS/OOS studies, replace with a paid data source (e.g. Dukascopy, FXCM)
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from .config import PAIRS

# yfinance ticker suffix for forex
_TICKER = {pair: f"{pair}=X" for pair in PAIRS}


def fetch_ohlcv(
    pairs: list[str] | None = None,
    interval: str = "5m",
    lookback_days: int = 50,
) -> dict[str, pd.DataFrame]:
    """
    Returns {pair: OHLCV DataFrame} with columns [Open, High, Low, Close, Volume].
    Pairs with no data are silently omitted.
    """
    if pairs is None:
        pairs = PAIRS

    end = datetime.utcnow()
    start = end - timedelta(days=lookback_days)

    result: dict[str, pd.DataFrame] = {}
    for pair in pairs:
        ticker = _TICKER.get(pair, f"{pair}=X")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(ticker, start=start, end=end, interval=interval, progress=False)

        if df.empty:
            print(f"[warn] No data returned for {pair}")
            continue

        # yfinance ≥0.2 returns MultiIndex columns when auto_adjust=True
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df[["Open", "High", "Low", "Close"]].dropna()
        df.index = pd.to_datetime(df.index, utc=True)
        result[pair] = df

    print(f"Loaded {len(result)}/{len(pairs)} pairs  "
          f"({result[next(iter(result))].index[0]} → {result[next(iter(result))].index[-1]})"
          if result else "No data loaded")
    return result


def load_csv(path: str, pair: str) -> dict[str, pd.DataFrame]:
    """
    Load OHLCV from a local CSV (fallback for offline / longer history).
    Expects columns: datetime, Open, High, Low, Close  (or similar).
    """
    df = pd.read_csv(path, parse_dates=[0], index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.capitalize() for c in df.columns]
    required = {"Open", "High", "Low", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    return {pair: df[list(required)].dropna()}
