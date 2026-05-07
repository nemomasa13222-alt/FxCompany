# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート バックテスト
実行: python japan_stocks/backtest_minervini.py

過去データで8条件の有効性を検証する。
月次で条件を評価し、その後1ヶ月・3ヶ月・6ヶ月のリターンを追跡する。
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from concurrent.futures import ThreadPoolExecutor, as_completed
import data as dt
import minervini_screener as mv
import jpx_universe as jpx

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START       = "2022-01-01"   # バックテスト用データ開始（長めに取る）
BACKTEST_START   = "2023-01-01"   # バックテスト開始日
BACKTEST_MONTHS  = 24             # 何ヶ月分を検証するか
FORWARD_PERIODS  = [21, 63, 126]  # 1ヶ月・3ヶ月・6ヶ月（営業日）
MARKET           = "prime"        # 対象市場
WORKERS          = 30             # 並列フェッチ数


def simulate_at_date(all_closes: dict[str, pd.Series], eval_date: pd.Timestamp) -> list[dict]:
    """
    特定日時点で8条件を評価して結果を返す。
    eval_date 時点のデータのみ使用（未来データ漏れなし）。
    """
    # eval_date 以前のデータに限定
    closes_at = {
        t: s.loc[:eval_date]
        for t, s in all_closes.items()
        if eval_date in s.index or s.index[-1] <= eval_date
    }
    closes_at = {t: s for t, s in closes_at.items() if len(s) >= 220}

    if not closes_at:
        return []

    rs_pcts = mv.calc_rs_percentiles(closes_at)

    results = []
    for ticker, close in closes_at.items():
        res = mv.check(close, rs_pcts.get(ticker, float("nan")))
        if res is not None:
            results.append({
                "ticker"    : ticker,
                "eval_date" : eval_date,
                **res,
            })
    return results


def calc_forward_return(close: pd.Series, from_date: pd.Timestamp, days: int) -> float | None:
    """from_date から days 営業日後のリターンを計算"""
    future = close.loc[from_date:]
    if len(future) <= days:
        return None
    return round((future.iloc[days] / future.iloc[0] - 1) * 100, 2)


def run_backtest():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  ミネルヴィニ バックテスト")
    print(f"  実行日時: {run_time}")
    print(f"{'='*60}\n")

    # ── データ取得（JPX全銘柄・並列）────────────────────────────────────
    print("JPX銘柄リスト取得中...")
    all_tickers = jpx.get_tickers_by_market(MARKET)
    print(f"  対象: {len(all_tickers)} 銘柄\n")

    print(f"データ取得中（{WORKERS}並列）...")
    all_closes = {}
    done = 0
    total = len(all_tickers)

    def _fetch(ticker):
        try:
            df = dt.fetch(ticker, start=DATA_START)
            if len(df) >= 300:
                return ticker, df["Close"]
        except Exception:
            pass
        return ticker, None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_fetch, t): t for t in all_tickers}
        for f in as_completed(futures):
            t, s = f.result()
            if s is not None:
                all_closes[t] = s
            done += 1
            if done % 200 == 0 or done == total:
                print(f"  {done}/{total}  有効: {len(all_closes)}", end="\r")

    print(f"\n  有効銘柄数: {len(all_closes)}\n")

    # ── 月次で評価日を生成 ─────────────────────────────────────────────
    eval_dates = pd.date_range(
        start=BACKTEST_START,
        periods=BACKTEST_MONTHS,
        freq="MS",          # 月初
    )

    # ── バックテスト実行 ───────────────────────────────────────────────
    all_records = []

    for eval_date in eval_dates:
        print(f"[{eval_date.strftime('%Y-%m')}] 評価中...")

        # eval_date に最も近い過去の営業日を探す
        nearest = None
        for t, s in all_closes.items():
            past = s.index[s.index <= eval_date]
            if len(past) > 0:
                nearest = past[-1]
                break

        if nearest is None:
            continue

        snapshots = simulate_at_date(all_closes, nearest)

        for snap in snapshots:
            ticker = snap["ticker"]
            close  = all_closes[ticker]

            record = {
                "eval_date"  : nearest.strftime("%Y-%m-%d"),
                "ticker"     : ticker,
                "passed_all" : snap["passed_all"],
                "score"      : snap["score"],
                "rs_rating"  : snap["rs_rating"],
                "price"      : snap["price"],
            }

            for days in FORWARD_PERIODS:
                ret = calc_forward_return(close, nearest, days)
                label = {21: "ret_1m", 63: "ret_3m", 126: "ret_6m"}[days]
                record[label] = ret

            all_records.append(record)

    if not all_records:
        print("データが不足しています。")
        return

    df = pd.DataFrame(all_records)

    # ── 統計集計 ───────────────────────────────────────────────────────
    _print_stats(df)

    # ── 結果保存 ───────────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"backtest_minervini_{ts}.md"
    _save_report(df, run_time, path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*60}\n")


