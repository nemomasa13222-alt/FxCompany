# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 バックテスト実行スクリプト
実行: python japan_stocks/run_backtest.py

処理フロー:
  1. J-Quantsで33業種ユニバース全件取得
  2. 各セクターの合成セクター指数を構築（等加重）
  3. 毎営業日「セクター指数 > 20SMA かつ 上位N業種」を動的選別
  4. 選別業種内でセクター追いつき戦略をバックテスト
  5. 結果をCSV / Markdown で保存

【パラメータ変更点（相談役フィードバック反映）】
  - セクター上昇閾値: 2% → 5%
  - 最低乖離率: 1.5% → 3%
  - 業種選別: 固定TOP10 → 動的（20SMA超 & 上位5業種）
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import sector_index as si
from backtest_stocks import BacktestConfig, Trade, run as bt_run, compute_stats, save_report

RESULTS_DIR = Path(__file__).parent / "results" / "backtest"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── IS / OOS 設計 ──────────────────────────────────────────────────────────────
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--is-start", default="2022-01-01")
_args, _ = _parser.parse_known_args()

TRADE_START = _args.is_start
DATA_START  = str(pd.Timestamp(TRADE_START) - pd.DateOffset(years=1))[:10]
IS_END      = "2023-12-31"
OOS_START   = "2024-01-01"

DATA_SOURCE           = "all_sectors"
MAX_STOCKS_PER_SECTOR = 20
MIN_STOCKS_PER_SECTOR = 5

# ── 動的セクター選別パラメータ ────────────────────────────────────────────────
N_ACTIVE_SECTORS   = 5    # 毎日選ぶ上位業種数（候補プール10業種の中から）
SMA_WINDOW         = 20   # 上昇トレンド判定SMAウィンドウ（営業日）
RANKING_WINDOW     = 20   # 業種ランキング基準期間（営業日）

# IS成績でPF上位の10業種を候補プールとして固定（追いつき戦略が機能する業種）
# この中から動的に上位5業種を毎日選別する
CANDIDATE_SECTORS = {
    "ゴム製品",
    "鉄鋼",
    "小売業",
    "保険業",
    "サービス業",
    "不動産業",
    "ガラス･土石製品",
    "海運業",
    "化学",
    "卸売業",
}


# ── 動的セクター選別 ──────────────────────────────────────────────────────────

def compute_active_sector_dates(
    sector_indices: dict[str, pd.Series],
    n_active: int = N_ACTIVE_SECTORS,
    sma_window: int = SMA_WINDOW,
    ranking_window: int = RANKING_WINDOW,
) -> dict[str, set[pd.Timestamp]]:
    """
    毎営業日について、以下のルールで「アクティブ業種」を決定する：
      1. セクター指数 > その20日SMA（上昇トレンド条件）
      2. 直近ranking_window日のリターン > 0%（上昇中であること）
      3. 上記を満たす業種を直近リターン降順に並べ、上位N業種を選択

    Returns: {sector_name: {entry_allowed_date, ...}}
    """
    # 全業種の全日付を統合
    all_dates = sorted(
        set().union(*[set(idx.index) for idx in sector_indices.values()])
    )
    active: dict[str, set[pd.Timestamp]] = {s: set() for s in sector_indices}

    min_window = max(sma_window, ranking_window)

    for date_i, date in enumerate(all_dates):
        if date_i < min_window:
            continue

        qualifying: dict[str, float] = {}  # sector -> recent return

        for sector, idx in sector_indices.items():
            if date not in idx.index:
                continue

            # SMAウィンドウ分のデータを取得
            past_dates = [d for d in all_dates[:date_i + 1]]
            sma_slice  = past_dates[-sma_window:]
            rank_start = past_dates[-ranking_window - 1] if len(past_dates) > ranking_window else past_dates[0]

            try:
                sma_vals = idx.reindex(sma_slice).dropna()
                if len(sma_vals) < sma_window * 0.8:
                    continue
                sma_val  = float(sma_vals.mean())
                now_val  = float(idx[date])

                # 条件1: 指数 > SMA
                if now_val <= sma_val:
                    continue

                # 条件2: 直近リターン > 0%
                past_val = float(idx.get(rank_start, np.nan))
                if np.isnan(past_val) or past_val <= 0:
                    continue
                recent_ret = (now_val / past_val - 1) * 100
                if recent_ret <= 0:
                    continue

                qualifying[sector] = recent_ret

            except Exception:
                continue

        # 上位N業種を選択
        top_n = sorted(qualifying.items(), key=lambda x: x[1], reverse=True)[:n_active]
        for sector, _ in top_n:
            active[sector].add(date)

    # サマリー表示用
    total_days = len([d for d_i, d in enumerate(all_dates) if d_i >= min_window])
    print(f"\n  [動的選別] 対象日数: {total_days}日 / 上位{n_active}業種 / SMA{sma_window}日")
    for sector in sorted(sector_indices.keys()):
        cnt = len(active[sector])
        pct = cnt / total_days * 100 if total_days > 0 else 0
        if cnt > 0:
            print(f"    {sector[:12]:<12} 選択日数: {cnt}日 ({pct:.0f}%)")

    return active


