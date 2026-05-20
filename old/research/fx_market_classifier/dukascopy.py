"""
Dukascopy 無償ヒストリカルデータ フェッチャー（Tick方式）
-----------------------------------------------------------
BIDローソク足 API は廃止済み。代わりに Tick データをダウンロードし、
1分足→任意タイムフレームにリサンプルします。

Tick URL:
  https://www.dukascopy.com/datafeed/{PAIR}/{YEAR}/{MONTH_0IDX:02d}/{DAY:02d}/{HOUR:02d}h_ticks.bi5

Tick バイナリフォーマット（LZMA圧縮、20バイト/tick、ビッグエンディアン）:
  uint32 : time_ms    — 時間先頭からのオフセット (ミリ秒)
  uint32 : ask_raw    — ASK × pip_factor
  uint32 : bid_raw    — BID × pip_factor
  float32: ask_vol    — ASK ティックボリューム
  float32: bid_vol    — BID ティックボリューム

Mid 価格 = (ask + bid) / 2 を OHLCV 計算に使用。

キャッシュ:
  1時間分を Parquet に保存。2回目以降はダウンロードスキップ。

実行例:
  # 動作確認（直近の過去日付 1時間）
  python -m fx_market_classifier.dukascopy --verify

  # 期間取得（時間がかかるため進捗表示）
  python -m fx_market_classifier.dukascopy --pair USDJPY --start 2022-01-01 --end 2025-01-01

  # 出力先指定
  python -m fx_market_classifier.dukascopy --pair USDJPY --start 2022-01-01 --end 2025-01-01 --out data/USDJPY_5min.parquet
"""
from __future__ import annotations

import argparse
import lzma
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# ── 設定 ──────────────────────────────────────────────────────────────────────

_TICK_URL = (
    "https://www.dukascopy.com/datafeed"
    "/{pair}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
)

_PIP_FACTOR: dict[str, int] = {
    "USDJPY": 1000, "EURJPY": 1000, "GBPJPY": 1000,
    "AUDJPY": 1000, "NZDJPY": 1000, "CHFJPY": 1000,
    "GBPUSD": 100000, "AUDUSD": 100000, "NZDUSD": 100000,
    "EURGBP": 100000, "EURAUD": 100000, "AUDNZD": 100000,
}

# Tick: uint32 time_ms, uint32 ask_raw, uint32 bid_raw, float32 ask_vol, float32 bid_vol
_TICK_FMT  = ">IIIff"
_TICK_SIZE = struct.calcsize(_TICK_FMT)   # 20 bytes

DEFAULT_CACHE = Path("cache") / "dukascopy"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.dukascopy.com/",
    "Accept":  "*/*",
}


# ── bi5 デコード ──────────────────────────────────────────────────────────────

def _decode_ticks(
    data: bytes,
    pip_factor: int,
    hour_start: datetime,
) -> pd.DataFrame:
    """LZMA 圧縮済み Tick bi5 → 1本1行の DataFrame。"""
    if not data:
        return pd.DataFrame()
    try:
        raw = lzma.decompress(data)
    except Exception:
        return pd.DataFrame()

    n = len(raw) // _TICK_SIZE
    if n == 0:
        return pd.DataFrame()

    tss, asks, bids, ask_vols, bid_vols = [], [], [], [], []
    for i in range(n):
        chunk = raw[i * _TICK_SIZE : (i + 1) * _TICK_SIZE]
        ts_ms, ask_r, bid_r, av, bv = struct.unpack(_TICK_FMT, chunk)
        tss.append(hour_start + timedelta(milliseconds=int(ts_ms)))
        asks.append(ask_r / pip_factor)
        bids.append(bid_r / pip_factor)
        ask_vols.append(av)
        bid_vols.append(bv)

    df = pd.DataFrame({
        "ask": asks, "bid": bids, "ask_vol": ask_vols, "bid_vol": bid_vols,
    }, index=pd.DatetimeIndex(tss, tz="UTC"))
    df.index.name = "datetime"
    df["mid"] = (df["ask"] + df["bid"]) / 2.0
    return df


