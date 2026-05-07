# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート バックテスト v2
実行: python japan_stocks/backtest_minervini_v2.py

v1からの改善点:
  1. エントリー: 月次評価→ 20日高値ブレイクアウト当日
  2. 損切り    : なし→ -7%で強制決済
  3. RS計算   : 銘柄内ランキング→ 日経225対比の相対強度
  4. 市場フィルター: なし→ 日経225 > MA200 のときのみ稼働
"""

import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
import jpx_universe as jpx

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START      = "2022-01-01"
BACKTEST_START  = "2023-04-01"   # MA200確立に13ヶ月必要なため遅らせる
NIKKEI_TICKER   = "^N225"
MARKET          = "prime"
WORKERS         = 30
STOP_LOSS_PCT   = 0.07           # 損切りライン: -7%
MAX_HOLD_DAYS   = 126            # 最大保有: 6ヶ月


# ── 前処理：1銘柄分のシグナルを一括計算 ──────────────────────────────────────

def build_signals(close: pd.Series, n225: pd.Series,
                  n225_ma200: pd.Series) -> pd.DataFrame:
    """
    1銘柄分の日次シグナルフラグを事前計算して返す。
    未来データ漏れなし（全て当日終値 or shift済み値のみ使用）。
    """
    n225_aligned    = n225.reindex(close.index, method="ffill")
    n225_ma200_aln  = n225_ma200.reindex(close.index, method="ffill")

    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    high_52w = close.rolling(252).max()
    low_52w  = close.rolling(252).min()

    # ── 8条件 ────────────────────────────────────────────────────────────────
    c1 = (close > ma150) & (close > ma200)
    c2 = ma150 > ma200
    c3 = ma200 > ma200.shift(20)          # 1ヶ月前より上昇
    c4 = (ma50 > ma150) & (ma50 > ma200)
    c5 = close >= low_52w * 1.25
    c6 = close >= high_52w * 0.75
    c8 = close > ma50

    # ── RS vs 日経225 ─────────────────────────────────────────────────────────
    # 株の12ヶ月リターン - 日経の12ヶ月リターン > 0 で相対優位
    stock_12m  = close / close.shift(252) - 1
    n225_12m   = n225_aligned / n225_aligned.shift(252) - 1
    rs_relative = stock_12m - n225_12m    # プラス = 日経よりアウトパフォーム
    c7 = rs_relative > 0                  # 日経225を上回っていること

    # ── ブレイクアウト ────────────────────────────────────────────────────────
    # 今日の終値 > 昨日時点の直近20日最高値（未来漏れなし）
    prev_20d_high = close.rolling(20).max().shift(1)
    breakout = close > prev_20d_high

    # ── 市場フィルター ────────────────────────────────────────────────────────
    market_bull = n225_aligned > n225_ma200_aln

    # ── 全条件 ────────────────────────────────────────────────────────────────
    all8     = c1 & c2 & c3 & c4 & c5 & c6 & c7 & c8
    entry_ok = all8 & breakout & market_bull

    df = pd.DataFrame({
        "close"    : close,
        "entry_ok" : entry_ok,
        "all8"     : all8,
    }, index=close.index)

    return df


# ── トレードシミュレーション（1銘柄）────────────────────────────────────────

def simulate_trades(ticker: str, close: pd.Series, sig: pd.DataFrame) -> list[dict]:
    """
    ブレイクアウトシグナル当日に買い、損切り or 最大保有で決済。
    同一銘柄は1ポジションのみ（前のトレードが終わるまで新規なし）。
    """
    trades   = []
    in_trade = False
    entry_px = 0.0
    entry_dt = None

    start_ts = pd.Timestamp(BACKTEST_START)

    for i, (dt_idx, row) in enumerate(sig.iterrows()):
        if dt_idx < start_ts:
            continue

        if in_trade:
            cur_px = row["close"]
            hold   = (dt_idx - entry_dt).days

            # 損切り判定
            if cur_px <= entry_px * (1 - STOP_LOSS_PCT):
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, dt_idx,
                                   entry_px, cur_px, ret, "stop", hold))
                in_trade = False
                continue

            # 最大保有
            if hold >= MAX_HOLD_DAYS:
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, dt_idx,
                                   entry_px, cur_px, ret, "time", hold))
                in_trade = False
                continue

        else:
            if row["entry_ok"]:
                in_trade = True
                entry_px = row["close"]
                entry_dt = dt_idx

    return trades


def _rec(ticker, entry_dt, exit_dt, entry_px, exit_px, ret, reason, hold):
    return {
        "ticker"    : ticker,
        "entry_date": entry_dt.strftime("%Y-%m-%d"),
        "exit_date" : exit_dt.strftime("%Y-%m-%d"),
        "entry_px"  : round(entry_px, 1),
        "exit_px"   : round(exit_px, 1),
        "ret_pct"   : round(ret, 2),
        "reason"    : reason,
        "hold_days" : hold,
    }


# ── 集計・表示 ────────────────────────────────────────────────────────────────

def print_stats(df: pd.DataFrame):
    print(f"\n{'='*60}")
    print("  バックテスト v2  集計結果")
    print(f"{'='*60}")

    if df.empty:
        print("  トレードなし")
        return

    ret = df["ret_pct"]
    print(f"\n  総トレード数 : {len(df)}")
    print(f"  平均リターン : {ret.mean():+.2f}%")
    print(f"  中央値       : {ret.median():+.2f}%")
    print(f"  勝率         : {(ret > 0).mean()*100:.1f}%")
    print(f"  損切り発生率 : {(df['reason']=='stop').mean()*100:.1f}%")
    print(f"  平均保有日数 : {df['hold_days'].mean():.1f}日")
    print(f"  最大利益     : {ret.max():+.2f}%")
    print(f"  最大損失     : {ret.min():+.2f}%")
    print(f"  プロフィットファクター: {_pf(ret):.2f}")

    # 年別
    df["year"] = pd.to_datetime(df["entry_date"]).dt.year
    print("\n  【年別内訳】")
    for yr, g in df.groupby("year"):
        r = g["ret_pct"]
        print(f"  {yr}:  {len(g):3d}件  平均{r.mean():+.2f}%  "
              f"勝率{(r>0).mean()*100:.0f}%  PF{_pf(r):.2f}")

    # 決済理由別
    print("\n  【決済理由別】")
    for reason, g in df.groupby("reason"):
        r = g["ret_pct"]
        label = "損切り" if reason == "stop" else "期間満了"
        print(f"  {label}:  {len(g):3d}件  平均{r.mean():+.2f}%  "
              f"勝率{(r>0).mean()*100:.0f}%")


def _pf(ret: pd.Series) -> float:
    wins  = ret[ret > 0].sum()
    loses = abs(ret[ret < 0].sum())
    return wins / loses if loses > 0 else float("inf")


def save_report(df: pd.DataFrame, run_time: str, path: Path):
    if df.empty:
        path.write_text("トレードなし\n", encoding="utf-8")
        return

    ret = df["ret_pct"]
    df["year"] = pd.to_datetime(df["entry_date"]).dt.year

    lines = [
        "# ミネルヴィニ バックテスト v2 結果\n",
        f"実行日時: {run_time}  \n",
        f"検証期間: {df['entry_date'].min()} ～ {df['entry_date'].max()}  \n",
        f"対象市場: 東証プライム  \n",
        "---\n",
        "## 改善点（v1 → v2）\n",
        "- エントリー: 月次評価 → 20日高値ブレイクアウト当日",
        "- 損切り: なし → -7%で強制決済",
        "- RS計算: 銘柄内ランキング → 日経225対比の相対強度",
        "- 市場フィルター: なし → 日経225 > MA200のときのみ稼働\n",
        "---\n",
        "## 全体サマリー\n",
        f"| 指標 | 値 |",
        f"|------|-----|",
        f"| 総トレード数 | {len(df)} |",
        f"| 平均リターン | {ret.mean():+.2f}% |",
        f"| 中央値 | {ret.median():+.2f}% |",
        f"| 勝率 | {(ret>0).mean()*100:.1f}% |",
        f"| 損切り発生率 | {(df['reason']=='stop').mean()*100:.1f}% |",
        f"| 平均保有日数 | {df['hold_days'].mean():.1f}日 |",
        f"| 最大利益 | {ret.max():+.2f}% |",
        f"| 最大損失 | {ret.min():+.2f}% |",
        f"| PF | {_pf(ret):.2f} |\n",
        "## 年別内訳\n",
        "| 年 | 件数 | 平均リターン | 勝率 | PF |",
        "|-----|------|------------|------|-----|",
    ]

    for yr, g in df.groupby("year"):
        r = g["ret_pct"]
        lines.append(f"| {yr} | {len(g)} | {r.mean():+.2f}% "
                     f"| {(r>0).mean()*100:.0f}% | {_pf(r):.2f} |")

    lines += [
        "\n## 全トレード一覧（上位50件）\n",
        "| 銘柄 | 買い日 | 売り日 | 買値 | 売値 | リターン | 理由 | 保有日数 |",
        "|------|--------|--------|------|------|---------|------|---------|",
    ]

    for _, r in df.nlargest(50, "ret_pct").iterrows():
        lines.append(
            f"| {r['ticker']} | {r['entry_date']} | {r['exit_date']} "
            f"| {r['entry_px']} | {r['exit_px']} | {r['ret_pct']:+.1f}% "
            f"| {'損切り' if r['reason']=='stop' else '期間'} | {r['hold_days']}日 |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  ミネルヴィニ バックテスト v2（本格版）")
    print(f"  実行日時: {run_time}")
    print(f"  エントリー: 20日高値ブレイクアウト")
    print(f"  損切り: -{STOP_LOSS_PCT*100:.0f}%  最大保有: {MAX_HOLD_DAYS}日")
    print(f"  市場フィルター: 日経225 > MA200")
    print(f"  RS: 日経225対比アウトパフォーム")
    print(f"{'='*60}\n")

    # ── 日経225取得（市場フィルター + RSベンチマーク）────────────────────
    print("日経225データ取得中...")
    n225_df  = dt.fetch(NIKKEI_TICKER, start=DATA_START)
    n225     = n225_df["Close"]
    n225_ma200 = n225.rolling(200).mean()
    bull_days = (n225 > n225_ma200).sum()
    total_days = len(n225)
    print(f"  日経225取得: {len(n225)}日  "
          f"MA200超: {bull_days}日 ({bull_days/total_days*100:.0f}%)\n")

    # ── 全銘柄データ取得 ──────────────────────────────────────────────────
    print("JPX銘柄リスト取得中...")
    tickers = jpx.get_tickers_by_market(MARKET)
    print(f"  対象: {len(tickers)} 銘柄\n")

    print(f"株価データ取得中（{WORKERS}並列）...")
    all_closes = {}
    done, total = 0, len(tickers)

    def _fetch(t):
        try:
            df = dt.fetch(t, start=DATA_START)
            if len(df) >= 300:
                return t, df["Close"]
        except Exception:
            pass
        return t, None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_fetch, t): t for t in tickers}
        for f in as_completed(futures):
            t, s = f.result()
            if s is not None:
                all_closes[t] = s
            done += 1
            if done % 300 == 0 or done == total:
                print(f"  {done}/{total}  有効: {len(all_closes)}", end="\r")

    print(f"\n  有効銘柄数: {len(all_closes)}\n")

    # ── シグナル計算 + トレードシミュレーション ───────────────────────────
    print("シグナル計算 + トレードシミュレーション中...")
    all_trades = []

    for i, (ticker, close) in enumerate(all_closes.items()):
        if i % 200 == 0:
            print(f"  {i}/{len(all_closes)} 銘柄処理中...", end="\r")
        try:
            sig    = build_signals(close, n225, n225_ma200)
            trades = simulate_trades(ticker, close, sig)
            all_trades.extend(trades)
        except Exception:
            pass

    print(f"\n  完了: {len(all_trades)} トレード検出\n")

    if not all_trades:
        print("トレードなし。パラメータを見直してください。")
        return

    df = pd.DataFrame(all_trades)

    # ── 集計表示 ──────────────────────────────────────────────────────────
    print_stats(df)

    # ── 保存 ──────────────────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"backtest_v2_{ts}.md"
    save_report(df, run_time, path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
