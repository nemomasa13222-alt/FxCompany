# -*- coding: utf-8 -*-
"""
GitHub Pages公開用: 米国経済指標カレンダーをティックリプレイ用イベントJSONに変換
  米国経済指標カレンダー_2023Dec-2026May.xlsx を読み込み、
  docs/tick_replay/data/events.json として書き出す。

  docs/tick_replay/index.html の「指標で呼び出す」プルダウンが
  このJSONを読み込み、選択されたイベントの前後（既定: 前30分〜後60分）を自動表示する。

  実行: python tick_publish_events.py
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
SRC = ROOT / "米国経済指標カレンダー_2023Dec-2026May.xlsx"
OUT = ROOT / "docs" / "tick_replay" / "data" / "events.json"

# ティックデータが存在しうる最も古い日（これより前のイベントは除外してプルダウンを短く保つ）
MIN_DATE = "2026-01-01"

# プルダウンでの表示順（重要指標を上に）
INDICATOR_ORDER = [
    "FOMC政策金利発表", "FRB議長記者会見", "FOMC議事録",
    "雇用統計(NFP)", "CPI(消費者物価指数)", "PPI(生産者物価指数)", "PCEデフレーター",
    "ADP民間雇用者数", "ISM製造業景況指数", "ISM非製造業景況指数", "小売売上高",
    "GDP(速報値)", "GDP(改定値)", "GDP(確定値)",
    "ミシガン大消費者信頼感(速報)", "消費者信頼感指数(CB)",
    "住宅着工件数", "耐久財受注(速報)",
]

_JST_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})\([^)]+\)\s+(\d{2}):(\d{2})")


def parse_jst(s):
    m = _JST_RE.match(str(s).strip())
    if not m:
        return None
    y, mo, d, hh, mm = m.groups()
    return f"{y}-{mo}-{d}T{hh}:{mm}"


def main():
    df = pd.read_excel(SRC, sheet_name=0)
    df["jst"] = df["日本時間(JST)"].map(parse_jst)
    df = df.dropna(subset=["jst"])
    df = df[df["jst"] >= MIN_DATE]

    events = []
    for _, row in df.sort_values("jst").iterrows():
        events.append({
            "name": row["指標名"],
            "jst": row["jst"],
            "period": row["対象期間"],
            "importance": row["重要度"],
        })

    present = [n for n in INDICATOR_ORDER if n in set(e["name"] for e in events)]
    extra = sorted(set(e["name"] for e in events) - set(present))

    payload = {"indicators": present + extra, "events": events}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"指標種別: {len(payload['indicators'])}種類")
    print(f"イベント件数: {len(events)}件（{MIN_DATE}以降）")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
