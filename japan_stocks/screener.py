# -*- coding: utf-8 -*-
"""
デイリースクリーナー
- セクターETFが上昇トレンドのとき
- そのセクター内で「遅行株」かつ「まだ動いていない」銘柄を抽出
- 毎営業日の引け後に実行する想定
"""

import pandas as pd
import numpy as np
from analyzer import analyze_sector, sector_trend


# ── スクリーニングパラメータ ──────────────────────────────────────────────

SECTOR_LOOKBACK    = 5      # セクタートレンド判定に使う日数
SECTOR_MIN_RISE    = 1.5    # セクターETFの最低上昇率（%）
STOCK_MAX_RISE     = 0.5    # 遅行株の最大上昇率（これ以下なら「まだ動いていない」）
MIN_CORR           = 0.20   # 遅行株として採用する最低相関（信頼性フィルター）
TARGET_CLASS       = ["遅行株", "中間株"]  # 対象分類


def screen(etf: pd.Series, stocks: dict[str, pd.Series],
           sector_name: str, analysis_df: pd.DataFrame) -> list[dict]:
    """
    スクリーニングを実行してシグナルリストを返す。

    analysis_df: analyze_sector() の戻り値（分類済み）
    """
    signals = []

    # ── 1. セクタートレンド確認 ──────────────────────────────────────────
    trend = sector_trend(etf, SECTOR_LOOKBACK)
    if not trend["is_up"] or trend["change_pct"] < SECTOR_MIN_RISE:
        return signals  # セクターが上昇していなければシグナルなし

    # ── 2. 遅行株・中間株をフィルタリング ───────────────────────────────
    candidates = analysis_df[
        analysis_df["classification"].isin(TARGET_CLASS) &
        (analysis_df["corr_best"] >= MIN_CORR)
    ]

    for _, row in candidates.iterrows():
        ticker = row["ticker"]
        if ticker not in stocks:
            continue

        stock = stocks[ticker]
        if len(stock) < SECTOR_LOOKBACK + 1:
            continue

        # 株価の直近N日変化率
        recent = stock.iloc[-SECTOR_LOOKBACK - 1:]
        stock_change = (recent.iloc[-1] / recent.iloc[0] - 1) * 100

        # ── 3. 「まだ動いていない」銘柄のみ ─────────────────────────────
        if stock_change > STOCK_MAX_RISE:
            continue  # すでに上昇済み → スキップ

        # 乖離率（セクター上昇幅 - 銘柄上昇幅）
        gap = trend["change_pct"] - stock_change

        signals.append({
            "sector"          : sector_name,
            "ticker"          : ticker,
            "classification"  : row["classification"],
            "best_lag"        : row["best_lag"],
            "corr_best"       : round(row["corr_best"], 3),
            "sector_change"   : trend["change_pct"],
            "stock_change"    : round(stock_change, 2),
            "gap"             : round(gap, 2),
            "latest_price"    : round(stock.iloc[-1], 1),
        })

    # 乖離率が大きい順に並べる（遅れが大きいほど追いつき余地が大きい）
    signals.sort(key=lambda x: x["gap"], reverse=True)
    return signals


def format_signals(signals: list[dict]) -> str:
    """シグナルを人が読みやすい形式で出力"""
    if not signals:
        return "  シグナルなし"

    lines = []
    for s in signals:
        lines.append(
            f"  [{s['sector']}] {s['ticker']}  {s['classification']}  "
            f"ラグ:{s['best_lag']}日  相関:{s['corr_best']}  "
            f"セクター+{s['sector_change']}% / 銘柄{s['stock_change']:+.1f}%  "
            f"乖離:{s['gap']:+.1f}%  直近株価:{s['latest_price']}円"
        )
    return "\n".join(lines)
