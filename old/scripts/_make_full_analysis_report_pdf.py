# -*- coding: utf-8 -*-
"""
全ペア × セッション  IS期間 統合報告書
出力: docs/full_analysis/report_is_full.pdf
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
from pathlib import Path
from fpdf import FPDF, XPos, YPos
from datetime import date
from scipy import stats

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

BASE     = Path(__file__).parent
FA_DIR   = BASE / "docs" / "full_analysis"
SJ_DIR   = BASE / "docs" / "strategy_judgment"
OUT_PATH = FA_DIR / "report_is_full.pdf"
FONT     = r"C:\Windows\Fonts\YuGothM.ttc"
CAPITAL  = 1_000_000

C_NAVY  = (15, 30, 70);   C_BLUE  = (30, 90,170)
C_TEAL  = (0, 160,120);   C_AMBER = (200,140,  0)
C_RED   = (180, 40, 40);  C_GREEN = (0, 130, 60)
C_SHORT = (26, 58,122);   C_LONG  = (176, 48, 48)
C_SH_L  = (190,210,240);  C_LO_L  = (240,190,190)
C_GRAY  = (160,160,160);  C_WHITE = (255,255,255)
C_BLACK = (20, 20, 20);   C_LGRAY = (235,235,235)
C_STRIPE= (235,242,255)

# ── データ読込 ────────────────────────────────────────────────
df_stats = pd.read_csv(FA_DIR/"stats_full.csv",    encoding="utf-8-sig") \
           if (FA_DIR/"stats_full.csv").exists()   else pd.DataFrame()
df_bt_res= pd.read_csv(FA_DIR/"bt_results.csv",   encoding="utf-8-sig") \
           if (FA_DIR/"bt_results.csv").exists()   else pd.DataFrame()
df_trades= pd.read_csv(FA_DIR/"bt_trades.csv",    encoding="utf-8-sig") \
           if (FA_DIR/"bt_trades.csv").exists()    else pd.DataFrame()
df_pb    = pd.read_csv(SJ_DIR/"playbook.csv",      encoding="utf-8-sig") \
           if (SJ_DIR/"playbook.csv").exists()     else pd.DataFrame()

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}

def bt_summary(df):
    if len(df)==0: return {}
    if "pnl_yen" not in df.columns: return {}
    df["pnl_yen"] = pd.to_numeric(df["pnl_yen"], errors="coerce")
    df["r_mult"]  = pd.to_numeric(df["r_mult"],  errors="coerce")
    w=df[df["pnl_yen"]>0]; l=df[df["pnl_yen"]<=0]
    gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=df["pnl_yen"].cumsum(); r=df["r_mult"].dropna()
    tr = np.percentile(r,95)/abs(np.percentile(r,5)) \
         if len(r)>0 and abs(np.percentile(r,5))>1e-10 else np.nan
    om = r[r>0].sum()/abs(r[r<0].sum()) if len(r[r<0])>0 else np.nan
    return {"n":len(df),"win_rate":len(w)/len(df)*100,
            "pf":pf,"total_pnl":df["pnl_yen"].sum(),
            "dd_pct":(cum.cummax()-cum).max()/CAPITAL*100,
            "avg_r":r.mean(),"tail_ratio":tr,"omega":om}

sv_total = bt_summary(df_trades) if len(df_trades) else {}

# ランキングデータ
if len(df_stats):
    df_ac = df_stats[df_stats["group"].isin(["Q10+ac>0","Q10+ac<0"])].copy()
    df_ac = df_ac[df_ac["n"]>=30].dropna(subset=["TailRatio","OmegaRatio"])
    df_short = df_ac[(df_ac["μ(%)"]<0)&(df_ac["group"]=="Q10+ac>0")].copy()
    df_short["score"] = (1/df_short["TailRatio"].clip(0.01))*(1/df_short["OmegaRatio"].clip(0.01))
    df_short = df_short.sort_values("score",ascending=False).head(15)
    df_long  = df_ac[(df_ac["μ(%)"]>0)&(df_ac["group"]=="Q10+ac<0")].copy()
    df_long["score"] = df_long["TailRatio"]*df_long["OmegaRatio"]
    df_long  = df_long.sort_values("score",ascending=False).head(15)
else:
    df_short = df_long = pd.DataFrame()

def img_h(path, w):
    if HAS_PIL and Path(path).exists():
        with PILImage.open(path) as im:
            iw,ih = im.size
        return w*ih/iw
    return w*0.6

# ════════════════════════════════════════════════════════════
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG","",FONT); self.add_font("YG","B",FONT)
        self.set_margins(14,14,14)
        self.set_auto_page_break(False)
        self._lim = 297-14-12

    def header(self):
        if self.page_no()==1: return
        self.set_font("YG","",7); self.set_text_color(*C_GRAY)
        self.set_xy(14,8)
        self.cell(182,4,"12通貨ペア × セッション別戦略  IS期間報告書",align="R")
        self.set_text_color(*C_BLACK)

    def footer(self):
        self.set_y(-11); self.set_font("YG","",7.5)
        self.set_text_color(*C_GRAY)
        self.cell(0,5,f"─  {self.page_no()}  ─",align="C")
        self.set_text_color(*C_BLACK)

    def need(self, h):
        if self.get_y()+h > self._lim: self.add_page(); return True
        return False

    def sec(self, t, force=False):
        if force: self.need(999)
        self.set_fill_color(*C_BLUE); self.set_text_color(*C_WHITE)
        self.set_font("YG","B",11)
        self.set_x(14); self.cell(182,8,f"  {t}",fill=True,
                                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*C_BLACK); self.ln(2)

    def sub(self, t, bg=None):
        self.need(7)
        c = bg or C_TEAL
        self.set_fill_color(*c); self.set_text_color(*C_WHITE)
        self.set_font("YG","B",9)
        self.set_x(14); self.cell(182,6,f"  {t}",fill=True,
                                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*C_BLACK); self.ln(1)

    def th(self, ws, hs, h=6):
        self.need(h)
        self.set_fill_color(*C_NAVY); self.set_text_color(*C_WHITE)
        self.set_font("YG","B",8); self.set_x(14)
        for w,hd in zip(ws,hs): self.cell(w,h,hd,fill=True,align="C")
        self.ln(); self.set_text_color(*C_BLACK)

    def tr(self, ws, vs, ev=False, colors=None, aligns=None, h=6):
        self.need(h)
        aligns = aligns or ["C"]*len(ws)
        colors = colors or [None]*len(ws)
        self.set_fill_color(*(C_STRIPE if ev else C_WHITE))
        x0,y0=14,self.get_y()
        self.rect(x0,y0,sum(ws),h,"F")
        cx=x0
        for w,v,a,c in zip(ws,vs,aligns,colors):
            self.set_xy(cx,y0)
            if c: self.set_text_color(*c)
            self.set_font("YG","",8); self.cell(w,h,str(v),align=a)
            self.set_text_color(*C_BLACK); cx+=w
        self.set_xy(14,y0+h)

    def kv(self, k, v, lw=44, vc=None):
        self.need(6)
        self.set_x(14); self.set_font("YG","B",8.5); self.cell(lw,6,k)
        self.set_font("YG","",8.5)
        if vc: self.set_text_color(*vc)
        self.cell(182-lw,6,str(v),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*C_BLACK)

    def body(self, t, c=None):
        if c: self.set_text_color(*c)
        self.set_font("YG","",8.5); self.set_x(14)
        self.multi_cell(182,5.5,t)
        self.set_text_color(*C_BLACK); self.ln(1)

    def img(self, path, w=182, note=None):
        p=Path(path)
        if not p.exists(): return
        h=img_h(p,w); self.need(h+4)
        self.set_x(14); self.image(str(p),x=14,w=w)
        if note:
            self.set_font("YG","",7); self.set_text_color(*C_GRAY)
            self.set_x(14); self.cell(182,4,note,align="C",
                                      new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            self.set_text_color(*C_BLACK)
        self.ln(2)

pdf = PDF()

# ════════════════════════════════════════════════════════════
# p1 表紙
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.set_fill_color(*C_NAVY); pdf.rect(0,0,210,297,"F")
pdf.set_y(48); pdf.set_font("YG","B",26); pdf.set_text_color(*C_WHITE)
pdf.cell(0,13,"12通貨ペア",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.cell(0,13,"セッション別戦略分析",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.set_font("YG","B",18)
pdf.cell(0,11,"IS期間報告書",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.ln(5)
pdf.set_fill_color(*C_TEAL)
pdf.set_x(14); pdf.cell(182,9,
    "  通貨強弱 × ブレイクダウン × 自己相関  /  Tail Ratio・Omega Ratio 評価",
    fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.ln(8); pdf.set_font("YG","",10)
for k,v in [
    ("分析対象",    "全12通貨ペア × 4セッション × 5グループ"),
    ("IS期間",     "2022-01-01  〜  2023-12-31"),
    ("全期間統計", "2022-01-01  〜  2024-12-31（3年間）"),
    ("ブレイク条件","現在足 Low < 前足 Low"),
    ("強弱フィルター","通貨強弱差 Q10（下位10%）"),
    ("自己相関",   "12本ローリングlag-1自己相関（ac12>0 / ac12<0）"),
    ("評価指標",   "μ, Skew, Kurt, VaR95, CVaR95, Tail Ratio, Omega Ratio"),
    ("作成日",     date.today().strftime("%Y年%m月%d日")),
]:
    pdf.set_font("YG","B",9.5); pdf.set_x(28); pdf.cell(56,8,k)
    pdf.set_font("YG","",9.5);  pdf.cell(0,8,v,new_x=XPos.LMARGIN,new_y=YPos.NEXT)

# IS全体クイックサマリー
pdf.set_y(200); pdf.set_fill_color(25,55,115)
pdf.rect(14,200,182,62,"F")
pdf.set_y(204); pdf.set_font("YG","B",10)
pdf.set_text_color(200,220,255); pdf.set_x(20)
pdf.cell(0,8,"IS期間バックテスト クイックサマリー",
         new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.set_font("YG","",9.5); pdf.set_text_color(*C_WHITE)
for k,v in [
    ("総トレード数",  f"{sv_total.get('n',0):,}件"),
    ("統合PF",       f"{sv_total.get('pf',0):.2f}"),
    ("総損益",       f"{sv_total.get('total_pnl',0):+,.0f}円  /  資金100万円"),
    ("MaxDD",        f"{sv_total.get('dd_pct',0):.1f}%"),
    ("Tail Ratio",   f"{sv_total.get('tail_ratio',0):.3f}"),
    ("Omega Ratio",  f"{sv_total.get('omega',0):.3f}"),
]:
    pdf.set_font("YG","B",9); pdf.set_x(22); pdf.cell(52,8,k)
    pdf.set_font("YG","",9);  pdf.cell(0,8,v,new_x=XPos.LMARGIN,new_y=YPos.NEXT)

# ════════════════════════════════════════════════════════════
# p2 分析手法
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("1  分析手法・指標定義",force=False)

pdf.sub("エントリーシグナル条件")
for k,v in [
    ("ブレイクダウン","現在5分足 Low < 直前5分足 Low"),
    ("強弱差フィルター","12ペア×7通貨スコアの差 = 下位10%（Q10）"),
    ("自己相関フィルター(SHORT)","直近12本リターンのlag-1自己相関 > 0（モメンタム継続）→ ac>0"),
    ("自己相関フィルター(LONG)","直近12本リターンのlag-1自己相関 < 0（反転しやすい）→ ac<0"),
    ("リターン計算","log(Close[t+h] / Close[t])  ← 全ペアで統一"),
    ("主分析ホライゾン","H=6本後（30分後）"),
]:
    pdf.kv(k,v,lw=56)
pdf.ln(3)

pdf.sub("評価指標定義")
metrics_def = [
    ("μ（期待値）",       "リターン系列の平均値（%換算）"),
    ("Skew（歪度）",      "負=左裾が厚い=下落リスク大 / 正=右裾が厚い=上昇余地大"),
    ("Kurtosis（超過尖度）","正規分布=0 / 大きいほどファットテール（極端な動きが多い）"),
    ("VaR95",             "5th percentile（5%確率で超える損失額）"),
    ("CVaR95",            "VaR95超過時の条件付期待損失（Expected Shortfall）"),
    ("P(r>σ)",           "全期間σを閾値とした上昇確率（%）"),
    ("P(r<-σ)",          "全期間σを閾値とした下落確率（%）"),
    ("Tail Ratio",        "P95 / |P5|  ← >1:右裾が厚い(LONG有利) / <1:左裾が厚い(SHORT有利)"),
    ("Omega Ratio",       "Σ利益 / Σ損失（threshold=0）← >1:利益>損失(LONG有利) / <1:逆"),
]
ws=[52,130]
pdf.th(ws,["指標","定義"],h=6)
for i,(k,v) in enumerate(metrics_def):
    pdf.tr(ws,[k,v],ev=(i%2==0),aligns=["L","L"])
pdf.ln(3)

pdf.sub("判定スコアリング")
pdf.body("各グループ（Q10+ac>0 or Q10+ac<0）に対して以下4条件を確認しスコア化:\n"
         "  ① μ < 0（SHORT）or > 0（LONG）\n"
         "  ② Skew < -0.2（SHORT）or > 0.2（LONG）\n"
         "  ③ Tail Ratio < 1（SHORT）or > 1（LONG）\n"
         "  ④ Omega Ratio < 1（SHORT）or > 1（LONG）\n"
         "  スコア3以上 → 強判定 / 2 → 中判定\n\n"
         "ランキングスコア:\n"
         "  SHORT: rank_score = (1/TailRatio) × (1/OmegaRatio) ← 大きいほど優位\n"
         "  LONG:  rank_score = TailRatio × OmegaRatio ← 大きいほど優位")

# ════════════════════════════════════════════════════════════
# p3 SHORT ランキング
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("2  SHORTランキング（順張り）─  Q10 + ac > 0")

pdf.body("ac>0（自己相関正）= 直近リターンにモメンタムが出ている状態。"
         "ブレイクダウン後も下落が継続しやすい。\n"
         "ランクスコア = (1/TailRatio) × (1/OmegaRatio)  ← 左裾・下落超過が大きいほど高スコア",
         c=C_AMBER)
pdf.ln(2)

ws_r=[8,24,48,16,14,16,16,16,16,16]
pdf.th(ws_r,["#","ペア","セッション","μ(%)","Skew","VaR95","CVaR95","TailR","Omega","Score"],h=6)
for ri,(_,row) in enumerate(df_short.iterrows()):
    m  = row.get("μ(%)",0); sk = row.get("Skew",0)
    va = row.get("VaR95(%)",0); cv = row.get("CVaR95(%)",0)
    tr = row.get("TailRatio",0); om = row.get("OmegaRatio",0)
    sc = row.get("score",0)
    pf_c = C_SHORT if m<0 else C_RED
    tr_c = C_GREEN if tr<1 else C_AMBER  # <1 は SHORT有利
    om_c = C_GREEN if om<1 else C_AMBER
    pdf.tr(ws_r,[
        str(ri+1),
        row.get("pair","─"),
        row.get("session","─").replace("\n"," ")[:14],
        f"{m:+.5f}", f"{sk:+.3f}",
        f"{va:+.5f}", f"{cv:+.5f}",
        f"{tr:.4f}", f"{om:.4f}", f"{sc:.4f}",
    ],ev=(ri%2==0),
    colors=[None,None,None,pf_c,None,None,None,tr_c,om_c,None])
pdf.ln(4)

pdf.sub("SHORTランキング 解釈")
pdf.body("欧州時間（15-21JST）のJPYペア（EURJPY・AUDJPY・GBPJPY等）が最上位。\n"
         "欧州オープン後のモメンタム（ac>0）が続く状況でブレイクダウンすると、\n"
         "下落継続の非対称分布（Tail Ratio<1）が現れる。\n\n"
         "注目値:\n"
         "  EURJPY 欧州: TailR=0.746, Omega=0.791 → 左裾が右裾の1.34倍厚い\n"
         "  AUDJPY 欧州: TailR=0.784, Omega=0.756 → 最もOmega低い（下落優位）")

# ════════════════════════════════════════════════════════════
# p4 LONG ランキング
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("3  LONGランキング（逆張り）─  Q10 + ac < 0")

pdf.body("ac<0（自己相関負）= 直近リターンが反転しやすい状態。"
         "ブレイクダウン後に価格が戻りやすい。\n"
         "ランクスコア = TailRatio × OmegaRatio  ← 右裾・上昇超過が大きいほど高スコア",
         c=C_AMBER)
pdf.ln(2)

ws_r2=[8,24,48,16,14,16,16,16,16,16]
pdf.th(ws_r2,["#","ペア","セッション","μ(%)","Skew","VaR95","CVaR95","TailR","Omega","Score"],h=6)
for ri,(_,row) in enumerate(df_long.iterrows()):
    m  = row.get("μ(%)",0); sk = row.get("Skew",0)
    va = row.get("VaR95(%)",0); cv = row.get("CVaR95(%)",0)
    tr = row.get("TailRatio",0); om = row.get("OmegaRatio",0)
    sc = row.get("score",0)
    pf_c = C_GREEN if m>0 else C_RED
    tr_c = C_GREEN if tr>1 else C_AMBER
    om_c = C_GREEN if om>1 else C_AMBER
    pdf.tr(ws_r2,[
        str(ri+1),
        row.get("pair","─"),
        row.get("session","─").replace("\n"," ")[:14],
        f"{m:+.5f}", f"{sk:+.3f}",
        f"{va:+.5f}", f"{cv:+.5f}",
        f"{tr:.4f}", f"{om:.4f}", f"{sc:.4f}",
    ],ev=(ri%2==0),
    colors=[None,None,None,pf_c,None,None,None,tr_c,om_c,None])
pdf.ln(4)

pdf.sub("LONGランキング 解釈")
pdf.body("AUDNZDの深夜時間が断トツ（TailR=1.502、Omega=1.813）。\n"
         "EURGBP・EURAUDなどクロスペアも深夜・欧州時間でLONG有利が続出。\n\n"
         "注目値:\n"
         "  AUDNZD 深夜: TailR=1.502, Omega=1.813 → 右裾が左裾の1.5倍厚い\n"
         "  EURAUD 深夜: Skew=+2.358 → 強い正歪み（大幅上昇が多い）\n"
         "  EURGBP 欧州: Skew=+0.763, TailR=1.220 → 安定した右裾優位")

# ════════════════════════════════════════════════════════════
# p5 散布図・ヒートマップ
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("4  Tail Ratio × Omega Ratio 分布")
pdf.img(FA_DIR/"tail_omega_scatter.png", w=182,
        note="● Q10+ac>0（SHORT候補）  ■ Q10+ac<0（LONG候補）  "
             "右上=LONG優位 / 左下=SHORT優位")

pdf.add_page()
pdf.sec("5  Tail Ratio / Omega Ratio ヒートマップ")
pdf.img(FA_DIR/"tail_omega_heatmap.png", w=182,
        note="Q10+ac>0群 / 6本後 / 赤=LONG有利（>1） / 青=SHORT有利（<1）")

# ════════════════════════════════════════════════════════════
# p6 ISバックテスト概要
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("6  ISバックテスト結果（2022-2023）")

pdf.sub("全体サマリー")
for k,v,vc in [
    ("総トレード数",  f"{sv_total.get('n',0):,}件",          None),
    ("統合PF",       f"{sv_total.get('pf',0):.2f}",          C_GREEN if sv_total.get('pf',0)>=1.2 else C_AMBER),
    ("総損益",       f"{sv_total.get('total_pnl',0):+,.0f}円（資金100万円）",
                                                              C_GREEN if sv_total.get('total_pnl',0)>0 else C_RED),
    ("MaxDD",        f"{sv_total.get('dd_pct',0):.1f}%",     C_GREEN if sv_total.get('dd_pct',0)<=25 else C_RED),
    ("Tail Ratio",   f"{sv_total.get('tail_ratio',0):.3f}",  None),
    ("Omega Ratio",  f"{sv_total.get('omega',0):.3f}",       C_GREEN if sv_total.get('omega',0)>=1.0 else C_RED),
]:
    pdf.kv(k,v,lw=40,vc=vc)
pdf.ln(3)

pdf.sub("ペア別バックテスト結果（損益順）")
ws_b=[26,14,12,10,14,22,10,16,16]
pdf.th(ws_b,["ペア","方向","n","勝率%","PF","損益(円)","DD%","TailR","Omega"],h=6)

if len(df_bt_res):
    df_bt_res["pf"]        = pd.to_numeric(df_bt_res.get("pf",0),       errors="coerce").fillna(0)
    df_bt_res["total_pnl"] = pd.to_numeric(df_bt_res.get("total_pnl",0),errors="coerce").fillna(0)
    df_bt_res["dd_pct"]    = pd.to_numeric(df_bt_res.get("dd_pct",0),   errors="coerce").fillna(0)

    for ri,(_,row) in enumerate(
        df_bt_res.sort_values("total_pnl",ascending=False).iterrows()
    ):
        pf  = row.get("pf",0)
        pnl = row.get("total_pnl",0)
        dd  = row.get("dd_pct",0)
        tr  = row.get("tail_ratio",0)
        om  = row.get("omega",0)
        pf_c = C_GREEN if pf>=1.2 else C_AMBER if pf>=1.0 else C_RED
        pnl_c= C_GREEN if pnl>0 else C_RED
        dd_c = C_GREEN if dd<=20 else C_AMBER if dd<=30 else C_RED
        d_lbl= "SHORT" if row.get("direction","")=="short" else "LONG"
        d_c  = C_SHORT if "SHORT" in d_lbl else C_LONG
        pdf.tr(ws_b,[
            f"{row.get('pair','─')}",
            d_lbl,
            f"{row.get('n',0):.0f}",
            f"{row.get('win_rate',0):.1f}",
            f"{pf:.2f}",
            f"{pnl:+,.0f}",
            f"{dd:.1f}",
            f"{tr:.3f}" if not (isinstance(tr,float) and np.isnan(tr)) else "─",
            f"{om:.3f}" if not (isinstance(om,float) and np.isnan(om)) else "─",
        ],ev=(ri%2==0),
        colors=[None,d_c,None,None,pf_c,pnl_c,dd_c,None,None])
else:
    pdf.body("バックテストデータがありません。")

# ════════════════════════════════════════════════════════════
# p7 累積損益曲線
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("7  累積損益曲線（IS期間 ペア別）")
pdf.img(FA_DIR/"bt_pnl_curves.png", w=182,
        note="SL: 資金0.5% / TP: トレーリング(ATR×1.0) / 最大48本 / IS期間 2022-2023")

# ════════════════════════════════════════════════════════════
# p8 ランキング図
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("8  戦略ランキング（Tail × Omega スコア順）")
pdf.img(FA_DIR/"ranking_table.png", w=182,
        note="左: SHORTランキング（Q10+ac>0）  右: LONGランキング（Q10+ac<0）")

# ════════════════════════════════════════════════════════════
# p9 総括
# ════════════════════════════════════════════════════════════
pdf.add_page()
pdf.sec("9  総括 & 次のアクション")

pdf.set_font("YG","B",11); pdf.set_text_color(*C_TEAL)
pdf.set_x(14)
pdf.cell(182,8,"IS期間 検証完了  →  上位ペア選定 & OOS開封へ",
         new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.set_text_color(*C_BLACK); pdf.ln(2)

pdf.sub("主要発見事項")
findings=[
    "1. 欧州時間（15-21JST）のJPYペアでSHORTエッジが最強。Tail Ratio<0.8かつOmega<0.8の組み合わせが複数確認。",
    "2. 深夜時間（03-09JST）のクロスペア（AUDNZD・EURGBP・EURAUD）でLONGエッジが突出。薄商いの中の反発構造。",
    "3. 自己相関フィルターの効果: ac>0でSHORTの分布が改善（左裾強化）、ac<0でLONGの分布が改善（右裾強化）。",
    "4. Tail Ratio × Omega Ratioスコアにより、Sharpeでは見えなかった非対称な分布エッジが定量化できた。",
    "5. 統合システムIS総合PF=1.26（28,649件）。総損益+1,509万円。MaxDD=35.3%は許容できるが、DDの大きいペアは要改善。",
]
for f in findings:
    pdf.set_font("YG","",8.5); pdf.set_x(14); pdf.multi_cell(182,5.5,f)
    pdf.ln(1)

pdf.ln(2); pdf.sub("採用推奨ペア（上位）")
adopted=[
    ("SHORT★★★","EURJPY・AUDJPY 欧州時間","Q10+ac>0  TailR≈0.75  Omega≈0.76"),
    ("SHORT★★",  "GBPJPY・NZDJPY 欧州時間","Q10+ac>0  TailR≈0.80"),
    ("LONG★★★",  "AUDNZD 深夜時間",        "Q10+ac<0  TailR=1.50  Omega=1.81"),
    ("LONG★★★",  "EURGBP 欧州/東京/NY時間","Q10+ac<0  全セッションで安定"),
    ("LONG★★",   "EURAUD・AUDUSD 深夜時間","Q10+ac<0  Skew正・右裾厚"),
]
ws_a=[30,70,80]
pdf.th(ws_a,["優先度","ペア・セッション","エッジ条件"],h=6)
for i,(g,p,c) in enumerate(adopted):
    gc = C_SHORT if "SHORT" in g else C_LONG
    pdf.tr(ws_a,[g,p,c],ev=(i%2==0),colors=[gc,None,None],
           aligns=["C","L","L"])

pdf.ln(3); pdf.sub("注意点・前提条件",bg=C_AMBER)
notes=[
    "スプレッド・スリッページ未考慮。実運用ではSHORTペアに特に注意（欧州オープン時に流動性スプレッド拡大）。",
    "MaxDD=35.3%は資金効率の観点から高め。上位ペアに絞り込みor資金配分調整が必要。",
    "リターン計算はclose/closeベース。実際のエントリーは次足Openのため、実績は多少異なる可能性あり。",
    "IS内最適化の要素（Q10・ac閾値）が含まれる。OOS開封でロバストネスを最終確認すること。",
]
for note in notes:
    pdf.set_font("YG","",8.2); pdf.set_x(14); pdf.multi_cell(182,5,f"・ {note}")

pdf.ln(3); pdf.sub("次のアクション",bg=C_NAVY)
steps=[
    ("Step 1 完了","全12ペア × 4セッション統計解析（μ/Skew/Kurt/VaR/CVaR/TailR/OmegaR）"),
    ("Step 2 完了","IS期間バックテスト（28,649件 PF=1.26 損益+1,509万円）"),
    ("Step 3 次",  "OOS期間（2024年）開封 → IS vs OOS 比較"),
    ("Step 4",     "上位ペア絞り込み（TailR・OmegaRスコア上位）→ ロバストネス検証"),
    ("Step 5",     "週次ランキングシステム統合 → デモ運用開始"),
]
for i,(s,d) in enumerate(steps):
    pdf.need(6.5)
    x0,y0=14,pdf.get_y()
    pdf.set_fill_color(*(C_STRIPE if i%2==0 else C_WHITE))
    pdf.rect(x0,y0,182,6.5,"F")
    pdf.set_xy(x0,y0); pdf.set_font("YG","B",8.5); pdf.cell(40,6.5,s)
    pdf.set_font("YG","",8.5); pdf.cell(142,6.5,d,
                                         new_x=XPos.LMARGIN,new_y=YPos.NEXT)

pdf.ln(5); pdf.set_font("YG","",7); pdf.set_text_color(*C_GRAY)
pdf.set_x(14); pdf.multi_cell(182,4.5,
    f"作成日: {date.today().strftime('%Y年%m月%d日')}  /  "
    "12通貨ペア × セッション別戦略分析 v1.0  /  "
    "データ: Dukascopy 5分足 2022-2024  /  IS期間報告書")

pdf.output(str(OUT_PATH))
print(f"PDF生成完了: {OUT_PATH}")
print(f"総ページ数: {pdf.page}")
