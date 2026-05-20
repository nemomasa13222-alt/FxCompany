# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from chatgpt_advisor import ask

ask(
    question="セクター指数の構成方法として等加重平均と時価総額加重のどちらが適切か？",
    context=(
        "国内株式市場でセクター内の遅行株がセクター指数に追いつく動きを取る短期トレード戦略を構築中。"
        "バックテスト→デモ→実運用の流れ。構成銘柄はJ-Quantsの東証33業種から取得。"
        "セクター内の中間〜遅行株を特定し、セクター指数との乖離が縮まる動きでエグジットする。"
    ),
)
