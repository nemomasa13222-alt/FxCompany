# -*- coding: utf-8 -*-
"""
損切なしサーベイ 報告書 PDF生成
実行: python -m fx_market_classifier.make_no_stop_report_pdf
"""
from datetime import date
from pathlib import Path
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR  = Path(__file__).parent.parent / "docs" / "synthetic"

NAVY   = (15,  30,  70);  BLUE  = (30,  80, 160);  ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255); WHITE = (255, 255, 255);  DARK   = (30,  30,  40)
GRAY   = (110, 120, 135); RED   = (180,  40,  40);  GREEN  = (20,  140,  80)
ORANGE = (200,  90,   0)


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", style="",  fname=FONT_PATH)
        self.add_font("YG", style="B", fname=FONT_PATH)
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def cover(self, today):
        self.add_page()
        self.set_fill_color(*NAVY);  self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 0, 210, 4, "F")
        self.set_y(50)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "損切なし スプレッド回帰検証",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(10, color=(160, 200, 240))
        self.cell(0, 8, "Synthetic Spread Strategy — 回帰性の検証",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)
        self._t(9, color=(180, 210, 240))
        self.cell(0, 7, "「乖離は本当に解消するか」をデータで確認する",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(14)
        # KPIs
        kpis = [("回帰率(exit0.1)", "100%"), ("回帰率(exit0.0)", "〜70%"),
                ("平均保有", "6〜35分"), ("ペア数", "11")]
        bw = 38; tw = bw*4+6*3; sx = (210-tw)/2
        for i,(lb,val) in enumerate(kpis):
            x = sx + i*(bw+6)
            self.set_fill_color(20,45,100); self.set_draw_color(60,100,180)
            self.rect(x, 165, bw, 24, "FD")
            self.set_xy(x, 167); self._t(7, color=(140,170,220))
            self.cell(bw, 5, lb, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_xy(x, 174); self._t(13, bold=True, color=ACCENT)
            self.cell(bw, 10, val, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(205); self.set_draw_color(60,90,150); self.line(40,205,170,205)
        self._t(8, color=(120,150,200)); self.set_y(210)
        self.cell(0, 6, f"検証: yfinance 5分足 直近50日  /  パラメータ: 60通り",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"作成日: {today}  |  FxCompany 研究部門",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def sec(self, num, title, sub=""):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,38,"F")
        self.set_fill_color(*ACCENT); self.rect(0,38,210,2,"F")
        self.set_y(8); self._t(9, color=(120,160,220))
        self.cell(0,6,f"SECTION  {num}",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(16,bold=True,color=WHITE)
        self.cell(0,11,title,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        if sub:
            self._t(8,color=(160,195,235))
            self.cell(0,5,sub,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*DARK); self.ln(8)

    def h2(self, title):
        self.ln(3)
        self.set_fill_color(*BLUE); self._t(9,bold=True,color=WHITE)
        self.cell(4,7,"",fill=True)
        self.set_fill_color(*LIGHT)
        self.cell(0,7,f"  {title}",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*DARK); self.ln(2)

    def body(self, text, size=9):
        self._t(size); self.multi_cell(0,6,text); self.ln(1)

    def callout(self, text, color=ACCENT):
        self.set_fill_color(230,248,242); self.set_draw_color(*color)
        self.set_line_width(0.8); x,y=self.get_x(),self.get_y()
        self.rect(x,y,self.epw,0.8,"F"); self.set_line_width(0.2)
        self._t(9,bold=True,color=color)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True)
        self.ln(3); self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def warn(self, text):
        self.callout(text, color=RED)

    def fbox(self, title, lines):
        self.set_fill_color(248,249,252); self.set_draw_color(180,195,220)
        self._t(8,bold=True,color=BLUE)
        self.cell(0,6,f"  {title}",border="LTR",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(8,color=DARK)
        for line in lines:
            self.cell(0,5.5,f"  {line}",border="LR",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.cell(0,2,"",border="LBR",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(3)

    def tbl(self, headers, rows, widths, hi_rows=None):
        self._t(8,bold=True,color=WHITE); self.set_fill_color(*NAVY)
        for h,w in zip(headers,widths):
            self.cell(w,7,h,border=1,fill=True,align="C")
        self.ln()
        if hi_rows is None: hi_rows=set()
        for i,row in enumerate(rows):
            is_hi = i in hi_rows
            bg = (220,245,220) if is_hi else ((245,248,255) if i%2==0 else WHITE)
            self.set_fill_color(*bg)
            for j,(cell,w) in enumerate(zip(row,widths)):
                self._t(8,bold=is_hi,color=GREEN if is_hi else DARK)
                self.cell(w,6,str(cell),border=1,fill=True,
                          align="L" if j==0 else "C")
            self.ln()
        self.ln(4)

    def img(self, path, w=174, caption=""):
        if Path(path).exists():
            self.image(path, x=self.get_x(), y=self.get_y(), w=w)
            self.ln(w*0.43+2)
        if caption:
            self._t(7,color=GRAY)
            self.cell(0,5,caption,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            self.ln(2)

    def divider(self):
        self.ln(3); self.set_draw_color(200,210,230)
        self.line(self.get_x(),self.get_y(),self.get_x()+self.epw,self.get_y())
        self.ln(4)


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf = PDF()

    # ══ 表紙 ═══════════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: 検証の目的 ═══════════════════════════════════════════════════
    pdf.sec("1", "検証の目的", "損切をなくすと何が分かるか")

    pdf.callout(
        "前回の検証（損切あり）では、損切1%による強制退場が多く、\n"
        "「乖離が本当に解消するのか」が判断できなかった。\n"
        "今回は損切を完全に取り除き、スプレッドが自然に解消するかどうかを直接確認する。"
    )
    pdf.ln(2)

    pdf.h2("1-1.  問い")
    pdf.body(
        "Synthetic Spread 戦略の根拠は「通貨ペアの価格乖離は平均回帰する」という仮説です。\n"
        "この仮説が正しければ、損切なしで保有し続けても乖離は解消するはずです。\n\n"
        "確認したいこと:\n"
        "  (1) 乖離は自然に解消するか？（回帰率）\n"
        "  (2) 解消までどれくらい時間がかかるか？（保有時間）\n"
        "  (3) 解消時と強制決済時で損益はどう違うか？"
    )

    pdf.h2("1-2.  設計の変更点")
    pdf.tbl(
        headers=["項目", "前回（損切あり）", "今回（損切なし）"],
        rows=[
            ["損切条件",   "PnL < -1% で即決済",       "なし（スプレッド解消のみ）"],
            ["エグジット", "損切 / 乖離解消 / データ末尾", "乖離解消 / データ末尾のみ"],
            ["主な観察指標", "PF / 勝率 / 最大DD",       "回帰率 / 保有時間 / 解消PnL"],
            ["パラメータ", "60通り",                     "同じ60通り（窓×閾値×exit比）"],
        ],
        widths=[30, 70, 74],
    )

    pdf.h2("1-3.  パラメータグリッド（60通り）")
    pdf.tbl(
        headers=["パラメータ", "候補値", "件数"],
        rows=[
            ["spread_window（累積窓）",  "3 / 6 / 12 / 24 本",            "4"],
            ["entry_threshold（閾値）",  "0.0005 / 0.001 / 0.002 / 0.003 / 0.005", "5"],
            ["exit_ratio（解消判定比）", "0.0 / 0.1 / 0.2",               "3"],
            ["合計",                     "4 × 5 × 3",                     "60通り"],
        ],
        widths=[52, 80, 42],
    )

    pdf.body(
        "exit_ratio の定義:\n"
        "  exit_threshold = entry_threshold × exit_ratio\n"
        "  0.0 → スプレッドがゼロに戻るまで保有（完全解消）\n"
        "  0.1 → スプレッドが閾値の10%まで縮めば決済\n"
        "  0.2 → スプレッドが閾値の20%まで縮めば決済"
    )

    # ══ Section 2: 回帰率ヒートマップ ══════════════════════════════════════════
    pdf.sec("2", "回帰率ヒートマップ", "スプレッドは何%の確率で自然解消するか")

    pdf.img(
        str(CHART_DIR / "no_stop_reversion_heatmap.png"), w=172,
        caption="各セルの数値 = スプレッドが exit_threshold 以内に戻った割合 (%)"
    )

    pdf.h2("2-1.  ヒートマップの読み方")
    pdf.body(
        "  緑（100%近い）= 乖離はほぼ必ず指定レベルまで解消する\n"
        "  赤（0%付近）  = 乖離は解消せず、データ末尾まで持ち越される\n\n"
        "左パネル（exit_ratio=0.0）: 「スプレッドがゼロに戻る」確率\n"
        "中パネル（exit_ratio=0.1）: 「スプレッドが閾値の10%まで縮む」確率\n"
        "右パネル（exit_ratio=0.2）: 「スプレッドが閾値の20%まで縮む」確率"
    )

    pdf.h2("2-2.  発見された3つのパターン")

    pdf.tbl(
        headers=["パターン", "exit_ratio", "回帰率", "意味"],
        rows=[
            ["完全解消（ゼロへ）",
             "0.0",
             "3bars:64〜70%  /  6+bars:0〜20%",
             "ゼロへの完全回帰は窓が短い場合のみ"],
            ["ほぼ解消（90%縮小）",
             "0.1",
             "全組み合わせで100%",
             "乖離は必ず大幅に縮小する"],
            ["概ね解消（80%縮小）",
             "0.2",
             "全組み合わせで100%",
             "同上（より緩い条件）"],
        ],
        widths=[32, 22, 64, 56],
        hi_rows={1, 2},
    )

    pdf.callout(
        "核心的な発見:\n"
        "スプレッドは必ず「ある程度」縮む（exit_ratio=0.1で100%解消）。\n"
        "ただし「完全にゼロ」まで戻るかは窓の長さに依存する。\n"
        "短い窓（3本=15分）なら70%がゼロに回帰する。"
    )

    # ══ Section 3: 詳細結果 ════════════════════════════════════════════════════
    pdf.sec("3", "上位結果と詳細分析", "回帰率順 / 代表例の深掘り")

    pdf.h2("3-1.  上位20件（回帰率降順）")
    pdf.tbl(
        headers=["順位", "window", "entry", "exit_r",
                 "trades", "回帰%", "強制%", "PF", "PnL%", "保有avg"],
        rows=[
            ["1〜18", "3〜6bars",  "0.0005〜0.005", "0.1/0.2", "1〜2077", "100%", "0%",
             "0.23〜0.66", "様々", "4〜14本"],
            ["19", "12bars", "0.0050", "0.1", "2", "100%", "0%", "0.00", "-0.4%", "14本"],
            ["20", "12bars", "0.0050", "0.0", "1", "100%", "0%", "0.00", "-0.6%", "6925本"],
        ],
        widths=[14, 16, 16, 14, 16, 12, 12, 12, 16, 16],
    )

    pdf.body(
        "注: exit_ratio=0.1/0.2 は全組み合わせで回帰率100%のため、\n"
        "      上位はほぼ exit_ratio>0 の組み合わせが占める。\n"
        "      回帰率でなくPFで見ると損切ありサーベイの結果と近くなる。"
    )

    pdf.h2("3-2.  代表例の深掘り（window=6, entry=0.002, exit_ratio=0.0）")
    pdf.body("この設定は前回の損切ありサーベイで最良PF=2.02を記録した設定。")

    pdf.tbl(
        headers=["指標", "値", "解釈"],
        rows=[
            ["トレード数",       "10件",     "サンプル少（50日データの限界）"],
            ["自然解消率",       "20%（2件）", "スプレッドがゼロに戻ったのは2件のみ"],
            ["強制決済率",       "80%（8件）", "データ末尾まで持ち越し"],
            ["平均保有期間",     "6,360本 ≈ 22日間", "ゼロ解消待ちは非常に長い"],
            ["中央値保有期間",   "7,013本 ≈ 24日間", ""],
            ["自然解消時PnL平均", "-0.42%",   "解消したトレードは小損"],
            ["強制決済時PnL平均", "+5.32%",   "末尾まで持つと利益が出た"],
        ],
        widths=[44, 36, 94],
        hi_rows={6},
    )

    pdf.warn(
        "重要な逆説: 「解消しなかった（強制決済）」ほうが平均+5.3%の利益。\n"
        "「解消した」ほうが平均-0.4%の損失。\n\n"
        "これは50日データの中に方向性の強いトレンドが存在し、\n"
        "ポジションがそのトレンドに乗っていたため強制決済でも利益になったと推測される。\n"
        "3年データで再検証しないと結論は出せない。"
    )

    # ══ Section 4: 回帰性の解釈 ════════════════════════════════════════════════
    pdf.sec("4", "回帰性の解釈", "「乖離は解消する」仮説の現時点での評価")

    pdf.h2("4-1.  exit_ratio別の結論")
    pdf.tbl(
        headers=["exit_ratio", "結論", "根拠"],
        rows=[
            ["0.0（完全回帰）",
             "条件付きで成立",
             "3bar窓で70%、6bar以上では15〜20%のみ"],
            ["0.1（90%縮小）",
             "強く成立",
             "全60通りで100%。乖離は必ず大幅に縮む"],
            ["0.2（80%縮小）",
             "強く成立",
             "同上。exit_ratioを上げても結論は変わらない"],
        ],
        widths=[30, 40, 104],
        hi_rows={1, 2},
    )

    pdf.h2("4-2.  仮説の修正")
    pdf.body(
        "当初の仮説:\n"
        "  「乖離は平均回帰してゼロに戻る」\n\n"
        "修正後の仮説:\n"
        "  「乖離は必ず大幅に縮小する（90%以上の縮小）。\n"
        "   ゼロへの完全回帰は短い窓（15分）では70%成立するが、\n"
        "   長い窓（30分以上）では50日間のデータ内で確認できない。」\n\n"
        "実用的な含意:\n"
        "  → exit_ratio=0.0（完全解消待ち）は不向き（保有期間が22日超になる）\n"
        "  → exit_ratio=0.1（90%縮小で決済）が現実的な設計"
    )

    pdf.h2("4-3.  CHFJPYの問題")
    pdf.fbox("Leave-One-Out時のCHFJPY除外問題", [
        "CHFが絡むペアはCHFJPYのみ（EURCHF・USDCHFは対象外）",
        "CHFJPYをLeave-One-Outすると、CHFの強弱が算出できない",
        "→ CHFJPYの疑似リターンはNaN率100%",
        "→ CHFJPYは実質的にこの戦略の対象外（11ペアで運用）",
        "",
        "解決策: EURCHF・USDCHFを対象ペアに追加する（将来対応）",
    ])

    # ══ Section 5: 今後 ════════════════════════════════════════════════════════
    pdf.sec("5", "今後の方針", "3年データ検証への道筋")

    pdf.h2("5-1.  現在の設定の問題点と改善方向")
    pdf.tbl(
        headers=["問題", "原因", "改善策"],
        rows=[
            ["exit_ratio=0.0の保有期間が22日超",
             "6bar窓のゼロ回帰率が低い",
             "exit_ratio=0.1に変更（100%解消・短期決済）"],
            ["exit_ratio=0.1時のPFが0.6未満",
             "entry後に逆行してから戻るため、途中でコストがかかる",
             "3年データで再検証。entry閾値の最適化"],
            ["CHFJPYが計算不可",
             "CHFの参照ペアが1つしかない",
             "EURCHF・USDCHFを追加"],
            ["サンプル数が少ない",
             "50日データの限界",
             "3年データ（Dukascopy）での再検証"],
        ],
        widths=[52, 60, 62],
    )

    pdf.h2("5-2.  3年データでの再検証ロードマップ")
    pdf.tbl(
        headers=["フェーズ", "内容", "確認ポイント"],
        rows=[
            ["IS期間\n（2022〜2023）",
             "同じ60通りサーベイを実行\n（損切あり・なし両方）",
             "回帰率が50日データと一致するか\n最良パラメータが変わるか"],
            ["OOS期間\n（2024）",
             "IS最良パラメータで検証\n（1回だけ開封）",
             "IS結果が再現するか\nPF > 1.0 を確認"],
            ["デモ\n（3ヶ月）",
             "実際のシグナルで模擬運用\nexit_ratio=0.1設定",
             "3ヶ月連続PF > 1.0\n回帰率 > 80%維持"],
        ],
        widths=[28, 88, 58],
    )

    pdf.callout(
        "Dukascopyデータは現在ダウンロード中（7/12ペア完了予定）。\n"
        "全ペア揃い次第、IS/OOS分割でこのサーベイを再実行する。\n"
        "現時点の結論: 「乖離は縮む（100%）」という仮説は50日データで確認できた。"
    )

    pdf.divider()
    pdf._t(8, color=GRAY)
    pdf.multi_cell(0, 6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。"
        "過去のバックテスト結果は将来の利益を保証するものではありません。"
    )

    out = OUTPUT_DIR / f"no_stop_survey_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
