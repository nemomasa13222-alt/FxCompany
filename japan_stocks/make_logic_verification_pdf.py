# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 — ロジック照合ドキュメント PDF
「戦略の意図」と「実際のコード」が一致しているかをゼロから確認するための資料

実行: python japan_stocks/make_logic_verification_pdf.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime
import tempfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUTPUT_DIR = Path(__file__).parent / "results" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NAVY  = (15, 30, 70);   BLUE  = (30, 90, 170);  TEAL  = (0, 160, 120)
GREEN = (0, 140, 80);   RED   = (190, 40, 40);   AMBER = (200, 140, 0)
LIGHT = (235, 242, 255); WHITE = (255, 255, 255); DARK  = (30, 30, 40)
GRAY  = (110, 110, 120); ORANGE= (220, 100, 0)

def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)

# ── チャート: 数値例フロー図 ────────────────────────────────────────────────────

def make_index_chart() -> str:
    """セクター指数の計算フロー（数値例）"""
    fig, ax = plt.subplots(figsize=(11, 4))
    fig.patch.set_facecolor("#F5F8FF"); ax.set_facecolor("#F5F8FF")
    ax.set_xlim(0,11); ax.set_ylim(0,4); ax.axis("off")

    def box(cx, cy, w, h, lines, fc="#EEF3FF", ec="#2266AA", fs=8.5):
        r = patches.FancyBboxPatch((cx-w/2,cy-h/2),w,h,
            boxstyle="round,pad=0.1",linewidth=1.5,edgecolor=ec,facecolor=fc)
        ax.add_patch(r)
        text = "\n".join(lines)
        ax.text(cx,cy,text,ha="center",va="center",
                fontproperties=_jp(fs),color="#1A1A2E",multialignment="center")

    def arr(x1,y1,x2,y2):
        ax.annotate("",xy=(x2,y2),xytext=(x1,y1),
            arrowprops=dict(arrowstyle="-|>",color="#444",lw=1.5))

    box(1.2,2.0,2.0,1.4,["銘柄A 終値","1000→1010","→ +1.00%"],fc="#DDEEFF",ec="#2266AA")
    box(1.2,0.8,2.0,1.0,["銘柄B 終値","500→505","→ +1.00%"],fc="#DDEEFF",ec="#2266AA")
    box(3.5,1.5,1.8,1.0,["等加重平均","(+1%+1%)/2","= +1.00%"],fc="#FFF3DC",ec="#CC6600")
    box(5.8,1.5,2.0,1.0,["前日指数×(1+r)","100×1.01","= 101.0"],fc="#DDFFF0",ec="#008060")
    box(8.5,1.5,2.2,1.4,["セクター指数","初日=100","→ 101.0→102.01..."],fc="#E8E0FF",ec="#6644AA",fs=8)

    arr(2.2,2.0,2.6,1.7); arr(2.2,0.8,2.6,1.3); arr(4.4,1.5,4.8,1.5)
    arr(6.8,1.5,7.4,1.5)

    ax.text(5.5,3.5,"【セクター指数の計算フロー】等加重・累積積算・初日=100",
            fontproperties=_jp(11),color="#1A3A7A",ha="center",fontweight="bold")
    ax.text(1.2,3.2,"① 各銘柄の日次リターン",fontproperties=_jp(8.5),color="#555",ha="center")
    ax.text(3.5,2.7,"② 平均",fontproperties=_jp(8.5),color="#555",ha="center")
    ax.text(5.8,2.7,"③ 累積",fontproperties=_jp(8.5),color="#555",ha="center")

    # コード対応
    ax.text(0.1,0.1,"コード: avg_ret = combined.mean(axis=1)  →  (1+avg_ret).cumprod() * 100",
            fontproperties=_jp(8),color="#666",style="italic")

    plt.tight_layout()
    tmp=tempfile.NamedTemporaryFile(suffix=".png",delete=False)
    plt.savefig(tmp.name,dpi=160,bbox_inches="tight",facecolor="#F5F8FF")
    plt.close(fig); return tmp.name


