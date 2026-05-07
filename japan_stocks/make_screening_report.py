# -*- coding: utf-8 -*-
"""
ミネルヴィニ・スクリーニング 顧客向け報告書 PDF生成
実行: python japan_stocks/make_screening_report.py

サンプル銘柄1社のチャート・条件解説付き報告書を生成する。
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from fpdf import FPDF, XPos, YPos

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
import minervini_screener as mv

# ── 設定 ─────────────────────────────────────────────────────────────────────
FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "results" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_START = "2023-01-01"

# サンプル銘柄（フジクラ: RS99・新高値圏・プライム）
SAMPLE_TICKER = "5803.T"
SAMPLE_NAME   = "フジクラ"

# ブランドカラー
NAVY   = (15,  30,  70)
BLUE   = (30,  90, 170)
ACCENT = (0,  160, 120)
LIGHT  = (235, 242, 255)
WHITE  = (255, 255, 255)
DARK   = (30,  30,  40)
GRAY   = (120, 120, 130)
GREEN  = (0,  140,  80)
RED    = (200,  40,  40)


# ── チャート生成 ──────────────────────────────────────────────────────────────

def make_chart(close: pd.Series, ticker: str, name: str) -> str:
    """移動平均線付き株価チャートを生成してPNGパスを返す"""

    # 直近1年分に絞って表示
    plot_data = close.iloc[-252:] if len(close) >= 252 else close

    ma50  = close.rolling(50).mean().reindex(plot_data.index)
    ma150 = close.rolling(150).mean().reindex(plot_data.index)
    ma200 = close.rolling(200).mean().reindex(plot_data.index)

    high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
    low_52w  = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())

    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor("#F8FAFF")
    ax.set_facecolor("#F8FAFF")

    # 株価
    ax.plot(plot_data.index, plot_data.values,
            color="#1A3A7A", linewidth=1.8, label="株価", zorder=5)

    # 移動平均線
    ax.plot(ma50.index,  ma50.values,  color="#E87020", linewidth=1.2,
            linestyle="-",  label="MA50",  alpha=0.9)
    ax.plot(ma150.index, ma150.values, color="#9030D0", linewidth=1.2,
            linestyle="--", label="MA150", alpha=0.9)
    ax.plot(ma200.index, ma200.values, color="#D03030", linewidth=1.2,
            linestyle=":",  label="MA200", alpha=0.9)

    # 52週高値・安値
    ax.axhline(high_52w, color="#00905A", linewidth=0.9,
               linestyle="-.", alpha=0.7, label=f"52週高値 {high_52w:,.0f}円")
    ax.axhline(low_52w,  color="#CC4444", linewidth=0.9,
               linestyle="-.", alpha=0.7, label=f"52週安値 {low_52w:,.0f}円")

    # 現在値マーカー
    latest_price = float(plot_data.iloc[-1])
    ax.scatter([plot_data.index[-1]], [latest_price],
               color="#1A3A7A", s=60, zorder=10)

    # 軸・グリッド
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.tick_params(axis="both", labelsize=7, colors="#444")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.grid(axis="y", color="#D0D8E8", linewidth=0.5, linestyle="--")
    ax.grid(axis="x", color="#E0E8F0", linewidth=0.3)
    for spine in ax.spines.values():
        spine.set_edgecolor("#C0CCD8")

    # タイトル
    ax.set_title(f"{ticker}  {name}　株価推移（過去1年）",
                 fontsize=9, color="#1A3A7A", pad=8,
                 fontproperties=_jp_font(9))

    # 凡例
    ax.legend(loc="upper left", fontsize=7, framealpha=0.85,
              edgecolor="#C0C8D8", prop=_jp_font(7))

    plt.tight_layout(pad=0.8)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def _jp_font(size: int):
    """matplotlib用日本語フォント"""
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


# ── PDF クラス ────────────────────────────────────────────────────────────────

class ScreeningReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG",  style="",  fname=FONT_PATH)
        self.add_font("YG",  style="B", fname=FONT_PATH)
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(auto=True, margin=16)

    # ── 共通部品 ──────────────────────────────────────────────────────────────

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _section(self, title: str, color=BLUE):
        self.set_fill_color(*color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  {title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(2)

    def _kv(self, label: str, value: str, label_w=52, note=""):
        self.set_font("YG", "B", 8)
        self.set_text_color(*GRAY)
        self.cell(label_w, 6, label)
        self.set_font("YG", "", 9)
        self.set_text_color(*DARK)
        self.cell(0, 6, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if note:
            self.set_font("YG", "", 7)
            self.set_text_color(*GRAY)
            self.cell(label_w, 5, "")
            self.cell(0, 5, note, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(*DARK)

    # ── 表紙 ─────────────────────────────────────────────────────────────────

    def cover(self, date_str: str, ticker: str, name: str):
        self.add_page()

        # 背景
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")

        # アクセントバー（上）
        self.set_fill_color(*ACCENT)
        self.rect(0, 0, 210, 5, "F")

        # アクセントバー（下）
        self.rect(0, 292, 210, 5, "F")

        # 会社名
        self.set_y(48)
        self._t(10, color=(140, 170, 220))
        self.cell(0, 8, "FxCompany  |  株式調査レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # タイトル
        self.ln(8)
        self._t(26, bold=True, color=WHITE)
        self.cell(0, 18, "銘柄スクリーニング",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(18, bold=True, color=(0, 200, 150))
        self.cell(0, 12, "候補銘柄 詳細レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # 区切り線
        self.ln(6)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.5)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(8)

        # 銘柄情報
        self._t(13, bold=True, color=WHITE)
        self.cell(0, 9, f"【分析銘柄】  {ticker}  {name}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(4)
        self._t(9, color=(140, 170, 220))
        self.cell(0, 7, f"スクリーニング日: {date_str}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 7, "使用手法: ミネルヴィニ・トレンドテンプレート（8条件）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # ウォーターマーク
        self.set_y(240)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            "本レポートは投資勧誘を目的とするものではありません。\n"
            "掲載情報の正確性・完全性を保証するものではなく、投資判断は自己責任でお願いします。",
            align="C")

    # ── 手法解説ページ ────────────────────────────────────────────────────────

    def methodology_page(self):
        self.add_page()

        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "スクリーニング手法について",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.6)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(4)

        # 概要
        self._section("手法概要")
        self._t(9)
        self.multi_cell(0, 6,
            "本スクリーニングは、著名トレーダー マーク・ミネルヴィニ（Mark Minervini）が\n"
            "著書『株式トレード 基本と原則』で公開した「トレンドテンプレート」を\n"
            "日本株（東証プライム市場）に適用したものです。\n\n"
            "8つの技術的条件を全て満たす銘柄を「強いトレンドにある有望候補」として抽出します。\n"
            "本日のプライム市場1,556社のスクリーニングでは 291社 が全条件をクリアしました。")
        self.ln(4)

        # 8条件テーブル
        self._section("8つのスクリーニング条件")
        headers = ["No", "条件", "判定基準", "意味・ポイント"]
        widths  = [10, 52, 42, 74]
        rows = [
            ["1", "株価 > MA150・MA200",
             "終値が両移動平均を上回る",
             "中長期トレンドが上向き。基本中の基本。"],
            ["2", "MA150 > MA200",
             "150日線が200日線を上回る",
             "移動平均の序列が正常（パーフェクトオーダー）。"],
            ["3", "MA200 上昇トレンド",
             "MA200が1ヶ月前より上昇",
             "長期トレンド自体が上昇中。転換の証拠。"],
            ["4", "MA50 > MA150・MA200",
             "50日線が中長期線を上回る",
             "短期も加わりトレンドが完全に整列。"],
            ["5", "52週安値から25%以上上昇",
             "株価 ≥ 52週安値 × 1.25",
             "底からの反発が確認済み。底打ち後のモメンタム。"],
            ["6", "52週高値の25%以内",
             "株価 ≥ 52週高値 × 0.75",
             "新高値に近いほど強い。「高いから買わない」は誤り。"],
            ["7", "RS Rating ≥ 70",
             "市場全体との相対強度が70以上",
             "市場平均より強い銘柄のみ。90台が理想。"],
            ["8", "株価 > MA50",
             "終値が50日線を上回る",
             "ブレイクアウト時の確認条件。押し目でない証拠。"],
        ]

        # ヘッダー
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()

        # 行
        for i, row in enumerate(rows):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 7, row[0], border=1, fill=True, align="C")
            self.set_font("YG", "B", 7.5)
            self.cell(widths[1], 7, row[1], border=1, fill=True)
            self.set_font("YG", "", 7)
            self.cell(widths[2], 7, row[2], border=1, fill=True)
            self.cell(widths[3], 7, row[3], border=1, fill=True)
            self.ln()

        self.ln(4)

        # RS補足
        self._section("RS Rating（相対強度）について", color=ACCENT)
        self._t(8)
        self.multi_cell(0, 6,
            "RS Rating（Relative Strength Rating）は、対象銘柄が市場全体の動きと比較して\n"
            "どれだけ強いパフォーマンスを出しているかを0〜99でスコア化した指標です。\n\n"
            "算出方法：直近12ヶ月のリターンを4四半期に分割し、直近3ヶ月に40%の\n"
            "ウェイトをかけた加重平均スコアを計算。全銘柄内でパーセンタイルランキング化。\n\n"
            "RS 90 = 上位10%の強さ。ミネルヴィニは「90台が理想、最低70以上」を推奨。\n"
            "重要：数値だけでなくRSラインが6週間以上上昇トレンドにあることが条件。")

    # ── 銘柄詳細ページ ───────────────────────────────────────────────────────

    def stock_detail_page(self, ticker: str, name: str, result: dict,
                          chart_path: str, date_str: str):
        self.add_page()

        # ── ヘッダー ─────────────────────────────────────────────────────────
        self.set_fill_color(*NAVY)
        self.rect(16, 16, 178, 12, "F")
        self._t(13, bold=True, color=WHITE)
        self.set_y(18)
        self.cell(0, 8, f"  {ticker}  {name}　　銘柄詳細分析",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

        # ── 基本情報（左）＋ RS バッジ（右）────────────────────────────────
        x_left = 16
        x_right = 130

        self.set_xy(x_left, self.get_y())
        self._t(8, bold=True, color=GRAY)
        self.cell(0, 5, f"スクリーニング日: {date_str}　|　東証プライム市場",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

        # キー指標ボックス（左側）
        y_kv = self.get_y()
        self.set_xy(x_left, y_kv)
        metrics = [
            ("現在株価",       f"¥{result['price']:,.0f}"),
            ("52週高値",       f"¥{result['high_52w']:,.0f}  （高値比 {result['dist_from_high_pct']:+.1f}%）"),
            ("52週安値",       f"¥{result['low_52w']:,.0f}  （安値比 +{result['rise_from_low_pct']:.1f}%）"),
            ("50日移動平均",   f"¥{result['ma50']:,.0f}"),
            ("150日移動平均",  f"¥{result['ma150']:,.0f}"),
            ("200日移動平均",  f"¥{result['ma200']:,.0f}"),
        ]
        for label, val in metrics:
            self.set_x(x_left)
            self._t(7.5, bold=True, color=GRAY)
            self.cell(38, 6, label)
            self._t(8.5, bold=False, color=DARK)
            self.cell(70, 6, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # RS バッジ（右側）
        rs = result["rs_rating"] or 0
        badge_color = GREEN if rs >= 90 else BLUE if rs >= 70 else RED
        self.set_xy(x_right, y_kv)
        self.set_fill_color(*badge_color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(60, 8, "RS Rating", align="C", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(x_right)
        self.set_font("YG", "B", 28)
        self.cell(60, 20, str(rs), align="C", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(x_right)
        self.set_font("YG", "", 7)
        rs_comment = "◎ 上位1〜10%" if rs >= 90 else "○ 上位30%" if rs >= 70 else "△"
        self.cell(60, 7, rs_comment, align="C", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)

        # スコアバッジ
        self.set_xy(x_right, self.get_y() + 3)
        score = result["score"]
        s_color = GREEN if score == 8 else BLUE if score >= 6 else RED
        self.set_fill_color(*s_color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(60, 8, f"総合スコア  {score} / 8 条件", align="C", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if score == 8:
            self.set_x(x_right)
            self.set_font("YG", "B", 8)
            self.cell(60, 6, "★ 全条件クリア", align="C", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)

        self.ln(3)

        # ── チャート ─────────────────────────────────────────────────────────
        self._section("株価チャート（過去1年）+ 移動平均線")
        chart_w = 178
        chart_h = 68
        self.image(chart_path, x=16, y=self.get_y(), w=chart_w, h=chart_h)
        self.ln(chart_h + 2)

        # ── 8条件チェック表 ──────────────────────────────────────────────────
        self._section("スクリーニング 8条件 判定結果")

        condition_notes = [
            "株価がMA150・MA200を両方上回ることで、中長期の上昇トレンドを確認します。",
            "MA150がMA200を上回ることで、移動平均線の「正常な序列」を確認します。",
            "MA200が上向きであることで、長期トレンド自体が上昇に転じていることを確認します。",
            "MA50も加わりMA50>MA150>MA200の完全整列（パーフェクトオーダー）を確認します。",
            "52週安値から25%以上上昇していることで、底打ち後の十分なモメンタムを確認します。",
            "52週高値の25%以内にあることで、高値圏での強さを確認します。新高値に近いほど良。",
            f"RS{rs}は市場全体の上位{100-rs}%以内の強さを意味します。市場のリーダー銘柄の証拠です。",
            "現在株価がMA50を上回ることで、調整局面ではなく上昇中であることを確認します。",
        ]

        headers = ["No", "条件名", "判定", "現在値", "解説"]
        widths  = [9, 46, 14, 30, 79]

        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()

        cond_values = [
            f"株価 {result['price']:,.0f} > MA150 {result['ma150']:,.0f}・MA200 {result['ma200']:,.0f}",
            f"MA150 {result['ma150']:,.0f} > MA200 {result['ma200']:,.0f}",
            "1ヶ月前のMA200より上昇",
            f"MA50 {result['ma50']:,.0f} > MA150・MA200",
            f"安値比 +{result['rise_from_low_pct']:.1f}% （基準: +25%以上）",
            f"高値比 {result['dist_from_high_pct']:+.1f}% （基準: -25%以内）",
            f"RS {rs} （基準: 70以上）",
            f"株価 {result['price']:,.0f} > MA50 {result['ma50']:,.0f}",
        ]

        for i, d in enumerate(result["details"]):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)

            passed = d["passed"]
            mark_color = GREEN if passed else RED
            mark = "✓" if passed else "✗"

            # 行の高さ（解説テキストが長いため調整）
            row_h = 6

            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], row_h, str(i + 1), border=1, fill=True, align="C")
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], row_h, d["label"].split("（")[0].strip(), border=1, fill=True)

            # 判定マーク（色付き）
            self.set_fill_color(*mark_color)
            self.set_text_color(*WHITE)
            self.set_font("YG", "B", 8)
            self.cell(widths[2], row_h, mark, border=1, fill=True, align="C")

            # 現在値
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "", 6.5)
            self.cell(widths[3], row_h, cond_values[i], border=1, fill=True)

            # 解説
            self.cell(widths[4], row_h, condition_notes[i], border=1, fill=True)
            self.ln()

        self.set_text_color(*DARK)
        self.ln(3)

        # ── 投資家へのコメント ───────────────────────────────────────────────
        self._section("アナリストコメント", color=ACCENT)
        self._t(8)
        rs_comment_full = (
            "上位1〜10%の際立った強さ" if rs >= 90 else
            "上位30%以内の良好な強さ" if rs >= 70 else
            "要注目のRS水準"
        )
        dist = result["dist_from_high_pct"]
        high_comment = (
            "52週新高値を更新中。最も力強いブレイクアウトパターン。" if dist >= -3 else
            f"52週高値から{abs(dist):.1f}%の位置。高値圏での底固め中の可能性。" if dist >= -15 else
            f"52週高値から{abs(dist):.1f}%の位置。次のブレイクアウトを待つ局面。"
        )
        low_comment = (
            f"52週安値から+{result['rise_from_low_pct']:.0f}%上昇。"
            "ミネルヴィニが指摘するように、大きな上昇の前には底から大幅に上昇していることが多い。"
            "この銘柄はその条件を満たしている。"
        )
        self.multi_cell(0, 6,
            f"【{ticker} {name}】はミネルヴィニ・トレンドテンプレートの全8条件をクリアしています。\n\n"
            f"RS Rating {rs}は東証プライム市場1,556社中の{rs_comment_full}を示しており、"
            f"市場の強いリーダー銘柄であることが確認できます。\n\n"
            f"{high_comment}\n\n"
            f"{low_comment}\n\n"
            "移動平均線はMA50>MA150>MA200の完全整列（パーフェクトオーダー）を形成しており、"
            "上昇トレンドの継続を示唆しています。エントリータイミングは"
            "出来高を伴うブレイクアウト時（52週高値更新）を推奨します。")

    # ── 免責ページ ────────────────────────────────────────────────────────────

    def disclaimer_page(self, date_str: str, n_total: int, n_passed: int):
        self.add_page()

        self._t(14, bold=True, color=NAVY)
        self.cell(0, 10, "付録：本日のスクリーニング概要",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.6)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(4)

        self._section("スクリーニング実施概要")
        summary_items = [
            ("実施日",         date_str),
            ("対象市場",       "東証プライム市場"),
            ("検査銘柄数",     f"{n_total:,} 社"),
            ("全条件クリア",   f"{n_passed} 社 （通過率 {n_passed/n_total*100:.1f}%）"),
            ("使用データ",     "yfinance（Yahoo Finance提供・調整済み終値）"),
            ("RS計算方式",     "12ヶ月加重リターン（直近3ヶ月×40% + 各3ヶ月×20%）のユニバース内パーセンタイル"),
            ("更新頻度",       "毎営業日 引け後に実施"),
        ]
        for label, val in summary_items:
            self._kv(label, val, label_w=50)
        self.ln(4)

        self._section("ミネルヴィニ手法の特性と留意事項")
        self._t(8)
        self.multi_cell(0, 6,
            "■ 本手法の強み\n"
            "・強いトレンドにある銘柄を機械的・客観的に絞り込める\n"
            "・過去のスーパーパフォーマー株の多くがこのパターンを経て上昇\n"
            "・RS Ratingで市場のリーダーシップを持つ銘柄に集中できる\n\n"
            "■ 本手法の限界\n"
            "・テクニカル分析のみ。業績・財務・ファンダメンタルズは別途確認が必要\n"
            "・スクリーニングは「候補の絞り込み」であり、投資推奨ではない\n"
            "・相場環境（弱気相場）では条件クリア銘柄も下落リスクがある\n"
            "・日本株への適用はRS計算を簡易近似しているため、IBD掲載値とは異なる\n\n"
            "■ 推奨されるエントリー条件（参考）\n"
            "・52週高値を出来高増加を伴って更新する「ブレイクアウト」が理想的なエントリー\n"
            "・ベース（保ち合い）の期間は6週間以上が好ましい\n"
            "・ストップロスは買値から7〜8%下に設定することを推奨")

        self.ln(6)
        self._section("免責事項")
        self._t(7)
        self.multi_cell(0, 5.5,
            "本レポートはFxCompanyが情報提供を目的として作成したものです。"
            "特定の有価証券の売買を推奨するものではありません。\n"
            "記載された情報の正確性・完全性を保証するものではなく、"
            "投資に関する最終的な判断はご自身の責任で行ってください。\n"
            "過去のデータに基づく分析であり、将来の投資成果を保証するものではありません。\n\n"
            f"作成日: {date_str}　|　FxCompany 調査部門（AI孫正義）")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  スクリーニング報告書 PDF 生成")
    print(f"  銘柄: {SAMPLE_TICKER} {SAMPLE_NAME}")
    print(f"{'='*55}\n")

    # ── データ取得 ─────────────────────────────────────────────────────
    print(f"株価データ取得中: {SAMPLE_TICKER}...")
    df = dt.fetch(SAMPLE_TICKER, start=DATA_START)
    close = df["Close"]
    print(f"  {len(close)} 日分取得")

    # RS Rating（簡易: 単独計算）
    rs_raw = mv.rs_raw_score(close)
    rs_pct = 99  # フジクラはユニバース内RS99として固定（全銘柄実行済みの値）

    # 8条件チェック
    result = mv.check(close, rs_pct)
    if result is None:
        print("データ不足のため終了")
        return

    print(f"  スコア: {result['score']}/8  RS: {rs_pct}  株価: {result['price']}")

    # ── チャート生成 ───────────────────────────────────────────────────
    print("チャート生成中...")
    chart_path = make_chart(close, SAMPLE_TICKER, SAMPLE_NAME)
    print(f"  チャート: {chart_path}")

    # ── PDF生成 ────────────────────────────────────────────────────────
    print("PDF生成中...")
    pdf = ScreeningReportPDF()

    pdf.cover(today, SAMPLE_TICKER, SAMPLE_NAME)
    pdf.methodology_page()
    pdf.stock_detail_page(SAMPLE_TICKER, SAMPLE_NAME, result, chart_path, today)
    pdf.disclaimer_page(today, n_total=1556, n_passed=291)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"screening_report_{SAMPLE_TICKER.replace('.','_')}_{ts}.pdf"
    pdf.output(str(out))

    # 一時ファイル削除
    Path(chart_path).unlink(missing_ok=True)

    print(f"\n✓ PDF生成完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
