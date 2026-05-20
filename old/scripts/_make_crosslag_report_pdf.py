# -*- coding: utf-8 -*-
"""
JPYクロスペア Lead-Lag 解析報告書 PDF生成
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import date
from pathlib import Path
import pandas as pd
import numpy as np
from fpdf import FPDF, XPos, YPos

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
ROOT      = Path(__file__).parent
DATA_DIR  = ROOT / "docs" / "crosslag"
OUT_DIR   = ROOT / "fx_market_classifier" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NAVY   = (15, 30, 70);  BLUE  = (30, 80,160);  ACCENT = (0,160,120)
LIGHT  = (240,245,255); WHITE = (255,255,255);  DARK   = (30, 30, 40)
GRAY   = (110,120,135); RED   = (180, 40, 40);  GREEN  = (20,140, 80)
PURPLE = (100, 40,160); AMBER = (200,120,  0)


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG","", FONT_PATH)
        self.add_font("YG","B",FONT_PATH)
        self.set_margins(18,18,18)
        self.set_auto_page_break(auto=True, margin=18)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG","B" if bold else "",size)
        self.set_text_color(*color)

    def _reset(self):
        self.set_text_color(*DARK); self.set_fill_color(*WHITE)
        self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def cover(self, today, n_sig, best_pf, best_corr):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,297,"F")
        self.set_fill_color(*ACCENT); self.rect(0,0,210,4,"F")
        self.set_y(40); self._t(9,color=(120,160,210))
        self.cell(0,6,"FxCompany  |  FX戦略研究レポート",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(6)
        self._t(16,bold=True,color=WHITE)
        self.cell(0,11,"JPYクロスペア Lead-Lag 解析報告",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(10,bold=True,color=ACCENT)
        self.cell(0,8,"リアルペア間の情報伝播検証",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(4); self._t(8,color=(160,200,240))
        self.cell(0,6,"IS期間: 2022-01-01 〜 2023-12-31  /  6ペア × 30組み合わせ  /  ラグ 1〜12本",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(12)

        kpis = [
            ("有意相関ペア数",  f"{n_sig}件"),
            ("最大相関係数",    f"{best_corr:.4f}"),
            ("最良PF",         f"{best_pf:.3f}"),
            ("黒字組み合わせ", "0 / 43件"),
        ]
        bw=38; tw=bw*4+6*3; sx=(210-tw)/2
        for i,(lb,val) in enumerate(kpis):
            x = sx+i*(bw+6)
            self.set_fill_color(20,45,100); self.set_draw_color(60,100,180)
            self.rect(x,162,bw,26,"FD")
            self.set_xy(x,164); self._t(7,color=(140,170,220))
            self.cell(bw,5,lb,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            col = RED if lb=="黒字組み合わせ" else ACCENT
            self.set_xy(x,172); self._t(13,bold=True,color=col)
            self.cell(bw,10,val,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)

        self.set_y(205)
        self.set_draw_color(60,90,150); self.line(40,205,170,205)
        self._t(8,color=(120,150,200)); self.set_y(210)
        self.cell(0,6,f"作成日: {today}  |  FxCompany 研究部門",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)

    def sec(self,num,title,sub=""):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,38,"F")
        self.set_fill_color(*ACCENT); self.rect(0,38,210,2,"F")
        self.set_y(8); self._t(9,color=(120,160,220))
        self.cell(0,6,f"SECTION  {num}",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(15,bold=True,color=WHITE)
        self.cell(0,10,title,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        if sub:
            self._t(8,color=(160,195,235))
            self.cell(0,5,sub,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._reset(); self.ln(8)

    def h2(self,title):
        self.ln(3)
        self.set_fill_color(*BLUE); self._t(9,bold=True,color=WHITE)
        self.cell(4,7,"",fill=True)
        self.set_fill_color(*LIGHT); self._t(9,bold=True,color=DARK)
        self.cell(0,7,f"  {title}",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._reset(); self.ln(2)

    def body(self,text,size=9):
        self._t(size,color=DARK); self.multi_cell(0,6,text); self.ln(1); self._reset()

    def callout(self,text,color=ACCENT):
        self.set_fill_color(230,248,242); self.set_draw_color(*color); self.set_line_width(0.8)
        self._t(9,bold=True,color=color)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True); self.ln(3); self._reset()

    def warn(self,text):
        self.set_fill_color(255,242,230); self.set_draw_color(*AMBER); self.set_line_width(0.8)
        self._t(9,bold=True,color=AMBER)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True); self.ln(3); self._reset()

    def son(self,text):
        self.set_fill_color(245,240,255); self.set_draw_color(*PURPLE); self.set_line_width(1.0)
        self._t(8,bold=True,color=PURPLE)
        self.cell(0,6,"  孫正義（AI CEO）のコメント",border="LTR",fill=True,
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_fill_color(245,240,255); self._t(9,color=DARK)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True); self.ln(3); self._reset()

    def tbl(self,headers,rows,widths,hi=None):
        self._t(8,bold=True,color=WHITE); self.set_fill_color(*NAVY)
        for h,w in zip(headers,widths):
            self.cell(w,7,h,border=1,fill=True,align="C")
        self.ln()
        if hi is None: hi=set()
        for i,row in enumerate(rows):
            is_hi = i in hi
            bg = (220,245,220) if is_hi else ((245,248,255) if i%2==0 else WHITE)
            self.set_fill_color(*bg)
            for j,(cell,w) in enumerate(zip(row,widths)):
                self._t(8,bold=is_hi,color=GREEN if is_hi else DARK)
                self.cell(w,6,str(cell),border=1,fill=True,align="L" if j==0 else "C")
            self.ln()
        self.ln(3); self._reset()

    def img(self,path,w=170,caption=""):
        p=Path(path)
        if p.exists():
            self.image(str(p),x=self.get_x(),y=self.get_y(),w=w); self.ln(w*0.43+2)
        if caption:
            self._t(7,color=GRAY)
            self.cell(0,5,caption,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT); self.ln(2)
        self._reset()

    def divider(self):
        self.ln(3); self.set_draw_color(200,210,230)
        self.line(self.get_x(),self.get_y(),self.get_x()+self.epw,self.get_y())
        self.ln(4); self._reset()


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf   = PDF()

    df_corr = pd.read_csv(DATA_DIR/"corr_IS.csv")   if (DATA_DIR/"corr_IS.csv").exists()   else pd.DataFrame()
    df_bt   = pd.read_csv(DATA_DIR/"backtest_IS.csv") if (DATA_DIR/"backtest_IS.csv").exists() else pd.DataFrame()
    df_st   = pd.read_csv(DATA_DIR/"state_IS.csv")   if (DATA_DIR/"state_IS.csv").exists()   else pd.DataFrame()

    n_sig    = len(df_bt) if not df_bt.empty else 0
    best_pf  = float(df_bt["pf"].max())  if not df_bt.empty else 0
    best_corr= float(df_corr["corr"].abs().max()) if not df_corr.empty else 0

    # ══ 表紙 ═══════════════════════════════════════════════════════════
    pdf.cover(today, n_sig, best_pf, best_corr)

    # ══ Section 1: 解析設計 ════════════════════════════════════════════
    pdf.sec("1","解析設計","通貨強弱を使わないリアルペア間のLead-Lag検証")

    pdf.h2("1-1.  検証の目的と設計")
    pdf.body(
        "従来のLead-Lag戦略は「通貨強弱インデックス（疑似価格）」を使用していたが、\n"
        "自己参照問題（Include-Self）により結果が歪む問題が確認された。\n\n"
        "本解析では通貨強弱を一切使わず、リアルな通貨ペアのリターン同士の\n"
        "直接的なクロス相関を検証し、真の情報伝播が存在するかを確かめる。"
    )
    pdf.tbl(
        headers=["項目","設定","備考"],
        rows=[
            ["対象ペア","USDJPY / EURJPY / GBPJPY\nAUDJPY / NZDJPY / CHFJPY","6ペア × 5 = 30方向"],
            ["IS期間","2022-01-01 〜 2023-12-31","146,000本/ペア（5分足）"],
            ["ラグ範囲","1〜12本（5〜60分）","360通りの相関計算"],
            ["有意閾値","|r| >= 0.003 かつ p < 0.01","43件が有意"],
            ["バックテスト","sign(leader_ret) × follower_ret(t+lag)","コスト往復0.04%込み"],
            ["市場状態分類","TREND / MR / NO_TRADE\n（ADX + SMA + BB）","状態別成績を比較"],
        ],
        widths=[30,80,64],
    )

    # ══ Section 2: クロス相関結果 ══════════════════════════════════════
    pdf.sec("2","クロス相関結果","30ペア × 12ラグ = 360通りの計算結果")

    pdf.h2("2-1.  相関係数の分布")
    pdf.callout(
        "最大相関係数: 0.0128（USDJPY→CHFJPY, lag=2）\n"
        "全360件の平均|r|: 0.0034\n"
        "|r| >= 0.003 かつ p < 0.01 の有意ペア: 43件 / 360件（11.9%）\n\n"
        "→ 相関は統計的に有意だが、その絶対値は0.003〜0.013と非常に小さい。"
    )

    if not df_corr.empty:
        top10 = (df_corr.assign(abs_corr=df_corr["corr"].abs())
                 .sort_values("abs_corr",ascending=False).head(10))
        rows = []
        for _, r in top10.iterrows():
            rows.append([
                f"{r['leader']}→{r['follower']}",
                str(int(r["lag"])),
                f"{r['corr']:+.5f}",
                f"{r['pval']:.2e}",
                str(int(r["n"])),
            ])
        pdf.tbl(
            headers=["ペア","ラグ（本）","相関係数","p値","サンプル数"],
            rows=rows, widths=[36,22,28,28,26],
        )

    pdf.img(str(DATA_DIR/"heatmap_corr_IS.png"), w=160,
            caption="相関係数ヒートマップ（行: Follower / 列: Leader / 値: 最良ラグでの相関）")
    pdf.img(str(DATA_DIR/"heatmap_lag_IS.png"), w=160,
            caption="最良ラグ（5分本数）ヒートマップ")

    # ══ Section 3: バックテスト結果 ════════════════════════════════════
    pdf.sec("3","バックテスト結果","コスト込み期待値の検証")

    pdf.h2("3-1.  致命的な構造問題：コスト vs 期待利益")
    pdf.warn(
        "【数学的に取引不可能な構造】\n\n"
        "5分足の典型的リターン（AUDJPY）:\n"
        "  平均絶対値: 0.0312%  /  中央値: 0.0224%\n\n"
        "コスト（往復）: 0.0400%\n\n"
        "Lead-Lag相関から得られる期待利益:\n"
        "  = max_corr × 平均ボラ = 0.012 × 0.0312% = 0.00037%\n\n"
        "純期待値: 0.00037% - 0.0400% = -0.03963% / トレード\n\n"
        "→ コストが期待利益の108倍。どのパラメータでも採算が取れない構造。"
    )

    pdf.h2("3-2.  バックテスト上位15件（全て赤字）")
    if not df_bt.empty:
        rows = []
        for _, r in df_bt.head(15).iterrows():
            rows.append([
                f"{r['leader']}→{r['follower']}",
                str(int(r["lag"])),
                f"{r['corr']:+.4f}",
                str(int(r["trades"])),
                f"{r['win_rate']*100:.1f}%",
                f"{r['pf']:.3f}",
                f"{r['ev_bp']:.3f}",
            ])
        pdf.tbl(
            headers=["ペア","ラグ","相関","T数","勝率","PF","EV(bp)"],
            rows=rows, widths=[36,14,20,20,18,18,18],
        )

    pdf.callout(
        "全43件 PF < 1.0  /  最良PF = 0.096（1.0には遠く及ばない）\n"
        "勝率が13〜15%しかない理由: 5分足の大半の値動きがコスト(0.04%)以下のため、\n"
        "方向が合っていてもコストで負けが確定する。"
    )

    pdf.img(str(DATA_DIR/"heatmap_pf_IS.png"), w=160,
            caption="PFヒートマップ（全て0.8〜1.0以下 = 赤字）")

    # ══ Section 4: 市場状態別分析 ══════════════════════════════════════
    pdf.sec("4","市場状態別分析","TREND / MR / NO_TRADE での成績差")

    pdf.h2("4-1.  市場状態別平均成績")
    if not df_st.empty:
        avg = df_st.groupby("state")[["pf","win_rate","ev_bp","trades"]].mean()
        rows = []
        for st in ["TREND","MR","NO_TRADE"]:
            if st in avg.index:
                r = avg.loc[st]
                rows.append([st, f"{r['pf']:.3f}", f"{r['win_rate']*100:.1f}%",
                              f"{r['ev_bp']:.3f}", f"{r['trades']:.0f}"])
        pdf.tbl(
            headers=["市場状態","PF","勝率","EV(bp)","平均T数"],
            rows=rows, widths=[36,28,28,28,24],
        )

    pdf.body(
        "TRENDでPFが若干高い（0.122）が、それでも1.0に遠く及ばない。\n"
        "MRとNO_TRADEはほぼ同等（PF~0.073）。\n"
        "市場状態による有意な差は確認できなかった。"
    )
    pdf.img(str(DATA_DIR/"state_IS.png"), w=160,
            caption="市場状態別成績比較")

    # ══ Section 5: 結論と孫さんコメント ═══════════════════════════════
    pdf.sec("5","結論と今後の方針","5分足JPYクロス間にLead-Lagアルファは存在しない")

    pdf.h2("5-1.  発見のまとめ")
    pdf.tbl(
        headers=["検証項目","結果","解釈"],
        rows=[
            ["クロス相関の存在","最大|r|=0.0128（統計的有意）","微弱だが存在する"],
            ["実用的な大きさ","|r|=0.003〜0.013","コスト回収に必要な水準の100分の1"],
            ["PF（コスト込み）","全43件 PF<0.1","完全に赤字"],
            ["コスト vs 期待利益","コストが期待利益の108倍","数学的に取引不可能"],
            ["市場状態との関係","TREND>MR≒NO_TRADE（差小）","状態フィルタ効果なし"],
            ["勝率の異常低さ","13〜15%（ランダムは50%）","コスト超えが稀なため"],
        ],
        widths=[46,44,84],
    )

    pdf.h2("5-2.  今後の方向性")
    pdf.tbl(
        headers=["アプローチ","概要","期待"],
        rows=[
            ["より長い時間足での検証\n（15分・1時間・日足）","5分足はコストが相対的に大きい\nより長い保有で克服できる可能性","中"],
            ["ティック・板情報の活用","超高頻度でのLead-Lagは存在するが\n個人投資家には実現困難","低（インフラ要件）"],
            ["経済指標イベント時の検証","重要指標発表直後の伝播は\n通常時より大きい可能性","中"],
            ["ペア間スプレッドの統計的裁定","直接Lead-Lagでなく\n共積分（Cointegration）ベースに転換","高"],
        ],
        widths=[46,90,38],
    )

    pdf.son(
        "この結果は正直です。そして正しい。\n\n"
        "「相関が存在する」と「利益が取れる」は全く別の話です。\n"
        "相関 0.012 × ボラ 0.03% = 期待利益 0.00037%。\n"
        "コスト 0.04%。差し引き -0.04%/トレード。\n\n"
        "5分足でのJPYクロス間 Lead-Lag は市場が効率的に消化済みです。\n"
        "これは「戦略が悪い」のではなく、「この市場・この時間足では\n"
        "個人投資家が介入できる余地が残っていない」ことを意味します。\n\n"
        "次のステップとして私が推奨するのは:\n"
        "1. 共積分（Cointegration）ベースのペアトレード — より長期の価格差を利用\n"
        "2. 経済指標発表イベント周辺の短期情報伝播 — 非定常なアルファが残りやすい\n"
        "3. 日足レベルでの通貨間モメンタム — トレンドフォローとの組み合わせ\n\n"
        "正しいロジックで正しいスケールを見つけることが次の課題です。"
    )

    pdf.divider()
    pdf._t(8,color=GRAY)
    pdf.multi_cell(0,6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。")

    out = OUT_DIR / f"crosslag_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
