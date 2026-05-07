# -*- coding: utf-8 -*-
"""
合成セクター指数ビルダー

J-Quantsで取得した構成銘柄の日次リターンを等加重平均して
セクター指数（初日=100）を構築する。
ETFの代わりにこの指数を使うことで、実際の構成銘柄の動きを反映した
正確なセクター基準が得られる。
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

CACHE_DIR = Path(__file__).parent / "results" / "jquants_cache" / "sector_indices"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIN_STOCKS    = 5    # 指数構築に必要な最低銘柄数
MIN_DATA_DAYS = 120  # 銘柄採用の最低データ日数


def build(
    sector33_code: str,
    start_date: str,
    end_date: str | None = None,
    max_stocks: int = 50,
    use_cache: bool = True,
) -> pd.Series:
    """
    等加重合成セクター指数を構築して返す。

    Returns:
        pd.Series: DatetimeIndex。初日=100に正規化。
                   データ不足時は空のSeriesを返す。
    """
    end        = end_date or datetime.today().strftime("%Y-%m-%d")
    safe_start = start_date.replace("-", "")
    safe_end   = end.replace("-", "")
    cache_path = CACHE_DIR / f"idx_{sector33_code}_{safe_start}_{safe_end}.parquet"

    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        if not cached.empty:
            return cached.squeeze().rename(f"sector_{sector33_code}")

    from jquants import JQuantsClient
    client = JQuantsClient()

    universe = client.get_small_cap_universe(sector33_code=sector33_code)
    if universe.empty:
        return pd.Series(dtype=float)

    codes = universe["Code"].dropna().astype(str).tolist()[:max_stocks]
    print(f"    セクター {sector33_code}: {len(codes)} 銘柄から指数構築中...")

    returns_list = []
    for code in codes:
        df = client.get_daily_quotes(code, start_date, end)
        if df.empty or len(df) < MIN_DATA_DAYS:
            continue
        df = df.set_index("Date")
        df.index = pd.to_datetime(df.index)
        col   = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
        close = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(close) < MIN_DATA_DAYS:
            continue
        returns_list.append(close.pct_change().dropna())

    if len(returns_list) < MIN_STOCKS:
        print(f"    データ不足: {len(returns_list)} 銘柄（最低 {MIN_STOCKS} 銘柄必要）")
        return pd.Series(dtype=float)

    combined  = pd.concat(returns_list, axis=1)
    avg_ret   = combined.mean(axis=1)
    idx       = (1 + avg_ret).cumprod() * 100
    idx.name  = f"sector_{sector33_code}"
    idx.index = pd.to_datetime(idx.index)

    pd.DataFrame(idx).to_parquet(cache_path)
    print(f"    → {len(returns_list)} 銘柄で指数構築完了 ({len(idx)} 日)")
    return idx


def build_from_price_dict(
    prices: dict[str, pd.Series],
    name: str = "sector_index",
) -> pd.Series:
    """
    取得済み株価Series辞書からセクター指数を構築。
    yfinanceデータや既存キャッシュにも対応。

    prices: {ticker: pd.Series（終値、DatetimeIndex）}
    """
    returns_list = [
        close.pct_change().dropna()
        for close in prices.values()
        if len(close) >= MIN_DATA_DAYS
    ]

    if len(returns_list) < MIN_STOCKS:
        return pd.Series(dtype=float)

    combined  = pd.concat(returns_list, axis=1)
    avg_ret   = combined.mean(axis=1)
    idx       = (1 + avg_ret).cumprod() * 100
    idx.name  = name
    return idx
