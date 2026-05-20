# -*- coding: utf-8 -*-
"""
各セクター独立 100,000円 バックテスト
ロジックは v2-f そのまま。資本のみ「セクターごとに10万円」で独立運用。

実行: python _run_per_sector_bt.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "japan_stocks"))

import sector_index as si
from backtest_stocks import (
    BacktestConfig, Trade,
    compute_stats,
    _precompute_classifications,
    run_cross_sector,
)
from run_backtest import (
    CANDIDATE_SECTORS, N_ACTIVE_SECTORS, SMA_WINDOW, RANKING_WINDOW,
    DATA_START, IS_END, OOS_START, TRADE_START,
    compute_active_sector_dates,
)

RESULTS_DIR = Path("japan_stocks/results/backtest_v2")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

FULL_END = "2026-05-20"
CAPITAL_PER_SECTOR = 100_000   # セクターごとの独立資本

BASE_CONFIG = dict(
    sector_min_rise = 2.0,
    min_gap         = 3.0,
    risk_pct        = 0.5,
    stop_dist_pct   = 1.5,
    min_corr        = 0.6,
    max_positions   = 3,
)


def _load_all_sectors() -> dict:
    import data as dt
    from jquants import JQuantsClient

    client = JQuantsClient()
    master = client.get_stock_list()
    prime  = master[master["MktNm"].str.contains("プライム", na=False)].copy()
    prime["Code"] = prime["Code"].astype(str).str.zfill(4)

    result = {}
    for (_, s33_name), group in prime.groupby(["S33", "S33Nm"]):
        if s33_name not in CANDIDATE_SECTORS:
            continue
        codes   = sorted(group["Code"].tolist())[:20]
        tickers = [(c[:4] if c.zfill(5).endswith("0") else c.zfill(5)) + ".T" for c in codes]

        sp, so = {}, {}
        for t in tickers:
            try:
                df = dt.fetch(t, start=DATA_START)
                if len(df) >= 120:
                    sp[t] = df["Close"]
                    if "Open" in df.columns:
                        so[t] = df["Open"]
            except Exception:
                pass

        if len(sp) >= 5:
            result[s33_name] = {"stocks": sp, "opens": so}

    print(f"有効業種数: {len(result)}")
    return result


def _print_stats(stats: dict, label: str):
    print(f"  [{label}] "
          f"件数:{stats['total_trades']}  勝率:{stats['win_rate']}%  "
          f"PF:{stats['profit_factor']}  DD:{stats['max_drawdown_pct']}%  "
          f"損益:{stats['total_pnl_jpy']:+,.0f}円")


def _combined_stats(all_trades: list, n_sectors: int) -> dict:
    """全セクター合算の統計（DDはポートフォリオ合計で計算）"""
    if not all_trades:
        return {}

    total_capital = CAPITAL_PER_SECTOR * n_sectors
    pnl = [t.net_pnl_jpy for t in all_trades]
    wins = sum(1 for p in pnl if p > 0)
    n    = len(pnl)
    gp   = sum(p for p in pnl if p > 0)
    gl   = sum(-p for p in pnl if p < 0)

    # ポートフォリオレベルのDD（時系列順）
    sorted_trades = sorted(all_trades, key=lambda t: t.exit_date)
    cumsum = np.cumsum([t.net_pnl_jpy for t in sorted_trades])
    running_max = np.maximum.accumulate(cumsum)
    dd_arr = (running_max - cumsum) / total_capital * 100
    max_dd = round(float(dd_arr.max()), 2) if len(dd_arr) > 0 else 0.0

    return {
        "total_trades":    n,
        "win_rate":        round(wins / n * 100, 1) if n > 0 else 0,
        "profit_factor":   round(gp / gl, 2) if gl > 0 else 999,
        "total_pnl_jpy":   round(sum(pnl)),
        "max_drawdown_pct": max_dd,
    }


def main():
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*65}")
    print(f"  各セクター独立 100,000円 バックテスト")
    print(f"  実行日時: {now}")
    print(f"  IS: {TRADE_START}~{IS_END}  OOS: {OOS_START}~{FULL_END}")
    print(f"  資本: {CAPITAL_PER_SECTOR:,}円/セクター × 最大{len(CANDIDATE_SECTORS)}業種")
    print(f"{'='*65}")

    # ── データ取得 ────────────────────────────────────────────────────
    sectors = _load_all_sectors()

    sector_indices, sector_stocks, sector_opens = {}, {}, {}
    print("\nセクター指数構築中...")
    for name, raw in sectors.items():
        sp = raw["stocks"]
        idx = si.build_from_price_dict(sp, name=name)
        if idx.empty:
            continue
        sector_indices[name] = idx
        sector_stocks[name]  = {t: c.rename("Close").to_frame() for t, c in sp.items()}
        sector_opens[name]   = raw.get("opens", {})

    all_dates_set = set()
    for idx in sector_indices.values():
        all_dates_set.update(idx.index.tolist())
    unified_dates = sorted(all_dates_set)
    print(f"  {len(sector_indices)}業種 / {len(unified_dates)}営業日")

    # ── 動的選別（全期間） ────────────────────────────────────────────
    active_dates = compute_active_sector_dates(
        sector_indices, n_active=N_ACTIVE_SECTORS,
        sma_window=SMA_WINDOW, ranking_window=RANKING_WINDOW,
    )

    # ── 分類キャッシュ ────────────────────────────────────────────────
    print("\n分類キャッシュ計算中...")
    cfg_cache = BacktestConfig(**BASE_CONFIG)
    class_caches = {}
    for name, idx in sector_indices.items():
        aligned_idx = idx.reindex(unified_dates)
        closes = {
            t: pd.to_numeric(df["Close"] if "Close" in df.columns else df.iloc[:, 0],
                             errors="coerce").reindex(unified_dates)
            for t, df in sector_stocks[name].items()
        }
        class_caches[name] = _precompute_classifications(
            aligned_idx, closes,
            cfg_cache.classification_window,
            cfg_cache.reclassify_interval,
        )
    print(f"  完了: {len(class_caches)}業種")

    is_dates   = [d for d in unified_dates if pd.Timestamp(TRADE_START) <= d <= pd.Timestamp(IS_END)]
    full_dates = [d for d in unified_dates if pd.Timestamp(TRADE_START) <= d <= pd.Timestamp(FULL_END)]
    oos_dates  = [d for d in unified_dates if pd.Timestamp(OOS_START)   <= d <= pd.Timestamp(FULL_END)]

    # ══════════════════════════════════════════════════════════════════
    # 1. IS期間 — セクターごと独立実行
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'='*65}")
    print(f"  1. IS期間  各セクター独立 100,000円")
    print(f"  {TRADE_START} ~ {IS_END}")
    print(f"{'='*65}")

    is_all: list[Trade] = []
    for sector in sorted(sector_indices.keys()):
        cfg = BacktestConfig(**BASE_CONFIG,
                             initial_capital=CAPITAL_PER_SECTOR,
                             start_date=TRADE_START, end_date=IS_END)
        trades = run_cross_sector(
            sector_indices      = {sector: sector_indices[sector]},
            sector_stocks_all   = {sector: sector_stocks[sector]},
            sector_opens_all    = {sector: sector_opens.get(sector, {})},
            active_sector_dates = {sector: active_dates.get(sector, set())},
            class_caches        = {sector: class_caches[sector]},
            unified_dates       = is_dates,
            config              = cfg,
        )
        closed = [t for t in trades if t.exit_reason != "end"]
        is_all.extend(closed)
        s = compute_stats(closed, CAPITAL_PER_SECTOR)
        print(f"  {sector:<14} 件数:{s['total_trades']:>4}  "
              f"勝率:{s['win_rate']:>5}%  PF:{s['profit_factor']:>5}  "
              f"DD:{s['max_drawdown_pct']:>6}%  損益:{s['total_pnl_jpy']:>+10,.0f}円")

    n_sec = len(sector_indices)
    is_combined = _combined_stats(is_all, n_sec)
    print(f"\n  {'合計（'+str(n_sec)+'業種）':<14} 件数:{is_combined['total_trades']:>4}  "
          f"勝率:{is_combined['win_rate']:>5}%  PF:{is_combined['profit_factor']:>5}  "
          f"DD:{is_combined['max_drawdown_pct']:>6}%  "
          f"損益:{is_combined['total_pnl_jpy']:>+10,.0f}円")

    # ══════════════════════════════════════════════════════════════════
    # 2. 全期間 OOS確認
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'='*65}")
    print(f"  2. 全期間  各セクター独立 100,000円")
    print(f"  {TRADE_START} ~ {FULL_END}")
    print(f"{'='*65}")

    full_all: list[Trade] = []
    for sector in sorted(sector_indices.keys()):
        cfg = BacktestConfig(**BASE_CONFIG,
                             initial_capital=CAPITAL_PER_SECTOR,
                             start_date=TRADE_START, end_date=FULL_END)
        trades = run_cross_sector(
            sector_indices      = {sector: sector_indices[sector]},
            sector_stocks_all   = {sector: sector_stocks[sector]},
            sector_opens_all    = {sector: sector_opens.get(sector, {})},
            active_sector_dates = {sector: active_dates.get(sector, set())},
            class_caches        = {sector: class_caches[sector]},
            unified_dates       = full_dates,
            config              = cfg,
        )
        closed = [t for t in trades if t.exit_reason != "end"]
        full_all.extend(closed)

    full_combined = _combined_stats(full_all, n_sec)

    # IS / OOS分割
    is_trades  = [t for t in full_all if t.exit_date <= pd.Timestamp(IS_END)]
    oos_trades = [t for t in full_all if t.exit_date >= pd.Timestamp(OOS_START)]

    is_s  = _combined_stats(is_trades,  n_sec)
    oos_s = _combined_stats(oos_trades, n_sec)

    print(f"\n  {'指標':<18} {'IS':>12} {'OOS':>12}  {'判定'}")
    print(f"  {'-'*52}")
    print(f"  {'件数':<18} {is_s['total_trades']:>12} {oos_s['total_trades']:>12}")
    print(f"  {'勝率(%)':<18} {is_s['win_rate']:>12.1f} {oos_s['win_rate']:>12.1f}"
          f"  {'OK' if oos_s['win_rate'] >= is_s['win_rate']*0.8 else 'NG'}")
    print(f"  {'PF':<18} {is_s['profit_factor']:>12.2f} {oos_s['profit_factor']:>12.2f}"
          f"  {'OK' if oos_s['profit_factor'] >= 1.10 else 'NG'}")
    print(f"  {'最大DD(%)':<18} {is_s['max_drawdown_pct']:>12.2f} {oos_s['max_drawdown_pct']:>12.2f}"
          f"  {'OK' if oos_s['max_drawdown_pct'] <= is_s['max_drawdown_pct']*1.5 else 'NG'}")
    print(f"  {'損益(万円)':<18} {is_s['total_pnl_jpy']/10000:>+12.1f} {oos_s['total_pnl_jpy']/10000:>+12.1f}"
          f"  {'OK' if oos_s['total_pnl_jpy'] > 0 else 'NG'}")
    print(f"\n  合計資本: {CAPITAL_PER_SECTOR:,}円 × {n_sec}業種 = {CAPITAL_PER_SECTOR*n_sec:,}円")
    print(f"  全期間損益: {full_combined['total_pnl_jpy']:+,.0f}円  "
          f"({full_combined['total_pnl_jpy']/(CAPITAL_PER_SECTOR*n_sec)*100:+.1f}%)")

    # CSV保存
    rows = [{"entry_date": str(t.entry_date)[:10],
             "exit_date":  str(t.exit_date)[:10],
             "sector":     t.sector_name,
             "ticker":     t.ticker,
             "entry_price":t.entry_price,
             "exit_price": t.exit_price,
             "shares":     t.shares,
             "net_pnl_jpy":t.net_pnl_jpy,
             "exit_reason":t.exit_reason} for t in full_all]
    csv_path = RESULTS_DIR / f"per_sector_full_{ts}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  CSV保存: {csv_path.name}")
    print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
