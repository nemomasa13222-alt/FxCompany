"""
USDJPY 5分足 探索チャート
----------------------------
3パネル構成:
  上段: 価格 + BB(1σ/3σ) + 市場状態を背景色で表示
  中段: ACF(lag=1, rolling 100) + 判定閾値
  下段: 通貨強弱差 (USD - JPY) + 判定閾値

背景色:
  水色  = TREND      （強弱差大 + ACF正）
  橙色  = MEAN_REV   （強弱差小 + ACF負）
  白/灰 = NO_TRADE

実行:
  python -m fx_market_classifier.explore
  python -m fx_market_classifier.explore --pair EURJPY --days 30
  python -m fx_market_classifier.explore --save          # PNG保存
"""
from __future__ import annotations

import argparse
from datetime import timezone

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .classifier import MarketClassifier, MarketState
from .config import ACF_REVERSION_MAX, ACF_TREND_MIN, STRENGTH_DIFF_THRESHOLD
from .data_fetcher import fetch_ohlcv

# ── スタイル ──────────────────────────────────────────────────────────────────
import matplotlib.font_manager as _fm
_JP_FONTS = ["Yu Gothic", "Meiryo", "MS Gothic", "IPAexGothic", "Noto Sans CJK JP"]
_available = {f.name for f in _fm.fontManager.ttflist}
_jp_font = next((f for f in _JP_FONTS if f in _available), None)

plt.rcParams.update({
    "figure.facecolor":  "#f8f9fc",
    "axes.facecolor":    "#ffffff",
    "axes.grid":         True,
    "grid.color":        "#e0e4ef",
    "grid.linewidth":    0.5,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "font.size":         8,
    **({"font.family": _jp_font} if _jp_font else {}),
})

_C_TREND = "#2196F3"   # 青
_C_MR    = "#FF9800"   # 橙
_C_NONE  = "#BDBDBD"   # 灰


# ── ユーティリティ ────────────────────────────────────────────────────────────

def _xfmt(ax: plt.Axes, freq: str = "3H"):
    """X軸を日時フォーマットに設定"""
    locator = mdates.HourLocator(interval=3)
    formatter = mdates.DateFormatter("%m/%d\n%H:%M")
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.tick_params(axis="x", labelsize=6.5)


def _fill_state(ax: plt.Axes, index: pd.DatetimeIndex, states: pd.Series):
    """状態に応じた背景色を塗る（axes座標で全高スパン）"""
    trans = ax.get_xaxis_transform()
    is_trend = (states == MarketState.TREND).values
    is_rev   = (states == MarketState.MEAN_REVERSION).values

    # NaN除去用マスク
    valid = ~pd.isna(states.values)

    ax.fill_between(index, 0, 1, where=is_trend & valid,
                    transform=trans, alpha=0.12, color=_C_TREND,
                    linewidth=0, label="TREND")
    ax.fill_between(index, 0, 1, where=is_rev & valid,
                    transform=trans, alpha=0.12, color=_C_MR,
                    linewidth=0, label="MEAN_REV")


def _legend_patches():
    return [
        mpatches.Patch(color=_C_TREND, alpha=0.5, label="TREND"),
        mpatches.Patch(color=_C_MR,   alpha=0.5, label="MEAN_REV"),
        mpatches.Patch(color=_C_NONE, alpha=0.5, label="NO_TRADE"),
    ]


# ── チャート描画 ──────────────────────────────────────────────────────────────