# ── データ読み込み ─────────────────────────────────────────────────────────────

def _load_all_sectors() -> dict[str, dict]:
    """33業種全件を取得（固定フィルタなし）"""
    import data as dt
    from jquants import JQuantsClient

    client = JQuantsClient()
    master = client.get_stock_list()

    prime = master[master["MktNm"].str.contains("プライム", na=False)].copy()
    prime["Code"] = prime["Code"].astype(str).str.zfill(4)

    result: dict[str, dict] = {}
    sectors = prime.groupby(["S33", "S33Nm"])
    print(f"\n対象業種: {len(sectors)} / 銘柄総数: {len(prime)}")

    for (s33_code, s33_name), group in sectors:
        codes = group["Code"].tolist()
        if len(codes) < MIN_STOCKS_PER_SECTOR:
            print(f"  [{s33_name}] {len(codes)}銘柄 → スキップ")
            continue

        codes = sorted(codes)[:MAX_STOCKS_PER_SECTOR]

        def _to_yf(c: str) -> str:
            c = str(c).zfill(5)
            return (c[:4] if c.endswith("0") else c) + ".T"
        tickers = [_to_yf(c) for c in codes]

        # 候補プールのみ取得（IS実績でPF上位10業種）
        if s33_name not in CANDIDATE_SECTORS:
            continue
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


def _split_is_oos(trades: list[Trade]) -> tuple[list[Trade], list[Trade]]:
    is_trades  = [t for t in trades
                  if str(t.entry_date)[:10] <= IS_END and t.exit_reason != "end"]
    oos_trades = [t for t in trades
                  if str(t.entry_date)[:10] >= OOS_START and t.exit_reason != "end"]
    return is_trades, oos_trades


def _print_stats(stats: dict, label: str):
    print(f"\n  [{label}]")
    cost = stats.get('total_cost_jpy', 0)
    print(f"  件数: {stats['total_trades']}  勝率: {stats['win_rate']}%  "
          f"PF: {stats['profit_factor']}  DD: {stats['max_drawdown_pct']}%  "
          f"損益(コスト後): {stats['total_pnl_jpy']:+,.0f}円  コスト: {cost:,.0f}円")


