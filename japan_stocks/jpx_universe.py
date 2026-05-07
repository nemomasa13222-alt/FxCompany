# -*- coding: utf-8 -*-
"""
JPX上場銘柄ユニバース取得モジュール
- 日本取引所グループが公開している上場銘柄一覧CSVをダウンロード
- yfinance形式（XXXX.T）のティッカーリストを返す
- キャッシュ: 7日間有効
"""

from pathlib import Path
from datetime import datetime, timedelta
import io

import requests
import pandas as pd

CACHE_DIR  = Path(__file__).parent / "results" / "cache"
CACHE_FILE = CACHE_DIR / "jpx_stock_list.parquet"
CACHE_DAYS = 7

# JPX 上場銘柄一覧（Excel形式）
JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

# 対象市場区分
TARGET_MARKETS = {"プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）"}


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
    return age < timedelta(days=CACHE_DAYS)


def fetch_stock_list(force: bool = False) -> pd.DataFrame:
    """
    JPX上場銘柄一覧を取得してDataFrameで返す。
    列: code（4桁）, name, market, sector33
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and _cache_is_fresh():
        return pd.read_parquet(CACHE_FILE)

    print("  JPX上場銘柄一覧をダウンロード中...")
    try:
        resp = requests.get(JPX_URL, timeout=30,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content), dtype=str)
    except Exception as e:
        raise RuntimeError(f"JPX銘柄一覧の取得に失敗: {e}\n"
                           f"URL: {JPX_URL}") from e

    # JPX Excel の固定列名でリネーム
    df = df.rename(columns={
        "コード"      : "code",
        "銘柄名"      : "name",
        "市場・商品区分": "market",
        "33業種区分"   : "sector33",
    })

    required = {"code", "name"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"列名の解析に失敗（見つからない列: {missing}）\n"
                           f"実際の列: {list(df.columns)}")

    # コードを4桁文字列に正規化
    df["code"] = df["code"].astype(str).str.strip().str.zfill(4)
    df = df[df["code"].str.match(r"^\d{4}$")]  # 数字4桁のみ

    # 市場フィルター（ETF・ETN等を除外、内国株式のみ）
    if "market" in df.columns:
        df = df[df["market"].isin(TARGET_MARKETS)]

    df = df.reset_index(drop=True)
    df.to_parquet(CACHE_FILE)
    print(f"  取得完了: {len(df)} 銘柄")
    return df


def get_all_tickers(force: bool = False) -> list[str]:
    """
    yfinance形式のティッカーリスト（XXXX.T）を返す。
    """
    df = fetch_stock_list(force=force)
    return [f"{code}.T" for code in df["code"].tolist()]


def get_tickers_by_market(market: str = "all") -> list[str]:
    """
    市場区分でフィルターしたティッカーリストを返す。
    market: "prime" | "standard" | "growth" | "all"
    """
    df = fetch_stock_list()
    if "market" not in df.columns or market == "all":
        return [f"{c}.T" for c in df["code"]]

    market_map = {
        "prime"   : "プライム（内国株式）",
        "standard": "スタンダード（内国株式）",
        "growth"  : "グロース（内国株式）",
    }
    target = market_map.get(market)
    if target:
        df = df[df["market"] == target]
    return [f"{c}.T" for c in df["code"]]


def get_ticker_info() -> dict[str, dict]:
    """ティッカー → {name, market, sector33} の辞書を返す"""
    df = fetch_stock_list()
    info = {}
    for _, row in df.iterrows():
        ticker = f"{row['code']}.T"
        info[ticker] = {
            "name"    : row.get("name", ""),
            "market"  : row.get("market", ""),
            "sector33": row.get("sector33", ""),
        }
    return info
