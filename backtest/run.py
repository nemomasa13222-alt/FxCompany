# -*- coding: utf-8 -*-
"""
バックテスト実行エントリーポイント

使い方:
    python backtest/run.py

手順:
    1. backtest/config.py でパラメータを設定する
    2. backtest/strategy.py に条件を記述する
    3. このファイルを実行する（条件は変えない）
"""

import sys
import hashlib
from pathlib import Path
from datetime import datetime

# backtest フォルダを import パスに追加
sys.path.insert(0, str(Path(__file__).parent))

import config
import engine
import report
from strategy import entry_condition, exit_condition


def _hash_strategy() -> str:
    """strategy.py の内容をハッシュ化してトレーサビリティに使用"""
    strategy_path = Path(__file__).parent / "strategy.py"
    content = strategy_path.read_bytes()
    return hashlib.md5(content).hexdigest()[:12]


def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    strategy_hash = _hash_strategy()

    print(f"\n{'='*50}")
    print(f"  バックテスト開始")
    print(f"  実行日時: {run_time}")
    print(f"  条件ハッシュ: {strategy_hash}")
    print(f"{'='*50}\n")

    # ── データ読み込み ──────────────────────────────────────────────
    print("データ読み込み中...")
    df = engine.load_data(config.DATA_DIR)
    df = engine.filter_period(df, config.START_DATE, config.END_DATE)
    print(f"  {len(df):,} 本  ({df['datetime'].iloc[0]} 〜 {df['datetime'].iloc[-1]})\n")

    # ── IS / OOS 分割 ──────────────────────────────────────────────
    is_trades  = None
    oos_trades = None

    if config.IS_END_DATE:
        df_is  = engine.filter_period(df, config.START_DATE, config.IS_END_DATE)
        df_oos = df[df["datetime"] > df_is["datetime"].iloc[-1]].reset_index(drop=True)
        print(f"IS期間:  {len(df_is):,} 本  〜 {config.IS_END_DATE}")
        print(f"OOS期間: {len(df_oos):,} 本  {config.IS_END_DATE} 〜\n")

        print("IS バックテスト走査中...")
        is_trades = engine.run(df_is, entry_condition, exit_condition, config)
        print(f"  IS エントリー: {len(is_trades)} 回")

        print("OOS バックテスト走査中...")
        oos_trades = engine.run(df_oos, entry_condition, exit_condition, config)
        print(f"  OOS エントリー: {len(oos_trades)} 回\n")

        all_trades = is_trades + oos_trades
    else:
        print("バックテスト走査中...")
        all_trades = engine.run(df, entry_condition, exit_condition, config)
        print(f"  総エントリー: {len(all_trades)} 回\n")

    # ── 統計計算 ────────────────────────────────────────────────────
    checkpoint_stats = engine.compute_checkpoints(all_trades, config.STATS_CHECKPOINTS)
    vd = engine.verdict(all_trades, config.INSUFFICIENT_THRESHOLD)

    # ── 結果オブジェクト ────────────────────────────────────────────
    result = {
        "config"          : config,
        "trades"          : all_trades,
        "is_trades"       : is_trades,
        "oos_trades"      : oos_trades,
        "checkpoint_stats": checkpoint_stats,
        "verdict"         : vd,
        "strategy_hash"   : strategy_hash,
        "run_time"        : run_time,
    }

    # ── 出力 ────────────────────────────────────────────────────────
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = config.RESULTS_DIR / f"trades_{ts}.csv"
    md_path  = config.RESULTS_DIR / f"report_{ts}.md"
    pdf_path = config.RESULTS_DIR / f"report_{ts}.pdf"

    report.save_trades_csv(all_trades, csv_path)
    print(f"CSV保存:      {csv_path.name}")

    report.save_markdown(result, md_path)
    print(f"Markdown保存: {md_path.name}")

    report.save_pdf(result, pdf_path)
    print(f"PDF保存:      {pdf_path.name}")

    # ── サマリー表示 ────────────────────────────────────────────────
    overall = engine.compute_stats(all_trades)
    print(f"\n{'='*50}")
    print(f"  結果サマリー")
    print(f"{'='*50}")
    print(f"  総エントリー: {len(all_trades)} 回")
    if overall["win_rate"] is not None:
        print(f"  勝率:         {overall['win_rate']*100:.1f}%")
        print(f"  期待値:       {overall['expectancy']:+.2f} pips/トレード")
        pf_str = f"{overall['pf']:.2f}" if overall['pf'] != float('inf') else "∞"
        print(f"  PF:           {pf_str}")
        print(f"  最大DD:       {overall['max_dd_pips']:.1f} pips")
    print(f"  判定:         {vd}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