def make_entry_chart() -> str:
    """エントリー条件の数値例"""
    fig, axes = plt.subplots(1,3,figsize=(12,3.8))
    fig.patch.set_facecolor("#F5F8FF")

    # 条件1: セクター上昇
    ax=axes[0]; ax.set_facecolor("#F5F8FF")
    days=list(range(6)); sector=[100,100.5,101,101.5,102,102.4]
    ax.plot(days,sector,color="#2266AA",lw=2.5,marker="o",ms=6)
    ax.axhspan(100,102.4,alpha=0.08,color="#2266AA")
    ax.set_title("条件①: セクター5日で+2%以上",fontproperties=_jp(10),color="#1A3A7A",pad=6)
    ax.annotate("",xy=(5,102.4),xytext=(0,100),
        arrowprops=dict(arrowstyle="<->",color="#CC3333",lw=1.8))
    ax.text(2.7,101.2,"+2.4%\n(≥2.0%OK)",fontproperties=_jp(8.5),
            color="#CC3333",ha="center",fontweight="bold")
    ax.set_xlabel("日数",fontproperties=_jp(8)); ax.set_ylabel("指数値",fontproperties=_jp(8))
    ax.grid(axis="y",color="#D0D8EC",lw=0.4,ls="--")

    # 条件2: クロスコリレーション
    ax=axes[1]; ax.set_facecolor("#F5F8FF")
    lags=list(range(-5,6))
    corrs=[-0.1,-0.05,0.1,0.2,0.35,0.4,0.55,0.65,0.7,0.6,0.45]
    colors=["#CC3333" if c<0 else "#2266AA" for c in corrs]
    ax.bar(lags,corrs,color=colors,alpha=0.8,width=0.7)
    ax.axvline(3,color="#CC3333",lw=2,ls="--")
    ax.text(2.0,0.55,"★遅行株の定義\nlag≥2\n→遅行株",fontproperties=_jp(8),color="#CC3333")
    ax.axvline(0,color="#888",lw=1,ls=":")
    ax.set_title("条件②: クロスコリレーション分類",fontproperties=_jp(10),color="#1A3A7A",pad=6)
    ax.set_xlabel("ラグ（日）",fontproperties=_jp(8))
    ax.set_ylabel("相関係数",fontproperties=_jp(8))
    ax.grid(axis="y",color="#D0D8EC",lw=0.4,ls="--")

    # 条件3: 乖離率（セクター乖離率）
    ax=axes[2]; ax.set_facecolor("#F5F8FF")
    cats=["セクター\n+2.4%","銘柄C\n-0.8%","乖離\n=3.2%"]
    vals=[2.4,-0.8,3.2]
    clrs=["#2266AA","#CC3333","#FF8800"]
    bars=ax.bar(range(len(cats)),vals,color=clrs,alpha=0.85,width=0.5)
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats,fontproperties=_jp(8))
    ax.axhline(3.0,color="#FF8800",lw=2,ls="--")
    ax.text(2.4,3.1,"最低乖離率\n3.0%",fontproperties=_jp(8),color="#FF8800",ha="center")
    ax.text(2,3.4,"★エントリー対象",fontproperties=_jp(9),color="#008060",
            ha="center",fontweight="bold",
            bbox=dict(boxstyle="round",facecolor="#DDFFF0",alpha=0.8))
    ax.set_title("条件③: セクター乖離率 ≥ 3%",fontproperties=_jp(10),color="#1A3A7A",pad=6)
    ax.set_ylabel("変化率（%）",fontproperties=_jp(8))
    ax.grid(axis="y",color="#D0D8EC",lw=0.4,ls="--")
    for bar,v in zip(bars,vals):
        ax.text(bar.get_x()+bar.get_width()/2,v+(0.1 if v>=0 else -0.2),
                f"{v:+.1f}%",ha="center",fontsize=9,fontweight="bold")

    plt.tight_layout(pad=0.9)
    tmp=tempfile.NamedTemporaryFile(suffix=".png",delete=False)
    plt.savefig(tmp.name,dpi=160,bbox_inches="tight",facecolor="#F5F8FF")
    plt.close(fig); return tmp.name


