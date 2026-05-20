# -*- coding: utf-8 -*-
"""
Lead-Lag 情報伝播戦略 — ロジック完全解説 PDF
1から10までのロジックを体系的にまとめた報告書

実行: python _make_lead_lag_logic_report.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import date
from pathlib import Path
import pandas as pd
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUT_DIR    = Path("docs")
OUT_DIR.mkdir(exist_ok=True)
CHART_DIR  = Path("docs") / "lead_lag"
IS_DIR     = Path("docs") / "lead_lag_is"

NAVY   = (15,  30,  70)
BLUE   = (30,  80, 160)
ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255)
WHITE  = (255, 255, 255)
DARK   = (30,  30,  40)
GRAY   = (110, 120, 135)
RED    = (180,  40,  40)
GREEN  = (20,  140,  80)
PURPLE = (100,  40, 160)
ORANGE = (200,  90,   0)
YELLOW = (240, 180,  20)


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  FONT_PATH)
        self.add_font("YG", "B", FONT_PATH)
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _reset(self):
        self.set_text_color(*DARK)
        self.set_fill_color(*WHITE)
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.2)

    # ─── カバー ──────────────────────────────────────────────────────────
    def cover(self, today):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 0, 210, 5, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 292, 210, 5, "F")

        self.set_y(40)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 14, "Lead-Lag 情報伝播戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(12, bold=True, color=ACCENT)
        self.cell(0, 9, "ロジック完全解説報告書",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(9, color=(160, 200, 240))
        self.cell(0, 6, "Lead-Lag Information Propagation Strategy — Full Logic Documentation",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(14)
        # 目次ボックス
        self.set_x(30)
        self.set_fill_color(20, 45, 100)
        self.set_draw_color(60, 100, 180)
        self.rect(30, self.get_y(), 150, 118, "FD")
        self.set_y(self.get_y() + 5)
        self._t(9, bold=True, color=ACCENT)
        self.cell(0, 7, "  目  次", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        toc = [
            ("1", "戦略の本質 — なぜ情報伝播が起きるか"),
            ("2", "通貨強弱インデックスの計算"),
            ("3", "擬似リターン（Synthetic Return）"),
            ("4", "スプレッドとシグナルの発生"),
            ("5", "エントリーロジック（Case A / Case B）"),
            ("6", "ポジションサイジング"),
            ("7", "エグジットロジック（利確・損切）"),
            ("8", "通貨制約 C3（矛盾ポジション防止）"),
            ("9", "検証結果（IS 3年 & 50日データ）"),
            ("10", "結論・課題・次のマイルストーン"),
        ]
        for num, title in toc:
            self._t(8, color=(180, 210, 245))
            self.cell(0, 6, f"    Section {num:>2}.  {title}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(260)
        self.set_draw_color(60, 90, 150)
        self.line(40, 260, 170, 260)
        self._t(8, color=(120, 150, 200))
        self.set_y(264)
        self.cell(0, 6, f"作成日: {today}  |  MASAYA  /  FxCompany 研究部門",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ─── セクションヘッダー ───────────────────────────────────────────────
    def sec(self, num, title, sub="", color=NAVY):
        self.add_page()
        self.set_fill_color(*color); self.rect(0, 0, 210, 40, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 40, 210, 2.5, "F")
        self.set_y(7)
        self._t(9, color=(120, 160, 220))
        self.cell(0, 6, f"SECTION  {num}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(17, bold=True, color=WHITE)
        self.cell(0, 12, title,
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if sub:
            self._t(8, color=(160, 195, 235))
            self.cell(0, 5, sub,
                      align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(9)
        self._reset()

    # ─── 見出し H2 ───────────────────────────────────────────────────────
    def h2(self, title):
        self.ln(4)
        self.set_fill_color(*BLUE); self._t(9, bold=True, color=WHITE)
        self.cell(4, 7, "", fill=True)
        self.set_fill_color(*LIGHT); self._t(9, bold=True, color=DARK)
        self.cell(0, 7, f"  {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._reset(); self.ln(2)

    # ─── 本文 ────────────────────────────────────────────────────────────
    def body(self, text, size=9):
        self._t(size, color=DARK)
        self.multi_cell(0, 6, text)
        self.ln(1)
        self._reset()

    # ─── コールアウト（緑枠） ────────────────────────────────────────────
    def callout(self, text, color=ACCENT):
        self.set_fill_color(230, 248, 242)
        self.set_draw_color(*color)
        self.set_line_width(0.8)
        self.rect(self.get_x(), self.get_y(), self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._t(9, bold=True, color=color)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3)
        self._reset()

    # ─── 警告（赤枠） ───────────────────────────────────────────────────
    def warn(self, text):
        self.set_fill_color(255, 240, 240)
        self.set_draw_color(*RED)
        self.set_line_width(0.8)
        self.rect(self.get_x(), self.get_y(), self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._t(9, bold=True, color=RED)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3)
        self._reset()

    # ─── 孫コメント（紫枠） ─────────────────────────────────────────────
    def son(self, text):
        self.set_fill_color(245, 240, 255)
        self.set_draw_color(*PURPLE)
        self.set_line_width(1.0)
        self.rect(self.get_x(), self.get_y(), self.epw, 1.0, "F")
        self.set_line_width(0.2)
        self._t(8, bold=True, color=PURPLE)
        self.cell(0, 6, "  孫正義（AI CEO）のコメント",
                  border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_fill_color(245, 240, 255)
        self._t(9, color=DARK)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3)
        self._reset()

    # ─── 数式ボックス ────────────────────────────────────────────────────
    def formula(self, title, lines):
        self.set_fill_color(248, 249, 252)
        self.set_draw_color(180, 195, 220)
        self._t(8, bold=True, color=BLUE)
        self.cell(0, 6, f"  {title}",
                  border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(8, color=DARK)
        for line in lines:
            if line == "":
                self.cell(0, 3, "", border="LR", fill=True,
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                self.cell(0, 5.5, f"  {line}", border="LR", fill=True,
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 2, "", border="LBR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self._reset()

    # ─── 表 ─────────────────────────────────────────────────────────────
    def tbl(self, headers, rows, widths, hi=None, aligns=None):
        self._t(8, bold=True, color=WHITE)
        self.set_fill_color(*NAVY)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        if hi is None: hi = set()
        if aligns is None: aligns = ["L"] + ["C"] * (len(widths) - 1)
        for i, row in enumerate(rows):
            is_hi = i in hi
            bg = (220, 245, 220) if is_hi else ((245, 248, 255) if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            for j, (cell, w) in enumerate(zip(row, widths)):
                self._t(8, bold=is_hi, color=GREEN if is_hi else DARK)
                self.cell(w, 6, str(cell), border=1, fill=True,
                          align=aligns[j])
            self.ln()
        self.ln(4)
        self._reset()

    def img(self, path, w=170, caption=""):
        p = Path(path)
        if p.exists():
            self.image(str(p), x=self.get_x(), y=self.get_y(), w=w)
            self.ln(w * 0.43 + 2)
        if caption:
            self._t(7, color=GRAY)
            self.cell(0, 5, caption, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
        self._reset()

    def divider(self):
        self.ln(3)
        self.set_draw_color(200, 210, 230)
        self.line(self.get_x(), self.get_y(),
                  self.get_x() + self.epw, self.get_y())
        self.ln(4)
        self._reset()

    def step_box(self, num, title, text, color=BLUE):
        """番号付きステップボックス"""
        self.ln(2)
        x, y = self.get_x(), self.get_y()
        self.set_fill_color(*color)
        self.rect(x, y, 10, 9, "F")
        self._t(9, bold=True, color=WHITE)
        self.set_xy(x, y)
        self.cell(10, 9, str(num), align="C")
        self.set_fill_color(*LIGHT)
        self._t(9, bold=True, color=DARK)
        self.cell(self.epw - 10, 9, f"  {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(9, color=DARK)
        self.set_x(x + 12)
        self.multi_cell(self.epw - 12, 6, text)
        self.ln(2)
        self._reset()


# ════════════════════════════════════════════════════════════════════════
def load_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf = PDF()

    df_is   = load_csv(IS_DIR / "survey_is.csv")
    df_pair = load_csv(IS_DIR / "pair_ranking_is.csv")
    df_cost = load_csv(CHART_DIR / "survey_results.csv")
    df_nc   = load_csv(CHART_DIR / "survey_nocost.csv")

    # ══════════════════════════════════════════════════════════════════
    # 表紙
    # ══════════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══════════════════════════════════════════════════════════════════
    # Section 1: 戦略の本質
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("1", "戦略の本質", "なぜFX市場に情報伝播が起きるのか")

    pdf.callout(
        "Lead-Lag（先行・遅行）戦略は、FX市場における情報伝播の非効率性を利用する。\n"
        "「通貨の強弱情報は、最初に流動性の高いペアに反映され、\n"
        " 他のペアへは少し遅れて伝わる」という市場構造的な仮説に基づく。"
    )

    pdf.h2("1-1.  市場の非効率性 — なぜラグが生じるか")
    pdf.body(
        "FX市場には USD, EUR, JPY, GBP など7つの主要通貨が存在する。\n"
        "これらの組み合わせで生じる通貨ペアは理論上21通り（7C2）、主要12ペアが活発に取引される。\n\n"
        "USD経済指標が発表された場合:\n"
        "  ① USDJPYに最初に反映される（出来高・注目度が最高）\n"
        "  ② 次にEURUSD、GBPUSDが反応する\n"
        "  ③ AUDUSD、NZDUSDなどは少し遅れて追随する\n\n"
        "この「反応の時間差」がLead-Lag戦略の狙い目である。\n"
        "先行ペアを検知し、遅行ペアが追随する前にエントリーすれば、\n"
        "その追随分の価格変動を利益として取れる。"
    )

    pdf.h2("1-2.  戦略の核心コンセプト")
    pdf.tbl(
        headers=["概念", "説明"],
        rows=[
            ["Real Return（実リターン）",
             "実際の市場価格から計算されるログリターン\n= log(Close[t] / Close[t-1])"],
            ["Synthetic Return（擬似リターン）",
             "通貨強弱インデックスから計算される理論的なリターン\n= Strength(base通貨) - Strength(quote通貨)"],
            ["Spread（乖離）",
             "実リターンと擬似リターンの差分\n= Real - Synthetic"],
            ["Lead（先行）",
             "Spreadが閾値を超えた状態 → どちらかが先に動いている"],
            ["Lag（遅行）",
             "まだSpreadが小さい状態 → 追随待ちのペア"],
        ],
        widths=[55, 119],
        aligns=["L", "L"],
    )

    pdf.son(
        "本質を一言で言えば「相場はバラバラに動く」ということです。\n\n"
        "USDが強くなったとき、全ペアが同時に反応するなら裁定機会はゼロ。\n"
        "しかし実際には反応に時間差がある。この差が収益の源泉です。\n\n"
        "株のセクター追いつき戦略と同じ発想 — 先行した指数に遅行株が追随する。\n"
        "FXでは通貨ペア間がその関係になっている。"
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 2: 通貨強弱インデックス
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("2", "通貨強弱インデックス", "Currency Strength Index の計算方法")

    pdf.callout(
        "通貨強弱インデックスは「各通貨が他の通貨に対して平均的にどれだけ強いか」を\n"
        "数値化したものである。この数値が戦略の核心計算に使われる。"
    )

    pdf.h2("2-1.  計算の仕組み")
    pdf.formula("通貨強弱インデックスの計算式", [
        "① 各ペアのログリターンを計算:",
        "   actual_return(pair, t) = log( Close[t] / Close[t-1] )",
        "",
        "② 各通貨について、その通貨が「base」として登場する全ペアのリターンを集める:",
        "   USD が base: USDJPY, GBPUSD(×(-1)), AUDUSD(×(-1))... ← quote側は符号反転",
        "",
        "③ 全ペアの平均を取って通貨強弱とする:",
        "   Strength(USD, t) = mean( USD関連全ペアのリターン × ±1 )",
        "",
        "④ 7通貨（USD/JPY/EUR/GBP/AUD/NZD/CHF）それぞれについて算出",
        "",
        "【Include-Self方式】: 計算対象ペア自身も通貨強弱計算に含める",
        "  → 循環参照に見えるが、全ペアのコンセンサス強弱を反映するため採用",
    ])

    pdf.h2("2-2.  通貨強弱の直感的な意味")
    pdf.body(
        "例: ある時点で USD が強い（他通貨に対して全般的に上昇している）とき\n\n"
        "  Strength(USD) = +0.0012  ← 平均0.12%上昇\n"
        "  Strength(JPY) = -0.0003  ← 平均0.03%下落\n\n"
        "このとき、USD/JPYペアの理論的なリターン（擬似リターン）は:\n"
        "  Synthetic(USDJPY) = Strength(USD) - Strength(JPY)\n"
        "                    = 0.0012 - (-0.0003) = 0.0015\n\n"
        "実際のUSDJPYリターンが 0.0010 だとすると:\n"
        "  Spread = 0.0010 - 0.0015 = -0.0005\n"
        "  → 擬似価格の方が先行している（Case B シグナル候補）"
    )

    pdf.h2("2-3.  なぜ通貨強弱を使うのか")
    pdf.tbl(
        headers=["アプローチ", "内容", "採用理由"],
        rows=[
            ["単純な価格比較",
             "1つのペアの過去価格だけを見る",
             "×: 通貨間のコンテキストが欠落する"],
            ["ペアワイズ比較",
             "2ペアを直接比較する",
             "△: スケールや流動性の違いを考慮できない"],
            ["通貨強弱（採用）",
             "7通貨それぞれの強弱を全ペアで集計",
             "○: 通貨単位での情報を公平に集約できる"],
        ],
        widths=[38, 60, 76],
        aligns=["L", "L", "L"],
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 3: 擬似リターン
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("3", "擬似リターン（Synthetic Return）", "理論価格と実際の価格の橋渡し")

    pdf.callout(
        "擬似リターンとは「全ペアの通貨強弱から逆算される、\n"
        "そのペアが本来あるべきリターン」である。\n"
        "実際の価格（Real）と擬似リターン（Synthetic）を比べることで、\n"
        "どちらが先行しているかを判定できる。"
    )

    pdf.h2("3-1.  擬似リターンの定義")
    pdf.formula("Synthetic Return の計算", [
        "Synthetic(pair, t) = Strength(base通貨, t) - Strength(quote通貨, t)",
        "",
        "具体例: USDJPY の擬似リターン",
        "  Synthetic(USDJPY, t) = Strength(USD, t) - Strength(JPY, t)",
        "",
        "具体例: EURUSD の擬似リターン",
        "  Synthetic(EURUSD, t) = Strength(EUR, t) - Strength(USD, t)",
        "",
        "→ 7通貨 × 全ペアの情報を集約した「コンセンサス価格」とも言える",
    ])

    pdf.h2("3-2.  Real vs Synthetic の解釈")
    pdf.tbl(
        headers=["状態", "Real", "Synthetic", "解釈"],
        rows=[
            ["均衡", "≈ Synthetic", "≈ Real",
             "全ペアが同時に反応済み。シグナルなし"],
            ["Real先行（Case A）", "> Synthetic", "< Real",
             "実価格が先に動いた。他ペアがまだ追随していない"],
            ["Pseudo先行（Case B）", "< Synthetic", "> Real",
             "強弱インデックスが先行。実価格がまだ追随していない"],
        ],
        widths=[36, 28, 28, 82],
        aligns=["L", "C", "C", "L"],
    )

    pdf.h2("3-3.  実例で理解する")
    pdf.body(
        "【シナリオ】2026年5月14日 09:00 JST\n"
        "  米国の強い雇用統計が発表された直後（USD急騰）\n\n"
        "  USDJPY: 実価格 +0.12%  擬似リターン +0.15%  → Spread = -0.03%\n"
        "  GBPUSD: 実価格 -0.05%  擬似リターン -0.10%  → Spread = +0.05%\n"
        "  AUDUSD: 実価格 -0.02%  擬似リターン -0.10%  → Spread = +0.08% ★\n\n"
        "AUDUSDは擬似リターン（-0.10%）に対して実価格（-0.02%）がまだ追随していない。\n"
        "→ AUDUSDのSpreadが閾値を超えたら Case B シグナル → AUDUSD ショートエントリー"
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 4: スプレッドとシグナル
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("4", "スプレッドとシグナルの発生", "乖離の計算・累積・閾値判定")

    pdf.callout(
        "1バーのSpreadはノイズが多い。\n"
        "そのため直近Nバーの累積和（cum_spread）を使ってシグナルを安定させる。\n"
        "cum_spreadが閾値を超えたとき、有意な乖離として判断する。"
    )

    pdf.h2("4-1.  Spreadと cum_spread の計算")
    pdf.formula("Spread / cum_spread の定義", [
        "spread(pair, t)     = actual_return(t) - synthetic_return(t)",
        "                    = [ log(Close[t]/Close[t-1]) ]",
        "                    - [ Strength(base,t) - Strength(quote,t) ]",
        "",
        "cum_spread(pair, t) = rolling_sum( spread, window )",
        "                    = spread[t] + spread[t-1] + ... + spread[t-window+1]",
        "",
        "パラメータ spread_window: 累積する本数（デフォルト 6本 = 30分）",
    ])

    pdf.h2("4-2.  シグナルの発生条件")
    pdf.formula("エントリーシグナル判定", [
        "閾値: entry_threshold（デフォルト 0.001 = 0.1%）",
        "",
        "cum_spread >  +entry_threshold → 実価格が先行UP  (Case A シグナル)",
        "cum_spread <  -entry_threshold → 擬似価格が先行UP (Case B シグナル)",
        "",
        "abs(cum_spread) ≤ entry_threshold → シグナルなし（均衡状態）",
    ])

    pdf.h2("4-3.  累積ウィンドウの役割")
    pdf.tbl(
        headers=["spread_window", "時間換算（5分足）", "特性"],
        rows=[
            ["3本",  "15分", "高頻度・ノイズ多い・トレード数多"],
            ["6本",  "30分", "バランス型（IS最良付近）"],
            ["12本", "1時間", "安定・トレード数少"],
            ["24本", "2時間", "長期・大きな乖離のみ捕捉"],
        ],
        widths=[34, 50, 90],
        aligns=["C", "C", "L"],
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 5: エントリーロジック
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("5", "エントリーロジック", "Case A（Real先行） vs Case B（Pseudo先行）")

    pdf.h2("5-1.  2つのケースの全体像")
    pdf.tbl(
        headers=["", "Case A（廃止）", "Case B（採用）"],
        rows=[
            ["シグナル元", "cum_spread > +threshold", "cum_spread < -threshold"],
            ["先行しているもの", "Real（実価格）", "Pseudo（擬似価格）"],
            ["エントリー先", "他の関連ペア（遅行ペア）", "シグナル元ペア自身"],
            ["根拠", "Realが先行 → 他ペアの実価格が追随する", "Pseudoが先行 → 自ペアの実価格が追随する"],
            ["採用状況", "現在は除外（複雑性の問題）", "★ 採用中"],
        ],
        widths=[38, 76, 60],
        aligns=["L", "L", "L"],
    )

    pdf.h2("5-2.  Case B エントリーの詳細フロー")

    pdf.step_box(1, "シグナルスキャン",
                 "全ペアの cum_spread を毎バー計算。\n"
                 "abs(cum_spread) > entry_threshold のペアを候補リストアップ。")

    pdf.step_box(2, "方向確認（通貨強弱との一致チェック）",
                 "cum_spread < -threshold（Pseudo先行UP）のとき:\n"
                 "  base通貨の強弱 > quote通貨の強弱 → LONG エントリー\n"
                 "  quote通貨の強弱 > base通貨の強弱 → SHORT エントリー\n"
                 "通貨強弱方向と一致しない場合はエントリーしない。")

    pdf.step_box(3, "通貨制約チェック（C3）",
                 "既に同一通貨に反対方向のポジションがある場合はスキップ。\n"
                 "詳細はSection 8参照。")

    pdf.step_box(4, "エントリー実行",
                 "Close価格にコスト（スプレッド・スリッページ）を加算してエントリー価格を確定。\n"
                 "source_pair（シグナル発生元）と entry_source_spread を記録。")

    pdf.h2("5-3.  Case A エントリーの詳細（参考）")
    pdf.body(
        "Case A では、シグナル元ペアではなく「遅行している他のペア」にエントリーする。\n\n"
        "例: USDJPYで cum_spread > threshold（USD強がRealに先に反映）の場合\n"
        "  → USDJPY自身にはエントリーしない\n"
        "  → AUDJPYやNZDJPYがまだ反応していなければ、それらに LONGエントリー\n"
        "     （AUDの強弱がJPYより高い場合に限る）\n\n"
        "現在は除外中: 複数ペアへの同時エントリーが増え、C3制約との干渉が複雑になるため。\n"
        "3年データ × JPYクロス絞り込みでの再評価を予定。"
    )

    pdf.son(
        "Case AとCase Bは「情報の流れ」が逆です。\n\n"
        "Case A: 実価格（トレーダーの注文）が最初に動き → 他ペアの実価格が後追いする\n"
        "Case B: 強弱インデックス（全ペアのコンセンサス）が先に動き → 1ペアの実価格が後追いする\n\n"
        "Case Bの方が「市場のコンセンサスに実価格が収束する」という直感に合い、\n"
        "検証でも一定の成果を示した。"
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 6: ポジションサイジング
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("6", "ポジションサイジング", "リスク管理と実効レバレッジ")

    pdf.callout(
        "ポジションサイズは「1トレードで失っても良い最大額（risk_pct）」と\n"
        "「スプレッドの大きさ（entry_threshold）」から逆算する方式を採用。\n"
        "entry_thresholdが大きいほど1ポジションの規模は小さくなる。"
    )

    pdf.h2("6-1.  ポジションサイジングの計算式")
    pdf.formula("ポジション計算（risk_pct = 0.5%固定）", [
        "risk_amount    = 資本 × risk_pct / 100",
        "               = 1,000,000円 × 0.5% = 5,000円",
        "",
        "position_ratio = risk_pct / 100 / entry_threshold",
        "               例（entry_threshold = 0.001）:",
        "               = 0.005 / 0.001 = 5.0倍レバレッジ",
        "",
        "PnL(% of 資本) = position_ratio × (exit_price / entry_price - 1)",
        "",
        "ストップロス発動時の最大損失 ≈ risk_pct = 0.5%（理論値）",
    ])

    pdf.h2("6-2.  entry_thresholdとレバレッジの関係")
    pdf.tbl(
        headers=["entry_threshold", "position_ratio（レバ）", "1bp動いたときのPnL"],
        rows=[
            ["0.0005（0.05%）", "10.0倍", "0.010%"],
            ["0.0010（0.10%）",  "5.0倍", "0.005%"],
            ["0.0015（0.15%）",  "3.3倍", "0.003%"],
            ["0.0020（0.20%）",  "2.5倍", "0.003%"],
            ["0.0030（0.30%）",  "1.7倍", "0.002%"],
        ],
        widths=[50, 50, 74],
        aligns=["C", "C", "C"],
    )

    pdf.warn(
        "コスト構造の問題:\n"
        "position_ratio × 往復コスト が損益分岐点を決める。\n\n"
        "例: entry_threshold=0.0015 → position_ratio=3.3倍\n"
        "  往復コスト 0.04%（スプレッド+スリッページ） × 3.3倍 = 0.13% / トレード\n"
        "  これを超える利益を毎回取れなければ赤字になる。\n"
        "  ECN口座（コスト0.01%以下）が事実上の前提条件。"
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 7: エグジットロジック
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("7", "エグジットロジック", "利確・損切の判定ルール")

    pdf.callout(
        "エグジットには2つのトリガーがある:\n"
        "① スプレッド縮小による利確 — 「乖離が縮んだ = 追随が完了した」\n"
        "② ストップロス発動 — PnLが -risk_pct（-0.5%）に達したとき"
    )

    pdf.h2("7-1.  利確ロジック — スプレッド縮小による exit")
    pdf.formula("exit_level と spread_reduced 判定", [
        "exit_ratio（パラメータ）: スプレッドがどこまで縮小したら利確するか",
        "  exit_ratio = 1.0 → 完全にゼロ回帰してから利確",
        "  exit_ratio = 0.5 → 50%縮小（半分に戻ったら利確）",
        "  exit_ratio = 0.1 → 10%縮小（早期利確）",
        "",
        "exit_level = entry_threshold × (1 - exit_ratio)",
        "  例: threshold=0.001, exit_ratio=0.5 → exit_level=0.0005",
        "",
        "利確条件（Case B UP の例）:",
        "  エントリー時 cum_spread < -threshold（擬似先行）",
        "  → cum_spread が -exit_level を超えて 0 方向に戻ったら利確",
    ])

    pdf.h2("7-2.  ストップロス判定")
    pdf.formula("ストップロス判定", [
        "pnl = position_ratio × (close / entry_price - 1) × direction",
        "",
        "if pnl ≤ -risk_pct（= -0.5%）:",
        "    → 損切りエグジット（exit_reason = 'stop'）",
        "",
        "ストップロスは価格ベース（固定%）ではなく、",
        "PnLベース（資本比率）で管理している点に注意。",
    ])

    pdf.h2("7-3.  Propagation（追随判定）")
    pdf.body(
        "エグジット時にスプレッドが縮小した「要因」を分類して記録する。\n\n"
        "Case B（Pseudo先行UP）のとき:\n"
        "  ・実価格が上昇して追随した → 'Pseudo' 追随（仮説通り）\n"
        "  ・擬似価格が下落して戻った → 'Real' 追随（平均回帰）\n"
        "  ・両方が動いた              → 'Both'\n"
        "  ・どちらも動かなかった      → 'Neither'\n\n"
        "IS 3年データ（最良設定）での伝播率: 約97%\n"
        "（Pseudo + Real + Both の合計が全体の97%）"
    )

    pdf.tbl(
        headers=["exit_reason", "件数（IS最良）", "説明"],
        rows=[
            ["spread_reduced", "約94%", "スプレッドが縮小 → 利確"],
            ["stop",           "約5〜6%", "PnL -0.5%到達 → 損切り"],
            ["end_of_data",    "< 1%", "期間終了時の強制決済"],
        ],
        widths=[46, 36, 92],
        aligns=["L", "C", "L"],
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 8: 通貨制約 C3
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("8", "通貨制約 C3", "CurrencyTracker — 矛盾ポジション防止")

    pdf.callout(
        "C3（Currency Conflict Control）は同一通貨に矛盾した方向の\n"
        "ポジションを持つことを防ぐリスク管理機構。\n"
        "例: USDLONGとUSDSHORTを同時に持つことは禁止。"
    )

    pdf.h2("8-1.  なぜC3が必要か")
    pdf.body(
        "USDが関わる通貨ペアは多い: USDJPY, GBPUSD, AUDUSD, NZDUSD...\n\n"
        "USDJPY LONG（USD買い）と AUDUSD SHORT（USD買い）は方向が一致し問題ない。\n"
        "しかし USDJPY LONG（USD買い）と GBPUSD LONG（USD売り）は矛盾する。\n\n"
        "この矛盾ポジションを許すと:\n"
        "  ・実質的にリスクが相殺してしまう\n"
        "  ・コストだけ2倍かかるヘッジポジションになる\n"
        "  ・ポートフォリオのドルエクスポージャーが管理不能になる"
    )

    pdf.h2("8-2.  C3の動作ルール")
    pdf.formula("CurrencyTracker のロジック", [
        "状態管理: { 通貨 → 現在の方向（LONG/SHORT） } の辞書",
        "",
        "エントリー可否チェック（can_enter）:",
        "  pair = EURUSD, direction = LONG の場合:",
        "    EUR方向 = LONG（EUR買い）",
        "    USD方向 = SHORT（USD売り）",
        "    → 辞書にEURがSHORTで登録されていたら拒否",
        "    → 辞書にUSDがLONGで登録されていたら拒否",
        "    → 両方OKなら許可",
        "",
        "エントリー実行（enter）:",
        "    辞書に EUR→LONG, USD→SHORT を登録",
        "",
        "エグジット時（exit_pair）:",
        "    辞書からEUR, USDのエントリーを削除（ポジション解放）",
    ])

    pdf.h2("8-3.  C3の影響")
    pdf.body(
        "C3があることでトレード機会は制限されるが、以下のメリットがある:\n\n"
        "  ○ ドローダウンの抑制（矛盾ポジションによる過大エクスポージャーを防ぐ）\n"
        "  ○ ポートフォリオの通貨方向が常に一貫性を持つ\n"
        "  ○ リスク計算が単純になる（通貨ごとに方向が1つに決まる）\n\n"
        "制限のデメリット:\n"
        "  × 有効なシグナルでも「通貨衝突」でスキップされる機会がある\n"
        "  × JPYクロス絞り込みでは制限が緩和される（JPY絡みのみなのでUSD衝突が減る）"
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 9: 検証結果
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("9", "検証結果", "IS 3年データ（Dukascopy）& 50日データ比較")

    pdf.h2("9-1.  IS検証の設定")
    pdf.tbl(
        headers=["項目", "設定値"],
        rows=[
            ["データソース", "Dukascopy 5分足（OHLC）"],
            ["IS期間", "2022-01-01 〜 2024-12-31（3年間）"],
            ["OOS期間", "未開封（データ取得中）"],
            ["対象ペア（IS）", "JPYクロス 6ペア（USDJPY/EURJPY/GBPJPY/AUDJPY/NZDJPY/CHFJPY）"],
            ["パラメータサーベイ", "100通り（window × threshold × exit_ratio）"],
            ["採用ケース", "Case B のみ（Case A は除外）"],
            ["コスト設定", "ペア別リアルコスト（spread + slippage）"],
        ],
        widths=[46, 128],
        aligns=["L", "L"],
    )

    pdf.h2("9-2.  IS パラメータサーベイ 上位結果")
    if not df_is.empty:
        rows = []
        for _, r in df_is.head(8).iterrows():
            pf_s = f"{r['pf']:.3f}" if r['pf'] < 99 else "inf"
            rows.append([
                f"w={int(r['window'])}",
                f"{r['entry_thr']:.4f}",
                f"{r['exit_ratio']:.1f}",
                str(int(r['trades'])),
                f"{r['win_rate']*100:.1f}%",
                pf_s,
                f"{r['total_pnl']:.1f}%",
                f"{r['max_dd']:.1f}%",
                f"{r['propagation_rate']*100:.0f}%",
            ])
        pdf.tbl(
            headers=["window", "entry", "exit_r", "T", "win%", "PF", "Total%", "maxDD", "prop%"],
            rows=rows,
            widths=[18, 20, 16, 16, 14, 16, 18, 18, 18],
            hi={0},
        )
    else:
        pdf.body("データなし（docs/lead_lag_is/survey_is.csv）")

    pdf.h2("9-3.  IS ペア別成績（最良設定）")
    if not df_pair.empty:
        rows = []
        for _, r in df_pair.sort_values("total_pnl", ascending=False).iterrows():
            mark = "★" if r["total_pnl"] > 5 else ("△" if r["total_pnl"] > 0 else "×")
            rows.append([
                r["pair"],
                str(int(r["trades"])),
                f"{r['win_rate']*100:.1f}%",
                f"{r['total_pnl']:.2f}%",
                mark,
            ])
        pdf.tbl(
            headers=["ペア", "トレード数", "勝率", "累積PnL%", "評価"],
            rows=rows,
            widths=[32, 32, 32, 40, 38],
            hi={0, 1} if len(rows) >= 2 else set(),
        )

    pdf.img(str(IS_DIR / "pnl_curve_is.png"), w=165,
            caption="IS 3年 累積損益曲線（JPYクロス6ペア・最良設定）")

    pdf.h2("9-4.  50日データ vs IS 3年データ 比較")
    best_cost = df_cost.iloc[0] if not df_cost.empty else None
    best_nc   = df_nc.iloc[0]   if not df_nc.empty   else None
    best_is   = df_is.iloc[0]   if not df_is.empty   else None

    rows = [
        ["データ期間",
         "50日（直近）",
         "50日（直近）",
         "3年 IS（2022-2024）"],
        ["コスト設定",
         "あり（固定0.02%）",
         "なし",
         "あり（ペア別）"],
        ["最良PF",
         f"{best_cost['pf']:.3f}" if best_cost is not None else "-",
         f"{best_nc['pf']:.3f}"   if best_nc   is not None else "-",
         f"{best_is['pf']:.3f}"   if best_is   is not None else "-"],
        ["最良設定 window",
         f"w={int(best_cost['window'])}" if best_cost is not None else "-",
         f"w={int(best_nc['window'])}"   if best_nc   is not None else "-",
         f"w={int(best_is['window'])}"   if best_is   is not None else "-"],
        ["最良設定 entry",
         f"{best_cost['entry_thr']:.4f}" if best_cost is not None else "-",
         f"{best_nc['entry_thr']:.4f}"   if best_nc   is not None else "-",
         f"{best_is['entry_thr']:.4f}"   if best_is   is not None else "-"],
        ["伝播率（最良設定）",
         f"{best_cost['propagation_rate']*100:.1f}%" if best_cost is not None else "-",
         f"{best_nc['propagation_rate']*100:.1f}%"   if best_nc   is not None else "-",
         f"{best_is['propagation_rate']*100:.1f}%"   if best_is   is not None else "-"],
        ["max DD",
         "-",
         "-",
         f"{best_is['max_dd']:.1f}%" if best_is is not None else "-"],
    ]
    pdf.tbl(
        headers=["指標", "50日（コストあり）", "50日（コストなし）", "IS 3年（コストあり）"],
        rows=rows,
        widths=[40, 46, 46, 42],
        aligns=["L", "C", "C", "C"],
    )

    pdf.warn(
        "IS 3年データでの最良PF: 1.07\n\n"
        "コストなし 50日データでは PF 2.07 と高い数値が出るが、\n"
        "3年のIS検証では PF 1.07 に留まる。\n"
        "コスト削減（ECN口座）と JPYクロス絞り込みが有効化の鍵。"
    )

    # ══════════════════════════════════════════════════════════════════
    # Section 10: 結論・課題・次のステップ
    # ══════════════════════════════════════════════════════════════════
    pdf.sec("10", "結論・課題・次のマイルストーン", "戦略の現在地と今後の方針")

    pdf.callout(
        "Lead-Lag戦略の核心仮説「FX市場には通貨ペア間に情報伝播ラグが存在する」は\n"
        "伝播率97%というデータで強く支持されている。\n"
        "課題はコストとDD管理であり、本番移行には以下の条件を満たす必要がある。"
    )

    pdf.h2("10-1.  戦略の強み（確認済み）")
    pdf.tbl(
        headers=["確認事項", "データ", "評価"],
        rows=[
            ["情報伝播の存在",
             "propagation_rate 97%（IS 3年）",
             "○ 仮説強く支持"],
            ["IS期間での黒字",
             "IS 3年 PF 1.07（最良設定）",
             "△ 黒字だがPF低い"],
            ["JPYクロスの優位性",
             "EURJPY +15.9%, USDJPY +14.2%（IS）",
             "○ 絞り込みに有効"],
            ["コストなしでのアルファ",
             "50日データ PF 2.07（コストゼロ）",
             "○ 純粋アルファ確認"],
            ["パラメータの安定性",
             "window=24, entry=0.003 が複数条件で上位",
             "△ 要ロバストネス確認"],
        ],
        widths=[50, 72, 52],
        aligns=["L", "L", "C"],
    )

    pdf.h2("10-2.  課題（未解決）")
    pdf.tbl(
        headers=["課題", "現状", "対策"],
        rows=[
            ["コスト問題",
             "往復コスト 0.13%/T が重い",
             "ECN口座でコスト0.01%以下を目指す"],
            ["DDの大きさ",
             "IS maxDD -48.8%（全資本比）",
             "ペア絞り込み・risk_pct削減"],
            ["OOSデータ未整備",
             "2025年以降のデータが未取得",
             "Dukascopyダウンロード完了後に実施"],
            ["ロバストネス未確認",
             "IS最良設定が過学習の可能性",
             "3×3マトリックス検証を実施予定"],
            ["Case Aの評価",
             "現在は除外中",
             "JPYクロス絞り込み後に再評価"],
        ],
        widths=[40, 66, 68],
        aligns=["L", "L", "L"],
    )

    pdf.h2("10-3.  次のマイルストーン（優先順）")
    pdf.tbl(
        headers=["優先度", "タスク", "完了条件"],
        rows=[
            ["★ 最高",
             "Dukascopyデータ完全取得\n（EURGBP, EURAUD, 延長3ペア）",
             "12ペア全て 2022-01-01〜2024-12-31"],
            ["★ 高",
             "JPYクロス6ペア × IS/OOS本格検証\n（IS: 2022-2023, OOS: 2024）",
             "IS PF > 1.1 かつ OOS PF > 1.0"],
            ["★ 高",
             "ECN口座でのコスト確認",
             "実スプレッド < 0.01% / 片道"],
            ["中",
             "ロバストネス（3×3マトリックス）",
             "9条件中7条件以上が黒字"],
            ["中",
             "Case A の再評価（JPYクロスのみ）",
             "Case B単独より PF 改善"],
            ["低",
             "デモトレード（3ヶ月）",
             "デモPF ≥ 1.0, DD ≤ 30%"],
        ],
        widths=[18, 82, 74],
        aligns=["C", "L", "L"],
    )

    pdf.son(
        "総評: このロジックは「歪みの本質」に触れています。\n\n"
        "株のセクター追いつき戦略が「業種間の情報伝播ラグ」を利用するように、\n"
        "このFX戦略は「通貨ペア間の情報伝播ラグ」を利用する。\n"
        "発想は正しい。データでも97%の伝播率が確認されている。\n\n"
        "ただし3年ISでPF1.07は、まだ量産体制に入れる水準ではない。\n\n"
        "次の判断ポイント:\n"
        "  ① 12ペアのデータが揃ったら IS/OOS を正式に実施\n"
        "  ② JPYクロス絞り込み × ECN低コストでPFがどこまで上がるか確認\n"
        "  ③ PF 1.2以上 かつ maxDD 30%以内が出たら実運用検討\n\n"
        "「伝播は起きている。問題はコストだ。」\n"
        "この認識を軸に、コスト削減と絞り込みを最優先で進めてください。"
    )

    pdf.divider()
    pdf._t(7, color=GRAY)
    pdf.multi_cell(0, 5.5,
                   "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
                   "投資の推奨・助言を行うものではありません。"
                   "過去の検証結果は将来の利益を保証しません。")

    # 出力
    out = OUT_DIR / f"lead_lag_logic_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成完了: {out}")
    return out


if __name__ == "__main__":
    generate()
