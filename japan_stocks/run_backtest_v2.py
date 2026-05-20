# -*- coding: utf-8 -*-
"""
クロスセクター共有資本プール版バックテスト実行スクリプト
実行: python japan_stocks/run_backtest_v2.py

処理フロー:
  1. run_backtest.py と同じデータロード・セクター指数構築
  2. 全セクターの分類キャッシュを事前計算
  3. IS期間 (2022-01-01 ~ 2023-12-31) でクロスセクターバックテスト実行
  4. IS期間でロバストネステスト (sector_min_rise: 1,2,3 × min_gap: 1,2,3 = 9通り)
  5. 全期間 (2022-01-01 ~ 2026-05-08) でも最適パラメータで実行してOOS確認
  6. 結果をprintとCSV保存
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path
from itertools import product

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import sector_index as si
from backtest_stocks import (
    BacktestConfig, Trade,
    compute_stats, save_report,
    _precompute_classifications, _get_close,
    run_cross_sector,
)
from run_backtest import (
    CANDIDATE_SECTORS, N_ACTIVE_SECTORS, SMA_WINDOW, RANKING_WINDOW,
    DATA_START, IS_END, OOS_START, TRADE_START,
    compute_active_sector_dates,
)

RESULTS_DIR = Path(__file__).parent / "results" / "backtest_v2"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 全期間終端
FULL_END = "2026-05-20"

# ── ベースパラメータ（v2-f採用設定） ────────────────────────────────────────
BASE_CONFIG = dict(
    sector_min_rise = 2.0,
    min_gap         = 3.0,
    risk_pct        = 0.5,
    stop_dist_pct   = 1.5,
    min_corr        = 0.6,
    max_positions   = 3,
)


# ── データロード（run_backtest._load_all_sectors と同等） ─────────────────────

def _load_all_sectors() -> dict[str, dict]:
    """CANDIDATE_SECTORS の株価・始値を取得"""
    import data as dt
    from jquants import JQuantsClient

    client = JQuantsClient()
    master = client.get_stock_list()

    prime = master[master["MktNm"].str.contains("プライム", na=False)].copy()
    prime["Code"] = prime["Code"].astype(str).str.zfill(4)

    MAX_STOCKS_PER_SECTOR = 20
    MIN_STOCKS_PER_SECTOR = 5

    result: dict[str, dict] = {}
    sectors = prime.groupby(["S33", "S33Nm"])
    print(f"\n対象業種: {len(sectors)} / 銘柄総数: {len(prime)}")

    for (s33_code, s33_name), group in sectors:
        if s33_name not in CANDIDATE_SECTORS:
            continue

        codes = group["Code"].tolist()
        if len(codes) < MIN_STOCKS_PER_SECTOR:
            print(f"  [{s33_name}] {len(codes)}銘柄 → スキップ")
            continue

        codes = sorted(codes)[:MAX_STOCKS_PER_SECTOR]

        def _to_yf(c: str) -> str:
            c = str(c).zfill(5)
            return (c[:4] if c.endswith("0") else c) + ".T"
        tickers = [_to_yf(c) for c in codes]

        print(f"  [{s33_name}] {len(tickers)}銘柄 取得中...", end=" ", flush=True)

        stocks_prices: dict[str, pd.Series] = {}
        stocks_opens:  dict[str, pd.Series] = {}
        for ticker in tickers:
            try:
                df = dt.fetch(ticker, start=DATA_START)
                if len(df) >= 120:
                    stocks_prices[ticker] = df["Close"]
                    if "Open" in df.columns:
                        stocks_opens[ticker] = df["Open"]
            except Exception:
                pass

        if len(stocks_prices) < MIN_STOCKS_PER_SECTOR:
            print(f"有効{len(stocks_prices)}銘柄 → スキップ")
            continue

        print(f"有効{len(stocks_prices)}銘柄 OK")
        result[s33_name] = {"stocks": stocks_prices, "opens": stocks_opens}

    print(f"\n有効業種数: {len(result)}")
    return result


# ── 統計表示ヘルパー ──────────────────────────────────────────────────────────

def _print_stats(stats: dict, label: str) -> None:
    cost = stats.get("total_cost_jpy", 0)
    print(
        f"  [{label}] "
        f"件数:{stats['total_trades']}  勝率:{stats['win_rate']}%  "
        f"PF:{stats['profit_factor']}  DD:{stats['max_drawdown_pct']}%  "
        f"損益:{stats['total_pnl_jpy']:+,.0f}円  コスト:{cost:,.0f}円"
    )


def _split_period(trades: list[Trade], start: str, end: str) -> list[Trade]:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    return [t for t in trades if s <= t.entry_date <= e and t.exit_reason != "end"]


def _to_df(trades: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame([{
        "entry_date"  : str(t.entry_date)[:10],
        "exit_date"   : str(t.exit_date)[:10],
        "sector"      : t.sector_name,
        "ticker"      : t.ticker,
        "entry_price" : t.entry_price,
        "exit_price"  : t.exit_price,
        "shares"      : t.shares,
        "pnl_jpy"     : t.pnl_jpy,
        "net_pnl_jpy" : t.net_pnl_jpy,
        "exit_reason" : t.exit_reason,
    } for t in trades])


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*60}")
    print(f"  クロスセクター共有資本プール版バックテスト v2")
    print(f"  実行日時: {run_time}")
    print(f"  IS: {TRADE_START} ~ {IS_END}  |  OOS: {OOS_START} ~ {FULL_END}")
    print(f"  候補プール: TOP10業種  max_positions=3 (共有)")
    print(f"{'='*60}")

    # ── データ取得 ────────────────────────────────────────────────────────────
    sectors = _load_all_sectors()

    # ── セクター指数・銘柄辞書構築 ────────────────────────────────────────────
    print("\nセクター指数構築中...")
    sector_indices: dict[str, pd.Series]               = {}
    sector_stocks:  dict[str, dict[str, pd.DataFrame]] = {}
    sector_opens:   dict[str, dict[str, pd.Series]]    = {}

    for name, raw in sectors.items():
        stocks_prices = raw.get("stocks", {})
        if not stocks_prices:
            continue
        idx = si.build_from_price_dict(stocks_prices, name=name)
        if idx.empty:
            print(f"  [{name}] 指数構築失敗。スキップ。")
            continue
        sector_indices[name] = idx
        sector_stocks[name] = {
            ticker: close.rename("Close").to_frame()
            for ticker, close in stocks_prices.items()
        }
        sector_opens[name] = raw.get("opens", {})

    print(f"  指数構築完了: {len(sector_indices)}業種")

    # ── unified_dates 構築（全セクター日付の和集合） ─────────────────────────
    all_dates_set: set = set()
    for idx in sector_indices.values():
        all_dates_set.update(idx.index.tolist())
    unified_dates: list[pd.Timestamp] = sorted(all_dates_set)
    print(f"  統合日付系列: {len(unified_dates)}営業日 "
          f"({unified_dates[0].date()} ~ {unified_dates[-1].date()})")

    # ── 動的セクター選別（全期間） ────────────────────────────────────────────
    print("\n動的セクター選別を計算中...")
    active_dates = compute_active_sector_dates(
        sector_indices,
        n_active       = N_ACTIVE_SECTORS,
        sma_window     = SMA_WINDOW,
        ranking_window = RANKING_WINDOW,
    )

    # ── 分類キャッシュを全セクター分事前計算 ─────────────────────────────────
    print("\n全セクター分類キャッシュ計算中...")
    cfg_for_cache = BacktestConfig(**BASE_CONFIG)

    class_caches: dict[str, dict] = {}
    for name, idx in sector_indices.items():
        print(f"  [{name}] 分類計算中...")
        aligned_idx = idx.reindex(unified_dates)
        closes_for_cache: dict[str, pd.Series] = {}
        for ticker, df in sector_stocks[name].items():
            col = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
            closes_for_cache[ticker] = (
                pd.to_numeric(df[col], errors="coerce").reindex(unified_dates)
            )
        class_caches[name] = _precompute_classifications(
            aligned_idx,
            closes_for_cache,
            cfg_for_cache.classification_window,
            cfg_for_cache.reclassify_interval,
        )
    print(f"  分類キャッシュ完了: {len(class_caches)}業種")

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. IS期間バックテスト（最適パラメータ）
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  1. IS期間バックテスト（最適パラメータ）")
    print(f"  {TRADE_START} ~ {IS_END}")
    print(f"{'='*60}")

    is_dates = [d for d in unified_dates if pd.Timestamp(TRADE_START) <= d <= pd.Timestamp(IS_END)]

    is_config = BacktestConfig(**BASE_CONFIG, start_date=TRADE_START, end_date=IS_END)
    is_trades_all = run_cross_sector(
        sector_indices      = sector_indices,
        sector_stocks_all   = sector_stocks,
        sector_opens_all    = sector_opens,
        active_sector_dates = active_dates,
        class_caches        = class_caches,
        unified_dates       = is_dates,
        config              = is_config,
    )

    is_trades = [t for t in is_trades_all if t.exit_reason != "end"]
    is_stats  = compute_stats(is_trades, is_config.initial_capital)
    _print_stats(is_stats, f"IS {TRADE_START}~{IS_END}")

    if is_trades:
        p = RESULTS_DIR / f"cs_is_{ts}.csv"
        _to_df(is_trades).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"  IS CSV: {p.name}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. IS期間ロバストネステスト (3×3 = 9通り)
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  2. IS期間ロバストネステスト (sector_min_rise × min_gap = 9通り)")
    print(f"{'='*60}")

    rise_vals = [1.0, 2.0, 3.0]
    gap_vals  = [1.0, 2.0, 3.0]

    robust_rows: list[dict] = []

    for rise, gap in product(rise_vals, gap_vals):
        rob_config = BacktestConfig(
            **{**BASE_CONFIG, "sector_min_rise": rise, "min_gap": gap},
            start_date = TRADE_START,
            end_date   = IS_END,
        )
        rob_trades_all = run_cross_sector(
            sector_indices      = sector_indices,
            sector_stocks_all   = sector_stocks,
            sector_opens_all    = sector_opens,
            active_sector_dates = active_dates,
            class_caches        = class_caches,
            unified_dates       = is_dates,
            config              = rob_config,
        )
        rob_trades = [t for t in rob_trades_all if t.exit_reason != "end"]
        rob_stats  = compute_stats(rob_trades, rob_config.initial_capital)

        marker = " ★採用" if (rise == 2.0 and gap == 3.0) else ""
        print(
            f"  rise={rise:.0f}% gap={gap:.0f}%{marker}  "
            f"件数:{rob_stats['total_trades']}  勝率:{rob_stats['win_rate']}%  "
            f"PF:{rob_stats['profit_factor']}  DD:{rob_stats['max_drawdown_pct']}%  "
            f"損益:{rob_stats['total_pnl_jpy']:+,.0f}円"
        )
        robust_rows.append({
            "sector_min_rise" : rise,
            "min_gap"         : gap,
            "total_trades"    : rob_stats["total_trades"],
            "win_rate"        : rob_stats["win_rate"],
            "profit_factor"   : rob_stats["profit_factor"],
            "max_drawdown_pct": rob_stats["max_drawdown_pct"],
            "total_pnl_jpy"   : rob_stats["total_pnl_jpy"],
        })

    rob_df = pd.DataFrame(robust_rows)
    rob_path = RESULTS_DIR / f"cs_robustness_{ts}.csv"
    rob_df.to_csv(rob_path, index=False, encoding="utf-8-sig")
    print(f"\n  ロバストネステスト CSV: {rob_path.name}")

    # ロバストネス合格基準チェック
    n_black   = (rob_df["total_pnl_jpy"] > 0).sum()
    n_pf13    = (rob_df["profit_factor"] >= 1.3).sum()
    n_pf12    = (rob_df["profit_factor"] >= 1.2).sum()
    print(f"\n  合格基準チェック:")
    print(f"    全条件黒字: {n_black}/9  {'OK' if n_black == 9 else 'NG'}")
    print(f"    PF>=1.3:   {n_pf13}/9  {'OK' if n_pf13 >= 7 else 'NG'}")
    print(f"    PF>=1.2:   {n_pf12}/9  {'OK' if n_pf12 >= 8 else 'NG'}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. 全期間バックテスト（最適パラメータ、OOS確認）
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  3. 全期間バックテスト（OOS確認）")
    print(f"  {TRADE_START} ~ {FULL_END}")
    print(f"{'='*60}")

    full_config = BacktestConfig(**BASE_CONFIG, start_date=TRADE_START, end_date=FULL_END)
    full_trades_all = run_cross_sector(
        sector_indices      = sector_indices,
        sector_stocks_all   = sector_stocks,
        sector_opens_all    = sector_opens,
        active_sector_dates = active_dates,
        class_caches        = class_caches,
        unified_dates       = unified_dates,
        config              = full_config,
    )

    full_trades = [t for t in full_trades_all if t.exit_reason != "end"]
    is_t2   = _split_period(full_trades, TRADE_START, IS_END)
    oos_t   = _split_period(full_trades, OOS_START, FULL_END)

    full_stats = compute_stats(full_trades, full_config.initial_capital)
    is_stats2  = compute_stats(is_t2,       full_config.initial_capital)
    oos_stats  = compute_stats(oos_t,       full_config.initial_capital)

    _print_stats(full_stats, f"全期間 {TRADE_START}~{FULL_END}")
    _print_stats(is_stats2,  f"IS     {TRADE_START}~{IS_END}")
    _print_stats(oos_stats,  f"OOS    {OOS_START}~{FULL_END}")

    # IS/OOS比較サマリー
    print(f"\n  IS vs OOS 比較:")
    print(f"    {'指標':<16} {'IS':>10} {'OOS':>10} {'判定'}")
    print(f"    {'-'*50}")
    metrics = [
        ("勝率(%)",       "win_rate",         lambda a,b: "OK" if b >= a*0.9 else "NG"),
        ("PF",            "profit_factor",    lambda a,b: "OK" if b >= 1.2 else "NG"),
        ("最大DD(%)",     "max_drawdown_pct", lambda a,b: "OK" if b <= a*1.5 else "NG"),
        ("損益(万円)",    "total_pnl_jpy",    lambda a,b: "OK" if b > 0 else "NG"),
    ]
    for label, key, judge in metrics:
        iv = is_stats2.get(key, 0)
        ov = oos_stats.get(key, 0)
        if "損益" in label:
            print(f"    {label:<16} {iv/10000:>+9.1f}万 {ov/10000:>+9.1f}万  {judge(iv,ov)}")
        else:
            print(f"    {label:<16} {iv:>10.2f} {ov:>10.2f}  {judge(iv,ov)}")

    # ── CSV保存 ───────────────────────────────────────────────────────────────
    if full_trades:
        p = RESULTS_DIR / f"cs_full_{ts}.csv"
        _to_df(full_trades).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"\n  全期間 CSV: {p.name}")

    if oos_t:
        p = RESULTS_DIR / f"cs_oos_{ts}.csv"
        _to_df(oos_t).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"  OOS CSV   : {p.name}")

    print(f"\n{'='*60}")
    print(f"  完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  出力先: {RESULTS_DIR}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
