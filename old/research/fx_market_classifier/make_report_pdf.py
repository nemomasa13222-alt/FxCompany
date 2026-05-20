# -*- coding: utf-8 -*-
"""
FX市場状態分類システム 設計根拠レポート PDF生成
実行: python -m fx_market_classifier.make_report_pdf
"""

from datetime import date
from pathlib import Path

from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── カラーパレット ─────────────────────────────────────────────────────────────
NAVY   = (15,  30,  70)
BLUE   = (30,  80, 160)
ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255)
WHITE  = (255, 255, 255)
DARK   = (30,  30,  40)
GRAY   = (110, 120, 135)
RED    = (180,  40,  40)
GREEN  = (20,  140,  80)


# ── ベースクラス ──────────────────────────────────────────────────────────────

class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YuGoth", style="",  fname=FONT_PATH)
        self.add_font("YuGoth", style="B", fname=FONT_PATH)
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)

    def _text(self, size=9, bold=False, color=DARK):
        self.set_font("YuGoth", "B" if bold else "", size)
        self.set_text_color(*color)

    # ── 表紙 ─────────────────────────────────────────────────────────────────

    def cover(self, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*ACCENT)
        self.rect(0, 0, 210, 4, "F")

        self.set_y(50)
        self._text(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)

        self._text(22, bold=True, color=WHITE)
        self.cell(0, 14, "FX市場状態分類システム",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._text(11, color=(160, 200, 240))
        self.cell(0, 8, "FX Market State Classification System",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)

        self._text(9, color=(180, 210, 240))
        self.cell(0, 7, "通貨強弱 x 自己相関係数による",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 7, "トレンド / 平均回帰 戦略フィルタリング",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(16)

        # KPIボックス
        kpis = [
            ("対象通貨ペア", "12ペア"),
            ("分析時間軸", "5分足"),
            ("分類クラス", "3種"),
            ("アルゴ", "ACF lag=1"),
        ]
        self._kpi_row(kpis, y=160)

        self.set_y(200)
        self.set_draw_color(60, 90, 150)
        self.line(40, 200, 170, 200)

        self._text(8, color=(120, 150, 200))
        self.set_y(205)
        self.cell(0, 6, f"作成日: {today}  |  作成: FxCompany 研究部門",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, "本資料はバックテスト研究目的の内部資料です",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def _kpi_row(self, items: list, y: float):
        self.set_y(y)
        box_w = 38
        total_w = box_w * len(items) + 6 * (len(items) - 1)
        start_x = (210 - total_w) / 2
        for i, (label, value) in enumerate(items):
            x = start_x + i * (box_w + 6)
            self.set_fill_color(20, 45, 100)
            self.set_draw_color(60, 100, 180)
            self.rect(x, y, box_w, 24, "FD")
            self.set_xy(x, y + 2)
            self._text(7, color=(140, 170, 220))
            self.cell(box_w, 5, label, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_xy(x, y + 9)
            self._text(14, bold=True, color=ACCENT)
            self.cell(box_w, 10, value, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── セクションページ ──────────────────────────────────────────────────────

    def section_page(self, number: str, title: str, subtitle: str = ""):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 38, "F")
        self.set_fill_color(*ACCENT)
        self.rect(0, 38, 210, 2, "F")
        self.set_y(8)
        self._text(9, color=(120, 160, 220))
        self.cell(0, 6, f"SECTION  {number}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._text(16, bold=True, color=WHITE)
        self.cell(0, 11, title,
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if subtitle:
            self._text(8, color=(160, 195, 235))
            self.cell(0, 5, subtitle,
                      align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)
        self.ln(8)

    # ── コンテンツヘルパー ────────────────────────────────────────────────────

    def h2(self, title: str):
        self.ln(3)
        self.set_fill_color(*BLUE)
        self._text(9, bold=True, color=WHITE)
        self.cell(4, 7, "", fill=True)
        self.set_fill_color(*LIGHT)
        self.cell(0, 7, f"  {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)
        self.ln(2)

    def h3(self, title: str):
        self.ln(2)
        self._text(9, bold=True, color=BLUE)
        self.cell(0, 6, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)

    def body(self, text: str, size: int = 9):
        self._text(size)
        self.multi_cell(0, 6, text)
        self.ln(1)

    def callout(self, text: str, color=ACCENT):
        self.set_fill_color(230, 248, 242)
        self.set_draw_color(*color)
        self.set_line_width(0.8)
        x, y = self.get_x(), self.get_y()
        self.rect(x, y, self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._text(9, bold=True, color=color)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3)
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.2)

    def formula_box(self, title: str, lines: list[str]):
        self.set_fill_color(248, 249, 252)
        self.set_draw_color(180, 195, 220)
        self._text(8, bold=True, color=BLUE)
        self.cell(0, 6, f"  {title}", border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._text(8, color=DARK)
        for line in lines:
            self.cell(0, 5.5, f"  {line}", border="LR", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 2, "", border="LBR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def table(self, headers: list, rows: list, widths: list,
              highlight_last: bool = True):
        self._text(8, bold=True, color=WHITE)
        self.set_fill_color(*NAVY)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        for i, row in enumerate(rows):
            is_last = highlight_last and (i == len(rows) - 1)
            bg = (235, 240, 255) if is_last else ((245, 248, 255) if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            for j, (cell, w) in enumerate(zip(row, widths)):
                self._text(8, bold=is_last, color=DARK)
                self.cell(w, 6, str(cell), border=1, fill=True,
                          align="L" if j == 0 else "C")
            self.ln()
        self.ln(4)

    def divider(self):
        self.set_draw_color(200, 210, 230)
        self.line(self.get_x(), self.get_y() + 1,
                  self.get_x() + self.epw, self.get_y() + 1)
        self.ln(4)


# ── レポート本文 ──────────────────────────────────────────────────────────────

def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf = ReportPDF()

    # ══ 表紙 ═══════════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: システム概要 ═════════════════════════════════════════════════
    pdf.section_page("1", "システム概要", "何をするシステムか・基本思想")

    pdf.callout(
        "このシステムは「未来予測」を行いません。\n"
        "現時点の市場が「どの戦略が機能しやすい状態にあるか」を自動分類するフィルターです。\n"
        "トレーダーは分類結果に合った戦略のみを実行し、それ以外は待機します。"
    )
    pdf.ln(2)

    pdf.h2("1-1.  分類する3つの市場状態")
    pdf.table(
        headers=["状態", "条件（概要）", "対応戦略", "イメージ"],
        rows=[
            ["TREND",
             "通貨強弱差が大 かつ ACF > 0",
             "BB 1σ 順張りブレイク",
             "強い通貨を買い、弱い通貨を売る"],
            ["MEAN_REVERSION",
             "通貨強弱差が小 かつ ACF < 0",
             "BB 3σ 逆張りタッチ",
             "行き過ぎた動きをフェードする"],
            ["NO_TRADE",
             "上記以外",
             "待機",
             "エッジなし。ポジションを持たない"],
        ],
        widths=[30, 48, 42, 54],
        highlight_last=False,
    )

    pdf.h2("1-2.  対象通貨ペア（12ペア）")
    pdf.body(
        "JPY絡み6ペア・USD絡み3ペア・クロスペア3ペアを対象とします。\n"
        "7通貨（USD / JPY / EUR / GBP / AUD / NZD / CHF）が登場します。"
    )
    pdf.table(
        headers=["JPYクロス", "USDペア", "その他クロス"],
        rows=[
            ["USDJPY", "GBPUSD", "EURGBP"],
            ["EURJPY", "AUDUSD", "EURAUD"],
            ["GBPJPY", "NZDUSD", "AUDNZD"],
            ["AUDJPY", "—", "—"],
            ["NZDJPY", "—", "—"],
            ["CHFJPY", "—", "—"],
        ],
        widths=[58, 58, 58],
        highlight_last=False,
    )

    pdf.h2("1-3.  分析パラメータ（初期値）")
    pdf.table(
        headers=["パラメータ", "値", "意味"],
        rows=[
            ["時間軸",              "5分足",   "デイトレ〜スキャルピング想定"],
            ["ACF計算ウィンドウ",   "100本",   "直近500分（約8.3時間）"],
            ["ACFラグ",             "1",       "1本前のバーとの相関"],
            ["ボリンジャーバンド",  "20本",    "エントリーシグナル用"],
            ["ATR",                "14本",    "ボラティリティ計測用"],
            ["強弱差閾値",          "0.0008",  "IS検証で要チューニング"],
            ["ACFトレンド閾値",     "+0.05",   "同上"],
            ["ACF平均回帰閾値",     "-0.05",   "同上"],
        ],
        widths=[52, 24, 98],
        highlight_last=False,
    )

    # ══ Section 2: 通貨強弱 ═════════════════════════════════════════════════════
    pdf.section_page("2", "通貨強弱の算出", "Strength Index — 設計根拠と計算式")

    pdf.h2("2-1.  なぜ通貨強弱を使うのか")
    pdf.body(
        "FXの値動きは「2通貨の相対的な力関係」で決まります。\n"
        "USDJPYが上昇しても、それがドル高なのか円安なのかは、USDJPYだけ見ても分かりません。\n\n"
        "通貨強弱を計算することで:\n"
        "  ・「強い通貨」と「弱い通貨」を客観的に特定できる\n"
        "  ・その差が大きいペアでトレンドが発生しやすいと判断できる\n"
        "  ・差が小さいペアでは方向感がなく、平均回帰が起きやすい"
    )

    pdf.h2("2-2.  計算の仕組み")
    pdf.body("各通貨ペアの対数リターンを、通貨ごとに符号付きで集計し単純平均します。")

    pdf.formula_box("Step 1: 各ペアの対数リターン（log return）", [
        "ret(ペア, t)  =  log( 終値(t) / 終値(t-1) )",
        "",
        "例: USDJPY が 155.00 → 155.31 に動いた場合",
        "    ret = log(155.31 / 155.00) = +0.001999...  ≒ +0.0020",
    ])

    pdf.formula_box("Step 2: 通貨ごとの符号付き貢献度", [
        "各ペアは「基軸通貨（Base）」と「決済通貨（Quote）」で構成される。",
        "",
        "規則:",
        "  ・基軸通貨（左）が上昇 → ペアのreturnが正 → 基軸通貨に +ret を加算",
        "  ・決済通貨（右）が上昇 → ペアのreturnが負 → 決済通貨に +(-ret) を加算",
        "",
        "例: USDJPY ret = +0.0020 の場合",
        "    USD への貢献: +0.0020",
        "    JPY への貢献: -0.0020",
    ])

    pdf.formula_box("Step 3: 通貨強弱値（単純平均）", [
        "Strength(通貨, t)  =  SUM(符号付き貢献度) / 関与ペア数",
        "",
        "例: USDが絡む4ペア（USDJPY, GBPUSD, AUDUSD, NZDUSD）の場合",
        "    Strength(USD, t)  =  (+ret_USDJPY - ret_GBPUSD - ret_AUDUSD - ret_NZDUSD) / 4",
        "",
        "正値 → その通貨が「強い」(他通貨より上昇している)",
        "負値 → その通貨が「弱い」(他通貨より下落している)",
    ])

    pdf.h2("2-3.  各通貨の関与ペア一覧（符号）")
    pdf.table(
        headers=["通貨", "関与ペア（+: 基軸, -: 決済）", "関与数"],
        rows=[
            ["USD", "+USDJPY  -GBPUSD  -AUDUSD  -NZDUSD",        "4"],
            ["JPY", "-USDJPY  -EURJPY  -GBPJPY  -AUDJPY  -NZDJPY  -CHFJPY", "6"],
            ["EUR", "+EURJPY  +EURGBP  +EURAUD",                  "3"],
            ["GBP", "+GBPJPY  +GBPUSD  -EURGBP",                 "3"],
            ["AUD", "+AUDJPY  +AUDUSD  -EURAUD  +AUDNZD",         "4"],
            ["NZD", "+NZDJPY  +NZDUSD  -AUDNZD",                 "3"],
            ["CHF", "+CHFJPY",                                     "1"],
        ],
        widths=[16, 128, 18],
        highlight_last=False,
    )

    pdf.body(
        "注: CHFは1ペア（CHFJPY）しか含まれていないため、強弱値の信頼性は他通貨より低い。\n"
        "    将来的にはEURCHF, USDCHFを追加してカバレッジを拡大することを推奨します。"
    )

    pdf.h2("2-4.  強弱差の解釈")
    pdf.formula_box("ペアの強弱差（Strength Diff）", [
        "StrengthDiff(ペア, t)  =  Strength(基軸通貨, t) - Strength(決済通貨, t)",
        "",
        "例: USDJPY の場合",
        "    StrengthDiff = Strength(USD) - Strength(JPY)",
        "",
        "StrengthDiff > 0  → USD が JPY より強い → USDJPY 上昇バイアス",
        "StrengthDiff < 0  → JPY が USD より強い → USDJPY 下落バイアス",
        "|StrengthDiff| が大きいほど → 方向性が強く、トレンドになりやすい",
    ])

    pdf.callout(
        "重要: 通貨強弱はどの単一ペアよりも「市場全体の力学」を反映します。\n"
        "USDJPY だけ見ていると「USD が上がったのか JPY が下がったのか」が分かりません。\n"
        "強弱値を見ることで、ドル全面高・円全面安を区別できます。"
    )

    # ══ Section 3: 自己相関係数 ════════════════════════════════════════════════
    pdf.section_page("3", "自己相関係数（ACF）の算出",
                     "Autocorrelation Coefficient — 設計根拠と計算式")

    pdf.h2("3-1.  なぜ自己相関係数を使うのか")
    pdf.body(
        "「通貨強弱差が大きい」だけでは不十分です。\n"
        "方向感があっても、値動きがノイジー（ランダム）であればトレンド戦略は機能しません。\n\n"
        "自己相関係数は「過去の値動きが今の値動きに与える影響の大きさ」を測ります。\n\n"
        "  ACF > 0: 前のバーが上昇 → 今のバーも上昇しやすい（トレンド性）\n"
        "  ACF < 0: 前のバーが上昇 → 今のバーは下落しやすい（平均回帰性）\n"
        "  ACF = 0: 過去の動きと無相関（ランダムウォーク）"
    )

    pdf.h2("3-2.  計算式（ローリング ACF, lag=1）")
    pdf.formula_box("1階自己相関係数（Pearson相関）", [
        "ACF(lag=1, t)  =  Corr( ret[t-W : t],  ret[t-W-1 : t-1] )",
        "",
        "  ret[t-W : t]     : 直近W本のlog-returnの時系列",
        "  ret[t-W-1 : t-1] : それを1本前にずらした時系列",
        "  W = 100本（5分足 x 100本 = 500分 ≒ 8.3時間）",
        "",
        "Pearson相関の定義:",
        "  Corr(X, Y) = Cov(X, Y) / ( StdDev(X) x StdDev(Y) )",
        "",
        "結果: -1 <= ACF <= +1",
    ])

    pdf.h2("3-3.  なぜ lag = 1 か")
    pdf.body(
        "ラグ（何本前と比較するか）は解釈のしやすさと計算効率の観点から lag=1 を選択しました。\n\n"
        "  lag=1: 直前のバーとの相関。最も即時的なモメンタム/反転を捉える\n"
        "  lag=2以上: やや遅い波動を捉えるが、ノイズが増加する\n\n"
        "5分足スキャルピングでは、1〜2本先の動きが最も重要です。"
    )

    pdf.h2("3-4.  ACF の解釈基準")
    pdf.table(
        headers=["ACF値の範囲", "状態", "意味", "適切な戦略"],
        rows=[
            ["+0.05 以上",     "強いトレンド性",    "上昇が上昇を呼ぶ状態",   "順張り（TREND）"],
            ["+0.01 〜 +0.05", "弱いトレンド性",    "わずかな継続傾向あり",   "待機推奨"],
            ["-0.01 〜 +0.01", "ランダムウォーク",  "方向感なし",              "待機（NO_TRADE）"],
            ["-0.05 〜 -0.01", "弱い平均回帰性",    "わずかな反転傾向あり",   "待機推奨"],
            ["-0.05 以下",     "強い平均回帰性",    "上昇後に反落しやすい状態", "逆張り（MEAN_REV）"],
        ],
        widths=[32, 30, 50, 38],
        highlight_last=False,
    )

    pdf.callout(
        "ACFは過去100本の「癖」を測定します。\n"
        "市場の性質は時間帯・ニュース・流動性によって変化するため、\n"
        "ローリング計算（毎バー更新）で常に最新状態を反映します。"
    )

    pdf.h2("3-5.  ランダムウォーク仮説との関係")
    pdf.body(
        "効率的市場仮説（EMH）はACF = 0を前提とします。\n"
        "しかし実際の5分足FXデータでは、以下の非効率が観察されます:\n\n"
        "  ・ニュース直後: ACFが一時的に正になる（モメンタム効果）\n"
        "  ・低ボラ・薄商い時間帯: ACFが負になる（B/Aスプレッドの影響）\n"
        "  ・東京・ロンドン・NYオープン前後: 特徴的なパターンが出やすい\n\n"
        "このシステムはこれらの市場構造的な非効率を利用することを意図しています。\n"
        "ただし、すべての利用可能性はIS/OOSバックテストで検証が必要です。"
    )

    # ══ Section 4: 分類ロジック ═════════════════════════════════════════════════
    pdf.section_page("4", "市場状態の分類ロジック",
                     "TREND / MEAN_REVERSION / NO_TRADE の判定フロー")

    pdf.h2("4-1.  分類フロー")
    pdf.formula_box("classify_bar(strength_diff, acf) の判定ロジック", [
        "入力: strength_diff = |Strength(Base) - Strength(Quote)|",
        "      acf           = ACF(lag=1, 直近100本)",
        "",
        "判定フロー:",
        "",
        "IF   |strength_diff| >= 0.0008",
        "AND  acf >= +0.05",
        "THEN → TREND（順張り戦略を適用）",
        "",
        "ELIF |strength_diff| <  0.0008",
        "AND  acf <= -0.05",
        "THEN → MEAN_REVERSION（逆張り戦略を適用）",
        "",
        "ELSE → NO_TRADE（待機）",
    ])

    pdf.h2("4-2.  各状態の意味と戦略")

    pdf.h3("TREND 状態")
    pdf.body(
        "条件: 通貨強弱差が大 + ACF正値\n"
        "意味: 「強い通貨と弱い通貨の差が開いており、かつ動きが継続する傾向にある」\n"
        "戦略: ボリンジャーバンド 1σ ブレイクアウトで順張りエントリー\n"
        "  ・StrengthDiff > 0 → 基軸通貨が強い → Long（買い）\n"
        "  ・StrengthDiff < 0 → 決済通貨が強い → Short（売り）"
    )

    pdf.h3("MEAN_REVERSION 状態")
    pdf.body(
        "条件: 通貨強弱差が小 + ACF負値\n"
        "意味: 「明確な方向感がなく、動きが反転する傾向にある」\n"
        "戦略: ボリンジャーバンド 3σ タッチで逆張りエントリー\n"
        "  ・価格が Upper 3σ を超えた → Short（売り）\n"
        "  ・価格が Lower 3σ を下回った → Long（買い）"
    )

    pdf.h3("NO_TRADE 状態")
    pdf.body(
        "条件: TRENDでもMEAN_REVERSIONでもない\n"
        "意味: 「どちらの戦略も統計的優位性が低い状態」\n"
        "対応: ポジションを持たず待機。無用なドローダウンを回避する。\n"
        "   → 「何もしない」がひとつの意思決定です"
    )

    pdf.h2("4-3.  閾値の根拠と課題")
    pdf.body(
        "現在の閾値（0.0008 / ±0.05）は初期設定値です。\n"
        "これらは研究の出発点であり、以下の検証が必要です:"
    )
    pdf.table(
        headers=["閾値", "現在値", "チューニング方法", "注意"],
        rows=[
            ["強弱差閾値",    "0.0008", "IS期間でパーセンタイル分析",    "過学習に注意"],
            ["ACFトレンド",   "+0.05",  "IS期間でACF分布の上位25%点",    "同上"],
            ["ACF平均回帰",   "-0.05",  "IS期間でACF分布の下位25%点",    "同上"],
            ["BBウィンドウ",  "20本",   "10〜50本をグリッドサーチ",       "パラメータ増加"],
        ],
        widths=[28, 20, 70, 36],
        highlight_last=False,
    )
    pdf.callout(
        "重要: 閾値の調整は必ずIS期間（学習データ）でのみ行い、\n"
        "OOS期間（未来データ）を開封するのは戦略確定後に1回だけとしてください。\n"
        "OOSを複数回開封すると過学習と同等の問題が発生します。"
    )

    # ══ Section 5: 戦略への応用 ═════════════════════════════════════════════════
    pdf.section_page("5", "戦略への応用",
                     "エントリー・エグジットルール / バックテスト構造")

    pdf.h2("5-1.  TREND 戦略（順張り）")
    pdf.formula_box("エントリー条件", [
        "状態: TREND",
        "方向: StrengthDiff > 0 → Long  /  StrengthDiff < 0 → Short",
        "",
        "Long エントリー:",
        "  Close(t) > BB_Upper(1σ, t)",
        "  AND Close(t-1) <= BB_Upper(1σ, t-1)  ← 直近でブレイクした",
        "",
        "Short エントリー:",
        "  Close(t) < BB_Lower(1σ, t)",
        "  AND Close(t-1) >= BB_Lower(1σ, t-1)  ← 直近でブレイクした",
    ])
    pdf.formula_box("エグジット条件（先に発生した方）", [
        "A. BB中心線（Midline）到達: 価格がBBの中心に戻った",
        "   Long  → Close >= BB_Mid",
        "   Short → Close <= BB_Mid",
        "",
        "B. 状態変化: 市場状態が TREND から変化した",
        "   → ポジションを直ちにクローズ",
    ])

    pdf.h2("5-2.  MEAN_REVERSION 戦略（逆張り）")
    pdf.formula_box("エントリー条件", [
        "状態: MEAN_REVERSION",
        "",
        "Long エントリー（下方3σタッチ）:",
        "  Close(t) < BB_Lower(3σ, t)",
        "  AND Close(t-1) >= BB_Lower(3σ, t-1)  ← 直近でタッチ",
        "",
        "Short エントリー（上方3σタッチ）:",
        "  Close(t) > BB_Upper(3σ, t)",
        "  AND Close(t-1) <= BB_Upper(3σ, t-1)  ← 直近でタッチ",
    ])
    pdf.formula_box("エグジット条件（先に発生した方）", [
        "A. BB中心線（Midline）到達: 平均回帰が完了",
        "   Long  → Close >= BB_Mid",
        "   Short → Close <= BB_Mid",
        "",
        "B. 状態変化: 市場状態が MEAN_REVERSION から変化した",
        "   → 逆張り根拠が崩れたためクローズ",
    ])

    pdf.h2("5-3.  バックテストの前提条件と限界")
    pdf.table(
        headers=["項目", "設定", "備考"],
        rows=[
            ["約定", "バークローズ価格", "ルックアヘッドバイアスなし（次足で約定）"],
            ["コスト", "往復0.04%（スプレッド相当）", "スリッページ・手数料は別途要検証"],
            ["ポジションサイジング", "なし（%損益ベース）", "実運用時は要設計"],
            ["最大同時ポジション", "ペアごとに1ポジション", "複数ペア同時保有は別途検討"],
            ["データソース", "yfinance（5分足）", "直近50日が上限。長期検証には別ソース要"],
        ],
        widths=[44, 54, 76],
        highlight_last=False,
    )

    # ══ Section 6: 使い方 ═══════════════════════════════════════════════════════
    pdf.section_page("6", "使い方",
                     "インストール / 起動 / 出力の読み方")

    pdf.h2("6-1.  インストール")
    pdf.formula_box("依存ライブラリのインストール", [
        "pip install yfinance pandas numpy matplotlib rich",
        "",
        "確認環境: Python 3.10+",
    ])

    pdf.h2("6-2.  リアルタイムモニター（主要な使い方）")
    pdf.body(
        "ターミナルに通貨強弱・ACF・推奨戦略をリアルタイム表示します。\n"
        "5分ごとに自動更新し、常に最新バーの状態を確認できます。"
    )
    pdf.formula_box("起動コマンド", [
        "# 300秒（5分バー）ごとに自動更新",
        "python -m fx_market_classifier.monitor",
        "",
        "# 1回だけ表示して終了（確認用）",
        "python -m fx_market_classifier.monitor --once",
        "",
        "# 更新間隔を60秒に変更",
        "python -m fx_market_classifier.monitor --interval 60",
        "",
        "# データ取得日数を変更（デフォルト7日）",
        "python -m fx_market_classifier.monitor --lookback 14",
    ])

    pdf.h2("6-3.  モニター出力の読み方")

    pdf.h3("上段: 通貨強弱ランキング")
    pdf.table(
        headers=["列名", "内容", "見方"],
        rows=[
            ["順位", "強い順に並ぶ（1位が最強）", "上位 = 買い有利通貨"],
            ["通貨", "7通貨（USD/JPY/EUR/GBP/AUD/NZD/CHF）", ""],
            ["強弱値", "+0.000173 など（対数リターン単位）", "正値=強い、負値=弱い"],
            ["バー", "###=強い  ---=弱い", "視覚的な強弱"],
        ],
        widths=[24, 80, 70],
        highlight_last=False,
    )

    pdf.h3("下段: ペア分類テーブル")
    pdf.table(
        headers=["列名", "内容", "見方"],
        rows=[
            ["強弱差",    "+0.00021 USD>JPY",   "差の大きさと方向を確認"],
            ["ACF(lag1)", "+0.12 (+) など",      "(+)=トレンド性  (-)=回帰性  ( )=中立"],
            ["状態",      "[TREND] / [MEAN_REV] / [---]", "どの戦略を使うか"],
            ["推奨アクション", "Long / Short / Fade / 待機", "具体的な方向感"],
        ],
        widths=[24, 60, 90],
        highlight_last=False,
    )

    pdf.formula_box("出力例の解釈", [
        "USDJPY | 強弱差: +0.00021 USD>JPY | ACF: +0.12 (+) | [TREND] | Long > 順張りBuy",
        "",
        "読み方:",
        "  ・USD が JPY より強い（差 = +0.00021 > 閾値 0.0008 ... 未満なら NO_TRADE）",
        "  ・ACF = +0.12 → 正値なのでトレンド性あり（閾値 +0.05 超え）",
        "  ・両条件を満たす → TREND 判定",
        "  ・USD 強 / JPY 弱 → USDJPY は上昇バイアス → Long（買い）方向",
        "",
        "アクション: USDJPY の BB 1σ 上方ブレイクを待って Long エントリーを検討",
    ])

    pdf.h2("6-4.  バックテストの実行")
    pdf.formula_box("バックテスト付きで起動", [
        "# バックテスト結果も表示",
        "python -m fx_market_classifier.main --backtest",
        "",
        "# 特定ペアの詳細チャートも表示",
        "python -m fx_market_classifier.main --backtest --pair USDJPY",
        "",
        "# チャートをPNGとして保存",
        "python -m fx_market_classifier.main --backtest --save",
        "",
        "# 出力ファイル: backtest_trades.csv（全トレード記録）",
    ])

    pdf.h2("6-5.  Pythonコードから直接使用する場合")
    pdf.formula_box("インポートして利用するサンプルコード", [
        "from fx_market_classifier import MarketClassifier, fetch_ohlcv",
        "",
        "# データ取得（直近7日間の5分足）",
        "price_data = fetch_ohlcv(lookback_days=7)",
        "",
        "# 分類器を初期化（通貨強弱・ACF・BBを自動計算）",
        "clf = MarketClassifier(price_data)",
        "",
        "# 現在の状態を取得",
        "current = clf.current_state()",
        "# → {'USDJPY': <MarketState.TREND>, 'EURJPY': <MarketState.NO_TRADE>, ...}",
        "",
        "# 通貨強弱の最新値",
        "latest_strength = clf.strength.iloc[-1]",
        "# → {'USD': 0.000173, 'JPY': 0.000035, ...}",
        "",
        "# 特定ペアのACF時系列",
        "usdjpy_acf = clf.acf['USDJPY']",
    ])

    pdf.h2("6-6.  閾値のカスタマイズ")
    pdf.body(
        "閾値は fx_market_classifier/config.py に集約されています。\n"
        "IS検証後はこのファイルのみを変更すれば全体に反映されます。"
    )
    pdf.formula_box("config.py の変更箇所", [
        "# 強弱差の閾値（大きくすると TREND 判定が厳しくなる）",
        "STRENGTH_DIFF_THRESHOLD = 0.0008",
        "",
        "# ACF のトレンド閾値（大きくすると TREND 判定が厳しくなる）",
        "ACF_TREND_MIN = 0.05",
        "",
        "# ACF の平均回帰閾値（絶対値を大きくすると MEAN_REV 判定が厳しくなる）",
        "ACF_REVERSION_MAX = -0.05",
    ])

    # ══ Section 7: 今後の課題 ══════════════════════════════════════════════════
    pdf.section_page("7", "今後の課題・ロードマップ",
                     "IS/OOS検証 → デモトレード → 実運用")

    pdf.h2("7-1.  検証ロードマップ")
    pdf.table(
        headers=["フェーズ", "内容", "合格基準", "状況"],
        rows=[
            ["設計",       "アルゴリズム構築・コード化",          "本書完成",              "完了"],
            ["IS検証",     "閾値チューニング・バックテスト",       "PF > 1.3  DD < 20%",    "次フェーズ"],
            ["OOS開封",    "未来データで1回だけ検証",              "PF > 1.0  DD < 25%",    "未着手"],
            ["デモ",       "リアルタイムシグナルで模擬取引",        "3ヶ月連続PF > 1.0",     "未着手"],
            ["実運用",     "少額実運用開始",                        "デモ合格後",             "未着手"],
        ],
        widths=[22, 64, 50, 22],
    )

    pdf.h2("7-2.  優先度の高い改善項目")
    pdf.body(
        "以下の順序で検証・改善を進めることを推奨します:"
    )
    pdf.table(
        headers=["優先度", "項目", "理由"],
        rows=[
            ["高",   "IS/OOS期間の設定と閾値チューニング",
             "現在の閾値は未検証。この一歩がないとすべてが仮説のまま"],
            ["高",   "データソースの拡充（Dukascopy 等）",
             "yfinanceは50日が限界。1〜2年のIS期間が必要"],
            ["中",   "CHFペアの追加（EURCHF, USDCHF）",
             "CHFは現在1ペアのみ。強弱値の精度が低い"],
            ["中",   "時間帯フィルター",
             "東京・ロンドン・NY各セッションでACFの特性が異なる可能性"],
            ["低",   "機械学習による動的閾値",
             "将来的な発展。まず固定閾値で十分な検証を先行させること"],
        ],
        widths=[16, 70, 88],
        highlight_last=False,
    )

    pdf.h2("7-3.  本番移行の条件（案）")
    pdf.callout(
        "デモトレード合格条件（3ヶ月間）:\n"
        "  ・PF >= 1.0（損益がプラス）\n"
        "  ・最大ドローダウン <= 25%\n"
        "  ・月次でプラスが2ヶ月以上\n\n"
        "上記をクリアした場合のみ実運用に移行する。\n"
        "合格しない場合は設計に戻り、IS/OOS再検証を行う。"
    )

    pdf.divider()
    pdf.body(
        "免責事項:\n"
        "本資料はバックテスト研究を目的とした内部資料です。\n"
        "投資の推奨・助言を行うものではありません。\n"
        "実際の投資に際しては自己責任でご判断ください。\n"
        "過去のバックテスト結果は将来の利益を保証するものではありません。",
        size=8,
    )

    # ── 出力 ────────────────────────────────────────────────────────────────────
    today_str = date.today().strftime("%Y%m%d")
    out = OUTPUT_DIR / f"fx_market_classifier_report_{today_str}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