def make_exit_chart() -> str:
    """エグジット条件の数値例（3パターン）"""
    fig, axes = plt.subplots(1,3,figsize=(12,3.8))
    fig.patch.set_facecolor("#F5F8FF")

    t=list(range(11))

    # A: 利確
    ax=axes[0]; ax.set_facecolor("#F5F8FF")
    entry=1000; sector_traj=[100,100.5,101,101.5,102,102.5,103,103.2,103.4,103.5,103.5]
    stock_traj=[1000,1000,1000,1001,1003,1006,1010,1018,1025,1031,1035]
    ax.plot(t,[s/sector_traj[0]*100 for s in sector_traj],
            color="#2266AA",lw=2,label="セクター")
    ax.plot(t,[s/stock_traj[0]*100 for s in stock_traj],
            color="#CC3333",lw=2,label="銘柄（遅行）")
    ax.axvspan(8,9,alpha=0.2,color="#2ECC71")
    ax.text(8.5,98,"乖離縮小\n≤0.5%\n→利確",fontproperties=_jp(8),
            color="#008060",ha="center",fontweight="bold")
    ax.set_title("A. 利確: 乖離が0.5%以下に縮小",fontproperties=_jp(9.5),color="#1A3A7A",pad=6)
    ax.legend(prop=_jp(8)); ax.set_xlabel("保有日数",fontproperties=_jp(8))
    ax.set_ylabel("基準100",fontproperties=_jp(8))
    ax.grid(axis="y",color="#D0D8EC",lw=0.4,ls="--")

    # B: 損切
    ax=axes[1]; ax.set_facecolor("#F5F8FF")
    stock2=[1000,998,995,990,985.1,984.5]
    stop=1000*(1-0.015)
    ax.plot(list(range(6)),stock2,color="#CC3333",lw=2.5,marker="o",ms=6,label="銘柄価格")
    ax.axhline(stop,color="#CC3333",lw=2,ls="--",label=f"損切ライン {stop:.1f}円")
    ax.scatter([5],[984.5],s=200,color="#CC3333",marker="x",zorder=5,lw=3)
    ax.text(3,987,"損切ライン到達\n→即決済",fontproperties=_jp(8.5),
            color="#CC3333",fontweight="bold",
            bbox=dict(boxstyle="round",facecolor="#FFE8E8",alpha=0.8))
    ax.set_title("B. 損切: エントリーから-1.5%",fontproperties=_jp(9.5),color="#1A3A7A",pad=6)
    ax.legend(prop=_jp(8)); ax.set_xlabel("保有日数",fontproperties=_jp(8))
    ax.set_ylabel("株価（円）",fontproperties=_jp(8))
    ax.grid(axis="y",color="#D0D8EC",lw=0.4,ls="--")

    # C: 時間切れ
    ax=axes[2]; ax.set_facecolor("#F5F8FF")
    stock3=[1000,1001,999,1002,1004,1003,1005,1004,1006,1005,1007]
    ax.plot(t,stock3,color="#888",lw=2.5,marker="o",ms=5)
    ax.axvline(10,color="#FF8800",lw=2.5,ls="--")
    ax.scatter([10],[1007],s=200,color="#FF8800",marker="D",zorder=5)
    ax.text(7,1001,"10営業日経過\n→強制決済",fontproperties=_jp(8.5),
            color="#FF8800",fontweight="bold",
            bbox=dict(boxstyle="round",facecolor="#FFF3DC",alpha=0.8))
    ax.set_title("C. 時間切れ: 10営業日で強制決済",fontproperties=_jp(9.5),color="#1A3A7A",pad=6)
    ax.set_xlabel("保有日数",fontproperties=_jp(8))
    ax.set_ylabel("株価（円）",fontproperties=_jp(8))
    ax.grid(axis="y",color="#D0D8EC",lw=0.4,ls="--")

    plt.tight_layout(pad=0.9)
    tmp=tempfile.NamedTemporaryFile(suffix=".png",delete=False)
    plt.savefig(tmp.name,dpi=160,bbox_inches="tight",facecolor="#F5F8FF")
    plt.close(fig); return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class VerificationPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG","",fname=FONT_PATH)
        self.add_font("YG","B",fname=FONT_PATH)
        self.set_margins(14,14,14)
        self.set_auto_page_break(auto=True,margin=14)

    def _t(self,size=9,bold=False,color=DARK):
        self.set_font("YG","B" if bold else "",size)
        self.set_text_color(*color)

    def _sec(self,title,color=BLUE):
        self.set_fill_color(*color); self.set_text_color(*WHITE)
        self.set_font("YG","B",9)
        self.cell(0,7,f"  {title}",new_x=XPos.LMARGIN,new_y=YPos.NEXT,fill=True)
        self.set_text_color(*DARK); self.ln(2)

    def _match_row(self, label, theory, code, status, note=""):
        """
        理論 vs コード 照合行（固定高さ方式 — ページ崩れ防止）
        全セルを同じ高さで描画し、テキストは収まる分だけ表示する。
        """
        ROW_H = 14         # 行高さ固定（2行分）
        LINE_H = 5         # 1行の高さ
        WIDTHS = [28, 52, 52, 12, 38]
        st_color = GREEN if status == "✓" else (RED if status == "✗" else AMBER)

        x0 = self.get_x()
        y0 = self.get_y()

        # ページ末尾チェック（はみ出す前に改ページ）
        if y0 + ROW_H > self.h - self.b_margin:
            self.add_page()
            x0 = self.get_x(); y0 = self.get_y()

        fills = [LIGHT, LIGHT, (245,245,245), LIGHT, LIGHT]
        texts = [label, theory, code, status, note]
        aligns= ["C", "L", "L", "C", "L"]
        bolds = [True, False, False, True, False]
        colors= [DARK, DARK, DARK, st_color, DARK]

        x = x0
        for txt, w, fc, align, bold, tc in zip(texts, WIDTHS, fills, aligns, bolds, colors):
            # 背景と枠線
            self.set_fill_color(*fc)
            self.set_draw_color(180, 190, 210)
            self.rect(x, y0, w, ROW_H, "FD")
            # テキスト（複数行は LINE_H ごとに分割して描画）
            self.set_text_color(*tc)
            self.set_font("YG", "B" if bold else "", 7)
            lines = str(txt).replace("\\n","\n").split("\n")
            for li, line in enumerate(lines[:2]):   # 最大2行まで
                self.set_xy(x + 1, y0 + 1 + li * LINE_H)
                self.cell(w - 2, LINE_H, line[:38], align=align)
            x += w

        self.set_xy(x0, y0 + ROW_H)
        self.set_text_color(*DARK)
        self.set_draw_color(0, 0, 0)

    def _row3(self, texts, widths, fills=None, bolds=None, aligns=None,
              row_h=14, line_h=5, font_size=8):
        """
        3列固定高さテーブル行（multi_cell不使用 → 崩れない）
        テキストは最大2行まで表示。
        """
        if fills  is None: fills  = [LIGHT] * 3
        if bolds  is None: bolds  = [False] * 3
        if aligns is None: aligns = ["C", "L", "L"]

        x0 = self.get_x(); y0 = self.get_y()
        if y0 + row_h > self.h - self.b_margin:
            self.add_page(); x0 = self.get_x(); y0 = self.get_y()

        x = x0
        for txt, w, fc, bold, align in zip(texts, widths, fills, bolds, aligns):
            self.set_fill_color(*fc)
            self.set_draw_color(180, 190, 210)
            self.rect(x, y0, w, row_h, "FD")
            self.set_text_color(*DARK)
            self.set_font("YG", "B" if bold else "", font_size)
            lines = str(txt).replace("\\n", "\n").split("\n")
            for li, line in enumerate(lines[:2]):
                self.set_xy(x + 1, y0 + 1 + li * line_h)
                self.cell(w - 2, line_h, line[:45], align=align)
            x += w

        self.set_xy(x0, y0 + row_h)
        self.set_text_color(*DARK)
        self.set_draw_color(0, 0, 0)

    def _table_header(self, headers, widths=None):
        """標準5列ヘッダー（固定幅）"""
        if widths is None:
            widths = [28, 52, 52, 12, 38]
        self.set_font("YG","B",7.5)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(*DARK)

    def _code_box(self,code:str,color=BLUE):
        self.set_fill_color(240,244,255)
        self.set_draw_color(*color); self.set_line_width(0.8)
        self.set_font("YG","",8.5); self.set_text_color(20,20,80)
        self.multi_cell(0,6,code,border=1,fill=True)
        self.set_text_color(*DARK); self.set_line_width(0.2); self.ln(2)

    # ── 表紙 ─────────────────────────────────────────────────────────────────
    def cover(self,today):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,297,"F")
        self.set_fill_color(*TEAL); self.rect(0,0,210,4,"F"); self.rect(0,293,210,4,"F")

        self.set_y(40)
        self._t(9,color=(120,160,210))
        self.cell(0,7,"FxCompany  |  セクター追いつき戦略",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(6)
        self._t(20,bold=True,color=WHITE)
        self.cell(0,13,"ロジック照合ドキュメント",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(11,bold=True,color=(0,220,170))
        self.cell(0,8,"戦略の意図 ⇔ コードの実装 完全照合",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(4)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(40,self.get_y(),170,self.get_y()); self.ln(6)
        self._t(8.5,color=(140,170,220))
        self.cell(0,6,f"作成日: {today}  |  v2-f（採用版）対象",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.cell(0,6,"MASAYAが1次情報で確認・再現できるように",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)

        self.set_y(150)
        items=[
            ("STEP 1","セクター指数の計算","等加重平均で指数を構築する仕組み"),
            ("STEP 2","銘柄分類（クロスコリレーション）","先行・中間・遅行株の判定ロジック"),
            ("STEP 3","エントリー条件3つ","コードと戦略の一致・不一致の確認"),
            ("STEP 4","エグジット条件3つ","利確・損切・時間切れの実装確認"),
            ("STEP 5","ポジションサイジング","株数計算の数値例"),
            ("STEP 6","発見された不一致・注意点","コードに潜む問題点の指摘"),
        ]
        for step,title,desc in items:
            self.set_fill_color(25,45,90); self.set_text_color(*TEAL)
            self.set_font("YG","B",9); self.cell(22,9,step,fill=True,align="C")
            self.set_text_color(210,225,255); self.set_font("YG","B",9)
            self.cell(55,9,f"  {title}",fill=True)
            self.set_text_color(170,190,220); self.set_font("YG","",8.5)
            self.cell(0,9,f"  {desc}",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)

        self.set_y(268)
        self._t(7,color=(60,80,120))
        self.multi_cell(0,5,
            "FxCompany 調査部門（AI孫正義）  |  "+today+"\n"
            "本資料はコード検証を目的とした内部資料です。",align="C")

    # ── STEP 1: セクター指数 ─────────────────────────────────────────────────
    def step1_page(self,idx_img):
        self.add_page()
        self._t(14,bold=True,color=NAVY)
        self.cell(0,9,"STEP 1  セクター指数の計算方法",
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14,self.get_y(),196,self.get_y()); self.ln(3)

        self._sec("戦略の意図（何をしたいか）",color=BLUE)
        self._t(8.5)
        self.multi_cell(0,5.5,
            "業種内の全銘柄（プライム市場、最大20銘柄）の株価を等しい重みで平均し、\n"
            "「その業種が今日全体としてどれだけ動いたか」を示す指数を毎日計算する。\n"
            "初日を100として累積していくことで、過去からの変化率がわかる。")
        self.ln(3)

        self._sec("数値例で理解する",color=TEAL)
        self.image(idx_img,x=14,y=self.get_y(),w=182,h=55)
        self.ln(59)

        self._sec("コードの実装（sector_index.py 78〜79行）",color=NAVY)
        self._code_box(
            "# 各銘柄の日次リターンを計算して横に並べる\n"
            "combined = pd.concat(returns_list, axis=1)  # 銘柄数 × 日数の行列\n\n"
            "# 等加重平均: 各日で全銘柄のリターンの単純平均\n"
            "avg_ret = combined.mean(axis=1)   # 例: (1%+1%)/2 = 1%\n\n"
            "# 累積積算して初日=100に正規化\n"
            "idx = (1 + avg_ret).cumprod() * 100  # 100→101→102.01..."
        )

        self._sec("照合結果",color=GREEN)
        self._table_header(["確認項目","戦略の意図","コードの実装","判定","備考"])
        rows=[
            ("重み付け","等加重（全銘柄同じ重み）",
             "combined.mean(axis=1)","✓","meanは等加重平均"),
            ("初期化","初日=100","cumprod() * 100","✓","正確"),
            ("株価の種類","調整済み終値を優先",
             "AdjustmentCloseを優先\nなければClose","✓","分割・配当を調整"),
            ("最低銘柄数","5銘柄未満は指数構築せず",
             "len(returns_list)<MIN_STOCKS","✓","MIN_STOCKS=5"),
        ]
        for label,theory,code,status,note in rows:
            self._match_row(label,theory,code,status,note)
        self.set_text_color(*DARK)

    # ── STEP 2: クロスコリレーション ─────────────────────────────────────────
    def step2_page(self):
        self.add_page()
        self._t(14,bold=True,color=NAVY)
        self.cell(0,9,"STEP 2  銘柄分類（クロスコリレーション）",
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14,self.get_y(),196,self.get_y()); self.ln(3)

        self._sec("戦略の意図",color=BLUE)
        self._t(8.5)
        self.multi_cell(0,5.5,
            "セクター指数と各銘柄の過去252営業日（約1年）のリターンを比較して、\n"
            "「この銘柄はセクターより何日遅れて動くか（ラグ）」を計算する。\n"
            "ラグが大きい（+2日以上）= 遅行株 → 追いつき狙いのエントリー対象。")
        self.ln(2)

        self._sec("分類の定義",color=TEAL)
        cls_rows=[
            ("先行株","ラグ ≤ -2日","セクターより早く動く。対象外"),
            ("中間株","-1 ≤ ラグ ≤ +1日","ほぼ同時。乖離あれば対象"),
            ("遅行株","ラグ ≥ +2日","セクターに遅れる。★主要ターゲット"),
        ]
        ws=[25,35,122]
        self.set_font("YG","B",8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h,w in zip(["分類","ラグ条件","意味・方針"],ws):
            self.cell(w,6.5,h,border=1,fill=True,align="C")
        self.ln()
        for cls, lag, desc in cls_rows:
            bg = (255, 252, 220) if "遅行" in cls else LIGHT
            self._row3(
                [cls, lag, desc], ws,
                fills=[bg, bg, bg],
                bolds=[True, False, False],
                aligns=["C", "C", "L"],
            )
        self.set_text_color(*DARK); self.ln(3)

        self._sec("コードの実装（analyzer.py）",color=NAVY)
        self._code_box(
            "# ラグを-5〜+5で変えながら相関係数を計算\n"
            "for lag in range(-5, 6):       # -5,-4,...,0,...,4,+5\n"
            "    r, _ = pearsonr(sector[:-lag], stock[lag:])  # lag>0の場合\n"
            "    result[lag] = r\n\n"
            "# 最も正の相関が高いラグを採用（負相関は追いつき対象外のため無視）\n"
            "best = max(result, key=lambda k: result[k])\n\n"
            "# 分類\n"
            "if best >= 2:  → 遅行株\n"
            "if best <= -2: → 先行株\n"
            "else:          → 中間株"
        )

        self._sec("照合結果",color=GREEN)
        self._table_header(["確認項目","戦略の意図","コードの実装","判定","備考"])
        rows2=[
            ("ラグ範囲","±5日以内で計算","range(-5, 6)","✓","問題なし"),
            ("ラグ決定方法","最も正の相関が高いラグ",
             "max(result, key=lambda k: result[k])","✓",
             "max()は正しい設計。\n負相関株はそもそも\n追いつき対象外"),
            ("分類境界","±2日で先行/遅行判定",
             "lag>=2→遅行 lag<=-2→先行","✓","コードと一致"),
            ("最低相関","0.60以上のみ採用",
             "corr < config.min_corr でスキップ","✓","min_corr=0.60に引き上げ済み"),
        ]
        for label,theory,code,status,note in rows2:
            self._match_row(label,theory,code,status,note)
        self.set_text_color(*DARK)

    # ── STEP 3: エントリー ────────────────────────────────────────────────────
    def step3_page(self,entry_img):
        self.add_page()
        self._t(14,bold=True,color=NAVY)
        self.cell(0,9,"STEP 3  エントリー条件の照合",
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14,self.get_y(),196,self.get_y()); self.ln(2)

        self.image(entry_img,x=14,y=self.get_y(),w=182,h=55)
        self.ln(59)

        self._sec("照合テーブル（3条件すべて満たすと候補銘柄に）",color=NAVY)
        self._table_header(["条件","戦略の意図","コードの実装","判定","備考"])
        rows=[
            ("条件①\nセクター上昇",
             "直近5日でセクター\n指数が+2%以上",
             "sec_change=(sec_now/sec_past-1)*100\nif sec_change < sector_min_rise: skip",
             "✓","sec_past=5日前のbar。\n問題なし"),
            ("条件②\n銘柄分類",
             "中間株または遅行株\n（相関0.30以上）",
             "if cls not in target_classes\n   or corr<min_corr: skip",
             "✓","target_classes=['遅行株','中間株']"),
            ("条件③\n乖離率",
             "セクター乖離率\n（セクター-銘柄）≥ 3%",
             "gap=sec_change - stock_chg\nif gap < min_gap: skip",
             "✓","同じ5日間で比較。一致"),
            ("エントリー価格",
             "翌日寄り付き成行",
             "entry_price = opens[ticker].iat[i+1]\n（シグナル翌日の始値）",
             "✓",
             "終値でシグナル確定後\n翌朝の寄り付き成行\n→実運用と一致"),
            ("エントリー候補選別",
             "乖離が大きい順に\n上位3銘柄を選ぶ",
             "candidates.sort(key=lambda x:x[1],\n   reverse=True)[:slots]",
             "✓","乖離大きい順にソート"),
        ]
        for label,theory,code,status,note in rows:
            self._match_row(label,theory,code,status,note)
        self.set_text_color(*DARK)
        self.ln(3)

        self._sec("✓ エントリー価格: 翌日寄り付き成行（確定）",color=GREEN)
        self._t(8.5)
        self.multi_cell(0,5.5,
            "当日終値でシグナル条件を確認し、翌朝の寄り付き成行注文でエントリーする設計に確定。\n"
            "引け後に成行注文を発注すれば、翌営業日の寄り付き（始値）で約定する。\n\n"
            "→ バックテストは翌日の始値（Open）をエントリー価格として使用。\n"
            "→ 一日遅れの分、ギャップ変動がコストとして加わるが実運用と一致する。")

    # ── STEP 4: エグジット ────────────────────────────────────────────────────
    def step4_page(self,exit_img):
        self.add_page()
        self._t(14,bold=True,color=NAVY)
        self.cell(0,9,"STEP 4  エグジット条件の照合",
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14,self.get_y(),196,self.get_y()); self.ln(2)

        self.image(exit_img,x=14,y=self.get_y(),w=182,h=55)
        self.ln(59)

        self._sec("照合テーブル（先に成立した条件で決済）",color=NAVY)
        self._table_header(["条件","戦略の意図","コードの実装","判定","備考"])
        rows=[
            ("A. 利確\n（追いつき）",
             "セクターとの乖離が\n0.5%以下に縮小",
             "sec_chg_5d - stock_chg_5d\n  <= target_gap_exit\n（直近5日間ローリング）",
             "✓",
             "エントリー条件と同じ\n5日間ウィンドウで統一\n→基準点の不整合を解消"),
            ("B. 損切",
             "エントリーから-1.5%\n（stop_dist_pct）",
             "if price_now <= pos.stop_price\n(stop_price=entry*0.985)",
             "✓","問題なし"),
            ("C. 時間切れ",
             "10営業日経過",
             "pos.days_held >= max_hold_days\n（days_heldは毎バー+1）",
             "✓","1バー=1営業日。正確"),
            ("決済価格\n（損切）",
             "損切ラインの価格で決済",
             "exit_price = pos.stop_price\n（終値ではなくストップ価格）",
             "⚠","ギャップ安では実際の\n約定はもっと安くなる\n→ スリッページ未考慮"),
            ("コスト計上",
             "往復0.20%",
             "cost=entry_price*shares\n       *round_trip_cost_pct/100",
             "⚠","exit価格ベースでなく\nentry価格ベースで計算\n→ 上昇時は若干過小計上"),
        ]
        for label,theory,code,status,note in rows:
            self._match_row(label,theory,code,status,note)
        self.set_text_color(*DARK)
        self.ln(3)

        self._sec("✓ 利確の「乖離」計算: 直近5日間ローリングに統一済み",color=GREEN)
        self._t(8.5)
        self.multi_cell(0,5.5,
            "エントリー条件の乖離（条件③）: 直近5日間の変化率の差\n"
            "  例: セクター+2.4%、銘柄-0.8% → 乖離3.2%\n\n"
            "利確判定の乖離（条件A）: 同じく直近5日間の変化率の差（統一済み）\n"
            "  例: 現時点の5日間でセクター+0.8%、銘柄+0.5% → 乖離0.3% → 利確\n\n"
            "→ エントリーと利確で同じ「5日間ローリング」の物差しを使う一貫した設計。\n"
            "  乖離が縮んだ状態（同じ窓で≤0.5%）を検出して追いつき完了と判断する。")

    # ── STEP 5: ポジションサイジング ─────────────────────────────────────────
    def step5_page(self):
        self.add_page()
        self._t(14,bold=True,color=NAVY)
        self.cell(0,9,"STEP 5  ポジションサイジング（株数計算）",
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14,self.get_y(),196,self.get_y()); self.ln(3)

        self._sec("計算式（理論）",color=BLUE)
        self.set_fill_color(235,242,255); self.set_draw_color(*BLUE)
        self.set_line_width(0.8); self.set_font("YG","B",10.5)
        self.set_text_color(*BLUE)
        self.multi_cell(0,8,
            "リスク金額 = 総資金 × risk_pct（0.5%）\n"
            "ストップ幅 = エントリー価格 × stop_dist_pct（1.5%）\n"
            "株数       = floor（リスク金額 ÷ ストップ幅）",
            border=1,fill=True,align="C")
        self.set_text_color(*DARK); self.set_line_width(0.2); self.ln(3)

        self._sec("数値例（資金100万円・1,000円株の場合）",color=TEAL)
        ex_rows=[
            ("資金（capital）","1,000,000円","変数capitalから取得（トレードごとに更新）"),
            ("リスク金額","1,000,000 × 0.5% = 5,000円","このトレードで失う上限額"),
            ("ストップ幅","1,000円 × 1.5% = 15円/株","エントリー→損切りまでの値幅"),
            ("株数","5,000 ÷ 15 = 333.3 → 333株","int()で小数点切り捨て（floor）"),
            ("投入金額","333株 × 1,000円 = 333,000円","資金の33.3%"),
            ("最大損失","333株 × 15円 = 4,995円","≒ 5,000円（資金の0.5%）✓"),
        ]
        ws=[40,60,82]
        self.set_font("YG","B",8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h,w in zip(["項目","計算","意味"],ws):
            self.cell(w,6.5,h,border=1,fill=True,align="C")
        self.ln()
        for i, (item, calc, meaning) in enumerate(ex_rows):
            bg = (255, 252, 220) if "最大損失" in item else (LIGHT if i%2==0 else WHITE)
            self._row3(
                [item, calc, meaning], ws,
                fills=[bg, bg, bg],
                bolds=[True, False, False],
                aligns=["C", "C", "L"],
            )
        self.set_text_color(*DARK); self.ln(3)

        self._sec("コードの実装（backtest_stocks.py 314〜316行）",color=NAVY)
        self._code_box(
            "risk_amount   = capital * config.risk_pct / 100    # 5,000円\n"
            "stop_dist_jpy = entry_price * config.stop_dist_pct / 100  # 15円\n"
            "shares        = int(risk_amount / stop_dist_jpy)   # 333株（切り捨て）"
        )

        self._sec("照合結果",color=GREEN)
        self._table_header(["確認項目","戦略の意図","コードの実装","判定","備考"])
        rows=[
            ("リスク金額","資金 × risk_pct%","capital*config.risk_pct/100","✓",""),
            ("ストップ幅","株価 × stop_dist%","entry*config.stop_dist_pct/100","✓",""),
            ("株数計算","切り捨て（floor）","int()","✓","int()はfloorと同義"),
            ("資金の更新","決済ごとに資金を更新",
             "capital += t.net_pnl_jpy","✓","複利効果が自動的に入る"),
            ("単元株制限","現実では100株単位",
             "なし（1株単位で計算）","✗",
             "実運用では100株単位に\n丸める処理が必要"),
        ]
        for label,theory,code,status,note in rows:
            self._match_row(label,theory,code,status,note)
        self.set_text_color(*DARK)

    # ── STEP 6: 発見された問題点 ─────────────────────────────────────────────
    def step6_page(self,today):
        self.add_page()
        self._t(14,bold=True,color=NAVY)
        self.cell(0,9,"STEP 6  照合結果サマリー・残課題",
                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14,self.get_y(),196,self.get_y()); self.ln(3)

        issues=[
            ("✓ A","エントリー: 翌日寄り付き成行に変更済み",
             "終値でシグナルを確認した後、翌朝の寄り付き（始値）で成行注文を執行する設計に確定。\n"
             "バックテストも翌日のOpen価格をエントリー価格として使用している。\n"
             "実運用との乖離は解消済み。一日遅れのギャップ変動がスリッページとして計上される。",
             GREEN,"解決済み"),
            ("✓ B","利確の乖離計算: 直近5日間ローリングに統一済み",
             "エントリー条件（条件③）と同じ「直近5日間の乖離率」で利確判定するよう変更済み。\n"
             "sec_chg_5d - stock_chg_5d <= target_gap_exit で縮小を判定する。\n"
             "基準点の不整合が解消され、エントリーと利確で同じ物差しを使う一貫した設計になった。",
             GREEN,"解決済み"),
            ("✓ C","クロスコリレーション: max()は意図的で正しい",
             "最適ラグの決定にmax()（最大の正の相関）を使うのは戦略上正しい設計。\n"
             "この戦略が狙うのは「セクターと同方向に動く遅行株」であり、\n"
             "負の相関を持つ逆相関株は追いつき対象外のため無視して問題ない。\n"
             "また相関係数閾値は0.30→0.60に引き上げ済みで、遅行確信度が向上している。",
             GREEN,"確認済み"),
            ("⚠ D","コスト計算の基準",
             "往復コスト0.20%をエントリー価格 × 株数で計算している。\n"
             "厳密には買い時のコスト（エントリー価格基準）と\n"
             "売り時のコスト（エグジット価格基準）を別々に計算すべき。\n"
             "上昇して利確した場合: 実コスト > 計算値（過小評価）\n"
             "損切りした場合: 実コスト < 計算値（過大評価）\n"
             "ただし誤差は小さく（0.1%程度）、全体的な影響は軽微。",
             GRAY,"軽微"),
            ("✗ E","単元株制限が未実装",
             "コードは1株単位で株数を計算する。日本株は通常100株単位（1単元）。\n"
             "実運用では計算された株数を100株単位に切り捨てる必要がある。\n"
             "例: 計算株数333株 → 実際は300株（3単元）\n"
             "これによりポジションサイジングが微妙にずれる。\n"
             "かぶミニ（1株単位）を使えばこの問題は解消される。",
             RED,"要実装"),
        ]
        for tag,title,desc,color,severity in issues:
            self.set_font("YG","B",9); self.set_text_color(*color)
            self.cell(0,7,f"{tag}  {title}  [{severity}]",
                      new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            self.set_font("YG","",8.5); self.set_text_color(*DARK)
            self.set_x(self.l_margin+5)
            self.multi_cell(0,5.5,desc); self.ln(2)

        self.ln(2)
        self._sec("正しいと確認できた項目（◎）",color=GREEN)
        ok_items=[
            "セクター指数の等加重計算（✓）",
            "セクター上昇率5日間の計算（✓）",
            "乖離率の計算方法（条件③）（✓）",
            "損切ラインの設定（✓）",
            "時間切れ（10営業日）のカウント（✓）",
            "ポジションサイジングの数式（✓）",
            "複利効果（capitalの更新）（✓）",
        ]
        for item in ok_items:
            self.set_font("YG","",9); self.set_text_color(*GREEN)
            self.cell(0,6.5,f"  ✓  {item}",
                      new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*DARK)

        self.set_y(270)
        self._t(7.5,color=GRAY)
        self.multi_cell(0,5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）\n"
            "このドキュメントはコードと戦略の照合を目的とした内部検証資料です。",
            align="C")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today=datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"  ロジック照合ドキュメント PDF生成")
    print(f"{'='*50}\n")

    print("チャート生成中...")
    idx_img   = make_index_chart()
    entry_img = make_entry_chart()
    exit_img  = make_exit_chart()

    print("PDF生成中...")
    pdf=VerificationPDF()
    pdf.cover(today)
    pdf.step1_page(idx_img)
    pdf.step2_page()
    pdf.step3_page(entry_img)
    pdf.step4_page(exit_img)
    pdf.step5_page()
    pdf.step6_page(today)

    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    out=OUTPUT_DIR/f"logic_verification_{ts}.pdf"
    pdf.output(str(out))

    for f in [idx_img,entry_img,exit_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*50}\n")

if __name__=="__main__":
    main()
