# -*- coding: utf-8 -*-
"""
エントリー・エグジット ルール整理 PDF
実行: python japan_stocks/make_rules_pdf.py
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "results" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ブランドカラー
NAVY  = (15,  30,  70)
BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120)
GREEN = (0,  140,  80)
AMBER = (200, 140,   0)
RED   = (190,  40,  40)
LIGHT = (235, 242, 255)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


# ── 図1: ベース＋エントリー概念図 ────────────────────────────────────────────

def make_base_chart() -> str:
    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    ax.set_xlim(0, 100)
    ax.set_ylim(60, 160)
    ax.axis("off")

    np.random.seed(42)

    # ── 上昇トレンド（ベース前）──────────────────────────────────────────
    x_up = np.linspace(0, 40, 80)
    y_up = 75 + x_up * 0.6 + np.random.randn(80) * 2.5
    ax.plot(x_up, y_up, color="#1A3A7A", lw=2)

    # ── ベース（保ち合い）────────────────────────────────────────────────
    x_base = np.linspace(40, 70, 80)
    base_center = y_up[-1]
    base_high = base_center + 6
    base_low  = base_center - 6
    y_base = base_center + np.sin(np.linspace(0, 4*np.pi, 80)) * 3 \
             + np.random.randn(80) * 1.5
    y_base = np.clip(y_base, base_low + 0.5, base_high - 0.5)
    ax.plot(x_base, y_base, color="#1A3A7A", lw=2)

    # ベース高値・安値ライン
    ax.hlines(base_high, 38, 73, color="#00905A", lw=1.8,
              linestyle="--", zorder=5)
    ax.hlines(base_low,  38, 73, color="#CC3333", lw=1.8,
              linestyle="--", zorder=5)

    # ベース塗り潰し
    ax.fill_between([38, 73], base_low, base_high,
                    alpha=0.08, color="#3060C0")

    # ── ブレイクアウト後の上昇 ────────────────────────────────────────────
    x_after = np.linspace(70, 100, 60)
    y_after = base_high + (x_after - 70) * 1.1 + np.random.randn(60) * 2
    ax.plot(x_after, y_after, color="#1A3A7A", lw=2.5)

    # ── 移動平均線 ────────────────────────────────────────────────────────
    all_x = np.concatenate([x_up, x_base, x_after])
    all_y = np.concatenate([y_up, y_base, y_after])
    from scipy.ndimage import uniform_filter1d
    ma50_y  = uniform_filter1d(all_y, size=20)
    ma150_y = uniform_filter1d(all_y, size=40)
    ax.plot(all_x, ma50_y,  color="#E07020", lw=1.3, ls="-",  alpha=0.8,
            label="MA50")
    ax.plot(all_x, ma150_y, color="#9030C0", lw=1.3, ls="--", alpha=0.8,
            label="MA150/200")

    # ── エントリーポイント ────────────────────────────────────────────────
    entry_x = 71.5
    entry_y = base_high + 1.5
    ax.scatter([entry_x], [entry_y], color="#00905A", s=180,
               zorder=10, marker="^")
    ax.annotate("★ エントリー\nベース高値ブレイク",
                xy=(entry_x, entry_y),
                xytext=(entry_x + 6, entry_y + 12),
                fontproperties=_jp(8.5),
                color="#006030",
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#006030", lw=1.5))

    # ── 損切りライン（ベース安値）────────────────────────────────────────
    ax.annotate("✗ 損切りライン\nベース安値を割ったら決済",
                xy=(55, base_low),
                xytext=(20, base_low - 12),
                fontproperties=_jp(8.5),
                color="#AA2222",
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#AA2222", lw=1.5))

    # ── 保ち合いラベル ────────────────────────────────────────────────────
    ax.text(55, base_center + 9, "保ち合い（ベース）",
            fontproperties=_jp(9), ha="center", color="#2244AA",
            fontweight="bold")
    ax.text(55, base_center + 6.5, "直近30日・レンジ20%以内",
            fontproperties=_jp(7.5), ha="center", color="#445588")

    # ← 矢印でベース幅を表示
    ax.annotate("", xy=(70, base_high + 2), xytext=(40, base_high + 2),
                arrowprops=dict(arrowstyle="<->", color="#2244AA", lw=1.2))
    ax.text(55, base_high + 3.5, "約6週間",
            fontproperties=_jp(7.5), ha="center", color="#2244AA")

    # ── 上昇トレンドラベル ────────────────────────────────────────────────
    ax.text(20, 78, "上昇トレンド\n(8条件クリア)",
            fontproperties=_jp(8), ha="center", color="#1A3A7A",
            style="italic")

    # ── ブレイクアウト後ラベル ────────────────────────────────────────────
    ax.text(87, y_after[-1] + 3, "ブレイクアウト後\n保有継続",
            fontproperties=_jp(8), ha="center", color="#1A3A7A")

    # 凡例
    ax.legend(loc="upper left", prop=_jp(8), framealpha=0.8,
              edgecolor="#C0C8D8")

    ax.set_title("ベース形成→ブレイクアウト→エントリー・損切りの概念図",
                 fontproperties=_jp(10), color="#1A3A7A", pad=8)
    plt.tight_layout(pad=0.8)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=170, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


# ── 図2: トレードフロー図 ─────────────────────────────────────────────────────

def make_flow_chart() -> str:
    fig, ax = plt.subplots(figsize=(10, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 40)
    ax.axis("off")

    steps = [
        (8,   20, "#1A3A7A", "① スクリーニング\n8条件全通過"),
        (28,  20, "#1A3A7A", "② ベース確認\n保ち合い形成？"),
        (50,  20, "#00905A", "③ エントリー\nベース高値ブレイク"),
        (72,  30, "#CC3333", "④a 損切り\nベース安値割れ"),
        (72,  10, "#1A5530", "④b 利確\n6ヶ月経過 or 目標"),
    ]

    for x, y, color, label in steps:
        w, h = 16, 12
        rect = mpatches.FancyBboxPatch(
            (x - w/2, y - h/2), w, h,
            boxstyle="round,pad=0.5",
            facecolor=color, edgecolor="white", lw=1.5, alpha=0.92
        )
        ax.add_patch(rect)
        ax.text(x, y, label, ha="center", va="center",
                fontproperties=_jp(8), color="white", fontweight="bold",
                linespacing=1.5)

    # 矢印
    arrows = [
        (17, 20, 19, 20),
        (37, 20, 41, 20),
        (59, 20, 63, 25),
        (59, 20, 63, 15),
    ]
    for x1, y1, x2, y2 in arrows:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#445577",
                                   lw=1.8, connectionstyle="arc3,rad=0"))

    # フィルター注記
    ax.text(18, 10, "毎日16時\n自動実行", fontproperties=_jp(7),
            ha="center", color="#556688", style="italic")
    ax.text(38, 10, "MA20乖離\n≤15%", fontproperties=_jp(7),
            ha="center", color="#556688", style="italic")

    ax.set_title("トレードフロー",
                 fontproperties=_jp(10), color="#1A3A7A", pad=6)
    plt.tight_layout(pad=0.5)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=170, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


# ── PDF クラス ────────────────────────────────────────────────────────────────

class RulesPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  fname=FONT_PATH)
        self.add_font("YG", "B", fname=FONT_PATH)
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(auto=True, margin=15)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _sec(self, title, color=BLUE, icon=""):
        self.set_fill_color(*color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  {icon}{title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(2)

    def _bullet(self, text, indent=4, size=8.5, color=DARK):
        self._t(size, color=color)
        self.set_x(self.l_margin + indent)
        self.multi_cell(0, 5.5, f"・{text}")

    # ── 表紙 ─────────────────────────────────────────────────────────────
    def cover(self, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(55)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  トレーディングルール",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)
        self._t(24, bold=True, color=WHITE)
        self.cell(0, 16, "エントリー・エグジット",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(16, bold=True, color=(0, 210, 160))
        self.cell(0, 11, "ルール完全整理",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(5)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(8)

        self._t(10, color=WHITE)
        self.cell(0, 8, "ミネルヴィニ・トレンドテンプレート（v3）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(9, color=(140, 170, 220))
        self.cell(0, 7, f"作成日: {today}  |  東証プライム市場対応",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # サマリーボックス
        self.set_y(175)
        items = [
            ("エントリー条件", "8条件全通過 + ベース高値ブレイク"),
            ("損切りライン",   "ベース安値（動的・エントリー時確定）"),
            ("利確ライン",     "最大6ヶ月保有 / 目標達成で随時"),
            ("市場フィルター", "日経225 > MA200 のとき稼働"),
            ("バックテスト",   "PF 1.78  勝率 49.9%  損切り率 39.3%"),
        ]
        for label, val in items:
            self._t(8.5, color=(140, 170, 220))
            self.cell(50, 7, label, align="R")
            self._t(9, bold=True, color=WHITE)
            self.cell(0, 7, f"  {val}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(262)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            "本資料は投資勧誘を目的とするものではありません。投資判断はご自身の責任で行ってください。",
            align="C")

    # ── フロー図ページ ────────────────────────────────────────────────────
    def flow_page(self, flow_img: str, base_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "トレードフロー全体像",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

        self.image(flow_img, x=15, y=self.get_y(), w=180, h=55)
        self.ln(58)

        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "ベース形成 → エントリー → 損切りの概念図",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(2)

        self.image(base_img, x=15, y=self.get_y(), w=180, h=82)
        self.ln(85)

        # 補足テキスト
        self._t(8, color=GRAY)
        self.multi_cell(0, 5.5,
            "★ポイント: ベースが形成される前（株価が大きく上昇している途中）では絶対にエントリーしない。"
            "必ずベースの収縮→ブレイクアウトの順序を待つ。")

    # ── スクリーニング条件ページ ──────────────────────────────────────────
    def screening_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "STEP 1  スクリーニング条件（8条件）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

        self._t(8.5, color=GRAY)
        self.multi_cell(0, 5.5,
            "以下8条件を全て満たす銘柄のみが候補となる。1つでも欠けたら対象外。\n"
            "毎営業日16時に自動スクリーニングを実施。")
        self.ln(3)

        # 条件テーブル
        headers = ["No", "条件名", "判定基準", "意味・なぜ重要か"]
        widths  = [9, 44, 42, 85]
        rows = [
            ("1", "株価 > MA150・MA200",
             "終値 > 150日線・200日線",
             "中長期の上昇トレンドを確認。これが崩れると手法の前提が消える。"),
            ("2", "MA150 > MA200",
             "150日線 > 200日線",
             "移動平均が正常な序列。弱気相場では逆転する。"),
            ("3", "MA200 上昇トレンド",
             "現在のMA200 > 20日前のMA200",
             "長期トレンド自体が上向き。横ばいや下降中はNG。"),
            ("4", "MA50 > MA150・MA200",
             "50日線 > 150日線・200日線",
             "短中長期すべてが整列（パーフェクトオーダー）。最強の状態。"),
            ("5", "安値から25%以上上昇",
             "株価 ≥ 52週安値 × 1.25",
             "底打ちからの反発を確認。大化け株は底から100〜300%上昇してから買い時が来る。"),
            ("6", "高値の25%以内",
             "株価 ≥ 52週高値 × 0.75",
             "新高値に近いほど強い。「高い＝危険」は間違い。強い株は高値圏で買う。"),
            ("7", "RS ≥ 70（日経対比）",
             "対日経225の相対強度が上位30%以内",
             "市場全体より強い銘柄のみ選ぶ。市場の弱さを補えるリーダー株が対象。"),
            ("8", "株価 > MA50",
             "終値 > 50日線",
             "押し目（調整局面）ではなく上昇中。ブレイクアウト確認に使う。"),
        ]

        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        for i, (no, cond, crit, note) in enumerate(rows):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, no,   border=1, fill=True, align="C")
            self.cell(widths[1], 6, cond, border=1, fill=True)
            self.set_font("YG", "", 7)
            self.cell(widths[2], 6, crit, border=1, fill=True)
            self.cell(widths[3], 6, note, border=1, fill=True)
            self.ln()

        self.set_text_color(*DARK)
        self.ln(4)

        # 追加フィルター
        self._sec("追加フィルター（自動適用）", color=TEAL)
        self._t(8.5)
        add_filters = [
            ("市場フィルター",  "日経225終値 > 日経225のMA200  ─ 弱気相場は完全停止"),
            ("MA20乖離フィルター", "株価のMA20乖離率 ≤ 15%  ─ ベースから離れすぎた追いかけ買いを排除"),
        ]
        for label, desc in add_filters:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*TEAL)
            self.cell(45, 6, label)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.cell(0, 6, desc, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── エントリーページ ──────────────────────────────────────────────────
    def entry_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "STEP 2〜3  ベース確認 → エントリー",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

        # ベース確認
        self._sec("ベース（保ち合い）の確認方法", color=BLUE)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "スクリーニング通過後、チャートを目視して以下を確認する。")
        self.ln(2)

        base_items = [
            ("期間",     "直近4〜8週間（最低3週間）",        "短すぎるベースは信頼性が低い"),
            ("レンジ",   "高値/安値の差が20%以内",           "狭いほど強いベース。5〜10%が理想"),
            ("出来高",   "保ち合い中に徐々に減少",           "エネルギーが蓄積されているサイン"),
            ("MA位置",   "MA20乖離率 ≤ 15%",               "MAに近い場所でのベースが理想"),
            ("形状",     "底値が切り上がっているか横ばい",   "切り下がりは弱気シグナルで除外"),
        ]
        ws = [22, 54, 104]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(["項目", "条件", "ポイント"], ws):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        for i, (item, cond, pt) in enumerate(base_items):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 8)
            self.cell(ws[0], 6, item, border=1, fill=True, align="C")
            self.set_font("YG", "", 8)
            self.cell(ws[1], 6, cond, border=1, fill=True)
            self.cell(ws[2], 6, pt,   border=1, fill=True)
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        # エントリータイミング
        self._sec("エントリータイミング", color=GREEN)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "ベース高値を終値でブレイクした日（またはその翌日寄り付き）にエントリーする。")
        self.ln(2)

        entry_rows = [
            ("◎ 理想", "ベース高値を0〜3%上抜けた当日引け成行",
             "#00601A", "最もリスクが低い。大きく離れる前に入れる"),
            ("○ 許容", "ベース高値から+5%以内なら翌日寄り付き",
             "#005090", "少し乖離しているが十分許容範囲"),
            ("✗ NG",   "ベース高値から+10%以上離れた追いかけ買い",
             "#AA1111", "MASAYAが指摘した「乖離しすぎ問題」。絶対やらない"),
        ]

        for mark, timing, color_hex, note in entry_rows:
            r, g, b = (int(color_hex[1:3], 16),
                       int(color_hex[3:5], 16),
                       int(color_hex[5:7], 16))
            self.set_font("YG", "B", 9)
            self.set_text_color(r, g, b)
            self.cell(14, 6.5, mark)
            self.set_font("YG", "B", 8.5)
            self.cell(88, 6.5, timing)
            self.set_font("YG", "", 8)
            self.set_text_color(*GRAY)
            self.cell(0, 6.5, note, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)
        self.ln(3)

        # エントリー強化チェックリスト
        self._sec("エントリー強化チェック（任意・高精度化）", color=AMBER)
        checks = [
            "出来高がブレイクアウト当日に直近平均の1.5倍以上に増加している",
            "RSライン（対日経225）が6週間以上の上昇トレンドにある",
            "52週高値の10%以内（新高値更新が最も理想的）",
            "週足でもMA13・MA26・MA52が正常な序列を形成している",
        ]
        for c in checks:
            self._bullet(c, size=8.5)

    # ── エグジットページ ──────────────────────────────────────────────────
    def exit_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "STEP 4〜5  保有管理 → エグジット",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

        # 損切り
        self._sec("損切りルール（ベース安値割れ）", color=RED)
        self._t(9, bold=True, color=RED)
        self.cell(0, 7, "終値 < エントリー時のベース安値 → 翌日寄り付き成行で決済",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
        self._t(8.5)
        stop_rules = [
            "損切りラインはエントリー時に確定し、以後変更しない（狭める方向のみ可）",
            "日中の下ヒゲは無視。終値ベースで判断する",
            "「またすぐ上がるかも」は禁物。ルール通りに機械的に実行する",
            "損切り後に株価が上昇しても「正しい判断だった」と評価する",
            "ベースが狭い銘柄（レンジ5〜10%）を選ぶと損切り幅も自然に小さくなる",
        ]
        for r in stop_rules:
            self._bullet(r, size=8.5)
        self.ln(3)

        # 利益確定
        self._sec("利益確定ルール", color=GREEN)
        profit_rules = [
            ("A. 期間満了（必須）",
             "エントリーから126日（約6ヶ月）経過したら決済。"
             "バックテストで期間満了組の平均リターンは+15.6%・勝率82%。"),
            ("B. 新ベース形成後の損切り引き上げ（推奨）",
             "+30%以上の利益が出た後、株価が新たなベースを形成し始めたら"
             "損切りラインをその新ベース安値に引き上げる（利益を守る）。"),
            ("C. 過熱感での早期利確（裁量）",
             "MA20からの乖離が+30%を超えた場合、"
             "一部または全部を利確することを検討する。"),
        ]
        for title, desc in profit_rules:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*GREEN)
            self.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 4)
            self.multi_cell(0, 5.5, desc)
            self.ln(1)
        self.ln(2)

        # 市場環境による全体停止
        self._sec("市場環境による全体停止ルール", color=NAVY)
        self._t(8.5)
        stop_market = [
            "日経225終値がMA200を下回ったら新規エントリーを全停止",
            "既存ポジションはベース安値割れまで保有継続（強制決済はしない）",
            "日経225がMA200を回復したらスクリーニング再開",
        ]
        for r in stop_market:
            self._bullet(r)
        self.ln(4)

        # バックテスト結果
        self._sec("バックテスト実績（参考）", color=TEAL)
        self._t(8)
        bt_rows = [
            ("v1（月次機械的買い）",      "4,208件", "+0.6%",   "47%",  "1.20", "─"),
            ("v2（固定-7%損切り）",        "4,198件", "+3.7%",   "40%",  "1.71", "55.7%"),
            ("v3（ベース安値損切り）★",    "3,189件", "+4.5%",   "50%",  "1.78", "39.3%"),
        ]
        ws2 = [52, 20, 22, 16, 14, 20, 36]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(["バージョン", "件数", "平均リターン",
                          "勝率", "PF", "損切り率", "備考"], ws2):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()

        bt_notes = ["月次固定買い・損切りなし",
                    "ブレイクアウト後、-7%で機械的損切り",
                    "ベースブレイク後、ベース安値で損切り"]
        for i, (ver, n, avg, wr, pf, sr) in enumerate(bt_rows):
            is_v3 = "★" in ver
            bg = (220, 255, 235) if is_v3 else (LIGHT if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B" if is_v3 else "", 7.5)
            self.cell(ws2[0], 6, ver, border=1, fill=True)
            self.set_font("YG", "", 7.5)
            for val, w in zip([n, avg, wr, pf, sr], ws2[1:6]):
                self.cell(w, 6, val, border=1, fill=True, align="C")
            self.cell(ws2[6], 6, bt_notes[i], border=1, fill=True)
            self.ln()
        self.set_text_color(*DARK)

    # ── 損切りパターンページ ──────────────────────────────────────────────
    def stoploss_divider(self):
        """損切りパターン集の区切りページ"""
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*RED)
        self.rect(0, 0, 4, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(95)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 8, "FxCompany  |  トレーディングルール",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(28, bold=True, color=WHITE)
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
        self._t(9, color=(140, 170, 220))
        self.cell(0, 7, "全6パターン  ─  ベース安値割れ損切り v3ルール準拠",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def pattern_page(self, no, title, chart_img, rule,
                     points, lesson, color=RED):
        self.add_page()
        self.set_fill_color(*color)
        self.rect(0, 0, 210, 11, "F")
        self.set_y(1.5)
        self._t(12, bold=True, color=WHITE)
        self.cell(0, 8, f"  パターン{no}　{title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.image(chart_img, x=14, y=self.get_y(), w=182, h=76)
        self.ln(79)
        self._sec("損切りルール", color=color)
        self._t(9, bold=True, color=color)
        self.cell(0, 6.5, rule, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self._sec("チェックポイント", color=NAVY)
        for pt in points:
            self._t(8.5)
            self.set_x(self.l_margin + 3)
            self.multi_cell(0, 5.5, f"・{pt}")
        self.ln(2)
        self._sec("教訓", color=TEAL)
        self._t(8.5)
        self.set_x(self.l_margin + 3)
        self.multi_cell(0, 5.5, lesson)

    def stoploss_summary(self, today):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "損切り 実行フローまとめ",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(4)

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
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*DARK)
            self.cell(0, 6, f"  {i+1}.  {p}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.ln(4)

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
             "保ち合いから徐々に下落",      "終値でベース安値割れた翌日",      "最も基本的なパターン"),
            ("②フォールスブレイク",
             "ブレイク後すぐ失速・反落",     "ベース安値割れで即決済",          "出来高確認が重要"),
            ("③ギャップダウン",
             "悪材料で窓開け急落",           "翌日寄り付きで成行決済",          "損切り幅が大きくなる場合あり"),
            ("④段階的な崩れ",
             "底値が少しずつ切り下がる",     "ベース安値割れで決済",            "本来は事前除外すべき"),
            ("⑤市場全体の急落",
             "日経225急落に巻き込まれる",    "日経MA200割れで新規停止\n個別はベース安値割れで決済", "市場フィルターが重要"),
            ("⑥損切り後に上昇",
             "切った後で株価が回復",         "ルール通りに実行済み\n後悔しない",  "再エントリー機会を待つ"),
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
        self.set_text_color(*DARK)

    # ── リスク管理ページ ──────────────────────────────────────────────────
    def risk_page(self, today: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "リスク管理 & 注意事項",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

        self._sec("ポジション管理", color=BLUE)
        pm = [
            "1銘柄への投入上限: 資産の10%以内",
            "同時保有数: 最大5〜8銘柄（集中しすぎない）",
            "1ヶ月の最大損失許容: 資産の5%以内（超えたらいったん休む）",
        ]
        for r in pm:
            self._bullet(r)
        self.ln(3)

        self._sec("この手法の弱点（正直な評価）", color=RED)
        weaknesses = [
            ("急落・ブラックスワン",
             "2024年8月のような日経12%急落は避けられない。"
             "市場フィルター（日経MA200）で大局を見極めるが完全回避は不可能。"
             "これはモメンタム手法の宿命として受け入れる。"),
            ("損切り幅の大きさ",
             "ベース安値損切りは平均-10.9%とやや大きい。"
             "ベースのタイトな（5〜10%レンジ）銘柄を選ぶことで改善できる。"),
            ("テクニカル分析のみ",
             "業績・財務・ファンダメンタルズは本手法に含まれない。"
             "スクリーニング通過後に決算短信を確認することを推奨。"),
        ]
        for title, desc in weaknesses:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*RED)
            self.cell(0, 6, f"▲ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 4)
            self.multi_cell(0, 5.5, desc)
            self.ln(1)
        self.ln(3)

        self._sec("1トレードの判断チェックリスト（最終確認）", color=TEAL)
        checklist = [
            "8条件を全て確認した",
            "チャートでベース（保ち合い）の形成を目視確認した",
            "ベース高値から+5%以内でエントリーしている（乖離しすぎていない）",
            "損切りライン（ベース安値）を事前に計算し記録した",
            "日経225はMA200の上にある（市場フィルター通過）",
            "1銘柄への投入額は資産の10%以内である",
        ]
        for c in checklist:
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 4)
            self.cell(8, 6, "□")
            self.cell(0, 6, c, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(6)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5.5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）\n"
            "本資料はFxCompanyが情報提供を目的として作成したものです。"
            "特定の有価証券の売買を推奨するものではありません。")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from make_stoploss_pdf import PATTERNS, CHART_FUNCS

    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  エントリー・エグジット + 損切りパターン集 PDF 生成")
    print(f"{'='*55}\n")

    print("図表生成中（フロー・ベース概念図）...")
    flow_img = make_flow_chart()
    base_img = make_base_chart()

    print("損切りパターンチャート生成中...")
    pattern_imgs = []
    for i, func in enumerate(CHART_FUNCS):
        print(f"  パターン{i+1} ...", end=" ", flush=True)
        pattern_imgs.append(func())
        print("完了")

    print("\nPDF生成中...")
    pdf = RulesPDF()

    # ── エントリー・エグジットルール ──────────────────────────────────
    pdf.cover(today)
    pdf.flow_page(flow_img, base_img)
    pdf.screening_page()
    pdf.entry_page()
    pdf.exit_page()
    pdf.risk_page(today)

    # ── 損切りパターン集 ──────────────────────────────────────────────
    pdf.stoploss_divider()
    for pattern, chart_img in zip(PATTERNS, pattern_imgs):
        pdf.pattern_page(
            no=pattern["no"],
            title=pattern["title"],
            chart_img=chart_img,
            rule=pattern["rule"],
            points=pattern["points"],
            lesson=pattern["lesson"],
            color=pattern["color"],
        )
    pdf.stoploss_summary(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"trading_rules_complete_{ts}.pdf"
    pdf.output(str(out))

    # 一時ファイル削除
    for f in [flow_img, base_img] + pattern_imgs:
        Path(f).unlink(missing_ok=True)

    print(f"\n✓ PDF生成完了: {out}")
    print(f"  総ページ数: エントリー・エグジット6P + 損切りパターン8P = 14P")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
