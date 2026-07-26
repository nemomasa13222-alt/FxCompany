# -*- coding: utf-8 -*-
"""
GitHub Pages公開用: USDJPYティックデータを日別JSONに分割書き出し
  data/tick/USDJPY_tick_YYYY.parquet を読み込み、JST日付ごとに
  docs/tick_replay/data/USDJPY/YYYY-MM-DD.json として書き出す。

  docs/tick_replay/index.html（ブラウザの期間指定プレイヤー）が
  必要な日だけfetchして、その場でティックリプレイを再生する。

  実行: python tick_publish_days.py --year 2026
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import argparse
import json
from pathlib import Path
from datetime import timedelta

import pandas as pd

ROOT     = Path(__file__).parent
TICK_DIR = ROOT / "data" / "tick"
OUT_DIR  = ROOT / "docs" / "tick_replay" / "data" / "USDJPY"
PAIR     = "USDJPY"


def main():
    p = argparse.ArgumentParser(description="ティックデータを日別JSONに分割書き出し（GitHub Pages公開用）")
    p.add_argument("--year", type=int, required=True, help="対象年（例: 2026）")
    p.add_argument("--force", action="store_true", help="既存の日別JSONも上書きする")
    args = p.parse_args()

    src = TICK_DIR / f"{PAIR}_tick_{args.year}.parquet"
    if not src.exists():
        print(f"エラー: {src} が見つかりません")
        sys.exit(1)

    print(f"読み込み中: {src}")
    df = pd.read_parquet(src)
    jst_date = (df.index + timedelta(hours=9)).date

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "manifest.json"
    dates_written = []

    groups = df.groupby(jst_date)
    total = len(groups)
    for i, (d, g) in enumerate(groups, 1):
        out_file = OUT_DIR / f"{d.isoformat()}.json"
        dates_written.append(d.isoformat())
        if out_file.exists() and not args.force:
            continue
        t = g.index.as_unit("ms").view("int64").tolist()  # ms epoch (UTC)
        b = [round(float(x), 3) for x in g["bid"]]
        a = [round(float(x), 3) for x in g["ask"]]
        payload = {"t": t, "b": b, "a": a}
        out_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        if i % 20 == 0 or i == total:
            print(f"  [{i}/{total}] {d} ({len(g):,} ticks)")

    # マニフェスト更新（他の年の書き出し分とも合算）
    all_dates = set(dates_written)
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            all_dates |= set(existing.get("dates", []))
        except Exception:
            pass
    all_dates = sorted(all_dates)
    manifest = {"pair": PAIR, "dates": all_dates, "min": all_dates[0], "max": all_dates[-1]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    total_mb = sum(f.stat().st_size for f in OUT_DIR.glob("*.json") if f.name != "manifest.json") / 1e6
    print(f"\n完了: {len(dates_written)}日分  合計 {total_mb:.1f}MB")
    print(f"→ {OUT_DIR}")


if __name__ == "__main__":
    main()
