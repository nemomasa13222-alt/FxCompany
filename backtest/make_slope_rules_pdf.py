# -*- coding: utf-8 -*-
"""
USD/JPY 20SMA接線ゼロクロス転換戦略 — ルール解説書PDF
実行: python backtest/make_slope_rules_pdf.py
"""
import sys, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# カラー定義
NAVY   = (15, 30, 70)
BLUE   = (30, 90, 170)
TEAL   = (0, 160, 120)
GREEN  = (0, 140, 80)
RED    = (190, 40, 40)
AMBER  = (200, 140, 0)
LIGHT  = (235, 242, 255)
WHITE  = (255, 255, 255)
DARK   = (30, 30, 40)
GRAY   = (110, 110, 120)

def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)

# ── チャート生成 ───────────────────────────────────────────────────────────────

def make_slope_pattern_chart() -> str:
    """良いパターン / 悪いパターンの比較図"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.patch.set_facecolor("#F5F8FF")

    good  = [0.4, 0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.4]
    bad   = [0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.1, -0.2, -0.1, 0.0, 0.1, 0.2]
    xs_g  = list(range(len(good)))
    xs_b  = list(range(len(bad)))

    for ax, vals, xs, title, entry_idx, result in [
        (ax1, good, xs_g, "良いパターン（ショートエントリー）", 7, True),
        (ax2, bad,  xs_b, "悪いパターン（キャンセル）",         5, False),
    ]:
        ax.set_facecolor("#F5F8FF")
        colors = ["#2266AA" if v > 0 else ("#CC3333" if v < 0 else "#888888") for v in vals]
        ax.bar(xs, vals, color=colors, alpha=0.85, width=0.7)
        ax.axhline(0, color="#333", lw=1.5)
        ax.axhline(-0.05, color="#FF8800", lw=1.5, ls="--", alpha=0.8)
        ax.text(len(xs)-0.3, -0.055, "確認閾値\n-0.05", fontproperties=_jp(8),
                color="#FF8800", ha="right", va="top")

        # ゼロクロス点をマーク
        zero_cross = next((i for i in range(1, len(vals)) if vals[i-1] > 0 and vals[i] <= 0), None)
        if zero_cross is not None:
            ax.axvline(zero_cross - 0.5, color="#888", lw=1.5, ls=":", alpha=0.6)
            ax.text(zero_cross - 0.4, max(vals)*0.85, "ゼロクロス\n検出",
                    fontproperties=_jp(8), color="#555", ha="left")

        # エントリー or キャンセルマーク
        if result and entry_idx < len(vals):
            ax.scatter([entry_idx], [vals[entry_idx]], s=200, zorder=5,
                       color="#CC3333", marker="v")
            ax.text(entry_idx, vals[entry_idx] - 0.04, "エントリー",
                    fontproperties=_jp(9), color="#CC3333", ha="center",
                    fontweight="bold")
        else:
            ax.text(len(xs)*0.7, max(vals)*0.7, "キャンセル\n(傾きが戻る)",
                    fontproperties=_jp(10), color="#CC3333", ha="center",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFE0E0", alpha=0.8))

        ax.set_title(title, fontproperties=_jp(11), color="#1A3A7A", pad=8)
        ax.set_xlabel("バー（時間→）", fontproperties=_jp(9))
        ax.set_ylabel("平均傾き（円/3本）", fontproperties=_jp(9))
        ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
        ax.set_ylim(-0.55, 0.55)

    plt.tight_layout(pad=1.2)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_flow_chart() -> str:
    """エントリーフローチャート"""
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    ax.set_xlim(0, 12); ax.set_ylim(0, 5); ax.axis("off")

    def box(cx, cy, w, h, text, fc="#EEF3FF", ec="#2266AA", fs=9, bold=False):
        r = patches.FancyBboxPatch((cx-w/2, cy-h/2), w, h,
            boxstyle="round,pad=0.12", linewidth=1.8,
            edgecolor=ec, facecolor=fc)
        ax.add_patch(r)
        ax.text(cx, cy, text, ha="center", va="center",
                fontproperties=_jp(fs), color="#1A1A2E",
                fontweight="bold" if bold else "normal",
                multialignment="center")

    def diamond(cx, cy, w, h, text, fc="#FFF3DC", ec="#CC6600"):
        xs = [cx, cx+w/2, cx, cx-w/2, cx]
        ys = [cy+h/2, cy, cy-h/2, cy, cy+h/2]
        ax.fill(xs, ys, facecolor=fc, edgecolor=ec, linewidth=1.8)
        ax.text(cx, cy, text, ha="center", va="center",
                fontproperties=_jp(8.5), color="#1A1A2E",
                multialignment="center")

    def arrow(x1, y1, x2, y2, label="", lc="#444"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="-|>", color=lc, lw=1.8))
        if label:
            mx, my = (x1+x2)/2+0.1, (y1+y2)/2
            ax.text(mx, my, label, fontproperties=_jp(8.5), color=lc)

    # ノード
    box(1.3, 2.5, 2.0, 0.7, "15分足\n毎バー処理", fc="#DDEEFF", fs=8.5)
    box(3.5, 2.5, 2.0, 0.7, "STEP1\n平均傾きゼロクロス\n検出", fc="#E8F4FF", fs=8)
    diamond(6.0, 2.5, 2.0, 0.8, "STEP2\n確認:\n傾き < -0.05?", fc="#FFF3DC", ec="#CC6600")
    box(9.0, 2.5, 2.0, 0.7, "STEP3\nエントリー\n(ショート)", fc="#DDFFF0", ec="#008060", fs=8.5, bold=True)
    box(6.0, 0.8, 2.2, 0.65, "キャンセル\n(傾きが戻る / タイムアウト)", fc="#FFE8E8", ec="#CC3333", fs=8)

    # 矢印
    arrow(2.3, 2.5, 2.5, 2.5)
    arrow(4.5, 2.5, 5.0, 2.5)
    arrow(7.0, 2.5, 8.0, 2.5, "YES")
    arrow(6.0, 2.1, 6.0, 1.13, "NO")

    ax.text(7.1, 2.65, "傾きが-0.05以下\n確認できた", fontproperties=_jp(8),
            color="#008060", ha="left")

    # ロング補足
    box(9.0, 4.0, 2.0, 0.65, "STEP3\nエントリー\n(ロング)", fc="#DDFFF0", ec="#008060", fs=8.5, bold=True)
    box(3.5, 4.0, 2.0, 0.65, "STEP1\nゼロを下→上\nクロス検出", fc="#E8F4FF", fs=8)
    diamond(6.0, 4.0, 2.0, 0.8, "STEP2\n確認:\n傾き > +0.05?", fc="#FFF3DC", ec="#CC6600")
    arrow(4.5, 4.0, 5.0, 4.0)
    arrow(7.0, 4.0, 8.0, 4.0, "YES")

    ax.text(0.2, 4.5, "ロング\nシグナル", fontproperties=_jp(8.5), color="#2266AA")
    ax.text(0.2, 2.0, "ショート\nシグナル", fontproperties=_jp(8.5), color="#CC3333")

    ax.set_title("エントリー判断フロー（毎15分バー実行）",
                 fontproperties=_jp(12), color="#1A3A7A", pad=10)
    plt.tight_layout()
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_backtest_chart() -> str:
    """IS/OOS比較バーチャート"""
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5))
    fig.patch.set_facecolor("#F5F8FF")

    data = {
        "IS（~2025/07）": {"勝率": 42.6, "PF": 1.39, "DD": 5.89},
        "OOS（2025/08~）": {"勝率": 42.3, "PF": 1.36, "DD": 5.03},
    }
    metrics = [("勝率（%）", "勝率", 33.3), ("PF", "PF", 1.0), ("最大DD（%）", "DD", None)]
    colors  = ["#2266AA", "#FF8800"]

    for ax, (title, key, threshold) in zip(axes, metrics):
        ax.set_facecolor("#F5F8FF")
        vals   = [data[k][key] for k in data]
        bars   = ax.bar(list(data.keys()), vals, color=colors, alpha=0.88, width=0.5)
        if threshold:
            ax.axhline(threshold, color="#CC3333", lw=1.5, ls="--", alpha=0.7)
            ax.text(1.45, threshold * 1.01,
                    f"損益分岐\n{threshold}%" if "勝率" in title else f"基準\n{threshold}",
                    fontproperties=_jp(7.5), color="#CC3333")
        ax.set_title(title, fontproperties=_jp(10), color="#1A3A7A", pad=6)
        ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
        ax.tick_params(labelsize=8)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x()+bar.get_width()/2, v+max(vals)*0.02,
                    f"{v:.2f}" if key=="PF" else f"{v:.1f}%",
                    ha="center", fontsize=9.5, fontweight="bold", color="#1A3A7A")

    plt.tight_layout(pad=0.9)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class RulesPDF(FPDF):
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
        self.cell(0, 7, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(2)

    def _rule_box(self, text, color=TEAL):
        self.set_fill_color(235, 248, 242)
        self.set_draw_color(*color)
        self.set_line_width(0.8)
        self.set_font("YG", "B", 10)
        self.set_text_color(*color)
        self.multi_cell(0, 7, text, border=1, fill=True, align="C")
        self.set_text_color(*DARK)
        self.set_line_width(0.2)
        self.ln(2)

    # ── 表紙 ─────────────────────────────────────────────────────────────────
    def cover(self, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(38)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 7, "FxCompany  |  FXトレーディングルール",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)
        self._t(22, bold=True, color=WHITE)
        self.cell(0, 14, "エントリー・エグジット",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(16, bold=True, color=WHITE)
        self.cell(0, 11, "ルール完全整理",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.6)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(6)
        self._t(11, bold=True, color=(0, 220, 170))
        self.cell(0, 8, "20SMA接線ゼロクロス転換戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  USD/JPY 15分足対応",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(175)
        for k, v in [
            ("エントリー条件", "SMA平均傾きゼロクロス + 傾き確認フィルター"),
            ("損切りライン",   "固定 5pips（エントリー価格から）"),
            ("利確ライン",     "固定 10pips（リスクリワード 1:2）"),
            ("イベントフィルター", "指標・FOMC前後60分はエントリー禁止"),
            ("バックテスト",   "IS: PF 1.39  勝率 42.6%  DD 5.9%"),
        ]:
            self._t(8.5, color=(140, 170, 220))
            self.cell(48, 7.5, k, align="R")
            self._t(9, bold=True, color=WHITE)
            self.cell(0, 7.5, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(270)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            "本資料は投資勧誘を目的とするものではありません。投資判断はご自身の責任で行ってください。",
            align="C")

    # ── Page2: 戦略コンセプト ──────────────────────────────────────────────────
    def concept_page(self, pattern_img: str, flow_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "戦略コンセプト — 波の転換点を捉える",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("仮説: 20SMAの傾きは波の天底を先行して示す", color=BLUE)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "相場は波のように上昇と下落を繰り返す。20SMA（20本移動平均）の「傾き」を見ると、\n"
            "波が天井をつけてから下落に転じる際、傾きはプラス→ゼロ→マイナスと変化する。\n"
            "この「ゼロクロス」を起点に、傾きが十分に傾いたことを確認してからエントリーする。")
        self.ln(3)

        self._sec("良いパターン vs 悪いパターン（接線の傾きの変化）", color=NAVY)
        self.image(pattern_img, x=14, y=self.get_y(), w=182, h=65)
        self.ln(69)

        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "良いパターン: ゼロクロス後も傾きが増大し続ける（転換が本物）\n"
            "悪いパターン: ゼロクロス後に傾きが戻る（偽シグナル→キャンセル）")
        self.ln(4)

        self._sec("エントリー判断フロー", color=NAVY)
        self.image(flow_img, x=14, y=self.get_y(), w=182, h=72)
        self.ln(76)

    # ── Page3: ロジック詳細 ────────────────────────────────────────────────────
    def logic_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "シグナル検出ロジック（計算式）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("STEP 1: インジケーター計算", color=BLUE)
        self._rule_box(
            "20SMA[i]  =  Close[i] の 20本移動平均\n"
            "生傾き[i] =  20SMA[i] - 20SMA[i-3]  （3本前との差）\n"
            "平均傾き[i]=  生傾き の 5本ローリング平均", color=BLUE)
        self._t(8)
        self.multi_cell(0, 5.5,
            "生傾きをさらに5本で平均化することで、1-2本のノイズに反応しない安定した傾きを得る。\n"
            "ゼロより大きい = 上昇トレンド中 / ゼロより小さい = 下降トレンド中。")
        self.ln(4)

        self._sec("STEP 2: ゼロクロス検出", color=BLUE)
        headers = ["方向", "条件", "意味"]
        widths  = [25, 90, 67]
        rows = [
            ("ロング", "平均傾き[i-1] < 0  かつ  平均傾き[i] >= 0", "傾きがゼロを下→上へ通過（波の底）"),
            ("ショート", "平均傾き[i-1] > 0  かつ  平均傾き[i] <= 0", "傾きがゼロを上→下へ通過（波の天井）"),
        ]
        self.set_font("YG","B",8)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, (d, c, m) in enumerate(rows):
            self.set_fill_color(LIGHT if i%2==0 else WHITE)
            self.set_text_color(*DARK)
            self.set_font("YG","B",8); self.cell(widths[0], 6, d, border=1, fill=True, align="C")
            self.set_font("YG","",8);  self.cell(widths[1], 6, c, border=1, fill=True, align="C")
            self.multi_cell(widths[2], 6, m, border=1, fill=True)
        self.set_text_color(*DARK)
        self.ln(4)

        self._sec("STEP 3: 傾き確認フィルター（核心のロジック）", color=AMBER)
        self._rule_box(
            "ゼロクロス後、以下を満たすまでエントリーを保留（Pending）\n"
            "ロング  : 平均傾き >= +0.05  （傾きが十分にプラス方向へ）\n"
            "ショート: 平均傾き <= -0.05  （傾きが十分にマイナス方向へ）", color=AMBER)

        self._t(8.5)
        self.multi_cell(0, 5.5,
            "このフィルターが「悪いパターン」を除外する核心。ゼロクロスしても傾きが弱いまま\n"
            "なら入らない。傾きが戻ってしまった場合（ロングでゼロ以下に戻る）は即キャンセル。")
        self.ln(3)

        self._sec("キャンセル条件", color=RED)
        cancel_rows = [
            ("タイムアウト",   "ゼロクロスから5本（75分）以内に確認できなかった",
             "弱い転換は待ちすぎると相場が別の方向へ"),
            ("傾き逆転",       "Pending中に傾きが元の方向へ戻った",
             "悪いパターン（0.0→-0.2→-0.1→0.0）を除外"),
        ]
        headers2 = ["キャンセル理由", "条件", "なぜ重要か"]
        widths2  = [35, 85, 62]
        self.set_font("YG","B",8)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(headers2, widths2):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, (r, c, why) in enumerate(cancel_rows):
            self.set_fill_color(LIGHT if i%2==0 else WHITE)
            self.set_text_color(*DARK)
            self.set_font("YG","B",8); self.cell(widths2[0], 6, r, border=1, fill=True, align="C")
            self.set_font("YG","",8);  self.cell(widths2[1], 6, c, border=1, fill=True, align="C")
            self.multi_cell(widths2[2], 6, why, border=1, fill=True)
        self.set_text_color(*DARK)

    # ── Page4: エントリー条件一覧 ──────────────────────────────────────────────
    def entry_page(self):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "エントリー条件 — 全条件を満たしたらエントリー",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("必須条件（全て満たすこと）", color=BLUE)
        conditions = [
            ("1", "ゼロクロス検出",
             "平均傾きが前バー>0かつ現バー<=0（ショート）\nまたは前バー<0かつ現バー>=0（ロング）",
             "波の転換点を機械的に検出"),
            ("2", "傾き確認フィルター",
             "ゼロクロス後、平均傾きが±0.05以上になるまで待つ\n（「傾きがちゃんと傾いた」確認）",
             "偽シグナル・弱い転換を除外。核心ロジック"),
            ("3", "タイムアウトなし",
             "ゼロクロスから5本（75分）以内に確認が取れること",
             "時間が経ちすぎた転換は使わない"),
            ("4", "クールダウン経過",
             "前回エントリーから8本（120分）以上経過していること",
             "連続エントリーによる資金の集中を防ぐ"),
            ("5", "イベントフィルター",
             "米国経済指標・FOMC発表の前後60分以外であること",
             "指標発表時の乱高下リスクを回避"),
        ]
        headers = ["No", "条件名", "判定基準", "なぜ重要か"]
        widths  = [10, 35, 90, 47]
        self.set_font("YG","B",8)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, (no, name, cond, why) in enumerate(conditions):
            self.set_fill_color(LIGHT if i%2==0 else WHITE)
            self.set_text_color(*DARK)
            self.set_font("YG","B",8)
            self.cell(widths[0], 12, no,    border=1, fill=True, align="C")
            self.cell(widths[1], 12, name,  border=1, fill=True, align="C")
            self.set_font("YG","",7.5)
            self.cell(widths[2], 12, cond,  border=1, fill=True)
            self.multi_cell(widths[3], 12, why, border=1, fill=True)
        self.set_text_color(*DARK)
        self.ln(4)

        self._sec("エントリー価格・ポジションサイジング", color=TEAL)
        self._t(8.5)
        sizing_rows = [
            ("方向", "ロング（Buy）", "ショート（Sell）"),
            ("エントリー価格", "現在Ask（終値 + スプレッド0.2pips）", "現在Bid（終値 - スプレッド0.2pips）"),
            ("損切り価格", "エントリー価格 - 5pips（固定）", "エントリー価格 + 5pips（固定）"),
            ("利確価格", "エントリー価格 + 10pips（固定）", "エントリー価格 - 10pips（固定）"),
            ("ユニット数", "口座残高 × 0.5% ÷ 5pips", "口座残高 × 0.5% ÷ 5pips"),
        ]
        ws3 = [40, 73, 69]
        self.set_font("YG","B",8)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(["項目","ロング","ショート"], ws3):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, row in enumerate(sizing_rows):
            self.set_fill_color(LIGHT if i%2==0 else WHITE)
            self.set_text_color(*DARK)
            self.set_font("YG","B",8 if i==0 else ""); self.set_font("YG","B" if i==0 else "",8)
            self.cell(ws3[0], 6, row[0], border=1, fill=True, align="C")
            self.set_font("YG","",8)
            self.cell(ws3[1], 6, row[1], border=1, fill=True, align="C")
            self.cell(ws3[2], 6, row[2], border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)
        self.ln(3)

        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "リスクリワード比 = 10pips ÷ 5pips = 1:2  "
            "（損益分岐勝率 = 5÷(5+10) = 33.3%）\n"
            "実績勝率42.6%（IS）/ 42.3%（OOS）は損益分岐を大きく上回る。")

    # ── Page5: エグジット & リスク管理 ────────────────────────────────────────
    def exit_page(self, bt_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "エグジット・リスク管理",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("エグジットルール（先に成立した条件で決済）", color=BLUE)
        exit_rows = [
            ("A. 利確（TP）",
             "エントリー価格から +10pips",
             "固定。スプレッド分控除して計算。\n到達した足の終値で決済。"),
            ("B. 損切り（SL）",
             "エントリー価格から -5pips",
             "固定。機械的に実行。\n「またすぐ戻るかも」は禁物。"),
        ]
        for title, cond, note in exit_rows:
            self.set_font("YG","B",9); self.set_text_color(*BLUE)
            self.cell(0, 6, f"▶ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_fill_color(235, 242, 255)
            self.set_draw_color(*BLUE); self.set_line_width(0.8)
            self.set_font("YG","B",9.5); self.set_text_color(*BLUE)
            self.multi_cell(0, 7, cond, border=1, fill=True, align="C")
            self.set_font("YG","",8); self.set_text_color(*DARK)
            self.set_x(self.l_margin+4)
            self.multi_cell(0, 5.5, note)
            self.set_line_width(0.2)
            self.ln(2)

        self._sec("バックテスト検証結果", color=NAVY)
        self.image(bt_img, x=14, y=self.get_y(), w=182, h=52)
        self.ln(56)

        headers = ["期間", "件数", "Long/Short", "勝率", "PF", "最大DD", "損益"]
        widths  = [28, 18, 24, 18, 14, 18, 62]
        rows = [
            ("IS（~2025/07）",  "136件", "75/61",  "42.6%", "1.39", "5.9%",  "+172,308円"),
            ("OOS（2025/08~）", "71件",  "33/38",  "42.3%", "1.36", "5.0%",  "+96,131円"),
        ]
        self.set_font("YG","B",8)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, row in enumerate(rows):
            self.set_fill_color(LIGHT if i%2==0 else WHITE)
            self.set_text_color(*DARK)
            for j, (val, w) in enumerate(zip(row, widths)):
                self.set_font("YG","B" if j==0 else "",8)
                if j == 6:
                    self.set_text_color(*GREEN)
                else:
                    self.set_text_color(*DARK)
                self.cell(w, 6, val, border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)
        self.ln(3)

        self._sec("この手法の特徴と注意点", color=RED)
        notes = [
            ("▲ スプレッドの影響",
             "TP10pips / SL5pipsのため、スプレッドが広い時間帯（流動性低下時）は不利。\n"
             "東京・ロンドン・NY各セッション中心での運用を推奨。"),
            ("▲ イベント時のギャップ",
             "SL5pipsは指標発表時のスリッページでギャップ突き抜けリスクあり。\n"
             "イベント前後60分のフィルターで軽減しているが完全回避は不可。"),
            ("▲ レンジ相場での連続損失",
             "ゼロクロスが頻繁に発生するレンジ相場では損失が続く可能性あり。\n"
             "クールダウン8本（120分）で連続エントリーは抑制。"),
        ]
        for title, desc in notes:
            self.set_font("YG","B",8.5); self.set_text_color(*RED)
            self.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG","",8); self.set_text_color(*DARK)
            self.set_x(self.l_margin+4)
            self.multi_cell(0, 5.5, desc)
            self.ln(1)

    # ── Page6: MT4実装 & チェックリスト ───────────────────────────────────────
    def checklist_page(self, today: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "MT4実装情報 & トレード判断チェックリスト",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("MT4ファイル構成", color=BLUE)
        mt4_rows = [
            ("インジケーター", "SMA_Tangent_Breakout.mq4",
             "メインチャートに20SMAを表示（平行=緑/上昇=青/下降=赤）"),
            ("シグナルインジケーター", "SMA_Slope_Signal.mq4",
             "サブウィンドウに平均傾きヒストグラム + ゼロクロス矢印"),
            ("EA（自動売買）", "SMA_Tangent_EA.mq4",
             "M15チャートで本戦略を自動実行（ストラテジーテスター対応）"),
        ]
        ws = [40, 55, 87]
        self.set_font("YG","B",8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(["種別","ファイル名","役割"], ws):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, row in enumerate(mt4_rows):
            self.set_fill_color(LIGHT if i%2==0 else WHITE); self.set_text_color(*DARK)
            self.set_font("YG","B",8); self.cell(ws[0], 6, row[0], border=1, fill=True, align="C")
            self.set_font("YG","",8);  self.cell(ws[1], 6, row[1], border=1, fill=True)
            self.multi_cell(ws[2], 6, row[2], border=1, fill=True)
        self.set_text_color(*DARK)
        self.ln(3)

        self._sec("ストラテジーテスター設定", color=TEAL)
        st_rows = [
            ("Expert", "SMA_Tangent_EA"),
            ("通貨ペア", "USDJPY"),
            ("期間（チャート足）", "M15（15分足）"),
            ("モデル", "Every tick（高精度）"),
            ("検証期間", "2024.10.14 ~ 2026.05.01"),
            ("初期証拠金", "1,000,000 JPY"),
            ("スプレッド", "2 points（= 0.2pips）"),
        ]
        ws2 = [55, 127]
        self.set_font("YG","B",8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(["設定項目","値"], ws2):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, (k, v) in enumerate(st_rows):
            self.set_fill_color(LIGHT if i%2==0 else WHITE); self.set_text_color(*DARK)
            self.set_font("YG","B",8); self.cell(ws2[0], 6, k, border=1, fill=True, align="C")
            self.set_font("YG","",8);  self.cell(ws2[1], 6, v, border=1, fill=True)
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        self._sec("1トレードの判断チェックリスト（最終確認）", color=NAVY)
        checks = [
            "平均傾きがゼロクロスしている（インジケーターのシグナル矢印を確認）",
            "ゼロクロス後、傾きが±0.05以上まで達している（確認フィルター通過）",
            "傾きがキャンセル条件（逆転・タイムアウト）に該当していない",
            "イベントカレンダーで前後60分以内に指標発表がないことを確認",
            "前回エントリーから120分（8バー）以上経過している",
            "損切り価格（エントリー±5pips）を事前に計算・記録した",
            "ロット数 = 口座残高 × 0.5% ÷ 5pips を計算した",
        ]
        for c in checks:
            self.set_font("YG","",9); self.set_text_color(*DARK)
            self.cell(0, 7, f"□  {c}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(270)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）\n"
            "本資料はFxCompanyが情報提供を目的として作成したものです。"
            "特定の有価証券・通貨の売買を推奨するものではありません。",
            align="C")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"  20SMA接線ゼロクロス転換戦略 ルール解説書PDF")
    print(f"{'='*50}\n")

    print("チャート生成中...")
    pattern_img = make_slope_pattern_chart()
    flow_img    = make_flow_chart()
    bt_img      = make_backtest_chart()
    print("  完了")

    print("PDF生成中...")
    pdf = RulesPDF()
    pdf.cover(today)
    pdf.concept_page(pattern_img, flow_img)
    pdf.logic_page()
    pdf.entry_page()
    pdf.exit_page(bt_img)
    pdf.checklist_page(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"usdjpy_slope_rules_{ts}.pdf"
    pdf.output(str(out))

    for f in [pattern_img, flow_img, bt_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
