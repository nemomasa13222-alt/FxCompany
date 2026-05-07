# -*- coding: utf-8 -*-
"""
損切りパターン集 PDF生成
実行: python japan_stocks/make_stoploss_pdf.py
"""

import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "results" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# PDF用カラー（0-255 tuple）
NAVY  = (15,  30,  70)
BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120)
GREEN = (0,  140,  80)
RED   = (190,  40,  40)
AMBER = (200, 140,   0)
LIGHT = (235, 242, 255)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)

# matplotlib用カラー（hex文字列）
MP_RED   = "#BE2828"
MP_GREEN = "#008040"
MP_NAVY  = "#0F1E46"


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


# ── チャート生成ユーティリティ ────────────────────────────────────────────────

def _base_setup(ax, title, bg="#F5F8FF"):
    ax.set_facecolor(bg)
    ax.tick_params(labelsize=7)
    ax.grid(axis="y", color="#D8E0EC", lw=0.4, ls="--")
    ax.grid(axis="x", color="#EBF0F8", lw=0.3)
    for sp in ax.spines.values():
        sp.set_edgecolor("#C4D0E0")
    ax.set_title(title, fontproperties=_jp(9.5), color="#1A3A7A", pad=7)


def _price_line(ax, x, y, **kw):
    ax.plot(x, y, color="#1A3A7A", lw=2.0, **kw)


def _mark_entry(ax, x, y, label="エントリー"):
    ax.scatter([x], [y], color="#008040", s=140, zorder=10, marker="^")
    ax.annotate(label, xy=(x, y), xytext=(x + 3, y + 4),
                fontproperties=_jp(8), color="#006030", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#006030", lw=1.2))


def _mark_stop_trigger(ax, x, y, label="損切り実行"):
    ax.scatter([x], [y], color="#CC2222", s=160, zorder=10, marker="v")
    ax.annotate(label, xy=(x, y), xytext=(x + 3, y - 5),
                fontproperties=_jp(8), color="#AA1111", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#AA1111", lw=1.2))


def _stop_line(ax, x_start, x_end, y, label="損切りライン（ベース安値）"):
    ax.hlines(y, x_start, x_end, color=MP_RED, lw=1.8, ls="--", zorder=5)
    ax.text(x_start + 1, y - 2.5, label,
            fontproperties=_jp(7.5), color="#AA1111")


def _base_zone(ax, x_start, x_end, y_low, y_high, label="ベース（保ち合い）"):
    ax.fill_between([x_start, x_end], y_low, y_high,
                    alpha=0.08, color="#3060C0")
    ax.hlines(y_high, x_start, x_end, color="#228844", lw=1.5,
              ls="--", zorder=5)
    ax.text(x_start + 1, y_high + 1, label,
            fontproperties=_jp(7.5), color="#225599")


def _save_fig(fig) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


# ── パターン1: クリーンなベース割れ ──────────────────────────────────────────

def chart_pattern1() -> str:
    """正統的なベース割れ損切り"""
    np.random.seed(1)
    fig, ax = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor("#F5F8FF")
    _base_setup(ax, "パターン①　クリーンなベース割れ（基本形）")

    # 上昇
    x1 = np.arange(0, 45)
    y1 = 80 + x1 * 0.5 + np.cumsum(np.random.randn(45) * 0.8)
    _price_line(ax, x1, y1)

    # ベース
    base_top = y1[-1]; base_bot = base_top - 8
    x2 = np.arange(45, 80)
    y2 = (base_top + base_bot) / 2 + np.sin(np.linspace(0, 3*np.pi, 35)) * 3 \
         + np.random.randn(35) * 0.8
    y2 = np.clip(y2, base_bot + 0.3, base_top - 0.3)
    _price_line(ax, x2, y2)
    _base_zone(ax, 44, 81, base_bot, base_top)

    # ブレイクアウト & 上昇
    x3 = np.arange(80, 100)
    y3 = base_top + np.arange(20) * 0.6 + np.random.randn(20) * 1.2
    _price_line(ax, x3, y3)
    _mark_entry(ax, 81, y3[1])

    # 反転 → ベース割れ
    x4 = np.arange(100, 125)
    y4 = y3[-1] - np.arange(25) * 0.6 + np.random.randn(25) * 1.5
    _price_line(ax, x4, y4)

    stop_y = base_bot
    _stop_line(ax, 80, 125, stop_y)

    # 割れポイント
    cross_idx = np.argmax(y4 < stop_y)
    if cross_idx > 0:
        _mark_stop_trigger(ax, x4[cross_idx], y4[cross_idx])

    ax.set_xlim(-2, 128)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))
    plt.tight_layout(pad=0.8)
    return _save_fig(fig)


