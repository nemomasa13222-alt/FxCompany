# -*- coding: utf-8 -*-
"""
Leave-One-Out vs Include-Self 比較報告書 PDF生成
実行: python -m fx_market_classifier.make_compare_report_pdf
"""
from datetime import date
from pathlib import Path
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR  = Path(__file__).parent.parent / "docs" / "synthetic"

NAVY   = (15,  30,  70);  BLUE   = (30,  80, 160);  ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255); WHITE  = (255, 255, 255);  DARK   = (30,  30,  40)
GRAY   = (110, 120, 135); RED    = (180,  40,  40);  GREEN  = (20,  140,  80)
ORANGE = (200,  90,   0); PURPLE = (100,  40, 160)


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
        self.set_fill_color(*NAVY);   self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 0, 210, 4,   "F")

        self.set_y(48)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)

        self._t(19, bold=True, color=WHITE)
        self.cell(0, 12, "疑似価格の算出方式 比較検証",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(11, color=(160, 200, 240))
        self.cell(0, 8, "Leave-One-Out  vs  Include-Self",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(9, color=(180, 210, 240))
        self.cell(0, 7, "ドル円をドル指数・円指数に含めるかどうかが",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 7, "スプレッドと戦略成績にどう影響するか",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(12)

        # KPI boxes
        kpis = [("LOO PF (entry=0.002)", "0.52"),
                ("INC PF (entry=0.002)", "0.78"),
                ("振幅比率 (USDJPY)",     "80%"),
                ("回帰率の差",            "なし")]
        bw = 38; tw = bw*4+6*3; sx = (210-tw)/2
        for i, (lb, val) in enumerate(kpis):
            x = sx + i*(bw+6)
            self.set_fill_color(20,45,100); self.set_draw_color(60,100,180)
            self.rect(x, 163, bw, 26, "FD")
            self.set_xy(x, 165); self._t(7, color=(140,170,220))
            self.cell(bw, 5, lb, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_xy(x, 173); self._t(13, bold=True, color=ACCENT)
            self.cell(bw, 10, val, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(205); self.set_draw_color(60,90,150); self.line(40,205,170,205)
        self._t(8, color=(120,150,200)); self.set_y(210)
        self.cell(0, 6, f"検証: yfinance 5分足 直近50日  /  60通り × 2方式 = 120通り",
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
        self.set_line_width(0.8)
        x,y = self.get_x(),self.get_y()
        self.rect(x,y,self.epw,0.8,"F"); self.set_line_width(0.2)
        self._t(9,bold=True,color=color)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True)
        self.ln(3); self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def son_comment(self, text):
        """孫さんコメントボックス（紫系）"""
        self.set_fill_color(245, 240, 255); self.set_draw_color(*PURPLE)
        self.set_line_width(1.0)
        x,y = self.get_x(),self.get_y()
        self.rect(x,y,self.epw,1.0,"F"); self.set_line_width(0.2)
        self._t(8,bold=True,color=PURPLE)
        label = "孫正義（AI CEO）のコメント"
        self.cell(0,6,f"  {label}",border="LTR",fill=True,
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_fill_color(245,240,255)
        self._t(9,color=DARK)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True)
        self.ln(3); self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def fbox(self, title, lines):
        self.set_fill_color(248,249,252); self.set_draw_color(180,195,220)
        self._t(8,bold=True,color=BLUE)
        self.cell(0,6,f"  {title}",border="LTR",fill=True,
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(8,color=DARK)
        for line in lines:
            self.cell(0,5.5,f"  {line}",border="LR",fill=True,
                      new_x=XPos.LMARGIN,new_y=YPos.NEXT)
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
            self.ln(w*0.44+2)
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

    # ══ Section 1: 問いと設計 ══════════════════════════════════════════════════
    pdf.sec("1", "問いと設計",
            "ドル円をドル指数・円指数に含めるべきか")

    pdf.callout(
        "MASAYAからの問い:\n"
        "「ドル円をドル指数・円指数の算出に含めていないなら、\n"
        " 含めた場合も解析してほしい。含めることで乖離が小さくなり、\n"
        " より保守的な設計になるのではないか。」"
    )
    pdf.ln(2)

    pdf.h2("1-1.  2つの算出方式")
    pdf.tbl(
        headers=["方式", "USD強弱の算出に使うペア", "JPY強弱の算出に使うペア"],
        rows=[
            ["Leave-One-Out\n（LOO・現行）",
             "GBPUSD / AUDUSD / NZDUSD\n（3ペア: USDJPYを除外）",
             "EURJPY / GBPJPY / AUDJPY\nNZDJPY / CHFJPY\n（5ペア: USDJPYを除外）"],
            ["Include-Self\n（INC・新規）",
             "USDJPY / GBPUSD / AUDUSD / NZDUSD\n（4ペア: USDJPYを含む）",
             "USDJPY / EURJPY / GBPJPY / AUDJPY\nNZDJPY / CHFJPY\n（6ペア: USDJPYを含む）"],
        ],
        widths=[30, 82, 62],
    )

    pdf.h2("1-2.  比較の目的")
    pdf.tbl(
        headers=["確認項目", "LOO", "INC（期待）"],
        rows=[
            ["スプレッド振幅",   "基準",      "小さくなるはず"],
            ["回帰率",           "基準",      "変わらないはず"],
            ["PF（収益性）",     "基準",      "どちらが優位か？"],
            ["シグナル純度",     "高い（他市場のみ）", "低い（自己混入あり）"],
        ],
        widths=[36, 56, 82],
    )

    # ══ Section 2: 数学的解説 ══════════════════════════════════════════════════
    pdf.sec("2", "数学的メカニズム",
            "なぜINCでスプレッドが小さくなるのか")

    pdf.h2("2-1.  LOO の計算")
    pdf.fbox("Leave-One-Out: synthetic_r_USDJPY の算出", [
        "USD強弱(LOO) = 平均{ -r_GBPUSD, -r_AUDUSD, -r_NZDUSD }",
        "JPY強弱(LOO) = 平均{ -r_EURJPY, -r_GBPJPY, -r_AUDJPY, -r_NZDJPY, -r_CHFJPY }",
        "",
        "synthetic_r(LOO) = USD強弱(LOO) - JPY強弱(LOO)",
        "",
        "spread(LOO) = r_USDJPY - synthetic_r(LOO)",
        "            = r_USDJPY - (他の8ペアから計算した適正リターン)",
        "  → USDJPYは完全に「外部の目線」で評価される",
    ])

    pdf.h2("2-2.  INC の計算と自己参照バイアス")
    pdf.fbox("Include-Self: USDJPYを含めた場合の数学的展開", [
        "USD強弱(INC) = 平均{ +r_USDJPY, -r_GBPUSD, -r_AUDUSD, -r_NZDUSD } / 4",
        "JPY強弱(INC) = 平均{ -r_USDJPY, -r_EURJPY, ... } / 6",
        "",
        "synthetic_r(INC) = USD強弱(INC) - JPY強弱(INC)",
        "  = r_USDJPY/4 + (...) - (-r_USDJPY/6 + (...))",
        "  = r_USDJPY × (1/4 + 1/6) + 他ペア分",
        "  = r_USDJPY × 5/12 + 他ペア分   ← 自分自身の動きが5/12混入",
        "",
        "spread(INC) = r_USDJPY - synthetic_r(INC)",
        "  = r_USDJPY - r_USDJPY × 5/12 - 他ペア分",
        "  = r_USDJPY × 7/12 - 他ペア分   ← 41.7%が自己相殺される",
        "",
        "理論上の振幅比: 7/12 = 58.3%  (実測: 80%、相関により緩和)",
    ])

    pdf.son_comment(
        "MASAYAさんの直感「INCは保守的」は結果的に正しいですが、理由が重要です。\n\n"
        "スプレッドが小さくなるのは「本当に乖離が小さい」からではなく、\n"
        "「USDJPYの動きが自分自身の指数に漏れ込んで相殺されているから」です。\n\n"
        "これは測定精度の問題です。\n"
        "LOOのほうが「他の市場が示す適正レートとの純粋な乖離」を測定できています。\n\n"
        "ただし実用上は、INCが自動的に「重要でない小さな乖離」をフィルターする\n"
        "効果を持ち、PFが高くなる可能性があります。\n"
        "3年データでどちらが勝るかを検証することが重要です。"
    )

    # ══ Section 3: 実証結果 ════════════════════════════════════════════════════
    pdf.sec("3", "実証結果",
            "50日データ / 60通り × 2方式 = 120通り解析")

    pdf.h2("3-1.  スプレッド振幅の比較")
    pdf.tbl(
        headers=["ペア", "LOO std", "INC std", "比率", "解釈"],
        rows=[
            ["USDJPY", "0.000184", "0.000146", "80%", "JPY絡み: 20%縮小"],
            ["EURJPY", "0.000126", "0.000105", "84%", "JPY絡み: 16%縮小"],
            ["AUDUSD", "0.000178", "0.000150", "84%", "USD絡み: 16%縮小"],
            ["GBPUSD", "0.000195", "0.000187", "96%", "USD絡みでも変化小"],
        ],
        widths=[22, 24, 24, 16, 88],
        hi_rows={0},
    )

    pdf.body(
        "理論値（7/12 = 58%）より実測値（80〜96%）が大きい理由:\n"
        "  通貨ペア間には相関関係があり、USDJPYの動きがGBPUSD等と連動している。\n"
        "  このため「自己相殺」の効果が理論より小さく、振幅の縮小も緩やかになる。"
    )

    pdf.h2("3-2.  スプレッド波形比較チャート")
    pdf.img(
        str(CHART_DIR / "compare_spread_amplitude.png"), w=170,
        caption="青: Leave-One-Out（現行）  ピンク: Include-Self  上段: USDJPY / 下段: GBPUSD"
    )

    pdf.h2("3-3.  回帰率ヒートマップ比較")
    pdf.img(
        str(CHART_DIR / "compare_loo_inc_heatmap.png"), w=172,
        caption="上段: Leave-One-Out / 下段: Include-Self  (各パネルは exit_ratio)"
    )

    pdf.callout(
        "exit_ratio=0.1（中段列）: LOO・INC ともに全組み合わせで回帰率100%。\n"
        "exit_ratio=0.0（左列）  : LOO 3bars=70%、INC 3bars=22〜68%（INCでやや低下）。\n"
        "→ 回帰する性質そのものは両方式で変わらない。振幅が小さいだけ。"
    )

    # ══ Section 4: PF比較 ══════════════════════════════════════════════════════
    pdf.sec("4", "収益性（PF）の比較",
            "exit_ratio=0.1 / window=6 / entry_threshold別")

    pdf.h2("4-1.  PF比較表")
    pdf.tbl(
        headers=["entry_threshold", "LOO PF", "INC PF", "差分", "トレード数(LOO→INC)", "解釈"],
        rows=[
            ["0.0005 (0.05%)", "0.43", "0.45", "+0.02", "2174→2066", "ほぼ同じ"],
            ["0.0010 (0.10%)", "0.59", "0.65", "+0.06", "434→398",   "INCがやや優位"],
            ["0.0020 (0.20%)", "0.52", "0.78", "+0.26", "41→64",     "INCが明確に優位"],
            ["0.0030 (0.30%)", "0.32", "0.54", "+0.22", "13→24",     "INCが明確に優位"],
            ["0.0050 (0.50%)", "0.00", "0.63", "+0.63", "1→6",       "サンプル少"],
        ],
        widths=[30, 16, 16, 14, 36, 62],
        hi_rows={2, 3},
    )

    pdf.body(
        "entry_threshold=0.002以上でINCのPFが顕著に高い。\n"
        "これは意外な結果に見えるが、以下で解釈する。"
    )

    pdf.h2("4-2.  INCでPFが高くなる理由の解釈")
    pdf.tbl(
        headers=["解釈", "内容"],
        rows=[
            ["A. ノイズフィルター効果",
             "INCでは小さな乖離（ノイズ）が自動的に小さくなる。\n"
             "entry閾値=0.002は実質的にINCでは約0.002/0.8=0.0025相当の純粋乖離。\n"
             "より意味のある乖離のみをトレードしている可能性がある。"],
            ["B. トレード数の増加（矛盾）",
             "スプレッドが小さいのにトレード数が増えている（41→64件）。\n"
             "これはスプレッドの形状（タイミング・方向）が変わっているためで、\n"
             "より多くの「浅い乖離」をキャッチしているとも解釈できる。"],
            ["C. 50日データの限界",
             "サンプル数が少ない（2〜64件）ため、統計的信頼性は低い。\n"
             "3年データで再検証しないと結論は出せない。"],
        ],
        widths=[36, 138],
    )

    pdf.son_comment(
        "INCのPFが高い点は興味深いですが、慎重に解釈する必要があります。\n\n"
        "「USDJPYを含めることで測定バイアスが入るがPFが上がる」という現象は、\n"
        "数学的に言えば「スプレッドの7/12だけを見ている」ことに相当します。\n\n"
        "これは偶然かもしれません。50日・11ペア程度のデータでは、\n"
        "PFの差0.26（0.52→0.78）は統計的に有意とは言えません。\n\n"
        "私の判断:\n"
        "  理論的にはLOOが正しい設計。\n"
        "  実用上はINCをサブ戦略として3年データで並列検証する価値がある。\n"
        "  3年データで両方を走らせ、IS/OOSで検証してから採用を決める。"
    )

    # ══ Section 5: 総合評価と推奨 ═════════════════════════════════════════════
    pdf.sec("5", "総合評価と今後の方針")

    pdf.h2("5-1.  両方式の総合比較")
    pdf.tbl(
        headers=["評価軸", "Leave-One-Out", "Include-Self", "推奨"],
        rows=[
            ["理論的純粋性",     "高（外部目線で測定）",    "低（自己参照バイアス）", "LOO"],
            ["スプレッド振幅",   "大（ノイズも含む）",      "小（自動フィルター）",   "INC"],
            ["回帰率",           "同等（exit=0.1で100%）",  "同等",                  "引き分け"],
            ["PF（50日）",       "0.52",                    "0.78（優位）",          "INC"],
            ["サンプル信頼性",   "低（50日データ）",        "低（同上）",            "3年で再検証"],
        ],
        widths=[32, 56, 56, 30],
        hi_rows={2},
    )

    pdf.h2("5-2.  MASAYAへの回答")
    pdf.callout(
        "「INCは保守的」という解釈について:\n\n"
        "正しい面: INCはスプレッドが約20%小さくなる → 閾値到達頻度が下がる → 保守的\n\n"
        "注意点 : スプレッドが小さいのは「本当に乖離が小さい」のではなく\n"
        "         「USDJPYが自分自身の指数に漏れ込んで相殺されているから」\n\n"
        "実用上の含意:\n"
        "  LOO: 乖離を正確に測れるが、ノイズも含んでしまう可能性\n"
        "  INC: 測定精度は下がるが、自動的にノイズフィルターになる可能性\n\n"
        "→ 50日データでは判断できず。3年データでのIS/OOS検証が必要。"
    )

    pdf.h2("5-3.  ロードマップ")
    pdf.tbl(
        headers=["フェーズ", "内容", "判断基準"],
        rows=[
            ["IS検証\n（2022〜2023）",
             "LOO・INC両方で60通りサーベイ\n3年データ（Dukascopy）",
             "両方式のPF差が一貫しているか\nサンプル数100件以上を確保"],
            ["OOS開封\n（2024）",
             "IS最良パラメータで検証\n両方式を並列で確認",
             "IS→OOSで両方式の順位が\n逆転しないか確認"],
            ["方式選択",
             "IS/OOS結果を踏まえて\nLOO or INC を決定",
             "PF・回帰率・最大DDを\n総合的に評価"],
        ],
        widths=[24, 98, 52],
    )

    pdf.divider()
    pdf._t(8, color=GRAY)
    pdf.multi_cell(0, 6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。"
        "過去のバックテスト結果は将来の利益を保証するものではありません。"
    )

    out = OUTPUT_DIR / f"compare_loo_inc_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