def _ticks_to_ohlcv(df_ticks: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Tick DataFrame を指定タイムフレームの OHLCV に変換。"""
    if df_ticks.empty:
        return pd.DataFrame()
    ohlcv = df_ticks["mid"].resample(timeframe, label="left", closed="left").ohlc()
    ohlcv.columns = ["Open", "High", "Low", "Close"]
    ohlcv["Volume"] = df_ticks["bid_vol"].resample(timeframe, label="left", closed="left").sum()
    return ohlcv.dropna(subset=["Open"])


# ── 1時間単位フェッチ（キャッシュ付き） ────────────────────────────────────────

def _hour_url(pair: str, dt: datetime) -> str:
    return _TICK_URL.format(
        pair=pair,
        year=dt.year,
        month=dt.month - 1,   # Dukascopy は 0-indexed month
        day=dt.day,
        hour=dt.hour,
    )


def _fetch_hour_ticks(
    session: requests.Session,
    pair: str,
    pip_factor: int,
    dt: datetime,
    cache_dir: Path,
    delay: float,
) -> pd.DataFrame:
    """1時間分の Tick を取得（キャッシュ優先）。戻り値は Tick DataFrame。"""
    cache_file = cache_dir / f"{dt.strftime('%Y%m%d_%H')}.parquet"

    if cache_file.exists():
        return pd.read_parquet(cache_file)

    url = _hour_url(pair, dt)
    try:
        resp = session.get(url, timeout=20, headers=_HEADERS)
    except requests.RequestException:
        return pd.DataFrame()

    if resp.status_code != 200 or not resp.content:
        return pd.DataFrame()

    df = _decode_ticks(resp.content, pip_factor, dt)
    if not df.empty:
        df.to_parquet(cache_file)

    if delay > 0:
        time.sleep(delay)

    return df


# ── 週末スキップ判定 ──────────────────────────────────────────────────────────

def _is_market_closed(dt: datetime) -> bool:
    wd = dt.weekday()  # 0=月〜6=日
    if wd == 5:
        return True   # 土曜: 全時間クローズ
    if wd == 6 and dt.hour < 22:
        return True   # 日曜22:00 UTC 未満: クローズ
    if wd == 4 and dt.hour >= 22:
        return True   # 金曜22:00 UTC 以降: クローズ
    return False


# ── メイン取得関数 ────────────────────────────────────────────────────────────

def fetch_pair(
    pair: str,
    start: str | datetime,
    end: str | datetime,
    timeframe: str = "5min",
    cache_dir: str | Path = DEFAULT_CACHE,
    delay: float = 0.15,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Dukascopy Tick → OHLCV を取得して返す。

    Parameters
    ----------
    pair      : "USDJPY" など
    start     : 開始日時 (UTC)。文字列 "YYYY-MM-DD" または datetime。
    end       : 終了日時 (UTC)。
    timeframe : pandas resample 文字列 ("5min", "15min", "1h" など)
    cache_dir : キャッシュ保存先
    delay     : リクエスト間隔（秒）。0 でスロットリングなし。
    verbose   : 進捗表示

    Returns
    -------
    pd.DataFrame  columns: [Open, High, Low, Close, Volume]  index: UTC DatetimeIndex
    """
    pair = pair.upper()
    pip_factor = _PIP_FACTOR.get(pair, 100000)

    cache_path = Path(cache_dir) / pair
    cache_path.mkdir(parents=True, exist_ok=True)

    if isinstance(start, str):
        start = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    if isinstance(end, str):
        end   = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)

    current = start.replace(minute=0, second=0, microsecond=0)
    total_h = int((end - start).total_seconds() / 3600) + 1

    if verbose:
        print(f"[{pair}]  {start.date()} ~ {end.date()}"
              f"  ({total_h:,}時間  timeframe={timeframe}  cache: {cache_path})")

    session = requests.Session()
    all_ticks: list[pd.DataFrame] = []
    fetched = cached = skipped = 0

    while current <= end:
        if _is_market_closed(current):
            current += timedelta(hours=1)
            continue

        was_cached = (cache_path / f"{current.strftime('%Y%m%d_%H')}.parquet").exists()
        df_h = _fetch_hour_ticks(session, pair, pip_factor, current, cache_path, delay)

        if not df_h.empty:
            all_ticks.append(df_h)
            cached += was_cached
            fetched += not was_cached
        else:
            skipped += 1

        if verbose and current.hour == 0:
            done = fetched + cached + skipped
            pct  = done / total_h * 100
            print(f"  {current.date()}  {pct:4.0f}%"
                  f"  DL:{fetched}  cache:{cached}  skip:{skipped}")

        current += timedelta(hours=1)

    session.close()

    if not all_ticks:
        if verbose:
            print(f"  データなし: {pair}")
        return pd.DataFrame()

    df_all_ticks = pd.concat(all_ticks).sort_index()
    df_all_ticks = df_all_ticks[~df_all_ticks.index.duplicated(keep="first")]

    df_out = _ticks_to_ohlcv(df_all_ticks, timeframe)

    if verbose:
        print(f"  完了: {len(df_out):,}本 ({timeframe})"
              f"  DL:{fetched}  cache:{cached}  skip:{skipped}")

    return df_out


