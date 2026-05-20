"""
パラメータグリッドサーチ（予備検証）
--------------------------------------
yfinance 50日データを使って閾値の感触を掴む。
特徴量（ACF・強弱・BB）は1回だけ計算し、閾値だけ変えて全組み合わせをバックテスト。

チューニング対象:
  STRENGTH_DIFF_THRESHOLD  … |強弱差| の最低値
  ACF_TREND_MIN            … TREND判定の ACF 下限
  ACF_REVERSION_MAX        … MEAN_REV 判定の ACF 上限

注意:
  50日データは統計的に少ない。傾向の把握のみに使うこと。
  本格 IS/OOS 検証は 3年データ取得後に実施する。

実行:
  python -m fx_market_classifier.param_search
  python -m fx_market_classifier.param_search --save   # PNG/CSV 保存
"""
from __future__ import annotations

import argparse
import math
from itertools import product
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # GUI不使用（バックグラウンド実行でのブロッキング防止）
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .backtest import BacktestEngine, BacktestConfig
from .classifier import MarketClassifier, MarketState
from .config import PAIR_CURRENCIES
from .data_fetcher import fetch_ohlcv

# ── グリッド定義 ──────────────────────────────────────────────────────────────

STRENGTH_GRID = [0.0003, 0.0005, 0.0008, 0.001, 0.0015, 0.002]
ACF_TREND_GRID = [0.02, 0.05, 0.08, 0.10, 0.15]
ACF_REV_GRID   = [-0.02, -0.05, -0.08, -0.10, -0.15]


# ── 閾値を変えて再分類 ────────────────────────────────────────────────────────

def _classify_bar(sd: float, acf: float,
                  str_thr: float, acf_pos: float, acf_neg: float) -> MarketState:
    if math.isnan(sd) or math.isnan(acf):
        return MarketState.NO_TRADE
    large = abs(sd) >= str_thr
    if large and acf >= acf_pos:
        return MarketState.TREND
    if large and acf <= acf_neg:       # 強弱差が大 + ACF負 → 平均回帰
        return MarketState.MEAN_REVERSION
    return MarketState.NO_TRADE        # 強弱差が小 → Chop


def reclassify(clf: MarketClassifier,
               str_thr: float, acf_pos: float, acf_neg: float) -> pd.DataFrame:
    """precomputed features にベクトル演算で新しい閾値を適用して states を再生成。"""
    out = {}
    for pair in clf.returns:
        sd = clf.strength_diff(pair)
        ac = clf.acf[pair]

        large    = sd.abs() >= str_thr
        is_trend = large & (ac >= acf_pos)
        is_rev   = large & (ac <= acf_neg)    # 強弱差が大 + ACF負 → 平均回帰

        states = pd.Series(MarketState.NO_TRADE, index=sd.index, name=pair, dtype=object)
        states[is_trend] = MarketState.TREND
        states[is_rev]   = MarketState.MEAN_REVERSION
        # NaN は NO_TRADE のまま
        nan_mask = sd.isna() | ac.isna()
        states[nan_mask] = MarketState.NO_TRADE
        out[pair] = states
    return pd.DataFrame(out)


# ── 1組み合わせのバックテスト ─────────────────────────────────────────────────

