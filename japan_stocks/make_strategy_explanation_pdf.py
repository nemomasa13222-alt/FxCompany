# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 ロジック解説書 PDF
顧客・相談役向けに計算式レベルから説明する資料

実行: python japan_stocks/make_strategy_explanation_pdf.py
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "results" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
ORANGE = (220, 100,  0)


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


# ── チャート：セクター追いつきの概念図 ────────────────────────────────────────

def make_concept_chart() -> str:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    t = np.linspace(0, 10, 300)
    # セクター指数：急騰→横ばい
    sector = np.where(t < 3, 100 + t * 5, 115 + np.sin((t - 3) * 0.5) * 2)
    # 先行株：セクターより早く動く
    leader = np.where(t < 2, 100 + t * 7, 114 + np.sin((t - 2) * 0.6) * 3)
    # 遅行株：セクターより遅れて動く
    laggard = np.where(t < 5, 100 + np.maximum(0, t - 2.5) * 4,
                       110 + np.sin((t - 5) * 0.4) * 2)

    ax.plot(t, sector,  color="#1A3A7A", lw=2.5, label="セクター指数（等加重平均）", zorder=5)
    ax.plot(t, leader,  color="#2ECC71", lw=2.0, ls="--", label="先行株（既に動いた）", zorder=4)
    ax.plot(t, laggard, color="#E74C3C", lw=2.5, label="遅行株（まだ動いていない）★買いシグナル", zorder=6)

    # エントリーゾーン
    ax.axvspan(2.5, 5.0, alpha=0.10, color="#E74C3C", label="乖離発生期間（エントリー候補）")
    ax.axvline(2.5, color="#E74C3C", lw=1.5, ls=":", alpha=0.7)

    # 乖離の矢印
    t_arrow = 3.8
    s_val = float(np.interp(t_arrow, t, sector))
    l_val = float(np.interp(t_arrow, t, laggard))
    ax.annotate("", xy=(t_arrow, s_val), xytext=(t_arrow, l_val),
                arrowprops=dict(arrowstyle="<->", color="#CC3333", lw=1.8))
    ax.text(t_arrow + 0.15, (s_val + l_val) / 2, "乖離\n（ここを狙う）",
            fontproperties=_jp(8.5), color="#CC3333", va="center")

    ax.set_xlabel("時間（営業日）", fontproperties=_jp(9))
    ax.set_ylabel("株価指数（基準=100）", fontproperties=_jp(9))
    ax.set_title("セクター追いつき戦略の仮説：遅行株はセクター指数に追いつく",
                 fontproperties=_jp(11), color="#1A3A7A", pad=10)
    ax.legend(prop=_jp(8.5), loc="upper left", framealpha=0.9)
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax.set_xlim(0, 10)
    ax.set_ylim(96, 125)
    ax.tick_params(labelsize=8)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_entry_flow_chart() -> str:
    """エントリー判断フローチャート"""
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    def box(cx, cy, w, h, text, color="#1A3A7A", fc="#EEF3FF", fs=8.5):
        rect = patches.FancyBboxPatch((cx - w/2, cy - h/2), w, h,
                                       boxstyle="round,pad=0.1",
                                       linewidth=1.5, edgecolor=color,
                                       facecolor=fc)
        ax.add_patch(rect)
        ax.text(cx, cy, text, ha="center", va="center",
                fontproperties=_jp(fs), color="#1A1A2E", wrap=True,
                multialignment="center")

    def diamond(cx, cy, w, h, text, color="#CC6600", fc="#FFF3E0"):
        xs = [cx, cx+w/2, cx, cx-w/2, cx]
        ys = [cy+h/2, cy, cy-h/2, cy, cy+h/2]
        ax.fill(xs, ys, facecolor=fc, edgecolor=color, linewidth=1.5)
        ax.text(cx, cy, text, ha="center", va="center",
                fontproperties=_jp(8), color="#1A1A2E", multialignment="center")

    def arrow(x1, y1, x2, y2, label="", lc="#555"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=lc, lw=1.5))
        if label:
            mx, my = (x1+x2)/2, (y1+y2)/2
            ax.text(mx+0.08, my, label, fontproperties=_jp(7.5), color=lc)

    # スタート
    box(1.2, 4.5, 1.8, 0.55, "毎営業日\n終値チェック", fc="#DDEEFF")

    # 条件1
    diamond(3.0, 4.5, 2.2, 0.7,
            "①セクター指数\n直近5日 ≥ +2.0%?", fc="#FFF3DC")
    arrow(2.1, 4.5, 1.9, 4.5)
    arrow(4.1, 4.5, 5.5, 4.5, "YES")
    ax.text(3.5, 4.1, "NO→スキップ", fontproperties=_jp(7.5), color="#CC3333")

    # 条件2
    diamond(6.5, 4.5, 2.2, 0.7,
            "②銘柄が「中間株」\nまたは「遅行株」?", fc="#FFF3DC")
    arrow(5.5, 4.5, 5.4, 4.5)
    arrow(7.6, 4.5, 8.5, 4.5, "YES")
    ax.text(6.8, 4.1, "NO→スキップ", fontproperties=_jp(7.5), color="#CC3333")

    # 条件3（右上）
    diamond(8.5, 3.5, 1.8, 0.7,
            "③乖離率\n≥ +1.5%?", fc="#FFF3DC")
    arrow(8.5, 4.15, 8.5, 3.85)
    arrow(8.5, 3.15, 8.5, 2.65, "YES")
    ax.text(8.6, 3.1, "NO→スキップ", fontproperties=_jp(7.5), color="#CC3333")

    # エントリー
    box(8.5, 2.2, 1.8, 0.7,
        "エントリー\n（引け成行）", color="#008060", fc="#DDFFF0", fs=9)

    # ポジションサイジング
    box(5.5, 2.2, 2.8, 1.1,
        "ポジションサイジング\n株数 = リスク金額 ÷ ストップ幅\nリスク金額 = 資金 × 1%",
        color="#1A3A7A", fc="#EEF3FF", fs=8)
    arrow(7.6, 2.2, 6.9, 2.2)

    # 制約
    box(3.0, 2.2, 2.8, 1.0,
        "制約チェック\n・業種あたり最大3ポジション\n・DD制限（15%超えたら停止）",
        color="#CC6600", fc="#FFF8EC", fs=7.5)
    arrow(4.8, 4.15, 4.2, 2.7)

    ax.set_title("エントリー判断フロー（毎営業日実行）",
                 fontproperties=_jp(11), color="#1A3A7A", pad=10)
    plt.tight_layout()
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_exit_chart() -> str:
    """エグジット条件の図解"""
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    t = np.linspace(0, 12, 200)
    # 架空の株価推移（3%ストップ付き）
    entry = 1000
    stop  = entry * 0.97
    target_gap = entry * 1.04  # 追いつき後のイメージ

    price = entry + np.where(
        t < 4,  t * 6,
        np.where(t < 8, 24 + (t-4) * 4.5,
                 42 + (t-8) * 2)
    )

    ax.plot(t, price, color="#1A3A7A", lw=2.5, label="銘柄株価")
    ax.axhline(stop,  color="#CC3333", lw=1.5, ls="--", label=f"損切ライン（-3%）: {stop:.0f}円")
    ax.axhline(entry, color="#666",    lw=1.0, ls=":",  label=f"エントリー価格: {entry:.0f}円")

    # 利確ゾーン（乖離縮小）
    ax.axvspan(7, 9, alpha=0.15, color="#2ECC71")
    ax.text(8, entry + 35, "利確ゾーン\n（乖離 ≤ 0.5%）",
            fontproperties=_jp(8), color="#008060", ha="center")

    # 時間切れライン
    ax.axvline(10, color="#CC6600", lw=1.5, ls="--")
    ax.text(10.1, entry + 10, "10営業日\n（時間切れ）",
            fontproperties=_jp(8), color="#CC6600")

    ax.set_xlabel("保有日数（営業日）", fontproperties=_jp(9))
    ax.set_ylabel("株価（円）", fontproperties=_jp(9))
    ax.set_title("エグジット条件の図解（3パターン）",
                 fontproperties=_jp(11), color="#1A3A7A", pad=8)
    ax.legend(prop=_jp(8.5), loc="upper left")
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax.tick_params(labelsize=8)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_dd_analysis_chart() -> str:
    """DD発生メカニズムと改善イメージ"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    # 左：DD発生パターン（現状）
    t = np.linspace(0, 20, 500)
    eq_raw = (1_000_000
              + np.where(t < 5,  t * 80_000,
              np.where(t < 12, 400_000 - (t-5) * 60_000,
                                -20_000 + (t-12) * 90_000))) / 1_000_000

    peak = np.maximum.accumulate(eq_raw)
    dd   = (peak - eq_raw) / peak * 100

    ax1.fill_between(t, -dd, 0, alpha=0.35, color="#CC3333", label="DDゾーン")
    ax1.plot(t, -dd, color="#CC3333", lw=1.5)
    ax1.axhline(-35.5, color="#CC3333", lw=2, ls="--", alpha=0.7)
    ax1.text(10, -37, "最大DD 35.5%（現状）", fontproperties=_jp(8), color="#CC3333")
    ax1.set_title("現状のDD（OOS期間）", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax1.set_ylabel("ドローダウン（%）", fontproperties=_jp(8))
    ax1.set_ylim(-45, 5)
    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax1.tick_params(labelsize=7.5)

    # 右：DD制限後（改善イメージ）
    eq_improved = eq_raw.copy()
    in_limit = False
    peak_v = eq_raw[0]
    for idx in range(len(eq_raw)):
        if eq_raw[idx] > peak_v:
            peak_v = eq_raw[idx]
            in_limit = False
        if (peak_v - eq_raw[idx]) / peak_v > 0.15:
            in_limit = True
        if in_limit and idx > 0:
            eq_improved[idx] = eq_improved[idx-1]  # 新規停止 = 資金変動なし

    peak2 = np.maximum.accumulate(eq_improved)
    dd2   = (peak2 - eq_improved) / peak2 * 100

    ax2.fill_between(t, -dd2, 0, alpha=0.35, color="#2266AA", label="改善後DD")
    ax2.plot(t, -dd2, color="#2266AA", lw=1.5)
    ax2.axhline(-15, color="#2266AA", lw=2, ls="--", alpha=0.7)
    ax2.text(10, -16.5, "DD制限ライン 15%", fontproperties=_jp(8), color="#2266AA")
    ax2.set_title("DD制限適用後（改善イメージ）", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax2.set_ylim(-45, 5)
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax2.tick_params(labelsize=7.5)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class ExplanationPDF(FPDF):
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
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  {title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(1.5)

    def _formula_box(self, formula: str, note: str = "", color=BLUE):
        """数式ボックス"""
        self.set_fill_color(235, 242, 255)
        self.set_draw_color(*color)
        self.set_line_width(0.8)
        x = self.get_x()
        w = self.epw
        self.set_font("YG", "B", 10)
        self.set_text_color(*color)
        self.multi_cell(w, 7, formula, border=1, fill=True, align="C")
        if note:
            self.set_font("YG", "", 7.5)
            self.set_text_color(*GRAY)
            self.multi_cell(w, 5, note, align="C")
        self.set_text_color(*DARK)
        self.set_line_width(0.2)
        self.ln(2)

    # ── ページ1: カバー ────────────────────────────────────────────────────────

    def cover(self, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(45)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 解説資料",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(22, bold=True, color=WHITE)
        self.cell(0, 14, "セクター追いつき戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(13, bold=True, color=(0, 220, 170))
        self.cell(0, 9, "Sector Catch-Up Strategy",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(6)
        self._t(10, color=(140, 180, 230))
        self.cell(0, 7, "ロジック・数式から理解する戦略設計書",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # コンテンツ一覧
        self.set_y(155)
        contents = [
            ("1", "戦略の仮説とアルファの源泉"),
            ("2", "銘柄分類：クロスコリレーション分析"),
            ("3", "エントリー条件（3条件・数式）"),
            ("4", "エグジット条件とポジションサイジング（数式）"),
            ("5", "検証結果サマリー（IS / OOS）"),
            ("6", "課題（DD）と改善策"),
            ("7", "今後のロードマップ"),
        ]
        for num, title in contents:
            self.set_fill_color(25, 45, 90)
            self.set_text_color(*TEAL)
            self.set_font("YG", "B", 9)
            self.cell(10, 8, num, fill=True, align="C")
            self.set_text_color(210, 225, 255)
            self.set_font("YG", "", 9)
            self.cell(0, 8, f"  {title}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)

        self.set_y(268)
        self._t(7.5, color=(80, 100, 150))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  作成日: {today}",
            align="C")

    # ── ページ2: 仮説・概念図 ──────────────────────────────────────────────────

    def hypothesis_page(self, concept_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "1.  戦略の仮説とアルファの源泉",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("【仮説】セクター内の株価は同期して動く傾向があるが、常に時間差が生じる", color=BLUE)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "株式市場において、同じ業種（セクター）の銘柄群は、同じ経済的ドライバー（金利・原材料価格・"
            "規制変化など）の影響を受けるため、長期的には同方向に動く傾向がある。\n\n"
            "しかし短期的には、「情報感度の差」「機関投資家のローテーション」「流動性の差」などにより、"
            "同セクター内でも動きの早い銘柄（先行株）と遅い銘柄（遅行株）が存在する。\n\n"
            "この戦略は、セクター全体が上昇した後に「まだ動いていない遅行株」を買い、"
            "セクター指数へ追いつく過程で利益を得る。")
        self.ln(3)

        self.image(concept_img, x=14, y=self.get_y(), w=182, h=68)
        self.ln(72)

        self._sec("アルファ（超過収益）の源泉", color=TEAL)
        rows = [
            ("情報の非対称性",
             "機関投資家は人気セクターの代表銘柄から買い始めるため、小型・中型の遅行株に出遅れが生じる"),
            ("モメンタム効果",
             "上昇し始めた銘柄は続けて上昇しやすい（行動ファイナンスの追随買い効果）"),
            ("平均回帰",
             "同セクター内の銘柄間の価格乖離は、長期的には縮小する統計的性質がある"),
            ("時間軸の優位性",
             "追いつきは通常10営業日以内と短期 → 資金効率が高く、DD期間も限定的"),
        ]
        for title, desc in rows:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*BLUE)
            self.cell(0, 6, f"▶ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 4)
            self.multi_cell(0, 5.5, desc)
            self.ln(1)

    # ── ページ3: 銘柄分類 ─────────────────────────────────────────────────────

    def classification_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "2.  銘柄分類：クロスコリレーション分析",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("クロスコリレーション（時差相関）とは", color=BLUE)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "通常の相関係数は「同時刻の2つの時系列がどれだけ似ているか」を測る。"
            "クロスコリレーションは「一方の時系列を時間方向にずらしたとき、"
            "どのラグ（遅れ）で最も相関が高いか」を測定する。\n\n"
            "これにより、銘柄がセクター指数に対して「先行・同行・遅行」のどの関係にあるかを定量的に判定できる。")
        self.ln(3)

        self._formula_box(
            "CCF(τ) = Σ[(Xₜ - X̄)(Yₜ₋τ - Ȳ)] / [N · σₓ · σᵧ]",
            "X：セクター指数リターン  Y：銘柄リターン  τ：ラグ（日数）  N：ウィンドウ長（252営業日）",
            color=BLUE
        )

        self._sec("分類ルール（最適ラグに基づく）", color=TEAL)
        cls_data = [
            ("先行株",   "τ* < -2日",  "セクターより早く動く。すでに動いており、買いの対象外"),
            ("中間株",   "-2 ≤ τ* ≤ 2日", "ほぼ同時に動く。乖離があれば買い候補"),
            ("遅行株",   "τ* > 2日",   "セクターより遅れて動く。主要な買い候補★"),
        ]
        widths = [28, 35, 119]
        headers = ["分類", "最適ラグ τ*", "意味・取引方針"]
        self.set_font("YG", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        row_colors = [LIGHT, WHITE, (255, 252, 220)]
        for i, (cls, lag, desc) in enumerate(cls_data):
            self.set_fill_color(*row_colors[i])
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 8)
            self.cell(widths[0], 6, cls, border=1, fill=True, align="C")
            self.set_font("YG", "", 8)
            self.cell(widths[1], 6, lag, border=1, fill=True, align="C")
            self.multi_cell(widths[2], 6, desc, border=1, fill=True)
        self.ln(3)

        self._sec("最適ラグの決定方法", color=BLUE)
        self._formula_box(
            "τ* = argmax |CCF(τ)|  for τ ∈ {-10, ..., +10}",
            "絶対値が最大となるラグを「最適ラグ」として採用。相関係数 ≥ 0.30 が必要条件",
            color=BLUE
        )

        self._t(8.5)
        self.multi_cell(0, 5.5,
            "分類は21営業日（約1ヶ月）ごとに再計算する（市場環境の変化に対応）。\n"
            "計算ウィンドウは252営業日（約1年）を使用し、短期ノイズの影響を排除する。")

    # ── ページ4: エントリー条件 ────────────────────────────────────────────────

    def entry_page(self, flow_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "3.  エントリー条件（3条件すべてを満たす日の引けで買い）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(flow_img, x=14, y=self.get_y(), w=182, h=75)
        self.ln(79)

        # 条件1
        self._sec("条件① セクタートレンド確認", color=BLUE)
        self._formula_box(
            "SectorReturn(t) = [SectorIndex(t) / SectorIndex(t-5)] - 1 ≥ +2.0%",
            "SectorIndex: 業種内銘柄の等加重平均株価  /  5日（＝1週間）ルックバック",
            color=BLUE
        )
        self._t(8)
        self.multi_cell(0, 5,
            "セクター全体の上昇を確認してから買うことで、方向性のない局面でのトレードを排除する。")
        self.ln(2)

        # 条件2
        self._sec("条件② 銘柄分類フィルター", color=TEAL)
        self._formula_box(
            "classify(ticker) ∈ {「中間株」,「遅行株」}  かつ  |CCF(τ*)| ≥ 0.30",
            "クロスコリレーション分析で分類（前ページ参照）。相関が低すぎる銘柄は除外",
            color=TEAL
        )
        self.ln(2)

        # 条件3
        self._sec("条件③ 乖離率確認", color=AMBER)
        self._formula_box(
            "Gap(t) = SectorReturn(t) - StockReturn(t) ≥ +1.5%",
            "StockReturn: 銘柄の同期間リターン  /  乖離が大きい銘柄を優先的に選択",
            color=AMBER
        )

    # ── ページ5: エグジット・ポジションサイジング ──────────────────────────────

    def exit_page(self, exit_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "4.  エグジット条件とポジションサイジング",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(exit_img, x=14, y=self.get_y(), w=182, h=58)
        self.ln(62)

        self._sec("エグジット条件（最初に成立した条件で決済）", color=BLUE)
        exit_rows = [
            ("A. 利確（追いつき完了）",
             "Gap_now = SectorReturn_since_entry - StockReturn_since_entry ≤ 0.5%",
             "乖離が縮小し、追いつきが完了したと判断。引け成行で決済"),
            ("B. 損切（ストップロス）",
             "StockPrice ≤ EntryPrice × (1 - 3.0%)",
             "エントリー価格から3%下落で即時損切。損失を限定する"),
            ("C. 時間切れ",
             "保有営業日数 ≥ 10日",
             "追いつきが起きなかった場合、10営業日で強制決済"),
        ]
        for title, formula, desc in exit_rows:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*BLUE)
            self.cell(0, 6, f"▶ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self._formula_box(formula, desc, color=BLUE)
        self.ln(2)

        self._sec("ポジションサイジング（固定リスク法）", color=TEAL)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "1トレードで失うリスクを「総資金の1%」に固定する。損切幅（3%）から逆算して株数を決める。")
        self.ln(1)
        self._formula_box(
            "RiskAmount = Capital × 1%\n"
            "StopWidth  = EntryPrice × 3%\n"
            "Shares     = floor( RiskAmount ÷ StopWidth )",
            "例: 資金100万円 → リスク1万円 / 1,000円株でストップ30円 → 株数 = 333株",
            color=TEAL
        )

        self._sec("コスト（往復 0.20%）", color=GRAY)
        self._formula_box(
            "Cost = EntryPrice × Shares × 0.20%",
            "スプレッド 0.10% × 2（往復）= 0.20%。手数料は無料前提。Net P&L = Gross P&L - Cost",
            color=GRAY
        )

    # ── ページ6: 検証結果 ─────────────────────────────────────────────────────

    def result_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "5.  検証結果サマリー（コスト 0.20% 控除後）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("IS / OOS 設計と結果", color=NAVY)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "IS（In-Sample）期間でパラメータを決定し、その後のOOS（Out-of-Sample）期間で"
            "戦略の有効性を検証する。OOSはISのデータを一切使わず「封印」した状態で独立検証する。")
        self.ln(2)

        headers = ["区分", "期間", "件数", "勝率", "PF", "最大DD", "損益（コスト後）"]
        widths  = [22, 40, 18, 18, 14, 18, 52]
        self.set_font("YG", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()

        rows = [
            ("IS（開発）", "2022-01-01\n～2023-12-31", "2,308件", "54.9%", "1.37",
             "21.1%", "¥+2,343,153", LIGHT),
            ("OOS（検証）★", "2024-01-01\n～現在", "2,450件", "52.9%", "1.24",
             "35.5% ⚠", "¥+1,803,045", (255, 252, 220)),
        ]
        for row in rows:
            *cells, bg = row
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            for cell, w in zip(cells, widths):
                bold = "OOS" in cells[0]
                self.set_font("YG", "B" if bold else "", 8)
                if "⚠" in str(cell) or (cell.startswith("¥") and "+" in cell):
                    self.set_text_color(*(RED if "35.5" in str(cell) else GREEN))
                else:
                    self.set_text_color(*DARK)
                self.cell(w, 6.5, str(cell).replace("\n", " "), border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)
        self.ln(3)

        self._sec("OOS 年別結果（2024~）", color=AMBER)
        yr_headers = ["年", "件数", "勝率", "PF", "損益（コスト後）", "評価"]
        yr_widths  = [20, 20, 22, 18, 68, 34]
        self.set_font("YG", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(yr_headers, yr_widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        yr_rows = [
            ("2024", "約1,200件", "約53%", "約1.3", "参照: 年別PDFのOOS列", "要確認"),
            ("2025", "約1,000件", "約53%", "約1.2", "参照: 年別PDFのOOS列", "要確認"),
            ("2026", "約250件",  "集計中", "集計中", "（2026年は途中）", "—"),
        ]
        for i, (yr, n, wr, pf, pnl, ev) in enumerate(yr_rows):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "", 7.5)
            for val, w in zip([yr, n, wr, pf, pnl, ev], yr_widths):
                self.cell(w, 6, val, border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)

        self.ln(3)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "※ 年別の正確な数値は advisor_report PDF を参照。上表は概算。\n"
            "※ 「最後まで保有していた株（Case A）」は集計から除外されている。"
            "これらはバックテスト最終日に時価強制決済されるが、未完結トレードとして統計対象外。")

    # ── ページ7: DD課題と改善策 ───────────────────────────────────────────────

    def dd_page(self, dd_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "6.  課題（DD 35.5%）と改善策",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RED)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("なぜDDが大きくなるか（原因分析）", color=RED)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "OOS期間（2024~）の最大DDが35.5%と基準（20%）を超えた。主な原因は以下の3点：")
        self.ln(1)
        causes = [
            ("① セクター間の相関上昇",
             "相場全体が下落するとき（例：2024年8月の急落）、10業種が同時に下落し"
             "ポジション（最大30）が同時に損失を出す。コストも一度に発生する。"),
            ("② コストの累積影響",
             "往復0.20%のコストが2,450件（OOS）かかると総コスト約216万円。"
             "これが損益を押し下げ、DDを深くする。"),
            ("③ 新規エントリー制限なし",
             "現行ロジックにはポートフォリオレベルのDDストッパーがなく、"
             "下落相場でも条件が揃えばエントリーし続ける設計になっている。"),
        ]
        for title, desc in causes:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*RED)
            self.cell(0, 6, f"▶ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.multi_cell(0, 5.5, f"    {desc}")
            self.ln(1)

        self.image(dd_img, x=14, y=self.get_y(), w=182, h=55)
        self.ln(59)

        self._sec("改善策（3案）", color=TEAL)
        improvements = [
            ("案①【実装済み】ポートフォリオDD制限",
             "portfolio_dd_limit_pct = 15.0%",
             "資金がピークから15%以上下落したとき、新規エントリーをすべて停止する。\n"
             "下落相場でのナンピン的なポジション積み上げを防ぐ。\n"
             "⚠ トレード件数は減少するが、DD抑制効果が最も即効性が高い。",
             TEAL),
            ("案②【検討中】市場フィルター（TOPIXトレンド）",
             "TOPIX > TOPIX_MA50  のときのみ新規エントリー許可",
             "市場全体が下落トレンドのとき（TOPIXが50日移動平均を下回る状態）は\n"
             "エントリーを全停止する。大きな相場下落を回避できる可能性がある。\n"
             "⚠ 上昇相場でのみ動く戦略になるため、機会損失が発生する可能性あり。",
             BLUE),
            ("案③【検討中】リスク量の動的調整",
             "risk_pct = 1.0% → DD進行に応じて 0.5% や 0.25% に縮小",
             "DDが深くなるほど1トレードのリスクを小さくする「アンチマルチンゲール」方式。\n"
             "損失が続く時期に集中的なリスクテイクを避けられる。\n"
             "⚠ 実装がやや複雑。IS/OOSで別途検証が必要。",
             AMBER),
        ]
        for title, formula, desc, color in improvements:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*color)
            self.cell(0, 6, f"▶ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self._formula_box(formula, "", color=color)
            self.set_font("YG", "", 8)
            self.set_text_color(*DARK)
            self.multi_cell(0, 5, desc)
            self.ln(2)

    # ── ページ8: ロードマップ ──────────────────────────────────────────────────

    def roadmap_page(self, today: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "7.  今後のロードマップ",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        steps = [
            ("STEP 1【完了】", "IS開発・パラメータ確定",
             "IS期間（2022-2023）でパラメータを決定。PF 1.37、DD 21.1%（コスト後）。",
             GREEN, "✓"),
            ("STEP 2【完了】", "OOS封印開封・検証",
             "OOS期間（2024~）で独立検証。PF 1.24、DD 35.5%（コスト後）。\n"
             "→ PFは合格基準1.2を超えているが、DDが20%基準を超過。",
             AMBER, "✓"),
            ("STEP 3【実施中】", "DD改善ロジックの開発・IS検証",
             "ポートフォリオDD制限（15%）を実装し、IS期間で効果を検証する。\n"
             "改善版のIS PF・DDが基準を満たすことを確認する。",
             BLUE, "→"),
            ("STEP 4【予定】", "改善版のOOS検証（2024~データで再検証）",
             "DD制限を加えた改善版を2024~のデータで検証する。\n"
             "OOS PF ≥ 1.2 かつ DD ≤ 20% が確認できたら次フェーズへ。",
             GRAY, "□"),
            ("STEP 5【予定】", "デモトレード（3ヶ月）",
             "改善版戦略をデモ口座で3ヶ月間実運用。\n"
             "日次でPF・DDをモニタリングし、乖離があれば見直す。",
             GRAY, "□"),
            ("STEP 6【予定】", "本番移行",
             "デモトレード結果が良好であれば本番口座で運用開始。\n"
             "初期ロットは小さく設定し、段階的にスケールアップする。",
             GRAY, "□"),
        ]

        for status, title, desc, color, mark in steps:
            self.set_fill_color(*color)
            self.set_text_color(*WHITE)
            self.set_font("YG", "B", 8)
            self.cell(8, 8, mark, fill=True, align="C")
            self.cell(35, 8, status, fill=True, align="C")
            self.cell(0, 8, f"  {title}", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_fill_color(245, 248, 255)
            self.set_text_color(*DARK)
            self.set_font("YG", "", 8)
            self.multi_cell(0, 5.5, f"    {desc}", fill=True)
            self.ln(2)

        self.ln(5)
        self._sec("最終判断基準（実運用移行の条件）", color=NAVY)
        self._t(9)
        criteria = [
            "改善版 IS PF ≥ 1.3  かつ  DD ≤ 20%",
            "改善版 OOS PF ≥ 1.2  かつ  DD ≤ 20%",
            "デモトレード3ヶ月  PF ≥ 1.0  かつ  DD ≤ 25%（実運用では若干の余裕を持つ）",
            "上記3条件を全て満たした段階で本番移行を承認する",
        ]
        for c in criteria:
            self.set_font("YG", "B", 9)
            self.set_text_color(*TEAL)
            self.cell(5, 7, "•")
            self.set_text_color(*DARK)
            self.set_font("YG", "", 9)
            self.cell(0, 7, c, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(265)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  作成日: {today}\n"
            "本資料は過去データに基づくシミュレーション結果です。将来の投資成果を保証するものではありません。",
            align="C")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  セクター追いつき戦略 ロジック解説書 PDF生成")
    print(f"{'='*55}\n")

    print("チャート生成中...")
    concept_img  = make_concept_chart()
    flow_img     = make_entry_flow_chart()
    exit_img     = make_exit_chart()
    dd_img       = make_dd_analysis_chart()
    print("  チャート完了")

    print("PDF生成中...")
    pdf = ExplanationPDF()
    pdf.cover(today)
    pdf.hypothesis_page(concept_img)
    pdf.classification_page()
    pdf.entry_page(flow_img)
    pdf.exit_page(exit_img)
    pdf.result_page()
    pdf.dd_page(dd_img)
    pdf.roadmap_page(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"strategy_explanation_{ts}.pdf"
    pdf.output(str(out))

    for f in [concept_img, flow_img, exit_img, dd_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
