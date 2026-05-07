# -*- coding: utf-8 -*-
"""
J-Quants API v2 クライアント（APIキー認証）
2025-12-22以降登録のアカウント向け。

事前準備:
  python setup_credentials.py を実行してAPIキーをWindows資格情報マネージャーに登録する。

使い方:
  from jquants import JQuantsClient
  client = JQuantsClient()
  stocks = client.get_stock_list()           # 全上場銘柄一覧
  prices = client.get_daily_quotes("6118")   # 日足データ
  codes  = client.get_sector33_codes()       # 東証33業種コード一覧
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import requests
import pandas as pd

CACHE_DIR = Path(__file__).parent / "results" / "jquants_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.jquants.com/v2"


class JQuantsClient:
    def __init__(self, api_key: str | None = None):
        if api_key:
            self._api_key = api_key
        else:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from setup_credentials import get_jquants_api_key
            self._api_key = get_jquants_api_key()

    def _headers(self) -> dict:
        return {"x-api-key": self._api_key}

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{BASE_URL}{path}", headers=self._headers(), params=params or {})
        resp.raise_for_status()
        return resp.json()

    # ── 銘柄一覧 ──────────────────────────────────────────────────────

    def get_stock_list(self, use_cache: bool = True) -> pd.DataFrame:
        """全上場銘柄一覧（コード、銘柄名、業種、市場区分等）"""
        cache = CACHE_DIR / "stock_list.parquet"
        if use_cache and cache.exists():
            age = (datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)).days
            if age < 7:
                return pd.read_parquet(cache)

        data = self._get("/equities/master")
        df = pd.DataFrame(data.get("data", data.get("master", data.get("info", []))))
        if not df.empty:
            df.to_parquet(cache)
        return df

    def get_small_cap_universe(self, sector33_code: str | None = None) -> pd.DataFrame:
        """
        小型株ユニバース取得。
        sector33_code: 東証33業種コード（例: "3710"）。None で全業種。
        """
        stocks = self.get_stock_list()
        if stocks.empty:
            return stocks

        # 上場市場フィルター
        if "MarketCodeName" in stocks.columns:
            stocks = stocks[stocks["MarketCodeName"].isin(
                ["プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）"]
            )]

        if sector33_code and "Sector33Code" in stocks.columns:
            stocks = stocks[stocks["Sector33Code"] == sector33_code]

        return stocks.reset_index(drop=True)

    # ── 価格データ ────────────────────────────────────────────────────

    def get_daily_quotes(self, code: str, start_date: str,
                          end_date: str | None = None) -> pd.DataFrame:
        """日足OHLCV取得（調整済み）。code は4桁証券コード。"""
        end = end_date or datetime.today().strftime("%Y-%m-%d")
        cache = CACHE_DIR / f"quotes_{code}.parquet"

        if cache.exists():
            cached = pd.read_parquet(cache)
            last = cached["Date"].max()
            next_start = (pd.Timestamp(last) + timedelta(days=1)).strftime("%Y-%m-%d")
            if next_start <= end:
                fresh = self._fetch_quotes(code, next_start, end)
                if not fresh.empty:
                    combined = pd.concat([cached, fresh]).drop_duplicates("Date")
                    combined.to_parquet(cache)
                    return combined[combined["Date"] >= start_date].reset_index(drop=True)
            return cached[cached["Date"] >= start_date].reset_index(drop=True)

        df = self._fetch_quotes(code, start_date, end)
        if not df.empty:
            df.to_parquet(cache)
        return df

    def _fetch_quotes(self, code: str, start: str, end: str) -> pd.DataFrame:
        try:
            data = self._get("/equities/bars/daily",
                             {"code": code, "from": start, "to": end})
            df = pd.DataFrame(data.get("data", data.get("daily_quotes", data.get("bars", []))))
            if df.empty:
                return df
            df["Date"] = pd.to_datetime(df["Date"])
            return df.sort_values("Date").reset_index(drop=True)
        except Exception:
            return pd.DataFrame()

    # ── 決算カレンダー ───────────────────────────────────────────────

    def get_earnings_calendar(self,
                              from_date: str = "2018-01-01",
                              to_date: str | None = None,
                              use_cache: bool = True
                              ) -> dict[str, list[pd.Timestamp]]:
        """
        J-Quants Lightプラン以上: 全銘柄の決算発表日を取得する。
        戻り値: {"1234_T": [Timestamp, ...], ...}
        キャッシュは7日間有効。
        """
        cache_path = CACHE_DIR / "earnings_calendar_jquants.parquet"

        if use_cache and cache_path.exists():
            age = (datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)).days
            if age < 7:
                df = pd.read_parquet(cache_path)
                cal: dict[str, list[pd.Timestamp]] = {}
                for _, row in df.iterrows():
                    cal.setdefault(row["ticker"], []).append(pd.Timestamp(row["date"]))
                print(f"  決算カレンダー（J-Quants キャッシュ）: {len(cal)} 銘柄")
                return cal

        end = to_date or datetime.today().strftime("%Y-%m-%d")
        print(f"  J-Quants 決算カレンダー取得中 ({from_date} 〜 {end})...")

        # ページネーション対応: next_token が空になるまでループ
        # Lightプランで利用可能なエンドポイントを順に試す
        items: list[dict] = []
        endpoints = [
            ("/equities/announcement", "announcement"),
            ("/equities/earnings",     "earnings"),
            ("/equities/statements",   "statements"),
        ]
        used_endpoint = None
        for ep, key in endpoints:
            try:
                resp = self._get(ep, {"from": from_date, "to": end})
                chunk = resp.get(key, resp.get("data", []))
                if chunk:
                    items.extend(chunk)
                    used_endpoint = ep
                    # ページネーション継続
                    token = resp.get("pagination_key") or resp.get("nextToken")
                    while token:
                        resp = self._get(ep, {"pagination_key": token})
                        chunk = resp.get(key, resp.get("data", []))
                        items.extend(chunk)
                        token = resp.get("pagination_key") or resp.get("nextToken")
                    break
            except Exception as e:
                print(f"  {ep} 試行: {e}")
                continue

        if used_endpoint:
            print(f"  使用エンドポイント: {used_endpoint}")

        if not items:
            print("  警告: 決算カレンダーデータが空です")
            return {}

        df = pd.DataFrame(items)

        # J-Quants APIのカラム名に対応（バージョン差異を吸収）
        date_col = next(
            (c for c in ["AnnouncementDate", "announcementDate", "Date", "date"] if c in df.columns), None
        )
        code_col = next(
            (c for c in ["LocalCode", "Code", "code", "localCode"] if c in df.columns), None
        )
        if not date_col or not code_col:
            print(f"  警告: 期待カラムなし: {list(df.columns)}")
            return {}

        records = []
        for _, row in df.iterrows():
            try:
                code = str(row[code_col]).zfill(4) + "_T"
                d    = pd.Timestamp(row[date_col]).normalize()
                if d.tzinfo is not None:
                    d = d.tz_localize(None)
                records.append({"ticker": code, "date": d})
            except Exception:
                pass

        if not records:
            return {}

        out = pd.DataFrame(records).drop_duplicates()
        out.to_parquet(cache_path)

        cal = {}
        for _, row in out.iterrows():
            cal.setdefault(row["ticker"], []).append(row["date"])
        print(f"  J-Quants 決算カレンダー: {len(cal)} 銘柄分を取得・キャッシュ")
        return cal

    # ── 業種マスタ ────────────────────────────────────────────────────

    def get_sector33_codes(self) -> dict[str, str]:
        """東証33業種コードと名称のマッピングを返す"""
        stocks = self.get_stock_list()
        if "Sector33Code" not in stocks.columns:
            return {}
        mapping = (stocks[["Sector33Code", "Sector33CodeName"]]
                   .drop_duplicates()
                   .sort_values("Sector33Code"))
        return dict(zip(mapping["Sector33Code"], mapping["Sector33CodeName"]))

    def build_universe_for_sector(self, sector33_code: str,
                                   max_stocks: int = 50) -> list[str]:
        """指定業種の銘柄コードリストを返す（yfinance形式: XXXX.T）"""
        universe = self.get_small_cap_universe(sector33_code=sector33_code)
        codes = universe["Code"].dropna().astype(str).tolist()
        return [f"{c}.T" for c in codes[:max_stocks]]
