# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート デイリースクリーナー
実行: python japan_stocks/run_minervini.py

毎日引け後に実行することで、8条件を満たす銘柄を抽出する。
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import data as dt
import minervini_screener as mv
from sector_map import SECTORS

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START  = "2023-01-01"
NIKKEI225   = "^N225"


def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  ミネルヴィニ・トレンドテンプレート スクリーナー")
    print(f"  実行日時: {run_time}")
    print(f"{'='*60}\n")

    # ── 全銘柄リストを収集 ─────────────────────────────────────────────
    all_tickers = []
    for sector_def in SECTORS.values():
        all_tickers.extend(sector_def["stocks"])
    all_tickers = list(set(all_tickers))

    # ── データ取得 ─────────────────────────────────────────────────────
    print("データ取得中...")
    closes = {}
    for ticker in all_tickers:
        try:
            df = dt.fetch(ticker, start=DATA_START)
            if len(df) >= 220:
                closes[ticker] = df["Close"]
        except Exception as e:
            print(f"  {ticker}: スキップ ({e})")

    print(f"  有効銘柄数: {len(closes)}")

    # ── RS Rating 計算（ユニバース全体でパーセンタイル化）────────────
    print("RS Rating 計算中...")
    rs_pcts = mv.calc_rs_percentiles(closes)

    # ── 8条件チェック ─────────────────────────────────────────────────
    results = []
    for ticker, close in closes.items():
        res = mv.check(close, rs_pcts.get(ticker, float("nan")))
        if res is not None:
            results.append({"ticker": ticker, **res})

    # ── ソート: 全条件クリア → スコア降順 → RS降順 ─────────────────
    results.sort(key=lambda r: (-r["passed_all"], -r["score"], -(r["rs_rating"] or 0)))

    # ── 結果表示 ───────────────────────────────────────────────────────
    perfect = [r for r in results if r["passed_all"]]
    partial = [r for r in results if not r["passed_all"]]

    print(f"\n{'='*60}")
    print(f"  スクリーニング結果  ({datetime.today().strftime('%Y-%m-%d')})")
    print(f"  全8条件クリア: {len(perfect)} 銘柄 / 検査: {len(results)} 銘柄")
    print(f"{'='*60}")

    if perfect:
        print("\n【★ 全条件クリア 銘柄】")
        for r in perfect:
            print(mv.format_result(r["ticker"], r))
            print()
    else:
        print("\n  全条件クリアの銘柄なし")

    if partial:
        print("\n【7/8 条件クリア 銘柄】")
        for r in partial[:10]:
            if r["score"] >= 7:
                print(mv.format_result(r["ticker"], r))
                print()

    # ── Markdown保存 ───────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"minervini_{ts}.md"
    _save_markdown(results, run_time, path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*60}\n")


def _save_markdown(results: list[dict], run_time: str, path: Path):
    today = datetime.today().strftime("%Y-%m-%d")
    lines = [
        f"# ミネルヴィニ・トレンドテンプレート スクリーニング結果\n",
        f"実行日時: {run_time}  \n",
        "---\n",
        "## スクリーニング条件（8条件）\n",
        "1. 株価 > MA150・MA200",
        "2. MA150 > MA200",
        "3. MA200 が少なくとも1ヶ月上昇トレンド",
        "4. MA50 > MA150・MA200",
        "5. 株価 ≥ 52週安値 × 1.25（25%以上上昇）",
        "6. 株価 ≥ 52週高値 × 0.75（高値の25%以内）",
        "7. RS Rating ≥ 70（理想は90台）",
        "8. 株価 > MA50（ブレイクアウト確認）\n",
        "---\n",
        f"## 結果一覧  {today}\n",
        "| 銘柄 | スコア | 株価 | MA50 | MA150 | MA200 | RS | 高値比 | 安値比 |",
        "|-----|--------|------|------|-------|-------|-----|--------|--------|",
    ]

    for r in results:
        star = "★" if r["passed_all"] else ""
        lines.append(
            f"| {star}{r['ticker']} | {r['score']}/8 | {r['price']} | {r['ma50']} "
            f"| {r['ma150']} | {r['ma200']} | {r['rs_rating']} "
            f"| {r['dist_from_high_pct']:+.1f}% | +{r['rise_from_low_pct']:.1f}% |"
        )

    lines.append("\n---\n")
    lines.append("## 条件別詳細\n")
    for r in results:
        if r["score"] >= 6:
            mark = "★ 全条件クリア" if r["passed_all"] else f"{r['score']}/8条件"
            lines.append(f"### {r['ticker']}  [{mark}]\n")
            for d in r["details"]:
                icon = "✓" if d["passed"] else "✗"
                lines.append(f"- {icon} {d['label']}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
