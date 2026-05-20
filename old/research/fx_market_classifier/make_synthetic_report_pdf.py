# -*- coding: utf-8 -*-
"""
Synthetic Spread Strategy 報告書 PDF生成
実行: python -m fx_market_classifier.make_synthetic_report_pdf
"""
from datetime import date
from pathlib import Path

from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHART_DIR  = Path(__file__).parent.parent / "docs" / "synthetic"

NAVY   = (15,  30,  70)
BLUE   = (30,  80, 160)
ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255)
WHITE  = (255, 255, 255)
DARK   = (30,  30,  40)
GRAY   = (110, 120, 135)
RED    = (180,  40,  40)
GREEN  = (20,  140,  80)


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", style="",  fname=FONT_PATH)
        self.add_font("YG", style="B", fname=FONT_PATH)
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def cover(self, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*ACCENT)
        self.rect(0, 0, 210, 4, "F")

        self.set_y(50)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)

        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "Synthetic Spread Strategy",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(10, color=(160, 200, 240))
        self.cell(0, 8, "通貨インデックス乖離を利用した平均回帰戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(12)

        self._t(9, color=(180, 210, 240))
        self.cell(0, 7, "12通貨ペアの疑似価格と実際価格の乖離を売買シグナルに転換",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # KPI boxes
        self.set_y(155)
        kpis = [("最良PF", "2.02"), ("最良PnL", "+22.3%"), ("データ", "50日"), ("ペア数", "12")]
        bw = 38
        tw = bw * 4 + 6 * 3
        sx = (210 - tw) / 2
        for i, (label, value) in enumerate(kpis):
            x = sx + i * (bw + 6)
            self.set_fill_color(20, 45, 100)
            self.set_draw_color(60, 100, 180)
            self.rect(x, 155, bw, 24, "FD")
            self.set_xy(x, 157)
            self._t(7, color=(140, 170, 220))
            self.cell(bw, 5, label, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_xy(x, 164)
            self._t(14, bold=True, color=ACCENT)
            self.cell(bw, 10, value, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(200)
        self.set_draw_color(60, 90, 150)
        self.line(40, 200, 170, 200)
        self._t(8, color=(120, 150, 200))
        self.set_y(205)
        self.cell(0, 6, f"検証データ: yfinance 5分足 直近50日  |  対象: 12通貨ペア",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"作成日: {today}  |  FxCompany 研究部門",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def section_page(self, number: str, title: str, subtitle: str = ""):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 38, "F")
        self.set_fill_color(*ACCENT)
        self.rect(0, 38, 210, 2, "F")
        self.set_y(8)
        self._t(9, color=(120, 160, 220))
        self.cell(0, 6, f"SECTION  {number}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(16, bold=True, color=WHITE)
        self.cell(0, 11, title, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if subtitle:
            self._t(8, color=(160, 195, 235))
            self.cell(0, 5, subtitle, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)
        self.ln(8)

    def h2(self, title: str):
        self.ln(3)
        self.set_fill_color(*BLUE)
        self._t(9, bold=True, color=WHITE)
        self.cell(4, 7, "", fill=True)
        self.set_fill_color(*LIGHT)
        self.cell(0, 7, f"  {title}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)
        self.ln(2)

    def body(self, text: str, size: int = 9):
        self._t(size)
        self.multi_cell(0, 6, text)
        self.ln(1)

    def callout(self, text: str, color=ACCENT):
        self.set_fill_color(230, 248, 242)
        self.set_draw_color(*color)
        self.set_line_width(0.8)
        x, y = self.get_x(), self.get_y()
        self.rect(x, y, self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._t(9, bold=True, color=color)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3)
        self.set_draw_color(180, 180, 180)

    def formula_box(self, title: str, lines: list[str]):
        self.set_fill_color(248, 249, 252)
        self.set_draw_color(180, 195, 220)
        self._t(8, bold=True, color=BLUE)
        self.cell(0, 6, f"  {title}", border="LTR", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(8, color=DARK)
        for line in lines:
            self.cell(0, 5.5, f"  {line}", border="LR", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 2, "", border="LBR", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def table(self, headers, rows, widths, highlight_rows=None):
        self._t(8, bold=True, color=WHITE)
        self.set_fill_color(*NAVY)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        if highlight_rows is None:
            highlight_rows = set()
        for i, row in enumerate(rows):
            is_hi = i in highlight_rows
            bg = (220, 240, 220) if is_hi else ((245, 248, 255) if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            for j, (cell, w) in enumerate(zip(row, widths)):
                self._t(8, bold=is_hi, color=GREEN if is_hi else DARK)
                self.cell(w, 6, str(cell), border=1, fill=True,
                          align="L" if j == 0 else "C")
            self.ln()
        self.ln(4)

    def insert_image(self, path: str, w: float = 174, caption: str = ""):
        if Path(path).exists():
            self.image(path, x=self.get_x(), y=self.get_y(), w=w)
            self.ln(w * 0.45 + 2)
        if caption:
            self._t(7, color=GRAY)
            self.cell(0, 5, caption, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf = ReportPDF()

    # ══ 表紙 ═══════════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: 戦略概要 ════════════════════════════════════════════════════
    pdf.section_page("1", "戦略概要", "Synthetic Spread Strategy とは何か")

    pdf.callout(
        "この戦略は「12通貨ペアから算出した疑似価格」と「実際の価格」の乖離を売買シグナルとして使う。\n"
        "乖離は市場の一時的な非効率として発生し、平均回帰的に解消される性質を利用する。"
    )
    pdf.ln(2)

    pdf.h2("1-1.  基本思想")
    pdf.body(
        "USDJPYの価格は、他のUSD絡みペア・JPY絡みペアの動きと連動しているはずです。\n"
        "しかし短期的には、USDJPYだけが過剰に動いたり、逆に遅れて動くことがあります。\n\n"
        "この「市場全体が示す適正レート（疑似USDJPY）」と「実際のUSDJPY」の乖離が\n"
        "一定以上になったとき、乖離を埋める方向にポジションを持ちます。"
    )

    pdf.table(
        headers=["状態", "乖離の方向", "エントリー", "エグジット"],
        rows=[
            ["実際 > 疑似", "実際が割高", "Short（実際が下がると予測）", "乖離がゼロに戻った時"],
            ["実際 < 疑似", "実際が割安", "Long（実際が上がると予測）",  "乖離がゼロに戻った時"],
        ],
        widths=[25, 28, 68, 53],
    )

    pdf.h2("1-2.  12ペアへの適用")
    pdf.body(
        "全12ペアそれぞれに対して独立に疑似価格を算出し、各ペアで独立にトレードします。\n"
        "例えばUSDJPYの疑似価格を算出する際、USDJPY自体は使わず残り11ペアから算出します\n"
        "（Leave-One-Out方式: 循環参照を防ぐため）。"
    )

    pdf.table(
        headers=["ペア", "USDJPYの疑似価格算出に使用するペア"],
        rows=[
            ["USD強弱 (3ペア)", "GBPUSD, AUDUSD, NZDUSD"],
            ["JPY強弱 (5ペア)", "EURJPY, GBPJPY, AUDJPY, NZDJPY, CHFJPY"],
            ["疑似USDJPYリターン", "USD強弱 - JPY強弱"],
        ],
        widths=[50, 124],
    )

    # ══ Section 2: 計算ロジック ═════════════════════════════════════════════════
    pdf.section_page("2", "計算ロジック", "スプレッド算出・エントリー・エグジット")

    pdf.h2("2-1.  スプレッドの算出（3ステップ）")

    pdf.formula_box("Step 1: 疑似リターン（Leave-One-Out）", [
        "synthetic_return(USDJPY, t)",
        "  = strength_ex(USD, t)  -  strength_ex(JPY, t)",
        "",
        "strength_ex(USD, t) = 平均{ -r_GBPUSD, -r_AUDUSD, -r_NZDUSD }  (USDJPYを除外)",
        "strength_ex(JPY, t) = 平均{ -r_EURJPY, -r_GBPJPY, -r_AUDJPY, -r_NZDJPY, -r_CHFJPY }",
    ])

    pdf.formula_box("Step 2: 1バーごとのスプレッド", [
        "spread(t)  =  actual_log_return(t)  -  synthetic_return(t)",
        "",
        "spread > 0: 実際が疑似より多く上昇 → 実際が割高",
        "spread < 0: 実際が疑似より多く下落 → 実際が割安",
    ])

    pdf.formula_box("Step 3: ローリング累積スプレッド（シグナル）", [
        "cum_spread(t)  =  Σ spread(t-W+1 to t)",
        "",
        "W = spread_window（デフォルト: 6本 = 30分）",
        "",
        "|cum_spread| > entry_threshold  → エントリーシグナル",
        "|cum_spread| <= exit_threshold  → エグジットシグナル（乖離解消）",
    ])

    pdf.h2("2-2.  エントリー・エグジット")
    pdf.table(
        headers=["フェーズ", "条件", "アクション"],
        rows=[
            ["エントリー", "|cum_spread| > entry_threshold",
             "cum_spread>0 → Short / cum_spread<0 → Long"],
            ["エグジット(利確)", "|cum_spread| <= exit_threshold",
             "ポジション全決済（乖離解消）"],
            ["エグジット(損切)", "PnL < -risk_pct%",
             "ハードストップ（資金の1%損失）"],
        ],
        widths=[30, 60, 84],
    )

    pdf.h2("2-3.  ポジションサイジング（PDF p.5 公式準拠）")
    pdf.formula_box("計算式", [
        "risk_amount    = capital × risk_pct / 100",
        "               = 1,000,000円 × 1% = 10,000円",
        "",
        "position_ratio = risk_pct / (entry_threshold × 100)",
        "               = 1.0% / (0.2%) = 5.0倍レバレッジ  ← entry=0.002の場合",
        "",
        "PnL(% of 資本) = position_ratio × 価格変動率",
        "",
        "損切到達時: position_ratio × entry_threshold = risk_pct = 1.0%  ✓",
    ])

    pdf.callout(
        "ポジションサイズは entry_threshold と連動して自動計算されます。\n"
        "entry_threshold を上げると: エントリー回数↓ / ポジション小↓ / 損失上限は常に1%\n"
        "entry_threshold を下げると: エントリー回数↑ / ポジション大↑ / ノイズを拾いやすい"
    )

    # ══ Section 3: パラメータ一覧 ══════════════════════════════════════════════
    pdf.section_page("3", "パラメータ一覧", "SyntheticConfig — サーベイ対象変数")

    pdf.h2("3-1.  全パラメータ")
    pdf.table(
        headers=["パラメータ", "デフォルト値", "意味", "サーベイ推奨範囲"],
        rows=[
            ["spread_window",   "6本（30分）",  "累積ウィンドウ幅",          "3〜48本（15分〜4時間）"],
            ["entry_threshold", "0.0010",        "エントリー閾値（対数リターン）", "0.0005〜0.005"],
            ["exit_threshold",  "0.0001",        "エグジット閾値（乖離解消判定）", "0.0〜0.0005"],
            ["risk_pct",        "1.0%",          "1トレードの最大損失",        "0.5〜2.0%"],
            ["capital",         "1,000,000円",   "初期資金",                  "—"],
            ["spread_cost_pct", "0.02%",         "片道スプレッドコスト",        "—"],
            ["position_ratio",  "自動計算",       "risk_pct / entry_threshold", "—"],
        ],
        widths=[34, 24, 52, 64],
        highlight_rows={1, 2},
    )

    pdf.body(
        "★ 最重要パラメータは entry_threshold と exit_threshold（緑ハイライト）。\n"
        "   この2つの組み合わせが戦略の勝敗を最も大きく左右することが今回の解析で判明。"
    )

    pdf.h2("3-2.  exit_ratio の定義")
    pdf.body(
        "パラメータサーベイでは、exit_threshold を entry_threshold との比率（exit_ratio）で定義。\n\n"
        "  exit_threshold = entry_threshold × exit_ratio\n\n"
        "  exit_ratio = 0.0: 乖離がゼロに戻るまで保有（完全解消待ち）\n"
        "  exit_ratio = 0.1: entry閾値の10%まで縮小したら決済（早期エグジット）\n"
        "  exit_ratio = 0.2: entry閾値の20%まで縮小したら決済"
    )

    # ══ Section 4: バックテスト結果（デフォルト） ══════════════════════════════
    pdf.section_page("4", "バックテスト結果（デフォルト設定）",
                     "window=6  /  entry=0.001  /  exit_ratio=0.1  /  50日データ")

    pdf.h2("4-1.  総合成績")
    pdf.table(
        headers=["指標", "値", "備考"],
        rows=[
            ["トレード数",   "483",     "12ペア合計"],
            ["勝率",         "31.3%",   "低いが損益比に注目"],
            ["Avg PnL%",    "-0.28%",  "1トレード平均（対資本）"],
            ["Total PnL%",  "-134.4%", "50日累積（デフォルト設定）"],
            ["Profit Factor","0.52",   "1未満 → 現設定は赤字"],
            ["Max DD",       "-136.6%", "対資本"],
            ["損切件数",     "107件",   "22%が損切で終了"],
            ["乖離解消件数", "376件",   "78%が自然解消"],
        ],
        widths=[40, 30, 104],
    )

    pdf.callout(
        "デフォルト設定（exit_ratio=0.1）は赤字。\n"
        "乖離が中途半端に縮まった時点で決済するため、十分な利益を確保できていない。\n"
        "exit_ratio=0.0（完全解消まで保有）に変更することで大幅改善が確認された。"
    )

    pdf.h2("4-2.  ペア別成績")
    pdf.table(
        headers=["ペア", "トレード数", "勝率", "Avg PnL%", "Total PnL%", "評価"],
        rows=[
            ["AUDUSD",  "24",  "50.0%", "+0.71%", "+17.0%", "★ 最良"],
            ["AUDNZD",  "46",  "45.7%", "+0.04%",  "+1.6%", "微プラス"],
            ["AUDJPY",  "12",  "33.3%", "-0.30%",  "-3.7%", ""],
            ["USDJPY",  "20",  "35.0%", "-0.37%",  "-7.4%", ""],
            ["EURJPY",  "17",  "29.4%", "-0.49%",  "-8.4%", ""],
            ["NZDUSD",  "40",  "37.5%", "-0.22%",  "-8.8%", ""],
            ["NZDJPY",  "35",  "34.3%", "-0.32%", "-11.2%", ""],
            ["GBPJPY",  "54",  "29.6%", "-0.22%", "-11.8%", ""],
            ["EURAUD",  "43",  "27.9%", "-0.41%", "-17.6%", ""],
            ["EURGBP", "104",  "20.2%", "-0.37%", "-38.1%", "最悪"],
            ["GBPUSD",  "88",  "29.5%", "-0.52%", "-46.1%", "最悪"],
        ],
        widths=[22, 24, 18, 24, 24, 62],
        highlight_rows={0, 1},
    )

    # ══ Section 5: パラメータサーベイ ══════════════════════════════════════════
    pdf.section_page("5", "パラメータサーベイ結果",
                     "60通り（window×entry_threshold×exit_ratio）")

    pdf.h2("5-1.  上位結果（PF降順）")
    pdf.table(
        headers=["順位", "window", "entry", "exit_r", "trades", "勝率", "PF", "PnL%", "DD%"],
        rows=[
            ["1 ★", "6bars",  "0.0020", "0.0",  "24",  "25.0%", "2.02", "+22.3%", "-12.3%"],
            ["2",    "12bars", "0.0020", "0.0",  "33",  "21.2%", "1.62", "+23.1%", "-13.6%"],
            ["3",    "12bars", "0.0050", "0.0",   "2",  "50.0%", "1.30",  "+0.3%",   "0.0%"],
            ["4",    "6bars",  "0.0010", "0.0", "117",   "8.5%", "1.22", "+36.6%", "-54.4%"],
            ["5",    "3bars",  "0.0020", "0.0",  "27",  "25.9%", "1.16",  "+4.0%",  "-7.3%"],
            ["6",    "3bars",  "0.0010", "0.0", "137",  "15.3%", "1.03",  "+5.8%", "-53.6%"],
            ["—",    "—",      "—",      "—",    "—",    "—",    "1.0",    "±0",     "—"],
            ["19",   "6bars",  "0.0010", "0.1", "483",  "31.3%", "0.52","-134.4%","-136.6%"],
        ],
        widths=[14, 20, 18, 18, 20, 16, 14, 22, 22],
        highlight_rows={0},
    )

    pdf.body("※ 3位（trades=2）と7位（損益ゼロライン）は統計的に信頼性が低い。")

    pdf.h2("5-2.  PFヒートマップ")
    hmap = str(CHART_DIR / "synthetic_survey_heatmap.png")
    pdf.insert_image(
        hmap, w=172,
        caption="横軸: entry_threshold / 縦軸: spread_window / 各パネル: exit_ratio"
    )

    pdf.h2("5-3.  発見された傾向")

    pdf.body("【発見1】exit_ratio = 0.0 が圧倒的に優位")
    pdf.table(
        headers=["exit_ratio", "最良PF", "傾向"],
        rows=[
            ["0.0（完全解消まで保有）", "2.02", "緑セルが存在 → 黒字化可能"],
            ["0.1（早期エグジット）",  "0.54", "全面赤 → 黒字ゼロ"],
            ["0.2（さらに早期）",      "0.65", "全面赤 → 黒字ゼロ"],
        ],
        widths=[60, 20, 94],
        highlight_rows={0},
    )

    pdf.body("【発見2】entry_threshold のスイートスポットは 0.002（0.2% ≈ 30pips @USDJPY150）")
    pdf.table(
        headers=["entry_threshold", "window=6 PF", "window=12 PF", "解釈"],
        rows=[
            ["0.0005 (0.05%)", "0.50", "0.48", "閾値低すぎ → ノイズを大量に拾う"],
            ["0.0010 (0.10%)", "1.22", "0.95", "やや低め → 多すぎるトレード"],
            ["0.0020 (0.20%)", "2.02", "1.62", "★ スイートスポット"],
            ["0.0030 (0.30%)", "0.73", "0.81", "やや高め → トレード不足"],
            ["0.0050 (0.50%)", "0.00", "1.30", "高すぎ → サンプル不足"],
        ],
        widths=[36, 24, 28, 86],
        highlight_rows={2},
    )

    # ══ Section 6: 推奨設定・チャート ══════════════════════════════════════════
    pdf.section_page("6", "推奨設定とチャート確認",
                     "暫定パラメータ  /  USDJPY チャート例")

    pdf.h2("6-1.  暫定推奨パラメータ（50日データ基準）")
    pdf.formula_box("SyntheticConfig（推奨版）", [
        "spread_window   = 6       # 30分（変更なし）",
        "entry_threshold = 0.0020  # 0.001 → 0.002 に引き上げ ★",
        "exit_threshold  = 0.0000  # 完全解消まで保有（exit_ratio=0.0）★",
        "risk_pct        = 1.0     # 最大損失 1%/トレード（変更なし）",
        "capital         = 1_000_000",
        "",
        "position_ratio = 1.0% / 0.2% = 5.0倍レバレッジ（自動計算）",
        "",
        "# 期待成績（50日 / デフォルトとの比較）",
        "# デフォルト: PF=0.52 / trades=483 / PnL=-134%",
        "# 推奨設定:  PF=2.02 / trades=24  / PnL=+22%  ← 要3年データ検証",
    ])

    pdf.callout(
        "注意: 推奨設定のトレード数は24件（50日）と少なく、統計的信頼性は低い。\n"
        "3年データが揃い次第、同じサーベイを実施して確認することを強く推奨する。\n"
        "特に EURGBP・GBPUSD はどの設定でも成績が悪く、除外も検討の余地あり。"
    )

    pdf.h2("6-2.  USDJPYチャート（推奨設定でのスプレッド可視化）")
    pdf.body(
        "下図の読み方:\n"
        "  上段: 実際のUSDJPY価格（黒）vs 疑似USDJPY価格（ピンク）\n"
        "  中段: 累積スプレッド。赤線(+0.002)を超えたらShort、青線(-0.002)でLong\n"
        "  下段: 1バーごとのスプレッド（上段を微分したもの）"
    )
    usdjpy_chart = str(CHART_DIR / "synthetic_USDJPY.png")
    pdf.insert_image(usdjpy_chart, w=170,
                     caption="USDJPY  5分足 / 50日 / デフォルト設定（entry=0.001, exit=0.0001）")

    # ══ Section 7: 今後 ════════════════════════════════════════════════════════
    pdf.section_page("7", "今後の課題・ロードマップ",
                     "3年データ検証 → パラメータ確定 → デモトレード")

    pdf.h2("7-1.  優先タスク")
    pdf.table(
        headers=["優先度", "タスク", "目的"],
        rows=[
            ["高", "3年データで同じサーベイを実行",
             "50日の結果が本物か検証。トレード数を確保して統計的信頼性を得る"],
            ["高", "EURGBP・GBPUSDを除外したサーベイ",
             "成績不良ペアが全体を引き下げている可能性を検証"],
            ["中", "IS/OOS分割検証",
             "IS(2022-2023)でチューニング→OOS(2024)で確認。過学習防止"],
            ["中", "エグジット条件の深掘り",
             "exit_ratio=0だと損切が増える。exit後の逆張りタイミングを研究"],
            ["低", "window × entry の組み合わせを細かくサーベイ",
             "0.001〜0.003の間を0.0005刻みで精度を上げる"],
        ],
        widths=[16, 76, 82],
    )

    pdf.h2("7-2.  ロジックの改善案（将来検討）")
    pdf.table(
        headers=["案", "内容", "期待効果"],
        rows=[
            ["A", "ペアごとに entry_threshold を最適化\n（USDJPY=0.002, EURGBP=0.003 etc.）",
             "ペアごとのボラティリティ差に対応"],
            ["B", "exit条件に時間制限を追加\n（N本以内に解消しなければ損切）",
             "ポジション長期化リスクの管理"],
            ["C", "ACF条件を追加\n（ACFが負のときのみエントリー）",
             "平均回帰が起きやすい状態のみを選別"],
        ],
        widths=[10, 96, 68],
    )

    pdf.divider = lambda: (pdf.ln(3), pdf.set_draw_color(200, 210, 230),
                            pdf.line(pdf.get_x(), pdf.get_y(),
                                     pdf.get_x() + pdf.epw, pdf.get_y()), pdf.ln(4))
    pdf.divider()
    pdf._t(8, color=GRAY)
    pdf.multi_cell(0, 6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。"
        "過去のバックテスト結果は将来の利益を保証するものではありません。"
    )

    out = OUTPUT_DIR / f"synthetic_spread_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
