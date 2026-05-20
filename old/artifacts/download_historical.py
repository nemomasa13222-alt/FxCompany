"""
Dukascopy 3年分 全ペア一括ダウンロード
2022-01-01 ~ 2025-01-01  5分足

進捗はペアごとに表示。キャッシュ済みのファイルはスキップ。
途中で中断しても再実行で続きから再開できます。

実行: python download_historical.py
"""
import time
from pathlib import Path
from datetime import datetime

from fx_market_classifier.dukascopy import fetch_pair
from fx_market_classifier.config import PAIRS

START     = "2022-01-01"
END       = "2025-01-01"
TIMEFRAME = "5min"
CACHE_DIR = Path("cache") / "dukascopy"
OUT_DIR   = Path("data") / "dukascopy"
DELAY     = 0.05          # サーバー負荷を抑えつつ高速化

OUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print(f"Dukascopy 一括ダウンロード")
print(f"期間: {START} ~ {END}  タイムフレーム: {TIMEFRAME}")
print(f"対象: {len(PAIRS)}ペア  {PAIRS}")
print(f"キャッシュ: {CACHE_DIR}")
print(f"出力先  : {OUT_DIR}")
print("=" * 60)

total_start = time.time()
success = []
failed  = []

for i, pair in enumerate(PAIRS, 1):
    out_file = OUT_DIR / f"{pair}_5min.parquet"
    print(f"\n[{i}/{len(PAIRS)}] {pair}  ", end="", flush=True)

    if out_file.exists():
        print(f"スキップ（取得済み: {out_file}）")
        success.append(pair)
        continue

    t0 = time.time()
    df = fetch_pair(
        pair      = pair,
        start     = START,
        end       = END,
        timeframe = TIMEFRAME,
        cache_dir = CACHE_DIR,
        delay     = DELAY,
        verbose   = True,
    )

    elapsed = time.time() - t0

    if df.empty:
        print(f"  WARN: {pair} データ取得失敗")
        failed.append(pair)
        continue

    df.to_parquet(out_file)
    print(f"  保存: {out_file}  ({len(df):,}本  {elapsed:.0f}秒)")
    success.append(pair)

total_elapsed = time.time() - total_start
print("\n" + "=" * 60)
print(f"完了!  成功:{len(success)}ペア  失敗:{len(failed)}ペア  合計:{total_elapsed/60:.1f}分")
if failed:
    print(f"失敗ペア: {failed}")
print(f"出力先: {OUT_DIR.resolve()}")
