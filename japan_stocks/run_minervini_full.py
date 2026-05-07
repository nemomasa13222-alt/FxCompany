# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート 全銘柄スクリーナー
実行: python japan_stocks/run_minervini_full.py

JPX上場銘柄（約3,800社）全体にミネルヴィニ8条件を適用する。
並列フェッチで高速化。毎日引け後に実行する想定。

オプション:
  --market prime|standard|growth|all  対象市場（デフォルト: all）
  --workers N                          並列スレッド数（デフォルト: 20）
  --min-score N                        最低スコア（デフォルト: 6）
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

import data as dt
import minervini_screener as mv
import jpx_universe as jpx

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START = "2023-01-01"


# ── データ取得（1銘柄） ─────────────────────────────────────────────────────

def _fetch_one(ticker: str) -> tuple[str, object]:
    """1銘柄の終値Seriesを取得。失敗したらNoneを返す。"""
    try:
        df = dt.fetch(ticker, start=DATA_START)
        if len(df) >= 220:
            return ticker, df["Close"]
    except Exception:
        pass
    return ticker, None


# ── メイン ─────────────────────────────────────────────────────────────────

def main(market: str = "all", workers: int = 20, min_score: int = 6):
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  ミネルヴィニ 全銘柄スクリーナー（JPX全市場）")
    print(f"  実行日時: {run_time}")
    print(f"  対象市場: {market}  並列数: {workers}")
    print(f"{'='*60}\n")

    # ── ティッカーリスト取得 ───────────────────────────────────────────
    print("JPX銘柄リスト取得中...")
    try:
        tickers = jpx.get_tickers_by_market(market)
        ticker_info = jpx.get_ticker_info()
    except RuntimeError as e:
        print(f"エラー: {e}")
        return

    print(f"  対象銘柄数: {len(tickers)}\n")

    # ── 並列データ取得 ─────────────────────────────────────────────────
    print(f"株価データ取得中（{workers}並列）...")
    closes = {}
    done = 0
    total = len(tickers)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, series = future.result()
            if series is not None:
                closes[ticker] = series
            done += 1
            if done % 100 == 0 or done == total:
                print(f"  {done}/{total}  有効: {len(closes)}", end="\r")

    print(f"\n  データ取得完了: {len(closes)} / {total} 銘柄有効\n")

    # ── RS Rating 計算 ─────────────────────────────────────────────────
    print("RS Rating 計算中（全銘柄ランキング）...")
    rs_pcts = mv.calc_rs_percentiles(closes)

    # ── 8条件チェック ─────────────────────────────────────────────────
    print("8条件チェック中...")
    results = []
    for ticker, close in closes.items():
        res = mv.check(close, rs_pcts.get(ticker, float("nan")))
        if res is not None and res["score"] >= min_score:
            info = ticker_info.get(ticker, {})
            results.append({
                "ticker" : ticker,
                "name"   : info.get("name", ""),
                "market" : info.get("market", ""),
                "sector" : info.get("sector33", ""),
                **res,
            })

    # ── ソート ────────────────────────────────────────────────────────
    results.sort(key=lambda r: (-r["passed_all"], -r["score"], -(r["rs_rating"] or 0)))

    # ── 結果表示 ───────────────────────────────────────────────────────
    perfect = [r for r in results if r["passed_all"]]
    near    = [r for r in results if not r["passed_all"] and r["score"] >= 7]

    print(f"\n{'='*60}")
    print(f"  スクリーニング結果  ({datetime.today().strftime('%Y-%m-%d')})")
    print(f"  全8条件クリア: {len(perfect)} 銘柄")
    print(f"  7/8条件クリア: {len(near)} 銘柄")
    print(f"  検査銘柄数:    {len(closes)}")
    print(f"{'='*60}")

    if perfect:
        print("\n【★ 全条件クリア 銘柄】")
        for r in perfect:
            print(_fmt(r))
    else:
        print("\n  全条件クリアの銘柄なし")

    if near:
        print(f"\n【7/8 条件クリア 銘柄（上位10件）】")
        for r in near[:10]:
            print(_fmt(r))

    # ── Markdown保存 ───────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"minervini_full_{ts}.md"
    _save_markdown(results, perfect, near, run_time, len(closes), path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*60}\n")


def _fmt(r: dict) -> str:
    star = "★" if r["passed_all"] else f"  {r['score']}/8"
    return (f"  {star} [{r['ticker']}] {r['name'][:20]:<20}  "
            f"株価:{r['price']:>8.0f}円  RS:{r['rs_rating'] or '-':>3}  "
            f"高値比:{r['dist_from_high_pct']:>+6.1f}%  市場:{r['market'][:3]}")


def _save_markdown(results, perfect, near, run_time, n_valid, path: Path):
    today = datetime.today().strftime("%Y-%m-%d")
    lines = [
        f"# ミネルヴィニ 全銘柄スクリーニング結果\n",
        f"実行日時: {run_time}  \n",
        f"検査銘柄: {n_valid} 社  \n",
        "---\n",
        f"## 全8条件クリア: {len(perfect)} 銘柄  {today}\n",
    ]

    if perfect:
        lines += [
            "| 銘柄コード | 銘柄名 | 市場 | 株価 | RS | 高値比 | 安値比 | MA50 | MA150 | MA200 |",
            "|-----------|--------|------|------|-----|--------|--------|------|-------|-------|",
        ]
        for r in perfect:
            lines.append(
                f"| {r['ticker']} | {r['name']} | {r['market'][:3]} "
                f"| {r['price']} | {r['rs_rating']} "
                f"| {r['dist_from_high_pct']:+.1f}% | +{r['rise_from_low_pct']:.1f}% "
                f"| {r['ma50']} | {r['ma150']} | {r['ma200']} |"
            )
    else:
        lines.append("条件クリアの銘柄なし\n")

    lines += ["\n---\n", f"## 7/8条件クリア: {len(near)} 銘柄\n"]

    if near:
        lines += [
            "| 銘柄コード | 銘柄名 | 市場 | 株価 | RS | スコア | 未達条件 |",
            "|-----------|--------|------|------|-----|--------|---------|",
        ]
        for r in near[:30]:
            failed = [d["label"] for d in r["details"] if not d["passed"]]
            lines.append(
                f"| {r['ticker']} | {r['name']} | {r['market'][:3]} "
                f"| {r['price']} | {r['rs_rating']} | {r['score']}/8 "
                f"| {'、'.join(failed)} |"
            )

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--market",    default="all",
                        choices=["prime", "standard", "growth", "all"])
    parser.add_argument("--workers",   type=int, default=20)
    parser.add_argument("--min-score", type=int, default=6)
    args = parser.parse_args()

    main(market=args.market, workers=args.workers, min_score=args.min_score)
