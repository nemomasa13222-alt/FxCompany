# -*- coding: utf-8 -*-
"""
米国経済指標カレンダー Excel → MT4用CSV 変換スクリプト
実行: python mt4/make_calendar_csv.py

出力先: mt4/EcoCalendar.csv
        → このファイルを MT4の MQL4/Files/ フォルダにコピーする
"""

import re
from pathlib import Path
import pandas as pd

BASE_DIR   = Path(__file__).parent.parent
EXCEL_PATH = BASE_DIR / "米国経済指標カレンダー_2023Dec-2026May.xlsx"
OUTPUT_CSV = Path(__file__).parent / "EcoCalendar.csv"


def parse_mt4_time(s: str) -> str | None:
    """
    "2023/12/01(金) 17:00" → "2023.12.01 17:00"
    MT4が読める形式に変換する
    """
    if not isinstance(s, str):
        return None
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})[^)]*\)\s*(\d{2}:\d{2})", s)
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)} {m.group(4)}"


def importance_to_level(s: str) -> str:
    if not isinstance(s, str):
        return "medium"
    # 星マーク（★ = U+2605）の数で判定
    star_count = s.count("★")
    if star_count >= 3:
        return "high"    # ★★★ = 最重要
    return "medium"      # ★★  = 重要


def main():
    print(f"読み込み: {EXCEL_PATH.name}")
    df = pd.read_excel(EXCEL_PATH)
    df.columns = ["no", "date_str", "name", "mt4_time",
                  "importance", "period", "us_time", "jst_time", "note"]

    records = []
    skipped = 0
    for _, row in df.iterrows():
        dt = parse_mt4_time(str(row["mt4_time"]))
        if not dt:
            skipped += 1
            continue
        name  = str(row["name"]).strip()
        level = importance_to_level(str(row["importance"]))
        records.append({"datetime": dt, "name": name, "importance": level})

    out = pd.DataFrame(records)
    out = out.sort_values("datetime").reset_index(drop=True)
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"出力: {OUTPUT_CSV.name}  ({len(out)}件, スキップ:{skipped}件)")
    print()
    print("次のステップ:")
    print(f"  mt4/EcoCalendar.csv  →  MT4の MQL4\\Files\\ フォルダにコピー")
    print(f"  mt4/indicators/EcoCalendar.mq4  →  MT4の MQL4\\Indicators\\ フォルダにコピー")
    print(f"  MT4でコンパイル後、チャートに適用")


if __name__ == "__main__":
    main()
