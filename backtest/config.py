# -*- coding: utf-8 -*-
# バックテスト設定ファイル（FxCompany版）
# このファイルのパラメータを固定してから run.py を実行すること

from pathlib import Path

# ── データ設定 ──────────────────────────────────────────────────────────
# FXデータ格納フォルダ（通貨ペアごとにサブフォルダを作成）
DATA_DIR = Path(r"C:\Users\MAI\OneDrive\デスクトップ\FX\.company\secretary\トレード\USDJPY")

# ── 検証期間 ─────────────────────────────────────────────────────────────
START_DATE  = None       # 例: "2024-10-14"
END_DATE    = None       # 例: "2026-04-29"
IS_END_DATE = None       # IS/OOS分割日。None で分割なし

# ── トレード設定 ─────────────────────────────────────────────────────────
# スプレッド参照: DMM FX コアタイム基準
# USD/JPY=0.2 / EUR/USD=0.3 / GBP/JPY=0.9 / AUD/JPY=0.5
SPREAD_PIPS   = 0.2
MAX_POSITIONS = 1
LOTS          = 1.0      # 1ロット = 1万通貨（1pip = 100円）

# ── 条件関数の設定 ────────────────────────────────────────────────────────
LOOKBACK = 960           # ロンドンブレイクアウト用（アジアセッション16時間分）

# ── 検証判定 ─────────────────────────────────────────────────────────────
INSUFFICIENT_THRESHOLD = 500
STATS_CHECKPOINTS      = [100, 300, 500, 1000]

# ── 出力設定 ─────────────────────────────────────────────────────────────
RESULTS_DIR = Path(__file__).parent / "results"
FONT_PATH   = r"C:\Windows\Fonts\YuGothM.ttc"