# ── パターン2: フォールスブレイクアウト ──────────────────────────────────────

def chart_pattern2() -> str:
    """だまし上抜け → 即ベース割れ"""
    np.random.seed(2)
    fig, ax = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor("#F5F8FF")
    _base_setup(ax, "パターン②　フォールスブレイクアウト（だまし）")

    x1 = np.arange(0, 40)
    y1 = 80 + x1 * 0.45 + np.cumsum(np.random.randn(40) * 0.7)
    _price_line(ax, x1, y1)

    base_top = y1[-1]; base_bot = base_top - 7
    x2 = np.arange(40, 75)
    y2 = (base_top + base_bot) / 2 + np.sin(np.linspace(0, 3*np.pi, 35)) * 2.5 \
         + np.random.randn(35) * 0.6
    y2 = np.clip(y2, base_bot + 0.2, base_top - 0.2)
    _price_line(ax, x2, y2)
    _base_zone(ax, 39, 76, base_bot, base_top)

    # だましブレイク（3〜5日で失速）
    x_fake = np.arange(75, 83)
    y_fake = np.array([base_top + 1.5, base_top + 3.2, base_top + 2.1,
                       base_top + 1.0, base_top - 0.5, base_top - 2.0,
                       base_top - 4.5, base_bot - 1.5])
    _price_line(ax, x_fake, y_fake)
    _mark_entry(ax, 76, base_top + 1.8, "エントリー\n（だましに乗る）")

    stop_y = base_bot
    _stop_line(ax, 75, 95, stop_y)
    _mark_stop_trigger(ax, 82, y_fake[-1] - 0.3,
                       "即損切り\n（ベース割れ）")

    # 下落継続
    x5 = np.arange(83, 110)
    y5 = base_bot - 2 - np.arange(27) * 0.3 + np.random.randn(27) * 1.5
    _price_line(ax, x5, y5)

    # フォールスブレイクの説明矢印
    ax.annotate("出来高なし\n失速のサイン",
                xy=(79, base_top + 3),
                xytext=(60, base_top + 10),
                fontproperties=_jp(8), color="#885500",
                arrowprops=dict(arrowstyle="->", color="#885500", lw=1.2))

    ax.set_xlim(-2, 112)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))
    plt.tight_layout(pad=0.8)
    return _save_fig(fig)


# ── パターン3: ギャップダウン（悪材料） ──────────────────────────────────────

