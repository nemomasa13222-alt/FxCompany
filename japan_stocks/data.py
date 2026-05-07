# -*- coding: utf-8 -*-
"""
データ取得モジュール
- yfinance でセクターETF・個別株の日足データを取得
- results/cache/ にParquet形式でキャッシュ（再取得を最小化）
"""

from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent / "results" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.replace('.', '_')}.parquet"


def fetch(ticker: str, start: str, end: str | None = None, use_cache: bool = True) -> pd.DataFrame:
    """
    日足OHLCV を取得。キャッシュがあれば差分取得。
    戻り値: DatetimeIndex, 列 = [Open, High, Low, Close, Volume]
    """
    cache = _cache_path(ticker)
    end_dt = end or datetime.today().strftime("%Y-%m-%d")

    if use_cache and cache.exists():
        cached = pd.read_parquet(cache)
        cached_first = cached.index[0].strftime("%Y-%m-%d")
        last = cached.index[-1].strftime("%Y-%m-%d")

        # 過去方向にキャッシュが足りない場合は遡って取得
        if cached_first > start:
            hist_end = (cached.index[0] - timedelta(days=1)).strftime("%Y-%m-%d")
            hist = _download(ticker, start, hist_end)
            if not hist.empty:
                cached = pd.concat([hist, cached])
                cached = cached[~cached.index.duplicated(keep="last")]
                cached.to_parquet(cache)

        if last >= end_dt:
            return cached.loc[start:end_dt]
        # 未来方向の差分取得
        new_start = (cached.index[-1] + timedelta(days=1)).strftime("%Y-%m-%d")
        fresh = _download(ticker, new_start, end_dt)
        if not fresh.empty:
            combined = pd.concat([cached, fresh])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined.to_parquet(cache)
            return combined.loc[start:end_dt]
        return cached.loc[start:end_dt]

    df = _download(ticker, start, end_dt)
    if not df.empty:
        df.to_parquet(cache)
    return df


def _download(ticker: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return df
    # MultiIndex列をフラットに
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def fetch_sector_and_stocks(sector: dict, start: str, end: str | None = None) -> dict:
    """
    セクターETFと全銘柄の終値を一括取得。
    戻り値: {"etf": Series, "stocks": {ticker: Series}}
    """
    etf_df   = fetch(sector["etf"],   start, end)
    etf_close = etf_df["Close"].rename("etf")

    stocks = {}
    for ticker in sector["stocks"]:
        df = fetch(ticker, start, end)
        if len(df) >= 60:  # データが少ない銘柄はスキップ
            stocks[ticker] = df["Close"]

    return {"etf": etf_close, "stocks": stocks}
