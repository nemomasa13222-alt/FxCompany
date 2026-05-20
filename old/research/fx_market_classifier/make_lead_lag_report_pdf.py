# -*- coding: utf-8 -*-
"""
Lead-Lag Information Propagation Strategy 報告書 PDF生成
実行: python -m fx_market_classifier.make_lead_lag_report_pdf
"""
from datetime import date
from pathlib import Path
import pandas as pd
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR  = Path(__file__).parent.parent / "docs" / "lead_lag"

NAVY   = (15,  30,  70);  BLUE   = (30,  80, 160);  ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255); WHITE  = (255, 255, 255);  DARK   = (30,  30,  40)
GRAY   = (110, 120, 135); RED    = (180,  40,  40);  GREEN  = (20,  140,  80)
PURPLE = (100,  40, 160); ORANGE = (200,  90,   0)


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

    def cover(self, today):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,297,"F")
        self.set_fill_color(*ACCENT); self.rect(0,0,210,4,"F")
        self.set_y(48); self._t(9, color=(120,160,210))
        self.cell(0,6,"FxCompany  |  FX戦略研究レポート",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(8)
        self._t(18,bold=True,color=WHITE)
        self.cell(0,12,"Lead-Lag 情報伝播戦略 検証報告",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(10,color=(160,200,240))
        self.cell(0,8,"Lead-Lag Information Propagation Strategy",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(6)
        self._t(9,color=(180,210,240))
        self.cell(0,7,"通貨強弱インデックスと擬似価格で先行・追随関係を検証する",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(10)
        kpis=[("伝播成功率","76.8%"),("最良PF(コストあり)","1.02"),
              ("最良PF(コストなし)","―"),("対象ペア","12")]
        bw=38; tw=bw*4+6*3; sx=(210-tw)/2
        for i,(lb,val) in enumerate(kpis):
            x=sx+i*(bw+6)
            self.set_fill_color(20,45,100); self.set_draw_color(60,100,180)
            self.rect(x,162,bw,26,"FD")
            self.set_xy(x,164); self._t(7,color=(140,170,220))
            self.cell(bw,5,lb,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            self.set_xy(x,172); self._t(13,bold=True,color=ACCENT)
            self.cell(bw,10,val,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_y(205); self.set_draw_color(60,90,150); self.line(40,205,170,205)
        self._t(8,color=(120,150,200)); self.set_y(210)
        self.cell(0,6,f"検証: yfinance 5分足 直近50日  /  パラメータ: 100通り × 2条件",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.cell(0,6,f"作成日: {today}  |  FxCompany 研究部門",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)

    def sec(self,num,title,sub=""):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,38,"F")
        self.set_fill_color(*ACCENT); self.rect(0,38,210,2,"F")
        self.set_y(8); self._t(9,color=(120,160,220))
        self.cell(0,6,f"SECTION  {num}",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(16,bold=True,color=WHITE)
        self.cell(0,11,title,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        if sub:
            self._t(8,color=(160,195,235))
            self.cell(0,5,sub,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*DARK); self.ln(8)

    def h2(self,title):
        self.ln(3)
        # 左の青帯（WHITE文字だが実際はテキストなし＝空セル）
        self.set_fill_color(*BLUE); self._t(9,bold=True,color=WHITE)
        self.cell(4,7,"",fill=True)
        # タイトル（DARK文字でLIGHT背景）← ここが修正点
        self.set_fill_color(*LIGHT); self._t(9,bold=True,color=DARK)
        self.cell(0,7,f"  {title}",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*DARK); self.set_fill_color(*WHITE); self.ln(2)

    def body(self,text,size=9):
        self._t(size,color=DARK); self.multi_cell(0,6,text); self.ln(1)

    def callout(self,text,color=ACCENT):
        self.set_fill_color(230,248,242); self.set_draw_color(*color)
        self.set_line_width(0.8); x,y=self.get_x(),self.get_y()
        self.rect(x,y,self.epw,0.8,"F"); self.set_line_width(0.2)
        self._t(9,bold=True,color=color)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True)
        self.ln(3)
        # ← カラーリセット（次の要素に漏れないよう）
        self.set_text_color(*DARK); self.set_fill_color(*WHITE)
        self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def son(self,text):
        self.set_fill_color(245,240,255); self.set_draw_color(*PURPLE)
        self.set_line_width(1.0); x,y=self.get_x(),self.get_y()
        self.rect(x,y,self.epw,1.0,"F"); self.set_line_width(0.2)
        self._t(8,bold=True,color=PURPLE)
        self.cell(0,6,"  孫正義（AI CEO）のコメント",
                  border="LTR",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_fill_color(245,240,255); self._t(9,color=DARK)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True)
        self.ln(3)
        # ← カラーリセット
        self.set_text_color(*DARK); self.set_fill_color(*WHITE)
        self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def fbox(self,title,lines):
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
        # ← カラーリセット
        self.set_text_color(*DARK); self.set_fill_color(*WHITE)

    def tbl(self,headers,rows,widths,hi=None):
        # ヘッダー（WHITE文字、NAVY背景）
        self._t(8,bold=True,color=WHITE); self.set_fill_color(*NAVY)
        for h,w in zip(headers,widths):
            self.cell(w,7,h,border=1,fill=True,align="C")
        self.ln()
        if hi is None: hi=set()
        for i,row in enumerate(rows):
            is_hi=i in hi
            bg=(220,245,220) if is_hi else ((245,248,255) if i%2==0 else WHITE)
            self.set_fill_color(*bg)
            for j,(cell,w) in enumerate(zip(row,widths)):
                # 各セルで色を明示的に指定
                self._t(8,bold=is_hi,color=GREEN if is_hi else DARK)
                self.cell(w,6,str(cell),border=1,fill=True,align="L" if j==0 else "C")
            self.ln()
        self.ln(4)
        # ← カラーリセット（ヘッダーのWHITE・最終行のGREENが漏れないよう）
        self.set_text_color(*DARK); self.set_fill_color(*WHITE)

    def img(self,path,w=174,caption=""):
        if Path(path).exists():
            self.image(path,x=self.get_x(),y=self.get_y(),w=w); self.ln(w*0.43+2)
        if caption:
            self._t(7,color=GRAY)
            self.cell(0,5,caption,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            self.ln(2)
        # ← カラーリセット
        self.set_text_color(*DARK)

    def divider(self):
        self.ln(3); self.set_draw_color(200,210,230)
        self.line(self.get_x(),self.get_y(),self.get_x()+self.epw,self.get_y())
        self.ln(4); self.set_text_color(*DARK)  # ← リセット追加


def load_survey(path):
    try: return pd.read_csv(path)
    except: return pd.DataFrame()


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf   = PDF()

    # コストあり・なし の結果を読み込む
    df_cost = load_survey(CHART_DIR / "survey_results.csv")
    df_nc   = load_survey(CHART_DIR / "survey_nocost.csv")

    # ══ 表紙 ════════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: 戦略概要 ═════════════════════════════════════════════════
    pdf.sec("1","戦略概要","Lead-Lag 情報伝播戦略とは")

    pdf.callout(
        "この戦略は単純な平均回帰ではなく、\n"
        "「通貨ペアのReal価格とPseudo価格の乖離が生じたとき、\n"
        " どちらが先行しているかを判定し、遅行側が追随する方向にポジションをとる」\n"
        "情報伝播型の戦略である。"
    )

    pdf.h2("1-1.  2つのケース")
    pdf.tbl(
        headers=["ケース","条件","判断","エントリー"],
        rows=[
            ["Case A\n(Real先行・廃止)",
             "cum_spread > threshold\nかつ通貨強弱方向一致",
             "Real価格が先行して上昇\n他ペアがまだ追随していない",
             "遅行している他の関連ペアに\n通貨強弱方向でエントリー"],
            ["Case B\n(Pseudo先行・採用)",
             "cum_spread < -threshold\nかつ通貨強弱方向一致",
             "Pseudo価格が先行して上昇\nReal価格がまだ追随していない",
             "対象ペア自身を順張りエントリー\n(Realが追随すると予測)"],
        ],
        widths=[28, 50, 58, 58],
        hi={1},
    )

    pdf.body("今回の検証ではCase A（他ペアへの伝播）は複雑性を増すため除外し、\n"
             "Case B（自ペアへの順張り）のみで検証した。")

    pdf.h2("1-2.  スプレッド計算")
    pdf.fbox("spread と cum_spread の定義", [
        "actual_return(t)   = log(Close(t) / Close(t-1))",
        "synthetic_return(t)= Strength(USD, t) - Strength(JPY, t)  ← Include-Self",
        "",
        "spread(t)          = actual_return(t) - synthetic_return(t)",
        "cum_spread(t)      = rolling_sum(spread, window)",
        "",
        "cum_spread > +entry_threshold: Real先行UP  → Case A シグナル",
        "cum_spread < -entry_threshold: Pseudo先行UP → Case B シグナル",
    ])

    pdf.h2("1-3.  ポジションサイジング")
    pdf.fbox("PDF p.5 公式準拠（risk_pct=0.5%固定）", [
        "risk_amount    = 1,000,000円 × 0.5% = 5,000円",
        "position_ratio = risk_pct/100 / entry_threshold",
        "                 例: 0.5% / 0.15% = 3.33倍レバレッジ",
        "PnL(% of 資本) = position_ratio × 価格変動率",
    ])

    # ══ Section 2: パラメータサーベイ ═══════════════════════════════════════
    pdf.sec("2","パラメータサーベイ",
            "コストあり vs コストなし  /  100通り × 2条件")

    pdf.h2("2-1.  サーベイ設定")
    pdf.tbl(
        headers=["パラメータ","候補値","意味"],
        rows=[
            ["spread_window","3 / 6 / 12 / 24本","ローリング累積幅（15分〜2時間）"],
            ["entry_threshold","0.0005〜0.003（5段階）","エントリー閾値"],
            ["exit_ratio","0.1 / 0.2 / 0.5 / 0.8 / 1.0","利確水準（spread縮小率）"],
            ["risk_pct","0.5%（固定）","1トレード最大損失"],
            ["spread_cost_pct","0.02%(コストあり) / 0%(コストなし)","往復コスト比較"],
        ],
        widths=[36,56,82],
    )

    pdf.h2("2-2.  コストあり 上位結果（Case B のみ）")
    if not df_cost.empty:
        rows=[]; top=df_cost.head(10)
        for _,r in top.iterrows():
            pf_s=f"{r['pf']:.2f}" if r.get('pf',0)<99 else "inf"
            rows.append([f"w={int(r['window'])}",f"{r['entry_thr']:.4f}",
                         f"{r['exit_ratio']:.1f}",str(int(r.get('trades',0))),
                         f"{r.get('win_rate',0)*100:.1f}%",pf_s,
                         f"{r.get('total_pnl',0):.1f}%",
                         f"{r.get('propagation_rate',0)*100:.0f}%"])
        pdf.tbl(headers=["window","entry","er","T","win%","PF","PnL%","propRate"],
                rows=rows, widths=[20,20,15,15,15,18,20,18], hi={0})
    else:
        pdf.body("データなし")

    pdf.h2("2-3.  コストなし 上位結果（Case B のみ）")
    if not df_nc.empty:
        rows=[]; top=df_nc.head(10)
        for _,r in top.iterrows():
            pf_s=f"{r['pf']:.2f}" if r.get('pf',0)<99 else "inf"
            rows.append([f"w={int(r['window'])}",f"{r['entry_thr']:.4f}",
                         f"{r['exit_ratio']:.1f}",str(int(r.get('trades',0))),
                         f"{r.get('win_rate',0)*100:.1f}%",pf_s,
                         f"{r.get('total_pnl',0):.1f}%",
                         f"{r.get('propagation_rate',0)*100:.0f}%"])
        pdf.tbl(headers=["window","entry","er","T","win%","PF","PnL%","propRate"],
                rows=rows, widths=[20,20,15,15,15,18,20,18], hi={0})
    else:
        pdf.body("コストなしデータ未生成（survey_nocost.csv が必要）")

    # ══ Section 3: 核心発見 ═════════════════════════════════════════════════
    pdf.sec("3","核心発見：Propagation率76.8%",
            "仮説「Real先行→Pseudoが追随」の検証")

    pdf.callout(
        "最重要発見: コストあり最良設定（window=3, entry=0.0015, exit_ratio=1.0）\n"
        "で99件のトレードを分析したところ、スプレッドが縮小した際の要因:\n\n"
        "  Pseudo が追随（他ペアがRealに追いついた）: 76件 (76.8%)\n"
        "  Real が戻った（逆行・平均回帰）          : 15件 (15.2%)\n"
        "  両方が動いた                              :  5件  (5.1%)\n"
        "  どちらも動かなかった                      :  3件  (3.0%)\n\n"
        "→ 仮説「Realが先行すると他ペアが追随する」が76.8%の確率で確認された。"
    )

    pdf.h2("3-1.  この発見の意味")
    pdf.body(
        "76.8%のPseudo追随は、単なる平均回帰（Realが戻る）ではなく、\n"
        "「情報が他の通貨ペアに伝播している」という市場構造的な証拠です。\n\n"
        "例: USDJPYがUSD強の方向に先に動いた場合、\n"
        "    → その後GBPUSD、AUDUSD、NZDUSDも同方向に動く（15.2%より76.8%が多い）\n\n"
        "これは「相場の歪み」の本質です:\n"
        "  ・市場参加者はすべての通貨ペアを同時に見ていない\n"
        "  ・情報（USD強弱）は最初に流動性の高いペアに反映され、他ペアに遅れて伝播する\n"
        "  ・この伝播ラグが一時的な乖離（spread）を生み出している"
    )

    pdf.h2("3-2.  なぜプラスにならないか（コスト分析）")
    pdf.fbox("コストの内訳", [
        "position_ratio = 0.5% / 0.15% = 3.33倍",
        "片道コスト     = 3.33 × 0.02% = 0.067%",
        "往復コスト     = 0.134% / トレード",
        "99トレード合計 = 0.134% × 99 = 13.3% のコスト負荷",
        "",
        "→ 勝率40%でも1トレード平均の粗利が0.134%を超えなければ赤字",
        "→ 実際のECNブローカーでは0.005〜0.01%程度に圧縮可能（1/2〜1/4）",
    ])

    pdf.son(
        "76.8%の伝播確率は非常に示唆的です。\n\n"
        "「相場の歪みの本質をついている」というMASAYAの直感は正しい。\n"
        "ただし現在の問題はコストです。\n\n"
        "伝播は起きている。しかし往復0.134%（100円台のJPYペアでは約20pips）を\n"
        "毎回支払いながら5〜10pipsの利益を取るのは数学的に難しい。\n\n"
        "解決策:\n"
        "1. ECN口座で実スプレッドを0.005%以下に圧縮する\n"
        "2. コストなし解析でPFを確認し、純粋なアルファの大きさを把握する\n"
        "3. exit_ratioを大きくして（longer hold）コスト比率を下げる\n"
        "4. JPYクロスのみに絞る（今回もJPYクロスの成績が良かった）"
    )

    # ══ Section 4: ペア別成績 ═══════════════════════════════════════════════
    pdf.sec("4","ペア別成績分析","JPYクロス vs USDクロス")

    pdf.h2("4-1.  最良設定でのペア別成績（コストあり）")
    pdf.tbl(
        headers=["ペア","業種","トレード数","勝率","Avg PnL%","Total PnL%","評価"],
        rows=[
            ["EURJPY","JPYクロス","5","60.0%","+0.63%","+3.13%","★ 最良"],
            ["CHFJPY","JPYクロス","22","50.0%","+0.12%","+2.66%","★ 安定"],
            ["AUDJPY","JPYクロス","5","80.0%","+0.38%","+1.90%","★ 高勝率"],
            ["GBPJPY","JPYクロス","10","40.0%","+0.05%","+0.45%",""],
            ["NZDJPY","JPYクロス","9","44.4%","+0.02%","+0.21%",""],
            ["USDJPY","JPYクロス","7","42.9%","-0.03%","-0.21%",""],
            ["AUDUSD","USDクロス","5","60.0%","-0.07%","-0.33%",""],
            ["NZDUSD","USDクロス","5","20.0%","-0.06%","-0.30%",""],
            ["EURAUD","クロス","2","0.0%","-0.69%","-1.38%","要検討"],
            ["EURGBP","クロス","9","11.1%","-0.28%","-2.53%","除外候補"],
            ["GBPUSD","USDクロス","20","30.0%","-0.16%","-3.22%","★ 最悪"],
        ],
        widths=[22,22,20,16,20,20,30],
        hi={0,1,2},
    )

    pdf.callout(
        "JPYクロス（EURJPY, CHFJPY, AUDJPY）が黒字。USDクロスが不振。\n"
        "→ JPYクロス絞り込み戦略を次フェーズで検討する。"
    )

    pdf.h2("4-2.  月別推移")
    pdf.tbl(
        headers=["月","トレード数","累積PnL%","勝率","傾向"],
        rows=[
            ["2026年3月","40","-13.6%","17.5%","損失集中期（序盤の連敗）"],
            ["2026年4月","35","+11.8%","57.1%","回復（勝率57%）"],
            ["2026年5月","24","+2.3%","54.2%","継続回復"],
        ],
        widths=[24,24,24,16,86],
        hi={1,2},
    )

    pdf.img(str(CHART_DIR/"pnl_curve.png"), w=170,
            caption="コストあり・全12ペア 累積損益曲線（最良設定）")

    # ══ Section 5: コストなし比較 ═══════════════════════════════════════════
    pdf.sec("5","コストなし分析",
            "純粋アルファの確認 — スプレッドコスト0で計算")

    pdf.body(
        "コストを完全にゼロにして計算し、「戦略に純粋なアルファが存在するか」を確認する。\n"
        "コストなしでPFが1.0を大幅に超えれば、コスト削減次第で収益化できる可能性がある。"
    )

    pdf.img(str(CHART_DIR/"pnl_nocost.png"), w=170,
            caption="コストなし・Case Bのみ 累積損益曲線（最良設定）")

    if not df_nc.empty:
        best_nc = df_nc.iloc[0]
        pdf.tbl(
            headers=["比較","コストあり","コストなし","差分"],
            rows=[
                ["最良PF",
                 f"{df_cost.iloc[0]['pf']:.2f}" if not df_cost.empty else "-",
                 f"{best_nc['pf']:.2f}","コスト除去の効果"],
                ["最良設定",
                 "w=3 entry=0.0015 er=1.0" if not df_cost.empty else "-",
                 f"w={int(best_nc['window'])} entry={best_nc['entry_thr']:.4f} er={best_nc['exit_ratio']:.1f}",
                 ""],
                ["伝播率",
                 "76.8%" if not df_cost.empty else "-",
                 f"{best_nc['propagation_rate']*100:.1f}%","コスト無関係"],
            ],
            widths=[28,52,60,34],
        )

    # ══ Section 6: 今後 ═════════════════════════════════════════════════════
    pdf.sec("6","今後の方針","コスト削減 → JPY絞り込み → 3年データ検証")

    pdf.h2("6-1.  優先タスク")
    pdf.tbl(
        headers=["優先度","タスク","期待効果"],
        rows=[
            ["高","ECN口座でコスト確認\n(目標: 0.005%以下/片道)",
             "コストを1/4に削減→PF大幅改善"],
            ["高","JPYクロス6ペアに絞った再検証\n(USDJPY/EURJPY/GBPJPY/AUDJPY/NZDJPY/CHFJPY)",
             "不振ペアを除外→勝率・PF向上"],
            ["中","3年データ（Dukascopy）でIS/OOS検証\n(IS:2022〜2023 / OOS:2024)",
             "50日データの偏りを排除"],
            ["中","exit_ratio最適化\n(1.0付近が良かった → longer hold)",
             "コスト比率を下げる"],
            ["低","Case Aの再評価\n(C3制約を緩めて再テスト)",
             "伝播機会を増やす"],
        ],
        widths=[16,90,68],
    )

    pdf.son(
        "私の評価: このロジックは「歪みの本質」に触れています。\n\n"
        "コスト問題が解決すれば、76.8%の伝播率はFX市場における\n"
        "情報伝播の非効率性を利用する有望な手法になる可能性があります。\n\n"
        "ただし、50日データでは検証不足です。\n"
        "次のマイルストーン: Dukascopy 3年データ × JPYクロス絞り込み × コストゼロ比較\n"
        "この3条件が揃ってから結論を出すことを推奨します。"
    )

    pdf.divider()
    pdf._t(8,color=GRAY)
    pdf.multi_cell(0,6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。"
        "過去のバックテスト結果は将来の利益を保証するものではありません。"
    )

    out = OUTPUT_DIR / f"lead_lag_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