def chart_pattern3() -> str:
    """決算ミス・不祥事などによる窓開け急落"""
    np.random.seed(3)
    fig, ax = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor("#F5F8FF")
    _base_setup(ax, "パターン③　ギャップダウン（決算ミス・悪材料）")

    x1 = np.arange(0, 40)
    y1 = 90 + x1 * 0.5 + np.cumsum(np.random.randn(40) * 0.8)
    _price_line(ax, x1, y1)

    base_top = y1[-1]; base_bot = base_top - 8
    x2 = np.arange(40, 72)
    y2 = (base_top + base_bot) / 2 + np.sin(np.linspace(0, 2*np.pi, 32)) * 3 \
         + np.random.randn(32) * 0.7
    y2 = np.clip(y2, base_bot + 0.2, base_top - 0.2)
    _price_line(ax, x2, y2)
    _base_zone(ax, 39, 73, base_bot, base_top)

    # ブレイクアウト後しばらく上昇
    x3 = np.arange(72, 90)
    y3 = base_top + np.arange(18) * 0.5 + np.random.randn(18) * 1.0
    _price_line(ax, x3, y3)
    _mark_entry(ax, 73, y3[1])

    stop_y = base_bot
    _stop_line(ax, 72, 110, stop_y)

    # ギャップダウン（前日比-15%）
    gap_x = 90
    gap_y_open = y3[-1] * 0.83  # -17%

    # ギャップを矢印で表現
    ax.annotate("", xy=(gap_x, gap_y_open), xytext=(gap_x, y3[-1]),
                arrowprops=dict(arrowstyle="-|>", color=MP_RED,
                                lw=2.5, mutation_scale=18))
    ax.text(gap_x + 1.5, (y3[-1] + gap_y_open) / 2,
            f"ギャップダウン\n(例: -17%)",
            fontproperties=_jp(8.5), color="#AA1111", fontweight="bold")

    # その後の価格
    x4 = np.arange(90, 115)
    y4 = gap_y_open - np.arange(25) * 0.2 + np.random.randn(25) * 1.2
    _price_line(ax, x4, y4)

    _mark_stop_trigger(ax, 90, gap_y_open,
                       "翌日寄りで決済\n（ベース安値遥か下）")

    # ロス表示
    entry_y = y3[1]
    actual_stop = gap_y_open
    loss_pct = (actual_stop / entry_y - 1) * 100
    ax.annotate(f"実際の損失: {loss_pct:.0f}%\n（ベース安値割れ後に発生）",
                xy=(91, actual_stop - 3),
                xytext=(95, actual_stop - 12),
                fontproperties=_jp(8), color="#AA1111",
                arrowprops=dict(arrowstyle="->", color="#AA1111", lw=1.0))

    ax.set_xlim(-2, 118)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))
    plt.tight_layout(pad=0.8)
    return _save_fig(fig)


# ── パターン4: 段階的な崩れ ──────────────────────────────────────────────────

def chart_pattern4() -> str:
    """ベースが少しずつ切り下がり最終的に割れる"""
    np.random.seed(4)
    fig, ax = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor("#F5F8FF")
    _base_setup(ax, "パターン④　段階的な崩れ（底値切り下がり）")

    x1 = np.arange(0, 40)
    y1 = 85 + x1 * 0.5 + np.cumsum(np.random.randn(40) * 0.8)
    _price_line(ax, x1, y1)

    # ベース形成（だが底値が少しずつ切り下がる）
    base_top = y1[-1]; base_bot = base_top - 7
    x2 = np.arange(40, 75)
    trend = -np.linspace(0, 3, 35)
    y2 = (base_top + base_bot) / 2 + trend \
         + np.sin(np.linspace(0, 4*np.pi, 35)) * 2.5 \
         + np.random.randn(35) * 0.8
    _price_line(ax, x2, y2)
    _base_zone(ax, 39, 76, base_bot, base_top,
               label="ベース（底が切り下がっている）")

    # 底値切り下がりトレンドライン
    bot1 = base_bot + 0.5
    bot2 = base_bot - 2.5
    ax.plot([45, 70], [bot1, bot2], color="#CC5500", lw=1.5,
            ls=":", zorder=6)
    ax.text(48, bot2 - 3, "底値切り下がり（警戒サイン）",
            fontproperties=_jp(8), color="#CC5500")

    # エントリー（ブレイクアウトと見せかけ）
    x3 = np.arange(75, 88)
    y3 = base_top + np.array([1.5, 2.5, 1.8, 0.5, -0.5,
                               -2, -3.5, -5, -7, -9, -11, -13, -14])
    _price_line(ax, x3, y3)
    _mark_entry(ax, 76, y3[1], "エントリー\n（底値切り下がり見落とし）")

    stop_y = base_bot
    _stop_line(ax, 74, 108, stop_y)

    # 割れ
    cross = np.argmax(y3 < stop_y)
    if cross > 0:
        _mark_stop_trigger(ax, x3[cross], y3[cross])

    x4 = np.arange(88, 110)
    y4 = y3[-1] - np.arange(22) * 0.4 + np.random.randn(22) * 1.2
    _price_line(ax, x4, y4)

    ax.annotate("◀ このベースは事前に除外すべきだった\n（底値切り下がりは弱気サイン）",
                xy=(57, base_bot - 1),
                xytext=(30, base_bot - 10),
                fontproperties=_jp(8), color="#885500",
                arrowprops=dict(arrowstyle="->", color="#885500", lw=1.0))

    ax.set_xlim(-2, 112)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))
    plt.tight_layout(pad=0.8)
    return _save_fig(fig)