def _print_stats(df: pd.DataFrame):
    print(f"\n{'='*60}")
    print("  バックテスト 集計結果")
    print(f"{'='*60}")

    passed = df[df["passed_all"] == True]
    failed = df[df["passed_all"] == False]

    for label, subset, name in [
        ("ret_1m", passed, "全条件クリア（1ヶ月後）"),
        ("ret_3m", passed, "全条件クリア（3ヶ月後）"),
        ("ret_6m", passed, "全条件クリア（6ヶ月後）"),
        ("ret_1m", failed, "条件未達（1ヶ月後）"),
        ("ret_3m", failed, "条件未達（3ヶ月後）"),
        ("ret_6m", failed, "条件未達（6ヶ月後）"),
    ]:
        col = subset[label].dropna()
        if len(col) == 0:
            continue
        print(f"\n  {name}  (n={len(col)})")
        print(f"    平均リターン : {col.mean():+.2f}%")
        print(f"    中央値       : {col.median():+.2f}%")
        print(f"    勝率（+0%超）: {(col > 0).mean() * 100:.1f}%")
        print(f"    最大         : {col.max():+.2f}%")
        print(f"    最小         : {col.min():+.2f}%")


def _save_report(df: pd.DataFrame, run_time: str, path: Path):
    passed = df[df["passed_all"] == True]
    failed = df[df["passed_all"] == False]

    lines = [
        "# ミネルヴィニ・トレンドテンプレート バックテスト結果\n",
        f"実行日時: {run_time}  \n",
        f"検証期間: {df['eval_date'].min()} ～ {df['eval_date'].max()}  \n",
        f"検査銘柄-日数: {len(df)} レコード  \n",
        "---\n",
        "## パフォーマンス比較\n",
        "| グループ | n | 平均1ヶ月 | 平均3ヶ月 | 平均6ヶ月 | 勝率(3ヶ月) |",
        "|---------|---|---------|---------|---------|-----------|",
    ]

    def row(name, subset):
        def stat(col):
            s = subset[col].dropna()
            return f"{s.mean():+.1f}%" if len(s) > 0 else "N/A"
        winrate = subset["ret_3m"].dropna()
        wr = f"{(winrate > 0).mean()*100:.0f}%" if len(winrate) > 0 else "N/A"
        return f"| {name} | {len(subset)} | {stat('ret_1m')} | {stat('ret_3m')} | {stat('ret_6m')} | {wr} |"

    lines.append(row("全8条件クリア", passed))
    lines.append(row("条件未達", failed))

    # スコア別集計
    lines.append("\n## スコア別 3ヶ月平均リターン\n")
    lines.append("| スコア | n | 平均3ヶ月リターン | 勝率 |")
    lines.append("|--------|---|----------------|------|")
    for score in range(8, -1, -1):
        sub = df[df["score"] == score]["ret_3m"].dropna()
        if len(sub) > 0:
            lines.append(f"| {score}/8 | {len(sub)} | {sub.mean():+.1f}% | {(sub>0).mean()*100:.0f}% |")

    # 全条件クリア銘柄の詳細
    if len(passed) > 0:
        lines.append("\n## 全条件クリア 銘柄一覧\n")
        lines.append("| 評価日 | 銘柄 | 株価 | RS | 1ヶ月後 | 3ヶ月後 | 6ヶ月後 |")
        lines.append("|--------|------|------|-----|--------|--------|--------|")
        for _, r in passed.iterrows():
            def fmt(v):
                return f"{v:+.1f}%" if pd.notna(v) else "N/A"
            lines.append(
                f"| {r['eval_date']} | {r['ticker']} | {r['price']} | {r['rs_rating']} "
                f"| {fmt(r['ret_1m'])} | {fmt(r['ret_3m'])} | {fmt(r['ret_6m'])} |"
            )

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run_backtest()
