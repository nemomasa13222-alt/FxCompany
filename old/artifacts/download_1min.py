"""
Dukascopy 5年分 全ペア一括ダウンロード（1分足）
2021-01-01 ~ 2026-05-18

- USDJPYを最初に処理
- 既存 Tick キャッシュ（2022-2025）は再ダウンロードなし → 高速
- 途中中断しても再実行で続きから再開

実行: python download_1min.py
"""
import time
from pathlib import Path

from fx_market_classifier.dukascopy import fetch_pair

START     = "2021-01-01"
END       = "2026-05-18"
TIMEFRAME = "1min"
CACHE_DIR = Path("cache") / "dukascopy"
OUT_DIR   = Path("data") / "dukascopy"

PAIRS = [
    "USDJPY",                                              # 最優先
    "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY",    # JPYクロス
    "GBPUSD", "AUDUSD", "NZDUSD",                         # USD
    "EURGBP", "EURAUD", "AUDNZD",                         # クロス
]

OUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print(f"Dukascopy 1分足 一括ダウンロード")
print(f"期間: {START} ~ {END}")
print(f"対象: {len(PAIRS)}ペア")
print(f"キャッシュ: {CACHE_DIR}  (既存Tick流用で2022-2025は高速)")
print(f"出力先  : {OUT_DIR}")
print("=" * 60)

total_start = time.time()
success = []
failed  = []

for i, pair in enumerate(PAIRS, 1):
    out_file = OUT_DIR / f"{pair}_1min.parquet"
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
        delay     = 0.05,
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
