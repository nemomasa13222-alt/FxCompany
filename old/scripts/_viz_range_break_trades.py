"""
USDJPY 5分足 レンジブレイク戦略
トレード履歴ビジュアライズ（TP50件 + 損切り50件）

出力: viz_range_break_trades.pdf
"""
from __future__ import annotations

import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import rcParams
from pathlib import Path

# Windows日本語フォント設定
for font in ["Yu Gothic", "MS Gothic", "Meiryo", "DejaVu Sans"]:
    try:
        rcParams["font.family"] = font
        import matplotlib.font_manager as fm
        fm.findfont(font, fallback_to_default=False)
        break
    except Exception:
        continue

from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

# ── 設定 ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path("data/dukascopy")
PAIR     = "USDJPY"
PIP      = 0.01

IS_START  = "2022-01-01"
IS_END    = "2024-01-01"
OOS_START = "2024-01-01"
OOS_END   = "2025-01-01"

RANGE_BARS      = 12
RANGE_PIPS      = 10
MIN_HOLD_BARS   = 5
STRENGTH_WINDOW = 20
ENTRY_COST_PIPS = 0.2

SAMPLE_N    = 50    # TP / 損切り それぞれ
RANDOM_SEED = 42
PRE_BARS    = 20    # エントリー前に表示するバー数
POST_BARS   = 5     # エグジット後に表示するバー数

OUT_PDF = Path("viz_range_break_trades.pdf")


# ── データ準備 ────────────────────────────────────────────────────────────────

def load_data():
    dfs = {}
    for p in PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if f.exists():
            dfs[p] = pd.read_parquet(f)
    return dfs

def compute_strength_diff(dfs):
    rd = {p: log_returns(df["Close"]) for p, df in dfs.items()}
    st = currency_strength(rd)
    usd = st["USD"].rolling(STRENGTH_WINDOW).sum()
    jpy = st["JPY"].rolling(STRENGTH_WINDOW).sum()
    return (usd - jpy).rename("sd")

def make_signals(df, sd):
    close     = df["Close"]
    roll_high = close.shift(1).rolling(RANGE_BARS).max()
    roll_low  = close.shift(1).rolling(RANGE_BARS).min()
    roll_mid  = (roll_high + roll_low) / 2
    in_range  = (roll_high - roll_low) <= RANGE_PIPS * PIP
    s         = sd.reindex(df.index)
    return pd.DataFrame({
        "close":       close,
        "open":        df["Open"],
        "high":        df["High"],
        "low":         df["Low"],
        "long_sig":    in_range & (close > roll_high) & (s > 0),
        "short_sig":   in_range & (close < roll_low)  & (s < 0),
        "range_high":  roll_high,
        "range_low":   roll_low,
        "range_mid":   roll_mid,
    })


# ── バックテスト（チャート用に詳細情報を記録） ────────────────────────────────

def run_backtest(signals: pd.DataFrame, df_full: pd.DataFrame) -> pd.DataFrame:
    """signals は IS+OOS 全期間。df_full は全期間の OHLC（window取得用）"""
    close = signals["close"].values
    open_ = signals["open"].values
    r_mid = signals["range_mid"].values
    r_hi  = signals["range_high"].values
    r_lo  = signals["range_low"].values
    l_sig = signals["long_sig"].values
    s_sig = signals["short_sig"].values
    idx   = signals.index
    n     = len(signals)

    # df_full の timestamp → integer position マップ
    ts_to_pos = {ts: i for i, ts in enumerate(df_full.index)}

    trades = []
    in_trade  = False
    direction = 0
    entry_px  = 0.0
    stop_px   = 0.0
    entry_bar = -1
    rh = rl = rm = 0.0

    for i in range(1, n - 1):
        if not in_trade:
            if l_sig[i - 1]:
                direction = 1
                entry_px  = open_[i] + ENTRY_COST_PIPS * PIP
                stop_px   = r_mid[i - 1]
                rh, rl, rm = r_hi[i-1], r_lo[i-1], r_mid[i-1]
                entry_bar = i
                in_trade  = True
            elif s_sig[i - 1]:
                direction = -1
                entry_px  = open_[i] - ENTRY_COST_PIPS * PIP
                stop_px   = r_mid[i - 1]
                rh, rl, rm = r_hi[i-1], r_lo[i-1], r_mid[i-1]
                entry_bar = i
                in_trade  = True
        else:
            held       = i - entry_bar
            unrealized = (close[i] - entry_px) * direction / PIP
            exit_px    = None
            reason     = ""

            if direction == 1 and close[i] <= stop_px:
                exit_px, reason = stop_px, "stop"
            elif direction == -1 and close[i] >= stop_px:
                exit_px, reason = stop_px, "stop"
            elif held >= MIN_HOLD_BARS and unrealized > 0:
                if direction == 1 and close[i] < close[i - 1]:
                    exit_px, reason = close[i], "tp"
                elif direction == -1 and close[i] > close[i - 1]:
                    exit_px, reason = close[i], "tp"

            if exit_px is not None:
                pnl = (exit_px - entry_px) * direction / PIP
                et = idx[entry_bar]
                xt = idx[i]
                trades.append({
                    "entry_time":  et,
                    "exit_time":   xt,
                    "direction":   "Long" if direction == 1 else "Short",
                    "entry_price": entry_px,
                    "exit_price":  exit_px,
                    "stop_price":  stop_px,
                    "range_high":  rh,
                    "range_low":   rl,
                    "range_mid":   rm,
                    "pnl_pips":    round(pnl, 3),
                    "exit_reason": reason,
                    "hold_bars":   held,
                    "entry_full_pos": ts_to_pos.get(et, -1),
                    "exit_full_pos":  ts_to_pos.get(xt, -1),
                })
                in_trade = False
                direction = 0

    return pd.DataFrame(trades)


