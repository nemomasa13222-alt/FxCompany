# -*- coding: utf-8 -*-
"""
20SMA平均傾きゼロクロス転換戦略 — エントリーポイント可視化
実行: python backtest/plot_entries.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import mplfinance as mpf

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
BASE_DIR   = Path(__file__).parent
PRICE_CSV  = BASE_DIR / "USDJPY" / "USDJPY__20241014~20260501（1分足）.csv"
TRADES_CSV = BASE_DIR / "results" / "usdjpy_slope_is_20260503_074228.csv"
OUTPUT_DIR = BASE_DIR / "results"

N_ENTRIES  = 10   # 表示するエントリー数
TF_MIN     = 15   # 足（分）
SMA_PERIOD = 20
SLOPE_WIN  = 3
SMOOTH_PER = 5


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def load_price_15m():
    df = pd.read_csv(PRICE_CSV, header=None,
                     names=["date","time","open","high","low","close","vol"])
    df["dt"] = pd.to_datetime(df["date"]+" "+df["time"], format="%Y.%m.%d %H:%M")
    df = df.set_index("dt").sort_index()
    for c in ["open","high","low","close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.resample(f"{TF_MIN}min", closed="left", label="left").agg(
        Open=("open","first"), High=("high","max"),
        Low=("low","min"),    Close=("close","last"),
    ).dropna()
    df["SMA"]          = df["Close"].rolling(SMA_PERIOD).mean()
    df["raw_slope"]    = df["SMA"].diff(SLOPE_WIN)
    df["smooth_slope"] = df["raw_slope"].rolling(SMOOTH_PER).mean()
    return df


def main():
    print("データ読み込み中...")
    price = load_price_15m()
    trades = pd.read_csv(TRADES_CSV)
    trades["entry_dt"] = pd.to_datetime(trades["entry_dt"])
    trades["exit_dt"]  = pd.to_datetime(trades["exit_dt"])

    # 最初のN件を使用
    sample = trades.head(N_ENTRIES).reset_index(drop=True)
    print(f"  対象トレード: {len(sample)}件")
    print(f"  期間: {sample['entry_dt'].iloc[0]} ~ {sample['exit_dt'].iloc[-1]}")

    # 表示期間（最初のエントリー前後にバッファ）
    t_start = sample["entry_dt"].iloc[0] - timedelta(hours=6)
    t_end   = sample["exit_dt"].iloc[-1] + timedelta(hours=4)
    seg     = price.loc[t_start:t_end].copy()

    if seg.empty:
        print("エラー: 表示期間のデータが見つかりません")
        return

    # ── 図の作成 ─────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 12), facecolor="#0F1A30")
    gs  = gridspec.GridSpec(3, 1, height_ratios=[4, 1, 1],
                            hspace=0.04, figure=fig)

    ax_price = fig.add_subplot(gs[0])
    ax_slope = fig.add_subplot(gs[1], sharex=ax_price)
    ax_info  = fig.add_subplot(gs[2])

    for ax in [ax_price, ax_slope]:
        ax.set_facecolor("#0F1A30")
        ax.tick_params(colors="white", labelsize=8)
        ax.spines[:].set_color("#2A3A5A")
        ax.yaxis.label.set_color("white")
        ax.grid(axis="y", color="#1A2840", lw=0.5, ls="--")

    # ── ローソク足 ────────────────────────────────────────────────────────────
    xs    = np.arange(len(seg))
    xmap  = {dt: x for x, dt in enumerate(seg.index)}
    w     = 0.4

    for x, (dt, row) in enumerate(seg.iterrows()):
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        color = "#26A69A" if c >= o else "#EF5350"
        # 実体
        ax_price.bar(x, abs(c - o), bottom=min(o, c),
                     width=w, color=color, alpha=0.9, zorder=3)
        # ヒゲ
        ax_price.plot([x, x], [l, h], color=color, lw=0.8, zorder=2)

    # SMA
    sma_x = [xmap[dt] for dt in seg.index if not pd.isna(seg.loc[dt, "SMA"])]
    sma_y = [seg.loc[seg.index[x], "SMA"] for x in sma_x]
    ax_price.plot(sma_x, sma_y, color="#5B9BD5", lw=1.5, label="20SMA", zorder=4)

    # ── 平均傾きヒストグラム ──────────────────────────────────────────────────
    for x, (dt, row) in enumerate(seg.iterrows()):
        ss = row["smooth_slope"]
        if pd.isna(ss): continue
        color = "#26A69A" if ss >= 0 else "#EF5350"
        ax_slope.bar(x, ss, color=color, alpha=0.8, width=0.8)
    ax_slope.axhline(0, color="#AAAAAA", lw=0.8)
    ax_slope.set_ylabel("平均傾き", color="white",
                         fontproperties=_jp(8))

    # ── エントリーポイントのプロット ──────────────────────────────────────────
    entries_info = []
    for idx, trade in sample.iterrows():
        edt = trade["entry_dt"]
        xdt = price.index.searchsorted(edt)
        # 最近傍の15分バー
        bar_dt = price.index[min(xdt, len(price)-1)]
        if bar_dt not in xmap: continue
        x = xmap[bar_dt]

        is_long = trade["direction"] == "long"
        ep  = trade["entry_price"]
        tp  = trade["tp_price"]
        sl  = trade["stop_price"]
        won = trade["exit_reason"] == "tp"

        # エントリー矢印
        if is_long:
            ax_price.annotate("", xy=(x, ep), xytext=(x, ep - 0.08),
                arrowprops=dict(arrowstyle="-|>", color="#00E676", lw=2))
            ax_price.text(x + 0.15, ep - 0.10, f"L{idx+1}",
                          color="#00E676", fontsize=7.5, fontweight="bold",
                          fontproperties=_jp(8))
        else:
            ax_price.annotate("", xy=(x, ep), xytext=(x, ep + 0.08),
                arrowprops=dict(arrowstyle="-|>", color="#FF5252", lw=2))
            ax_price.text(x + 0.15, ep + 0.06, f"S{idx+1}",
                          color="#FF5252", fontsize=7.5, fontweight="bold",
                          fontproperties=_jp(8))

        # TP/SL水平線（エントリーから決済まで）
        xexit_dt = trade["exit_dt"]
        x2_idx = price.index.searchsorted(xexit_dt)
        bar_dt2 = price.index[min(x2_idx, len(price)-1)]
        x2 = xmap.get(bar_dt2, x + 4)

        ax_price.plot([x, x2], [tp, tp], color="#00C853",
                      lw=1.2, ls="--", alpha=0.7, zorder=5)
        ax_price.plot([x, x2], [sl, sl], color="#FF1744",
                      lw=1.2, ls="--", alpha=0.7, zorder=5)

        # 決済マーカー
        result_color = "#00E676" if won else "#FF5252"
        ax_price.scatter(x2, trade["exit_price"], marker="D",
                         color=result_color, s=40, zorder=6, edgecolors="white", lw=0.5)

        entries_info.append({
            "no": idx+1, "dir": "Long" if is_long else "Short",
            "entry": f"{ep:.3f}", "tp": f"{tp:.3f}", "sl": f"{sl:.3f}",
            "result": "TP✓" if won else "SL✗",
            "pnl": f"{trade['pnl_jpy']:+,.0f}円",
        })

    # ── 凡例・タイトル ────────────────────────────────────────────────────────
    ax_price.set_title(
        f"USD/JPY 15分足  20SMA平均傾きゼロクロス転換戦略\n"
        f"最初の{N_ENTRIES}エントリー  {seg.index[0].strftime('%Y/%m/%d')} "
        f"~ {seg.index[-1].strftime('%Y/%m/%d')}",
        color="white", fontproperties=_jp(12), pad=8)
    ax_price.set_ylabel("価格（円）", color="white", fontproperties=_jp(9))

    legend_elems = [
        mpatches.Patch(color="#5B9BD5", label="20SMA"),
        plt.Line2D([0],[0], color="#00E676", lw=1.5, ls="--", label="TP (緑)"),
        plt.Line2D([0],[0], color="#FF1744", lw=1.5, ls="--", label="SL (赤)"),
        plt.scatter([],[], marker="D", color="#00E676", s=30, label="TP到達"),
        plt.scatter([],[], marker="D", color="#FF5252", s=30, label="SL到達"),
    ]
    ax_price.legend(handles=legend_elems, loc="upper left",
                    prop=_jp(8), facecolor="#1A2840", labelcolor="white",
                    edgecolor="#2A3A5A")

    # X軸ラベル（日付）
    tick_step = max(1, len(seg) // 12)
    tick_pos  = list(range(0, len(seg), tick_step))
    tick_lab  = [seg.index[i].strftime("%m/%d\n%H:%M") for i in tick_pos]
    ax_slope.set_xticks(tick_pos)
    ax_slope.set_xticklabels(tick_lab, color="white",
                               fontproperties=_jp(7.5))
    plt.setp(ax_price.get_xticklabels(), visible=False)

    # ── トレードサマリーテーブル ───────────────────────────────────────────────
    ax_info.set_facecolor("#0A1020")
    ax_info.axis("off")

    col_labels = ["No.", "方向", "エントリー", "TP", "SL", "結果", "損益"]
    table_data = [[str(e["no"]), e["dir"], e["entry"], e["tp"], e["sl"],
                   e["result"], e["pnl"]] for e in entries_info]

    won_count  = sum(1 for e in entries_info if "TP" in e["result"])
    total_pnl  = sum(trade["pnl_jpy"] for _, trade in sample.iterrows()
                     if _ < N_ENTRIES)

    tbl = ax_info.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)

    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor("#0F1A30" if r > 0 else "#1A2840")
        cell.set_text_props(color="white", fontproperties=_jp(8.5))
        cell.set_edgecolor("#2A3A5A")
        if r > 0:
            result = table_data[r-1][5]
            if c == 5:
                cell.set_text_props(color="#00E676" if "TP" in result else "#FF5252",
                                    fontproperties=_jp(8.5), fontweight="bold")
            if c == 6:
                val = table_data[r-1][6]
                cell.set_text_props(
                    color="#00E676" if "+" in val else "#FF5252",
                    fontproperties=_jp(8.5))

    ax_info.set_title(
        f"サマリー: {won_count}/{len(entries_info)}勝  "
        f"勝率{won_count/len(entries_info)*100:.0f}%  "
        f"損益合計 {total_pnl:+,.0f}円",
        color="white", fontproperties=_jp(10), pad=4)

    plt.tight_layout()
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"entry_visualization_{ts}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight",
                facecolor="#0F1A30", edgecolor="none")
    plt.close(fig)
    print(f"\n完了: {out}")
    print(f"勝敗: {won_count}勝 {len(entries_info)-won_count}敗  "
          f"勝率{won_count/len(entries_info)*100:.0f}%  "
          f"損益 {total_pnl:+,.0f}円")


if __name__ == "__main__":
    main()
