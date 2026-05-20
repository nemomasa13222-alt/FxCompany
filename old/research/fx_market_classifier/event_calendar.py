"""
Economic Calendar — ForexFactory public JSON API wrapper.

API: https://nfs.faireconomy.media/ff_calendar_thisweek.json
Response fields: title, country (currency code), date (ISO8601), impact

All functions are safe to call even when the network is unavailable;
they return empty DataFrames rather than raising exceptions.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import requests

from .config import PAIR_CURRENCIES

_FF_URL   = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_TIMEOUT  = 10   # seconds
_TTL      = 3600 # cache seconds (1 hour)

# ── Module-level cache (works outside Streamlit too) ─────────────────────────
_cache_time: float   = 0.0
_cache_df:   Optional[pd.DataFrame] = None


def _parse_event_time(date_str: str) -> Optional[datetime]:
    """Parse ISO8601 date string to UTC-aware datetime. Returns None on failure."""
    try:
        from dateutil import parser as _dp
        return _dp.parse(date_str).astimezone(timezone.utc)
    except Exception:
        return None


def fetch_calendar() -> pd.DataFrame:
    """
    Fetch this week's economic events from ForexFactory.
    Results are cached for 1 hour at module level.

    Returns DataFrame with columns:
        title       : str
        country     : str  (currency code, e.g. "USD", "JPY")
        event_time  : datetime  (UTC-aware)
        impact      : str  ("High" / "Medium" / "Low" / "Holiday")

    Returns empty DataFrame on any network/parse error.
    """
    global _cache_time, _cache_df

    now = time.monotonic()
    if _cache_df is not None and (now - _cache_time) < _TTL:
        return _cache_df

    try:
        resp = requests.get(_FF_URL, timeout=_TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        # Return stale cache if available, else empty DF
        return _cache_df if _cache_df is not None else pd.DataFrame()

    rows = []
    for item in data:
        et = _parse_event_time(item.get("date", ""))
        if et is None:
            continue
        rows.append({
            "title":      item.get("title",   ""),
            "country":    item.get("country", "").upper(),
            "event_time": et,
            "impact":     item.get("impact",  ""),
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["title", "country", "event_time", "impact"]
    )

    _cache_time = now
    _cache_df   = df
    return df


def get_today_events(
    impact:  list[str]              = None,
    df:      Optional[pd.DataFrame] = None,
    days_ahead: int                 = 1,
) -> pd.DataFrame:
    """
    Return High/Medium events for today and the next `days_ahead` days (UTC).

    Args:
        impact:     Impact filter. Defaults to ["High", "Medium"].
        df:         Pre-fetched calendar DataFrame. Fetched automatically if None.
        days_ahead: How many days after today to include (default 1 = today + tomorrow).

    Returns DataFrame sorted by event_time ascending. Empty DF if no events.
    """
    if impact is None:
        impact = ["High", "Medium"]

    if df is None:
        df = fetch_calendar()

    if df.empty:
        return df

    now_utc   = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff    = now_utc + timedelta(days=days_ahead + 1)

    mask = (
        df["event_time"] >= now_utc
    ) & (
        df["event_time"] <  cutoff
    ) & (
        df["impact"].isin(impact)
    )

    return df[mask].sort_values("event_time").reset_index(drop=True)


def is_event_near(
    pair:    str,
    events:  pd.DataFrame,
    minutes: int = 30,
) -> bool:
    """
    Return True if there is a High/Medium event for either currency in `pair`
    within the next `minutes` minutes.

    Args:
        pair:    Currency pair string, e.g. "USDJPY".
        events:  DataFrame from get_today_events().
        minutes: Lookahead window in minutes.

    Returns False on any error (never raises).
    """
    try:
        if events.empty:
            return False

        base, quote = PAIR_CURRENCIES.get(pair, (None, None))
        if base is None:
            return False

        now_utc    = datetime.now(timezone.utc)
        window_end = now_utc + timedelta(minutes=minutes)

        mask = (
            events["country"].isin([base, quote])
        ) & (
            events["event_time"] >= now_utc
        ) & (
            events["event_time"] <= window_end
        )

        return bool(mask.any())
    except Exception:
        return False


def format_event_time(event_time: datetime) -> str:
    """Format event_time to local-friendly HH:MM string (UTC)."""
    return event_time.strftime("%m/%d %H:%M UTC")
