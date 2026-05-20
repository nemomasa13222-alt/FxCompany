# -*- coding: utf-8 -*-
"""
12ペア完全取得スクリプト
- 未取得ペアを新規ダウンロード
- 途中で止まっているペアを差分延長
- AUDNZD の開始日を 2022-01-01 に遡及
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import time
from pathlib import Path
import pandas as pd

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
CACHE_DIR = ROOT / "cache" / "dukascopy"
DATA_DIR.mkdir(parents=True, exist_ok=True)

START = "2022-01-01"
END   = "2025-01-01"  # 2024-12-31 まで取得

sys.path.insert(0, str(ROOT))
from fx_market_classifier.dukascopy import fetch_pair

# 取得タスク定義: (pair, start, end, mode)
# mode: "new"=新規, "extend_fwd"=前進延長, "extend_bwd"=後退延長
TASKS = [
    ("NZDUSD", START, END, "new"),
    ("EURGBP", START, END, "new"),
    ("EURAUD", START, END, "new"),
    ("GBPUSD", "2023-10-27", END, "extend_fwd"),
    ("AUDUSD", "2024-01-12", END, "extend_fwd"),
    ("AUDNZD", START, "2022-12-08", "extend_bwd"),
]

DELAY = 0.05

def download_and_save(pair, start, end, mode):
    out_path = DATA_DIR / f"{pair}_5min.parquet"
    print(f"\n{'='*50}")
    print(f"[{pair}] {mode}  {start} ~ {end}")

    t0 = time.time()
    df_new = fetch_pair(
        pair=pair, start=start, end=end,
        timeframe="5min",
        cache_dir=CACHE_DIR,
        delay=DELAY,
        verbose=True,
    )

    if df_new.empty:
        print(f"  WARNING: {pair} データ取得失敗")
        return False

    # 既存データとマージ
    if out_path.exists() and mode in ("extend_fwd", "extend_bwd"):
        df_exist = pd.read_parquet(out_path)
        df_combined = pd.concat([df_exist, df_new])
        df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
        df_combined = df_combined.sort_index()
        df_combined.to_parquet(out_path)
        print(f"  マージ完了: {len(df_exist):,}本 + {len(df_new):,}本 → {len(df_combined):,}本")
    else:
        df_new.to_parquet(out_path)
        print(f"  保存完了: {len(df_new):,}本")

    elapsed = time.time() - t0
    print(f"  所要時間: {elapsed:.0f}秒")

    # 確認
    df_check = pd.read_parquet(out_path)
    if df_check.index.tz is not None:
        df_check.index = df_check.index.tz_convert("UTC").tz_localize(None)
    print(f"  最終範囲: {df_check.index[0].date()} ~ {df_check.index[-1].date()}  ({len(df_check):,}本)")
    return True


def main():
    print("=" * 60)
    print("12ペア 差分ダウンロード")
    print(f"  対象: {len(TASKS)}タスク")
    print("=" * 60)

    results = []
    for pair, start, end, mode in TASKS:
        ok = download_and_save(pair, start, end, mode)
        results.append((pair, mode, ok))

    print("\n" + "=" * 60)
    print("完了サマリー")
    for pair, mode, ok in results:
        status = "OK" if ok else "FAIL"
        print(f"  {pair:<10} {mode:<12} [{status}]")

    # 最終確認
    print("\n最終データ一覧:")
    all_pairs = ["USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
                 "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD"]
    for p in all_pairs:
        f = DATA_DIR / f"{p}_5min.parquet"
        if f.exists():
            df = pd.read_parquet(f)
            if df.index.tz is not None:
                df.index = df.index.tz_convert("UTC").tz_localize(None)
            start_d = df.index[0].date()
            end_d   = df.index[-1].date()
            ok_flag = "OK" if str(start_d) <= "2022-01-03" and str(end_d) >= "2024-12-29" else "要確認"
            print(f"  {p:<10} {len(df):>8,}本  {start_d} ~ {end_d}  [{ok_flag}]")
        else:
            print(f"  {p:<10}  *** なし ***  [MISSING]")


if __name__ == "__main__":
    main()