def plot_explore(
    pair: str,
    clf: MarketClassifier,
    save_path: str | None = None,
):
    df     = clf.price_data[pair]
    close  = df["Close"]
    index  = close.index

    # timezone-aware → matplotlib は UTC で扱う
    if index.tzinfo is None:
        index = index.tz_localize("UTC")

    acf_s  = clf.acf[pair].reindex(df.index)
    sd     = clf.strength_diff(pair).reindex(df.index)
    states = clf.states[pair].reindex(df.index)
    bb1    = clf.bb1[pair].reindex(df.index)
    bb3    = clf.bb3[pair].reindex(df.index)

    base_ccy, quote_ccy = pair[:3], pair[3:]
    n = len(close)

    # ── Figure ───────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 13), layout="constrained")
    fig.suptitle(
        f"{pair}  5min  ({str(index[0])[:10]} ~ {str(index[-1])[:10]})  "
        f"  n={n:,} bars",
        fontsize=11, fontweight="bold",
    )

    gs = fig.add_gridspec(
        4, 1,
        height_ratios=[5, 2, 2, 1],
        hspace=0.06,
    )
    ax1 = fig.add_subplot(gs[0])  # 価格
    ax2 = fig.add_subplot(gs[1], sharex=ax1)  # ACF
    ax3 = fig.add_subplot(gs[2], sharex=ax1)  # 強弱差
    ax4 = fig.add_subplot(gs[3], sharex=ax1)  # 状態バー

    # ── 上段: 価格 + BB ───────────────────────────────────────────────────────
    _fill_state(ax1, index, states)

    ax1.plot(index, close.values, color="#1a1a2e", linewidth=0.6, label="Close", zorder=3)

    ax1.plot(index, bb1["upper"].values, color=_C_TREND, linewidth=0.7,
             linestyle="--", alpha=0.85, label="BB 1σ upper")
    ax1.plot(index, bb1["lower"].values, color=_C_TREND, linewidth=0.7,
             linestyle="--", alpha=0.85, label="BB 1σ lower")
    ax1.fill_between(index, bb1["lower"].values, bb1["upper"].values,
                     alpha=0.05, color=_C_TREND)

    ax1.plot(index, bb3["upper"].values, color=_C_MR, linewidth=0.7,
             linestyle=":",  alpha=0.85, label="BB 3σ upper")
    ax1.plot(index, bb3["lower"].values, color=_C_MR, linewidth=0.7,
             linestyle=":",  alpha=0.85, label="BB 3σ lower")

    ax1.plot(index, bb1["mid"].values, color="#888888", linewidth=0.5,
             linestyle="-", alpha=0.6, label="BB mid")

    ax1.set_ylabel(f"{pair}  Close", fontsize=8)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))

    # 凡例（右外）
    legend_lines = ax1.legend(
        loc="upper left", fontsize=6.5, ncol=3,
        framealpha=0.8, edgecolor="#cccccc",
    )
    ax1.add_artist(legend_lines)
    ax1.legend(handles=_legend_patches(), loc="upper right",
               fontsize=6.5, framealpha=0.8)

    # ── 中段: ACF ────────────────────────────────────────────────────────────
    _fill_state(ax2, index, states)

    acf_vals = acf_s.values.astype(float)
    ax2.plot(index, acf_vals, color="#673AB7", linewidth=0.7, label="ACF lag=1")
    ax2.axhline(0, color="#333333", linewidth=0.6, linestyle="-")
    ax2.axhline(ACF_TREND_MIN, color=_C_TREND, linewidth=0.8,
                linestyle="--", alpha=0.9, label=f"Trend min ({ACF_TREND_MIN:+.2f})")
    ax2.axhline(ACF_REVERSION_MAX, color=_C_MR, linewidth=0.8,
                linestyle="--", alpha=0.9, label=f"MR max ({ACF_REVERSION_MAX:+.2f})")

    # ACF正負を色塗り
    ax2.fill_between(index, acf_vals, ACF_TREND_MIN,
                     where=(acf_vals >= ACF_TREND_MIN),
                     alpha=0.20, color=_C_TREND)
    ax2.fill_between(index, acf_vals, ACF_REVERSION_MAX,
                     where=(acf_vals <= ACF_REVERSION_MAX),
                     alpha=0.20, color=_C_MR)

    ax2.set_ylabel("ACF (lag=1)\nrolling 100", fontsize=7.5)
    ax2.set_ylim(-0.6, 0.6)
    ax2.yaxis.set_major_locator(mticker.MultipleLocator(0.2))
    ax2.legend(loc="upper left", fontsize=6, ncol=3, framealpha=0.8)

    # ── 下段: 強弱差 ─────────────────────────────────────────────────────────
    _fill_state(ax3, index, states)

    sd_vals = sd.values.astype(float)
    ax3.plot(index, sd_vals, color="#E91E63", linewidth=0.7,
             label=f"Strength: {base_ccy} - {quote_ccy}")
    ax3.axhline(0, color="#333333", linewidth=0.6)
    ax3.axhline( STRENGTH_DIFF_THRESHOLD, color="#555555", linewidth=0.7,
                linestyle="--", alpha=0.8, label=f"+threshold ({STRENGTH_DIFF_THRESHOLD})")
    ax3.axhline(-STRENGTH_DIFF_THRESHOLD, color="#555555", linewidth=0.7,
                linestyle="--", alpha=0.8)

    ax3.fill_between(index, sd_vals, 0,
                     where=(sd_vals > 0), alpha=0.15, color="#4CAF50")
    ax3.fill_between(index, sd_vals, 0,
                     where=(sd_vals < 0), alpha=0.15, color="#f44336")

    ax3.set_ylabel(f"Strength Diff\n{base_ccy} - {quote_ccy}", fontsize=7.5)
    ax3.legend(loc="upper left", fontsize=6, ncol=2, framealpha=0.8)

    # ── 最下段: 状態バー ──────────────────────────────────────────────────────
    state_num = states.map({
        MarketState.TREND: 1.0,
        MarketState.MEAN_REVERSION: -1.0,
        MarketState.NO_TRADE: 0.0,
    }).fillna(0.0).values

    # imshow風に pcolormesh で描画
    xedges = np.concatenate([mdates.date2num(index.to_pydatetime()),
                              [mdates.date2num(index[-1].to_pydatetime()) +
                               (mdates.date2num(index[-1].to_pydatetime()) -
                                mdates.date2num(index[-2].to_pydatetime()))]])
    ax4.pcolormesh(
        xedges, [0, 1],
        state_num.reshape(1, -1),
        cmap=plt.cm.RdYlBu, vmin=-1, vmax=1, shading="flat",
    )
    ax4.set_yticks([])
    ax4.set_ylabel("State", fontsize=7.5)

    # X軸フォーマット（最下段のみ表示）
    for ax in [ax1, ax2, ax3]:
        plt.setp(ax.get_xticklabels(), visible=False)
    _xfmt(ax4)

    # ── 統計サマリー（タイトル付近に表示） ────────────────────────────────────
    state_counts = states.value_counts()
    total        = len(states.dropna())
    trend_pct    = state_counts.get(MarketState.TREND, 0) / total * 100 if total else 0
    rev_pct      = state_counts.get(MarketState.MEAN_REVERSION, 0) / total * 100 if total else 0
    no_pct       = state_counts.get(MarketState.NO_TRADE, 0) / total * 100 if total else 0
    acf_mean     = float(np.nanmean(acf_vals))
    acf_std      = float(np.nanstd(acf_vals))

    summary = (
        f"State:  TREND {trend_pct:.1f}%  |  MEAN_REV {rev_pct:.1f}%  |  NO_TRADE {no_pct:.1f}%"
        f"     ACF mean {acf_mean:+.3f}  std {acf_std:.3f}"
        f"     |StrengthDiff| mean {float(np.nanmean(np.abs(sd_vals[~np.isnan(sd_vals)]))):.5f}"
    )
    fig.text(0.5, 0.97, summary, ha="center", fontsize=8, color="#444444")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"保存: {save_path}")
    else:
        plt.show()

    return fig


# ── エントリーポイント ─────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="FX 探索チャート")
    parser.add_argument("--pair",   default="USDJPY", help="通貨ペア（デフォルト: USDJPY）")
    parser.add_argument("--days",   type=int, default=50, help="取得日数（デフォルト: 50日）")
    parser.add_argument("--save",   action="store_true", help="PNG保存（表示しない）")
    args = parser.parse_args(argv)

    pair = args.pair.upper()
    print(f"データ取得中: {pair}  {args.days}日分...")
    price_data = fetch_ohlcv(pairs=[pair], lookback_days=args.days)

    if not price_data:
        print(f"データ取得失敗: {pair}")
        return

    # 他のペアも強弱計算に必要なので全ペア取得
    print("全ペア取得中（通貨強弱計算のため）...")
    all_data = fetch_ohlcv(lookback_days=args.days)

    clf = MarketClassifier(all_data)

    save_path = f"explore_{pair}_{args.days}d.png" if args.save else None
    plot_explore(pair, clf, save_path=save_path)


if __name__ == "__main__":
    main()