def run_one(clf: MarketClassifier, cfg: BacktestConfig,
            str_thr: float, acf_pos: float, acf_neg: float) -> dict:
    """閾値1セットでバックテストして指標を返す。"""
    original_states = clf.states
    try:
        clf.states = reclassify(clf, str_thr, acf_pos, acf_neg)
        engine = BacktestEngine(clf, cfg)
        trades_df = engine.run()
        m = engine.metrics()
        ms = engine.metrics_by_strategy()
    finally:
        clf.states = original_states   # 必ず元に戻す

    state_counts = clf.states.apply(lambda c: c.value_counts()).T.fillna(0)

    def _strat_metric(strategy: str, key: str, default=0.0):
        if ms.empty or strategy not in ms.index:
            return default
        row = ms.loc[strategy]
        return float(row[key]) if key in row else default

    total = max(1, len(clf.states.iloc[-1].dropna()))
    trend_pct = state_counts.get(MarketState.TREND, pd.Series(dtype=float)).sum() / max(1, state_counts.sum(axis=1).sum()) * 100
    mr_pct    = state_counts.get(MarketState.MEAN_REVERSION, pd.Series(dtype=float)).sum() / max(1, state_counts.sum(axis=1).sum()) * 100

    return {
        "str_thr":   str_thr,
        "acf_pos":   acf_pos,
        "acf_neg":   acf_neg,
        # 全体
        "trades":    m.get("total_trades", 0),
        "win_rate":  m.get("win_rate", 0.0),
        "pf":        m.get("profit_factor", 0.0),
        "total_pnl": m.get("total_pnl_pct", 0.0),
        "max_dd":    m.get("max_dd_pct", 0.0),
        # TREND
        "t_trades":  _strat_metric(MarketState.TREND.value,  "trades"),
        "t_wr":      _strat_metric(MarketState.TREND.value,  "win_rate"),
        "t_pf":      _strat_metric(MarketState.TREND.value,  "total_pnl"),
        # MEAN_REV
        "m_trades":  _strat_metric(MarketState.MEAN_REVERSION.value, "trades"),
        "m_wr":      _strat_metric(MarketState.MEAN_REVERSION.value, "win_rate"),
        "m_pf":      _strat_metric(MarketState.MEAN_REVERSION.value, "total_pnl"),
        # 状態割合
        "trend_pct": trend_pct,
        "mr_pct":    mr_pct,
    }


# ── グリッドサーチ本体 ────────────────────────────────────────────────────────

def grid_search(
    clf: MarketClassifier,
    strength_grid: list = STRENGTH_GRID,
    acf_trend_grid: list = ACF_TREND_GRID,
    acf_rev_grid: list   = ACF_REV_GRID,
    bt_config: BacktestConfig | None = None,
) -> pd.DataFrame:
    cfg = bt_config or BacktestConfig()
    combos = list(product(strength_grid, acf_trend_grid, acf_rev_grid))
    total  = len(combos)
    print(f"グリッドサーチ開始: {total}通り")

    rows = []
    for i, (str_thr, acf_pos, acf_neg) in enumerate(combos, 1):
        result = run_one(clf, cfg, str_thr, acf_pos, acf_neg)
        rows.append(result)
        if i % 10 == 0 or i == total:
            print(f"  {i}/{total}  最新: str={str_thr:.4f} acf+={acf_pos:.2f} acf-={acf_neg:.2f}"
                  f"  PF={result['pf']:.2f}  trades={result['trades']}")

    df = pd.DataFrame(rows)
    df = df.sort_values("pf", ascending=False).reset_index(drop=True)
    return df


# ── 結果の表示 ────────────────────────────────────────────────────────────────

def print_results(df: pd.DataFrame, top_n: int = 20):
    print(f"\n{'='*90}")
    print(f"グリッドサーチ結果（上位{top_n}件 / PF降順）   ※50日データの予備検証")
    print(f"{'='*90}")
    print(f"{'#':>3}  {'str_thr':>8}  {'acf+':>6}  {'acf-':>6}  "
          f"{'trades':>7}  {'win%':>6}  {'PF':>6}  {'pnl%':>7}  {'DD%':>7}  "
          f"{'T件':>5}  {'M件':>5}  {'T%':>5}  {'M%':>5}")
    print("-" * 90)
    for i, row in df.head(top_n).iterrows():
        pf_str = f"{row['pf']:.2f}" if not math.isinf(row['pf']) else " inf"
        print(f"{i+1:>3}  {row['str_thr']:>8.4f}  {row['acf_pos']:>6.2f}  {row['acf_neg']:>6.2f}  "
              f"{int(row['trades']):>7}  {row['win_rate']*100:>6.1f}  {pf_str:>6}  "
              f"{row['total_pnl']:>7.3f}  {row['max_dd']:>7.3f}  "
              f"{int(row['t_trades']):>5}  {int(row['m_trades']):>5}  "
              f"{row['trend_pct']:>5.1f}  {row['mr_pct']:>5.1f}")

    print(f"\n現在の採用値: str_thr=0.0008  acf+=0.05  acf-=-0.05")

    # 現在値の結果を探して表示
    current = df[(df.str_thr == 0.0008) & (df.acf_pos == 0.05) & (df.acf_neg == -0.05)]
    if not current.empty:
        r = current.iloc[0]
        pf_str = f"{r['pf']:.2f}" if not math.isinf(r['pf']) else "inf"
        rank = df.index[df.str_thr == 0.0008][0] + 1
        print(f"  → 現在値の順位: {rank}位 / {len(df)}位  PF={pf_str}  trades={int(r['trades'])}")