def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  株式バックテスト -- セクター追いつき戦略 v2（動的選別）")
    print(f"  実行日時: {run_time}")
    print(f"  IS: {TRADE_START} ~ {IS_END}  |  OOS: {OOS_START}~ (封印)")
    print(f"  候補プール: TOP10業種 → 動的選別: 上位{N_ACTIVE_SECTORS}業種 / SMA{SMA_WINDOW}日 / ランキング{RANKING_WINDOW}日")
    print(f"{'='*60}")

    # パラメータ変更: 閾値を引き上げ
    config = BacktestConfig(
        start_date        = DATA_START,
        sector_min_rise   = 2.0,
        min_gap           = 3.0,
        risk_pct          = 0.5,
        stop_dist_pct     = 1.5,   # 3% → 1.5%（ポジション株数2倍、損切タイト）
        min_corr          = 0.6,   # 0.30 → 0.60（遅行確信度の閾値引き上げ）
    )
    print(f"  セクター上昇閾値: {config.sector_min_rise}%  乖離率閾値: {config.min_gap}%")
    print(f"  リスク/トレード: {config.risk_pct}%")

    # ── データ取得 ────────────────────────────────────────────────────────────
    sectors = _load_all_sectors()

    # ── セクター指数をすべて構築 ──────────────────────────────────────────────
    print("\nセクター指数構築中...")
    sector_indices: dict[str, pd.Series]              = {}
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
        sector_stocks[name]  = {
            ticker: close.rename("Close").to_frame()
            for ticker, close in stocks_prices.items()
        }
        sector_opens[name] = raw.get("opens", {})

    print(f"  指数構築完了: {len(sector_indices)}業種")

    # ── 動的セクター選別（全期間） ────────────────────────────────────────────
    print("\n動的セクター選別を計算中...")
    active_dates = compute_active_sector_dates(
        sector_indices,
        n_active       = N_ACTIVE_SECTORS,
        sma_window     = SMA_WINDOW,
        ranking_window = RANKING_WINDOW,
    )

    # ── バックテスト実行 ──────────────────────────────────────────────────────
    print("\nバックテスト実行中...")
    all_trades: list[Trade] = []

    for name in sorted(sector_indices.keys()):
        allowed = active_dates.get(name, set())
        if not allowed:
            continue  # 一度も選ばれなかった業種はスキップ

        print(f"  [{name}] 選択日数:{len(allowed)}日 バックテスト中...", end=" ", flush=True)
        trades = bt_run(
            sector_indices[name],
            sector_stocks[name],
            config,
            sector_name          = name,
            allowed_entry_dates  = allowed,
            stocks_opens         = sector_opens.get(name, {}),
        )
        all_trades.extend(trades)
        is_t, oos_t = _split_is_oos(trades)
        is_s = compute_stats(is_t, config.initial_capital)
        print(f"IS {is_s['total_trades']}件 勝率{is_s['win_rate']}% "
              f"PF{is_s['profit_factor']} {is_s['total_pnl_jpy']:+,.0f}円 | "
              f"OOS {len(oos_t)}件")

    # ── IS / OOS 集計 ─────────────────────────────────────────────────────────
    is_trades, oos_trades = _split_is_oos(all_trades)

    print(f"\n{'='*60}")
    print(f"  IS集計  [{TRADE_START} ~ {IS_END}]")
    print(f"{'='*60}")
    is_stats = compute_stats(is_trades, config.initial_capital)
    _print_stats(is_stats, "IS 全セクター（動的選別）")
    print(f"  総件数: {is_stats['total_trades']}  最終資金: {is_stats['final_capital']:,.0f}円")

    print(f"\n{'='*60}")
    print(f"  OOS [{OOS_START}~] -- 封印中 (Case A: 保有中除外済み)")
    print(f"  トレード数: {len(oos_trades)}件（未集計）")
    print(f"{'='*60}")

    # ── CSV保存 ───────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _to_df(trades):
        return pd.DataFrame([{
            "entry_date"  : str(t.entry_date)[:10],
            "exit_date"   : str(t.exit_date)[:10],
            "sector"      : t.sector_name,
            "ticker"      : t.ticker,
            "entry_price" : t.entry_price,
            "exit_price"  : t.exit_price,
            "shares"      : t.shares,
            "pnl_jpy"     : t.pnl_jpy,
            "exit_reason" : t.exit_reason,
        } for t in trades])

    if is_trades:
        p = RESULTS_DIR / f"sector_is_{ts}.csv"
        _to_df(is_trades).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"  IS CSV : {p.name}")

    if oos_trades:
        p = RESULTS_DIR / f"sector_oos_{ts}.csv"
        _to_df(oos_trades).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"  OOS CSV: {p.name}  <- 開封厳禁")

    path = RESULTS_DIR / f"backtest_{ts}.md"
    save_report(is_trades, is_stats, config, path,
                sector_name="全セクター IS（動的選別）", is_end_date=IS_END)
    print(f"  MD     : {path.name}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