# ── 複数ペア一括取得 ──────────────────────────────────────────────────────────

def fetch_all_pairs(
    pairs: list[str],
    start: str,
    end: str,
    timeframe: str = "5min",
    cache_dir: str | Path = DEFAULT_CACHE,
    delay: float = 0.15,
) -> dict[str, pd.DataFrame]:
    result = {}
    for pair in pairs:
        df = fetch_pair(pair, start, end, timeframe, cache_dir, delay)
        if not df.empty:
            result[pair] = df
    return result


# ── 動作確認 ──────────────────────────────────────────────────────────────────

def verify_download(pair: str = "USDJPY") -> bool:
    """過去の固定日付 1時間分を取得してデコードを確認。"""
    import tempfile

    test_dt = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)   # 月曜確実データあり
    print(f"テストURL: {_hour_url(pair, test_dt)}")

    with tempfile.TemporaryDirectory() as tmp:
        df = fetch_pair(pair, test_dt, test_dt + timedelta(hours=1),
                        timeframe="5min", cache_dir=tmp, delay=0.1, verbose=True)

    if df.empty:
        print("FAIL: データ取得できません")
        return False

    print(df.to_string())
    c = df["Close"]
    if pair.endswith("JPY") and not (50 < c.min() < 300):
        print("WARN: JPYペアとして価格が異常 (pip_factor を確認)")
        return False

    print(f"\nOK: {pair} Close 範囲 {c.min():.3f} ~ {c.max():.3f}")
    return True


# ── エントリーポイント ─────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="Dukascopy FX Tick データ取得")
    parser.add_argument("--pair",   default="USDJPY")
    parser.add_argument("--start",  default="2022-01-01")
    parser.add_argument("--end",    default="2025-01-01")
    parser.add_argument("--tf",     default="5min")
    parser.add_argument("--out",    default=None,           help="出力 Parquet パス")
    parser.add_argument("--cache",  default=str(DEFAULT_CACHE))
    parser.add_argument("--delay",  type=float, default=0.15)
    parser.add_argument("--verify", action="store_true",    help="動作確認のみ（1時間分取得）")
    args = parser.parse_args(argv)

    if args.verify:
        verify_download(args.pair)
        return

    df = fetch_pair(args.pair, args.start, args.end,
                    args.tf, args.cache, args.delay)

    if df.empty:
        print("データなし")
        return

    print(f"\n先頭5件:\n{df.head(5).to_string()}")
    print(f"\n末尾5件:\n{df.tail(5).to_string()}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out)
        print(f"\n保存: {out}")


if __name__ == "__main__":
    main()