# ── パターン5: 市場全体の急落 ────────────────────────────────────────────────

def chart_pattern5() -> str:
    """日経225がMA200割れ → 全体暴落の巻き添え"""
    np.random.seed(5)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5),
                                    gridspec_kw={"height_ratios": [2, 1]})
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle("パターン⑤　市場全体の急落（日経225 MA200割れ）",
                 fontproperties=_jp(9.5), color="#1A3A7A", y=1.01)

    # 上段: 個別株
    _base_setup(ax1, "個別株 チャート")
    x1 = np.arange(0, 45)
    y1 = 90 + x1 * 0.5 + np.cumsum(np.random.randn(45) * 0.8)
    ax1.plot(x1, y1, color="#1A3A7A", lw=2)

    base_top = y1[-1]; base_bot = base_top - 8
    x2 = np.arange(45, 78)
    y2 = (base_top + base_bot) / 2 \
         + np.sin(np.linspace(0, 2*np.pi, 33)) * 2.8 \
         + np.random.randn(33) * 0.7
    y2 = np.clip(y2, base_bot + 0.2, base_top - 0.2)
    ax1.plot(x2, y2, color="#1A3A7A", lw=2)
    _base_zone(ax1, 44, 79, base_bot, base_top)

    x3 = np.arange(78, 92)
    y3 = base_top + np.arange(14) * 0.4 + np.random.randn(14) * 1
    ax1.plot(x3, y3, color="#1A3A7A", lw=2)
    _mark_entry(ax1, 79, y3[1])

    # 市場急落 → 個別株も暴落
    crash_start = 92
    x4 = np.arange(crash_start, 115)
    y4 = y3[-1] - (np.arange(23) ** 1.3) * 0.5 + np.random.randn(23) * 1.5
    ax1.plot(x4, y4, color="#1A3A7A", lw=2)

    stop_y = base_bot
    _stop_line(ax1, 78, 115, stop_y)
    cross = np.argmax(y4 < stop_y)
    if cross > 0:
        _mark_stop_trigger(ax1, x4[cross], y4[cross])

    ax1.axvline(crash_start, color=MP_RED, lw=1.5, ls=":", alpha=0.7)
    ax1.text(crash_start + 1, base_top + 6, "市場全体\n急落開始",
             fontproperties=_jp(8), color="#AA1111")
    ax1.set_xlim(-2, 118)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))

    # 下段: 日経225
    _base_setup(ax2, "日経225（参考）")
    n225_up = 28000 + np.arange(92) * 30 + np.cumsum(np.random.randn(92) * 80)
    n225_crash = n225_up[-1] - (np.arange(23) ** 1.4) * 15 \
                 + np.random.randn(23) * 60
    n225 = np.concatenate([n225_up, n225_crash])
    x_n = np.arange(len(n225))
    ax2.plot(x_n, n225, color="#445577", lw=1.8)

    ma200_n = pd.Series(n225).rolling(40, min_periods=1).mean().values
    ax2.plot(x_n, ma200_n, color=MP_RED, lw=1.3, ls="--", label="MA200（簡易）")

    ma200_cross = np.argmax((n225 < ma200_n) & (x_n > 90))
    if ma200_cross > 0:
        ax2.axvline(ma200_cross, color=MP_RED, lw=1.5, ls=":", alpha=0.7)
        ax2.text(ma200_cross + 1,
                 n225[ma200_cross] * 0.985,
                 "MA200割れ\n新規停止",
                 fontproperties=_jp(7.5), color="#AA1111")

    ax2.legend(loc="upper left", prop=_jp(7.5))
    ax2.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    ax2.set_xlim(-2, 118)

    plt.tight_layout(pad=0.6)
    return _save_fig(fig)


