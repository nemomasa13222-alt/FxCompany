"""失敗した4ペアを再ダウンロード"""
import sys; sys.path.insert(0, '.')
from pathlib import Path
from fx_market_classifier.dukascopy import fetch_pair

PAIRS  = ["NZDUSD", "EURGBP", "EURAUD"]
OUT    = Path("data/dukascopy")
OUT.mkdir(exist_ok=True)

for pair in PAIRS:
    out = OUT / f"{pair}_5min.parquet"
    if out.exists():
        print(f"スキップ: {pair}")
        continue
    print(f"\n{pair} ダウンロード開始...")
    df = fetch_pair(pair, "2022-01-01", "2025-01-01",
                    timeframe="5min", cache_dir="cache/dukascopy", delay=0.05)
    if df.empty:
        print(f"失敗: {pair}")
    else:
        df.to_parquet(out)
        print(f"保存: {out}  ({len(df):,}本)")
print("\n完了")
