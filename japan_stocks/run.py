# -*- coding: utf-8 -*-
"""
エントリーポイント
実行: python japan_stocks/run.py

処理内容:
  1. 全セクターのデータ取得
  2. クロスコリレーション分析（先行/中間/遅行の分類）
  3. 本日時点のスクリーニング（買いシグナル候補の抽出）
  4. 結果をMarkdownで保存
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from sector_map import SECTORS
import data as dt
import analyzer
import screener

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START  = "2023-01-01"   # データ取得開始日
TODAY       = datetime.today().strftime("%Y-%m-%d")


def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  日本株 セクター遅行株スクリーナー")
    print(f"  実行日時: {run_time}")
    print(f"{'='*60}\n")

    all_signals = []
    analysis_results = {}

    for sector_name, sector_def in SECTORS.items():
        print(f"[{sector_name}] データ取得中...")
        try:
            raw = dt.fetch_sector_and_stocks(sector_def, start=DATA_START)
        except Exception as e:
            print(f"  エラー: {e}")
            continue

        etf    = raw["etf"]
        stocks = raw["stocks"]

        if len(etf) < 60 or not stocks:
            print(f"  データ不足 — スキップ")
            continue

        print(f"  ETF: {len(etf)}日分  銘柄: {len(stocks)}銘柄")

        # ── クロスコリレーション分析 ──────────────────────────────────
        print(f"  クロスコリレーション分析中...")
        analysis_df = analyzer.analyze_sector(etf, stocks)
        analysis_results[sector_name] = {"etf": etf, "stocks": stocks, "df": analysis_df}

        # ── スクリーニング ─────────────────────────────────────────────
        signals = screener.screen(etf, stocks, sector_name, analysis_df)
        all_signals.extend(signals)

        # セクター内分類を表示
        leaders  = analysis_df[analysis_df["classification"] == "先行株"]
        middles  = analysis_df[analysis_df["classification"] == "中間株"]
        laggers  = analysis_df[analysis_df["classification"] == "遅行株"]
        trend    = analyzer.sector_trend(etf)
        print(f"  セクタートレンド({trend['lookback_days']}日): {trend['change_pct']:+.2f}%")
        print(f"  分類 → 先行:{len(leaders)}  中間:{len(middles)}  遅行:{len(laggers)}")
        if signals:
            print(f"  ★ シグナル {len(signals)}件")
        print()

    # ── 結果表示 ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  本日のシグナル一覧  ({TODAY})")
    print(f"{'='*60}")
    if all_signals:
        for s in all_signals:
            print(
                f"  [{s['sector']}] {s['ticker']:8s}  {s['classification']}  "
                f"ラグ:{s['best_lag']:+d}日  相関:{s['corr_best']:.2f}  "
                f"セクター{s['sector_change']:+.1f}% / 銘柄{s['stock_change']:+.1f}%  "
                f"乖離:{s['gap']:+.1f}%  株価:{s['latest_price']}円"
            )
    else:
        print("  本日のシグナルなし（セクター上昇中かつ遅行銘柄なし）")

    # ── Markdown保存 ───────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"screen_{ts}.md"
    _save_markdown(all_signals, analysis_results, run_time, path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*60}\n")


def _save_markdown(signals, analysis_results, run_time, path):
    lines = [
        f"# 日本株 セクター遅行株スクリーニング結果\n",
        f"実行日時: {run_time}\n",
        "---\n",
        "## 本日のシグナル\n",
    ]

    if signals:
        lines.append("| セクター | 銘柄 | 分類 | ラグ | 相関 | セクター変化 | 銘柄変化 | 乖離 | 直近株価 |")
        lines.append("|---------|------|------|------|------|------------|---------|------|---------|")
        for s in signals:
            lines.append(
                f"| {s['sector']} | {s['ticker']} | {s['classification']} "
                f"| {s['best_lag']:+d}日 | {s['corr_best']:.2f} "
                f"| {s['sector_change']:+.1f}% | {s['stock_change']:+.1f}% "
                f"| {s['gap']:+.1f}% | {s['latest_price']}円 |"
            )
    else:
        lines.append("本日のシグナルなし\n")

    lines.append("\n---\n")
    lines.append("## セクター別 分類詳細\n")

    for sector_name, res in analysis_results.items():
        df = res["df"]
        trend = analyzer.sector_trend(res["etf"])
        lines.append(f"### {sector_name}  （{trend['change_pct']:+.2f}% / {trend['lookback_days']}日）\n")
        lines.append("| 銘柄 | 分類 | ベストラグ | ラグ時相関 | lag=0相関 |")
        lines.append("|------|------|-----------|-----------|---------|")
        for _, row in df.iterrows():
            lines.append(
                f"| {row['ticker']} | {row['classification']} "
                f"| {row['best_lag']:+d}日 | {row['corr_best']:.3f} | {row['corr_0']:.3f} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