# ── パターン6: 損切り後に上昇 ────────────────────────────────────────────────

def chart_pattern6() -> str:
    """損切りしたら翌日から上昇。それでも正解だった理由"""
    np.random.seed(6)
    fig, ax = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor("#F5F8FF")
    _base_setup(ax, "パターン⑥　損切り後に上昇した場合（それでも正解）")

    x1 = np.arange(0, 40)
    y1 = 85 + x1 * 0.5 + np.cumsum(np.random.randn(40) * 0.8)
    ax.plot(x1, y1, color="#1A3A7A", lw=2)

    base_top = y1[-1]; base_bot = base_top - 8
    x2 = np.arange(40, 73)
    y2 = (base_top + base_bot) / 2 \
         + np.sin(np.linspace(0, 3*np.pi, 33)) * 2.8 \
         + np.random.randn(33) * 0.7
    y2 = np.clip(y2, base_bot + 0.2, base_top - 0.2)
    ax.plot(x2, y2, color="#1A3A7A", lw=2)
    _base_zone(ax, 39, 74, base_bot, base_top)

    x3 = np.arange(73, 85)
    y3 = base_top + np.arange(12) * 0.3 + np.random.randn(12) * 0.8
    ax.plot(x3, y3, color="#1A3A7A", lw=2)
    _mark_entry(ax, 74, y3[1])

    # 一時的なベース割れ（その後回復）
    x4 = np.arange(85, 95)
    dip = np.array([y3[-1] - 1, y3[-1] - 3, base_bot - 2.5,
                    base_bot - 4, base_bot - 2, base_bot + 0.5,
                    base_bot + 3, base_bot + 6, base_bot + 9, base_bot + 12])
    ax.plot(x4, dip, color="#1A3A7A", lw=2)

    stop_y = base_bot
    _stop_line(ax, 73, 120, stop_y, label="損切りライン")

    # 損切り実行点
    _mark_stop_trigger(ax, 87, base_bot - 2, "損切り実行")

    # その後上昇（損切りしたのに上がった）
    x5 = np.arange(95, 120)
    y5 = dip[-1] + np.arange(25) * 0.7 + np.random.randn(25) * 1.2
    ax.plot(x5, y5, color="#888899", lw=1.8, ls="-", alpha=0.7)
    ax.text(100, y5[-1] + 2, "損切り後に上昇（悔しい）",
            fontproperties=_jp(8), color="#556688")

    # 解説テキスト
    ax.annotate(
        "◀ ベース安値を明確に割った\n  ルール通りの損切りは正解",
        xy=(87, base_bot - 2.5),
        xytext=(60, base_bot - 14),
        fontproperties=_jp(8.5), color="#2244AA", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#2244AA", lw=1.2))

    # リスクの説明
    ax.fill_between(x4[:4], stop_y - 15, stop_y,
                    alpha=0.06, color=MP_RED)
    ax.text(84, stop_y - 10, "ここから\nさらに落ちる\n可能性もあった",
            fontproperties=_jp(7.5), color="#AA1111", ha="center")

    ax.set_xlim(-2, 122)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))
    plt.tight_layout(pad=0.8)
    return _save_fig(fig)


# ── PDF クラス ────────────────────────────────────────────────────────────────

class StopLossPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  fname=FONT_PATH)
        self.add_font("YG", "B", fname=FONT_PATH)
        self.set_margins(14, 14, 14)
        self.set_auto_page_break(auto=True, margin=14)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _sec(self, title, color=BLUE):
        self.set_fill_color(*color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 8.5)
        self.cell(0, 6.5, f"  {title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(1.5)

    def cover(self, today):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")
        self.set_fill_color(*RED)
        self.rect(0, 0, 4, 297, "F")

        self.set_y(50)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  トレーディングルール",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)
        self._t(26, bold=True, color=WHITE)
        self.cell(0, 18, "損切り",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(16, bold=True, color=(255, 120, 120))
        self.cell(0, 11, "パターン集",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(5)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(7)

        self._t(10, color=WHITE)
        self.cell(0, 8, "ベース安値割れ損切り 全6パターン",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 7, f"作成日: {today}  |  ミネルヴィニ v3ルール準拠",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(185)
        patterns = [
            ("①", "クリーンなベース割れ",     "基本形。ベース安値を終値で下抜け"),
            ("②", "フォールスブレイクアウト",  "だまし上抜け→即ベース割れ"),
            ("③", "ギャップダウン",            "決算ミス・悪材料による窓開け急落"),
            ("④", "段階的な崩れ",              "底値切り下がりのベース失敗"),
            ("⑤", "市場全体の急落",            "日経225 MA200割れに巻き込まれる"),
            ("⑥", "損切り後に上昇",            "悔しいが正解だった理由"),
        ]
        for no, name, desc in patterns:
            self._t(10, bold=True, color=(255, 160, 160))
            self.cell(14, 8, no, align="C")
            self._t(10, bold=True, color=WHITE)
            self.cell(62, 8, name)
            self._t(8.5, color=(160, 185, 220))
            self.cell(0, 8, desc, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(265)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            "本資料は投資教育を目的として作成したものです。投資判断はご自身の責任で行ってください。",
            align="C")

    def pattern_page(self, no: str, title: str, chart_img: str,
                     rule: str, points: list[str],
                     lesson: str, color=RED):
        self.add_page()

        # ヘッダー
        self.set_fill_color(*color)
        self.rect(0, 0, 210, 11, "F")
        self.set_y(1.5)
        self._t(12, bold=True, color=WHITE)
        self.cell(0, 8, f"  パターン{no}　{title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(2)

        # チャート
        self.image(chart_img, x=14, y=self.get_y(), w=182, h=76)
        self.ln(79)

        # 損切りルール
        self._sec("損切りルール", color=color)
        self._t(9, bold=True, color=color)
        self.cell(0, 6.5, rule, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

        # ポイント
        self._sec("チェックポイント", color=NAVY)
        for pt in points:
            self._t(8.5)
            self.set_x(self.l_margin + 3)
            self.multi_cell(0, 5.5, f"・{pt}")
        self.ln(2)

        # 教訓
        self._sec("教訓", color=TEAL)
        self._t(8.5)
        self.set_x(self.l_margin + 3)
        self.multi_cell(0, 5.5, lesson)

    def summary_page(self, today):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "損切り 実行フローまとめ",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(4)

        # 基本原則ボックス
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, "  損切り実行の基本原則",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(2)

        principles = [
            "エントリー時にベース安値を確認し、損切りラインとして記録する",
            "終値がベース安値を下回ったら翌日寄り付き成行で決済（日中の下ヒゲは無視）",
            "損切りラインは変更しない（狭める方向のみ可。広げるのは絶対NG）",
            "「またすぐ上がるかも」は禁物。ルールが崩れたらルール通り切る",
            "損切り後に上昇しても後悔しない。リスクを排除した判断は正しい",
        ]
        for i, p in enumerate(principles):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin)
            self.cell(6, 6, f"  {i+1}", fill=True)
            self.multi_cell(0, 6, f" {p}", fill=True)
        self.ln(4)

        # パターン別対応表
        self._sec("パターン別 対応一覧", color=BLUE)
        headers = ["パターン", "発生状況", "損切りタイミング", "備考"]
        widths  = [30, 54, 54, 44]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        rows = [
            ("①クリーンなベース割れ",
             "保ち合いから徐々に下落",
             "終値でベース安値割れた翌日",
             "最も基本的なパターン"),
            ("②フォールスブレイク",
             "ブレイク後すぐ失速・反落",
             "ベース安値割れで即決済",
             "出来高確認が重要"),
            ("③ギャップダウン",
             "悪材料で窓開け急落",
             "翌日寄り付きで成行決済",
             "損切り幅が大きくなる場合あり"),
            ("④段階的な崩れ",
             "底値が少しずつ切り下がる",
             "ベース安値割れで決済",
             "本来は事前除外すべきパターン"),
            ("⑤市場全体の急落",
             "日経225急落に巻き込まれる",
             "日経MA200割れで新規停止\n個別はベース安値割れで決済",
             "市場フィルターが重要"),
            ("⑥損切り後に上昇",
             "切った後で株価が回復",
             "ルール通りに実行済みなので\n後悔しない",
             "別の再エントリー機会を待つ"),
        ]
        for i, row in enumerate(rows):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B" if i == 0 else "", 7.5)
            self.cell(widths[0], 6, row[0], border=1, fill=True)
            self.set_font("YG", "", 7.5)
            for val, w in zip(row[1:], widths[1:]):
                self.cell(w, 6, val, border=1, fill=True)
            self.ln()

        self.ln(4)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5.5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）\n"
            "本資料はFxCompanyが情報提供を目的として作成したものです。")


# ── メイン ────────────────────────────────────────────────────────────────────

PATTERNS = [
    {
        "no": "①", "title": "クリーンなベース割れ（基本形）",
        "rule": "終値がベース安値を明確に割り込んだ → 翌日寄り付き成行で決済",
        "points": [
            "出来高が増加しながらベース安値を割ると信頼性が高い",
            "日中の下ヒゲや一時的な割れは無視し、終値ベースで判断する",
            "割れた後は迷わず翌日の寄り付きで成行注文を入れる",
        ],
        "lesson": (
            "最も教科書的なパターン。「ベース安値割れ＝手法の前提崩壊」と理解すれば迷いがなくなる。"
            "損切り幅はベースの大きさ（5〜10%レンジ）に比例するため、"
            "タイトなベースを選ぶことが最大の防御策になる。"
        ),
        "color": RED,
    },
    {
        "no": "②", "title": "フォールスブレイクアウト（だまし）",
        "rule": "ブレイクアウト後に株価が失速→ベース安値まで戻り割れ → 即決済",
        "points": [
            "ブレイクアウト当日の出来高が少ない場合はだましの可能性が高い",
            "ブレイク後3〜5日以内にベース高値を下回ったら警戒する",
            "ベース安値まで戻ったら問答無用で損切りを実行する",
        ],
        "lesson": (
            "だましは必ず起きる。重要なのは「だましだと分かった時点で即座に切ること」だ。"
            "「少し様子を見よう」と待つほど損失が膨らむ。"
            "ブレイクアウト時の出来高確認（平均の1.5倍以上）がだまし回避の最善策。"
        ),
        "color": AMBER,
    },
    {
        "no": "③", "title": "ギャップダウン（決算ミス・悪材料）",
        "rule": "窓開け急落でベース安値を大きく下回る → 翌日寄り付きで成行決済（値段は選ばない）",
        "points": [
            "ギャップダウンは損切りラインより大きく下で始まることが多い",
            "「少し待てば戻るかも」は厳禁。悪材料の翌日は早朝の流動性が薄い",
            "決算発表前日はポジションを減らすか、早めの利確も選択肢に入れる",
        ],
        "lesson": (
            "ギャップダウンは防ぎようがない。だからこそ「1銘柄10%以内のポジションサイジング」が重要だ。"
            "どんな大きなギャップダウンでも、資産全体への影響は限定的になる。"
            "また、決算前後のイベントリスクを意識してポジションを小さくしておくことも有効。"
        ),
        "color": RED,
    },
    {
        "no": "④", "title": "段階的な崩れ（底値切り下がり）",
        "rule": "ベース内で底値が切り下がっている → 本来はエントリー前に除外すべきパターン",
        "points": [
            "ベース確認の段階で「底値が切り下がっていないか」を必ずチェックする",
            "保ち合い中の底値が毎回切り下がっているベースは弱気サイン",
            "エントリー後に気づいた場合は、ベース安値割れで通常通り損切り",
        ],
        "lesson": (
            "最大の教訓は「事前に除外できたパターン」だということ。"
            "ベース確認時に「底値切り上がり（または横ばい）」を必ず確認する習慣をつけることで、"
            "このパターンへのエントリー自体を防げる。損切りより「エントリーしない」が最善。"
        ),
        "color": AMBER,
    },
    {
        "no": "⑤", "title": "市場全体の急落（日経MA200割れ）",
        "rule": "日経225がMA200を割り込む → 新規エントリー全停止。保有はベース安値割れで決済",
        "points": [
            "市場フィルター（日経225 > MA200）が機能している間のみ新規エントリーする",
            "MA200割れが発生したら即座に新規エントリーをゼロにする",
            "保有ポジションはパニック売りせず、ベース安値割れを待って淡々と処理する",
        ],
        "lesson": (
            "市場全体の急落は個別銘柄の問題ではないため「なぜ俺の銘柄だけ」と感じやすい。"
            "しかし相場の大局観を見誤ると全てのポジションが同時に損切りになる。"
            "日経225のMA200は「入場禁止ライン」として絶対に守る。"
        ),
        "color": (100, 30, 120),
    },
    {
        "no": "⑥", "title": "損切り後に上昇した場合",
        "rule": "ルール通りに損切りを実行した → 後悔しない。再エントリーの機会を待つ",
        "points": [
            "一時的なベース割れの後に回復する「ウィップソー」は必ず起きる",
            "「あのとき切らなければ良かった」という後悔はルールを壊す思考",
            "再び上昇し新たなベースを形成したら、改めてエントリーの機会がある",
        ],
        "lesson": (
            "損切り後の上昇が悔しく感じるのは心理的に当然だ。しかし考え方を変えよう。\n"
            "「ベース安値割れ」とは手法の前提が崩れたシグナル。その後上昇したのは「たまたま」であり、"
            "同じ状況が100回あれば多くはそのまま下落する。\n"
            "ルールを守り続けることで期待値がプラスになる。1回の「悔しさ」でルールを曲げると、"
            "長期的に大きな損失につながる。"
        ),
        "color": TEAL,
    },
]

CHART_FUNCS = [
    chart_pattern1, chart_pattern2, chart_pattern3,
    chart_pattern4, chart_pattern5, chart_pattern6,
]


def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  損切りパターン集 PDF 生成")
    print(f"{'='*55}\n")

    print("チャート生成中...")
    charts = []
    for i, func in enumerate(CHART_FUNCS):
        print(f"  パターン{i+1} ...", end=" ")
        charts.append(func())
        print("完了")

    print("\nPDF生成中...")
    pdf = StopLossPDF()
    pdf.cover(today)

    for pattern, chart_img in zip(PATTERNS, charts):
        pdf.pattern_page(
            no=pattern["no"],
            title=pattern["title"],
            chart_img=chart_img,
            rule=pattern["rule"],
            points=pattern["points"],
            lesson=pattern["lesson"],
            color=pattern["color"],
        )

    pdf.summary_page(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"stoploss_patterns_{ts}.pdf"
    pdf.output(str(out))

    for c in charts:
        Path(c).unlink(missing_ok=True)

    print(f"\n✓ PDF生成完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