# ── ヒートマップ ──────────────────────────────────────────────────────────────

def plot_heatmaps(df: pd.DataFrame, save_path: str | None = None):
    """PF ヒートマップ: TREND用 (str_thr × acf_pos) と MEAN_REV用 (str_thr × acf_neg)"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle("Parameter Grid Search — Profit Factor Heatmap\n(50-day data: preliminary only)",
                 fontsize=11, fontweight="bold")

    def _draw_heatmap(ax, pivot_df, title: str, xlabel: str, ylabel: str):
        vals = pivot_df.values.astype(float)
        # inf → cap at 5 for display
        vals = np.where(np.isinf(vals), 5.0, vals)
        im = ax.imshow(vals, cmap="RdYlGn", vmin=0.5, vmax=2.0,
                       aspect="auto", origin="lower")
        ax.set_xticks(range(len(pivot_df.columns)))
        ax.set_xticklabels([f"{v:.4f}" for v in pivot_df.columns], rotation=40, ha="right", fontsize=7)
        ax.set_yticks(range(len(pivot_df.index)))
        ax.set_yticklabels([f"{v:.2f}" for v in pivot_df.index], fontsize=7)
        ax.set_xlabel(xlabel, fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_title(title, fontsize=9, fontweight="bold")
        # セルに値を表示
        for r in range(vals.shape[0]):
            for c in range(vals.shape[1]):
                v = vals[r, c]
                txt = f"{v:.2f}" if v < 5 else "inf"
                ax.text(c, r, txt, ha="center", va="center",
                        fontsize=6, color="black" if 0.8 < v < 1.8 else "white")
        plt.colorbar(im, ax=ax, label="Profit Factor")

    # TREND: str_thr × acf_pos (acf_neg で平均)
    trend_df = df.groupby(["acf_pos", "str_thr"])["pf"].mean().unstack("str_thr")
    _draw_heatmap(axes[0], trend_df,
                  "TREND Strategy\n(acf_pos × str_thr, avg over acf_neg)",
                  "Strength Diff Threshold", "ACF Trend Min")

    # MEAN_REV: str_thr × acf_neg (acf_pos で平均)
    mr_df = df.groupby(["acf_neg", "str_thr"])["pf"].mean().unstack("str_thr")
    _draw_heatmap(axes[1], mr_df,
                  "MEAN_REV Strategy\n(acf_neg × str_thr, avg over acf_pos)",
                  "Strength Diff Threshold", "ACF Reversion Max")

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"保存: {save_path}")
    else:
        plt.show()

    return fig


# ── エントリーポイント ─────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="パラメータグリッドサーチ")
    parser.add_argument("--days",  type=int, default=50, help="データ取得日数")
    parser.add_argument("--save",  action="store_true",  help="CSV/PNG 保存")
    parser.add_argument("--top",   type=int, default=20, help="表示件数")
    args = parser.parse_args(argv)

    # ── データ取得・特徴量計算（1回のみ） ──────────────────────────────────────
    print(f"データ取得中（直近{args.days}日）...")
    price_data = fetch_ohlcv(lookback_days=args.days)
    print(f"特徴量計算中...")
    clf = MarketClassifier(price_data)

    n_bars = sum(len(df) for df in price_data.values())
    print(f"準備完了: {len(price_data)}ペア  合計{n_bars:,}本")
    print(f"グリッド: {len(STRENGTH_GRID)}×{len(ACF_TREND_GRID)}×{len(ACF_REV_GRID)}"
          f" = {len(STRENGTH_GRID)*len(ACF_TREND_GRID)*len(ACF_REV_GRID)}通り\n")

    # ── グリッドサーチ ─────────────────────────────────────────────────────────
    results_df = grid_search(clf)

    # ── 結果表示 ───────────────────────────────────────────────────────────────
    print_results(results_df, top_n=args.top)

    if args.save:
        out_csv = Path("param_search_results.csv")
        results_df.to_csv(out_csv, index=False)
        print(f"\n保存: {out_csv}")
        plot_heatmaps(results_df, save_path="param_search_heatmap.png")
    else:
        plot_heatmaps(results_df)


if __name__ == "__main__":
    main()