# ── ローソク足描画 ────────────────────────────────────────────────────────────

def draw_candles(ax, df_w: pd.DataFrame, entry_rel: int, exit_rel: int,
                 trade: pd.Series):
    """df_w: windowのOHLC。entry_rel/exit_rel: df_w内の相対位置"""

    close_arr = df_w["Close"].values
    open_arr  = df_w["Open"].values
    high_arr  = df_w["High"].values
    low_arr   = df_w["Low"].values
    xs = np.arange(len(df_w))

    # ローソク足
    for x in xs:
        bull = close_arr[x] >= open_arr[x]
        col  = "#26a69a" if bull else "#ef5350"
        # ヒゲ
        ax.plot([x, x], [low_arr[x], high_arr[x]],
                color="#888", linewidth=0.6, zorder=1)
        # ボディ
        bot = min(open_arr[x], close_arr[x])
        hgt = max(abs(close_arr[x] - open_arr[x]), PIP * 0.1)
        ax.bar(x, hgt, bottom=bot, color=col, width=0.7, alpha=0.85, zorder=2)

    # レンジ高値・安値・中値
    rh = trade["range_high"]
    rl = trade["range_low"]
    rm = trade["range_mid"]
    ax.axhline(rh, color="#888", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhline(rl, color="#888", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhline(rm, color="#e74c3c", linestyle=":", linewidth=0.9, alpha=0.8)

    # エントリー価格
    ax.axhline(trade["entry_price"], color="#27ae60",
               linestyle=":", linewidth=0.8, alpha=0.7)

    # エントリーマーカー
    ep = trade["entry_price"]
    if trade["direction"] == "Long":
        ax.scatter([entry_rel], [ep - PIP * 3],
                   marker="^", color="#27ae60", s=60, zorder=5)
    else:
        ax.scatter([entry_rel], [ep + PIP * 3],
                   marker="v", color="#27ae60", s=60, zorder=5)

    # エグジットマーカー
    xp = trade["exit_price"]
    ex_col = "#2980b9" if trade["exit_reason"] == "tp" else "#c0392b"
    ex_mk  = "o"
    ax.scatter([exit_rel], [xp], marker=ex_mk, color=ex_col, s=60, zorder=5)

    # エントリー・エグジット縦線
    ax.axvline(entry_rel, color="#27ae60", linewidth=0.8, alpha=0.5)
    ax.axvline(exit_rel,  color=ex_col,    linewidth=0.8, alpha=0.5)

    # 軸設定
    pad = (high_arr.max() - low_arr.min()) * 0.15
    ax.set_ylim(low_arr.min() - pad, high_arr.max() + pad)
    ax.tick_params(labelsize=5)
    ax.yaxis.set_major_formatter(plt.FormatStrFormatter("%.2f"))


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    print("データ読み込み中...")
    dfs = load_data()
    df_usdjpy = dfs[PAIR]

    print("強弱差計算中...")
    sd = compute_strength_diff(dfs)

    print("シグナル生成・バックテスト実行中...")
    sig_all = make_signals(df_usdjpy, sd)
    trades  = run_backtest(sig_all, df_usdjpy)

    print(f"  全トレード数: {len(trades)}")

    tp_trades   = trades[trades["exit_reason"] == "tp"].reset_index(drop=True)
    stop_trades = trades[trades["exit_reason"] == "stop"].reset_index(drop=True)

    print(f"  TP: {len(tp_trades)}件  損切り: {len(stop_trades)}件")

    rng = random.Random(RANDOM_SEED)
    tp_sample   = tp_trades.sample(n=min(SAMPLE_N, len(tp_trades)),
                                   random_state=RANDOM_SEED).reset_index(drop=True)
    stop_sample = stop_trades.sample(n=min(SAMPLE_N, len(stop_trades)),
                                     random_state=RANDOM_SEED).reset_index(drop=True)

    all_samples = pd.concat([
        tp_sample.assign(_label="TP"),
        stop_sample.assign(_label="Stop"),
    ]).reset_index(drop=True)

    print(f"サンプル: TP {len(tp_sample)}件 + 損切り {len(stop_sample)}件 = {len(all_samples)}件")
    print(f"チャート生成中 → {OUT_PDF}")

    COLS, ROWS = 5, 4          # 1ページ = 20チャート
    PER_PAGE   = COLS * ROWS
    n_trades   = len(all_samples)
    n_pages    = (n_trades + PER_PAGE - 1) // PER_PAGE

    with PdfPages(OUT_PDF) as pdf:
        for page in range(n_pages):
            batch = all_samples.iloc[page * PER_PAGE : (page + 1) * PER_PAGE]
            fig, axes = plt.subplots(ROWS, COLS,
                                     figsize=(20, 14),
                                     facecolor="#1a1a2e")
            axes = axes.flatten()

            for ax_i, (_, trade) in enumerate(batch.iterrows()):
                ax = axes[ax_i]
                ax.set_facecolor("#16213e")

                ep  = trade["entry_full_pos"]
                xp  = trade["exit_full_pos"]

                if ep < 0 or xp < 0:
                    ax.text(0.5, 0.5, "データなし", transform=ax.transAxes,
                            ha="center", va="center", color="white", fontsize=7)
                    continue

                start = max(0, ep - PRE_BARS)
                end   = min(len(df_usdjpy) - 1, xp + POST_BARS + 1)
                df_w  = df_usdjpy.iloc[start:end]

                entry_rel = ep - start
                exit_rel  = xp - start

                draw_candles(ax, df_w, entry_rel, exit_rel, trade)

                # タイトル
                label   = trade["_label"]
                pnl     = trade["pnl_pips"]
                direc   = trade["direction"]
                hold    = trade["hold_bars"]
                t_color = "#2ecc71" if label == "TP" else "#e74c3c"
                title   = (f"#{page*PER_PAGE + ax_i + 1} "
                           f"[{label}] {direc}  "
                           f"{pnl:+.1f}p  {hold}本")
                ax.set_title(title, fontsize=6.5, color=t_color, pad=2)

                # 日付ラベル（X軸 エントリー位置のみ）
                entry_dt = trade["entry_time"]
                if hasattr(entry_dt, "strftime"):
                    dt_str = entry_dt.strftime("%m/%d %H:%M")
                    ax.text(entry_rel, ax.get_ylim()[0],
                            dt_str, fontsize=4.5, color="#aaa",
                            ha="center", va="bottom")

                for spine in ax.spines.values():
                    spine.set_edgecolor("#444")

            # 余りサブプロットを非表示
            for ax_i in range(len(batch), PER_PAGE):
                axes[ax_i].set_visible(False)

            # 凡例
            legend_items = [
                mpatches.Patch(color="#27ae60", label="Entry"),
                mpatches.Patch(color="#2980b9", label="TP Exit"),
                mpatches.Patch(color="#c0392b", label="Stop Exit"),
                mpatches.Patch(color="#888",    label="Range H/L", linestyle="--"),
                mpatches.Patch(color="#e74c3c", label="Stop Level"),
            ]
            fig.legend(handles=legend_items, loc="lower center",
                       ncol=5, fontsize=7, facecolor="#1a1a2e",
                       labelcolor="white", framealpha=0.8,
                       bbox_to_anchor=(0.5, 0.0))

            page_label = "TP 50件" if page < n_pages // 2 + 1 else "損切り 50件"
            fig.suptitle(
                f"USDJPY 5min レンジブレイク  |  Page {page+1}/{n_pages}  "
                f"|  bars=12 pips=10 hold=5",
                fontsize=11, color="white", y=1.01,
            )
            plt.tight_layout(rect=[0, 0.03, 1, 1])
            pdf.savefig(fig, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close(fig)
            print(f"  Page {page+1}/{n_pages} 完了")

    print(f"\n完了: {OUT_PDF.resolve()}")


if __name__ == "__main__":
    main()
