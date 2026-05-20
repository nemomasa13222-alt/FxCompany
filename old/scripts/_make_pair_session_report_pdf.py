# -*- coding: utf-8 -*-
"""
12通貨ペア × 時間帯別戦略  PDF報告書
出力: docs/pair_session_charts/strategy_report.pdf
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
from pathlib import Path
from fpdf import FPDF, XPos, YPos
from datetime import date

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

BASE     = Path(__file__).parent
CHART_DIR= BASE / "docs" / "pair_session_charts"
STATS_DIR= BASE / "docs" / "pair_session_analysis"
OUT_PATH = CHART_DIR / "strategy_report.pdf"
FONT     = r"C:\Windows\Fonts\YuGothM.ttc"

# ── カラー ───────────────────────────────────────────────────
C_NAVY  = (15, 30, 70);   C_BLUE  = (30, 90,170)
C_TEAL  = (0,160,120);    C_AMBER = (200,140,  0)
C_RED   = (180, 40, 40);  C_GREEN = (0, 130, 60)
C_LONG  = (200, 40, 40);  C_SHORT = (30, 80,170)
C_LONG_L= (240,190,190);  C_SHORT_L=(190,210,240)
C_GRAY  = (180,180,180);  C_WHITE = (255,255,255)
C_BLACK = (20, 20, 20);   C_LGRAY = (235,235,235)
C_STRIPE= (235,242,255)

# ── 判定色テーブル ────────────────────────────────────────────
def judge_color(j: str):
    if   "▲LONG"     in j: return C_LONG,   C_WHITE, "▲ LONG（強）"
    elif "△long"     in j: return C_LONG_L, C_BLACK, "△ long（弱）"
    elif "▼SHORT"    in j: return C_SHORT,  C_WHITE, "▼ SHORT（強）"
    elif "▽short"    in j: return C_SHORT_L,C_BLACK, "▽ short（弱）"
    else:                   return C_LGRAY,  C_GRAY,  "─"

# ── データ読込 ────────────────────────────────────────────────
df_jt = pd.read_csv(STATS_DIR/"judgment_table.csv", encoding="utf-8-sig")
df_st = pd.read_csv(STATS_DIR/"stats_all.csv",      encoding="utf-8-sig")

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}

SESSIONS_DEF = [
    ("東京 09-15JST", (0,160,120,0)),
    ("欧州 15-21JST", (0,160,120,0)),
    ("NY   21-03JST", (0,160,120,0)),
    ("深夜 03-09JST", (0,160,120,0)),
]
SESS_COLS = ["東京 09-15", "欧州 15-21", "NY   21-03", "深夜 03-09"]
SESS_LABELS = ["東京\n09-15JST", "欧州\n15-21JST", "NY\n21-03JST", "深夜\n03-09JST"]
SESS_COLORS = [
    (224,123,  0),   # orange
    ( 34,170,100),   # green
    ( 56,102,168),   # blue
    (153, 51,204),   # purple
]

def img_height(path, w_mm):
    if HAS_PIL and Path(path).exists():
        with PILImage.open(path) as im:
            iw, ih = im.size
        return w_mm * ih / iw
    return w_mm * 0.6

# ════════════════════════════════════════════════════════════
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG","",FONT); self.add_font("YG","B",FONT)
        self.set_margins(14,14,14)
        self.set_auto_page_break(False)
        self._lim = 297 - 14 - 12

    def header(self):
        if self.page_no()==1: return
        self.set_font("YG","",7); self.set_text_color(*C_GRAY)
        self.set_xy(14,8); self.cell(182,4,"12通貨ペア × 時間帯別戦略報告書",align="R")
        self.set_text_color(*C_BLACK)

    def footer(self):
        self.set_y(-11); self.set_font("YG","",7.5); self.set_text_color(*C_GRAY)
        self.cell(0,5,f"─  {self.page_no()}  ─",align="C")
        self.set_text_color(*C_BLACK)

    def need(self, h):
        if self.get_y()+h > self._lim: self.add_page(); return True
        return False

    def sec(self, t, force=True):
        if force: self.need(999)
        self.set_fill_color(*C_BLUE); self.set_text_color(*C_WHITE)
        self.set_font("YG","B",11)
        self.set_x(14); self.cell(182,8,f"  {t}",fill=True,
                                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*C_BLACK); self.ln(2)

    def sub(self, t, bg=None):
        self.need(7)
        c = bg or C_TEAL
        self.set_fill_color(*c); self.set_text_color(*C_WHITE); self.set_font("YG","B",9)
        self.set_x(14); self.cell(182,6,f"  {t}",fill=True,
                                  new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*C_BLACK); self.ln(1)

    def th(self, ws, hs, h=6):
        self.need(h+1)
        self.set_fill_color(*C_NAVY); self.set_text_color(*C_WHITE)
        self.set_font("YG","B",8); self.set_x(14)
        for w,hd in zip(ws,hs): self.cell(w,h,hd,fill=True,align="C")
        self.ln(); self.set_text_color(*C_BLACK)

    def tr(self, ws, vs, bg=None, aligns=None, colors=None, h=6):
        self.need(h+1)
        aligns = aligns or ["C"]*len(ws)
        colors = colors or [None]*len(ws)
        self.set_fill_color(*(bg or C_WHITE))
        x0,y0 = 14, self.get_y()
        self.rect(x0,y0,sum(ws),h,"F")
        cx = x0
        for w,v,a,c in zip(ws,vs,aligns,colors):
            self.set_xy(cx,y0)
            if c: self.set_text_color(*c)
            self.set_font("YG","",8); self.cell(w,h,str(v),align=a)
            self.set_text_color(*C_BLACK); cx+=w
        self.set_xy(14,y0+h)

    def img(self, path, w=182, note=None):
        p = Path(path)
        if not p.exists(): return
        h = img_height(p, w)
        self.need(h+3)
        self.set_x(14); self.image(str(p), x=14, w=w)
        if note:
            self.set_font("YG","",7); self.set_text_color(*C_GRAY)
            self.set_x(14); self.cell(182,4,note,align="C",
                                       new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            self.set_text_color(*C_BLACK)
        self.ln(2)

    def kv(self, k, v, lw=42, vc=None):
        self.need(6)
        self.set_x(14); self.set_font("YG","B",8.5); self.cell(lw,6,k)
        self.set_font("YG","",8.5)
        if vc: self.set_text_color(*vc)
        self.cell(182-lw,6,str(v),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_text_color(*C_BLACK)

    def body(self, text, c=None):
        if c: self.set_text_color(*c)
        self.set_font("YG","",8.5); self.set_x(14)
        self.multi_cell(182,5.5,text)
        self.set_text_color(*C_BLACK); self.ln(1)

# ════════════════════════════════════════════════════════════
pdf = PDF()

# ── p1: 表紙 ─────────────────────────────────────────────────
pdf.add_page()
pdf.set_fill_color(*C_NAVY); pdf.rect(0,0,210,297,"F")
pdf.set_y(55); pdf.set_font("YG","B",26); pdf.set_text_color(*C_WHITE)
pdf.cell(0,13,"12通貨ペア",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.cell(0,13,"時間帯別戦略分析報告書",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.ln(6)
pdf.set_fill_color(*C_TEAL)
pdf.set_x(14); pdf.cell(182,9,"  通貨強弱 × ブレイクダウン × セッション別分布分析",
                         fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.ln(8); pdf.set_font("YG","",10)
for k,v in [
    ("分析対象",    "全12通貨ペア × 4セッション"),
    ("分析期間",    "2022-01-01 〜 2024-12-31（3年間）"),
    ("ブレイク条件", "現在足 Low < 前足 Low"),
    ("強弱フィルター","USD-JPY等の強弱差 下位10%（Q10）"),
    ("先行ホライゾン","1・3・6・12・24本後"),
    ("作成日",      date.today().strftime("%Y年%m月%d日")),
]:
    pdf.set_font("YG","B",9); pdf.set_x(30); pdf.cell(50,8,k)
    pdf.set_font("YG","",9);  pdf.cell(0,8,v,new_x=XPos.LMARGIN,new_y=YPos.NEXT)

# 凡例ボックス
pdf.set_y(200); pdf.set_fill_color(30,60,110)
pdf.rect(14,200,182,62,"F")
pdf.set_y(205); pdf.set_font("YG","B",10); pdf.set_text_color(200,220,255)
pdf.set_x(20); pdf.cell(0,8,"判定凡例",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.set_font("YG","",9.5); pdf.set_text_color(*C_WHITE)
for judge,desc in [
    ("▲ LONG（強）",  "Mean>0 AND Skew>0.2 AND 上昇率>51% AND p<0.15"),
    ("△ long（弱）",  "Mean>0 のみ（統計的有意性やや弱い）"),
    ("▼ SHORT（強）", "Mean<0 AND Skew<-0.2 AND 下落率>51% AND p<0.15"),
    ("▽ short（弱）", "Mean<0 のみ（統計的有意性やや弱い）"),
    ("─  不明",        "明確なエッジなし"),
]:
    pdf.set_font("YG","B",9); pdf.set_x(22); pdf.cell(46,8,judge)
    pdf.set_font("YG","",8.5); pdf.cell(0,8,desc,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
pdf.set_y(268); pdf.set_font("YG","",7); pdf.set_text_color(140,160,200)
pdf.set_x(14); pdf.cell(182,4,"本報告書はバックテスト統計に基づく。将来のパフォーマンスを保証しない。",align="C")

# ── p2: 分析条件 ──────────────────────────────────────────────
pdf.add_page()
pdf.sec("1  分析条件・方法", force=False)

pdf.sub("エントリーシグナル定義")
for k,v in [
    ("ブレイク条件",    "現在5分足 Low < 直前5分足 Low（ブレイクダウン）"),
    ("強弱差フィルター","通貨強弱スコア（LOO法）の差が下位Q10（極端にベース通貨弱）"),
    ("強弱算出窓",      "直近24本（2時間）の12ペア対数リターンから7通貨スコアを算出"),
    ("LOO方式",        "対象ペア自身を除外した強弱を算出（循環参照回避）"),
    ("先行リターン",    "次足Open基準  log(Close[t+h] / Open[t+1]) × 100（%）"),
]:
    pdf.kv(k,v,lw=44)
pdf.ln(3)

pdf.sub("セッション定義（JST）")
ws=[50,40,40,52]
pdf.th(ws,["セッション","開始","終了","特徴"])
for i,(sname,start,end,char) in enumerate([
    ("東京 09-15JST","09:00","15:00","JPYペア主役・押し目買い多発"),
    ("欧州 15-21JST","15:00","21:00","欧州オープン・トレンド転換"),
    ("NY   21-03JST","21:00","03:00","最大流動性・トレンド継続"),
    ("深夜 03-09JST","03:00","09:00","薄商い・ノイズ多い"),
]):
    bg = C_LGRAY if i%2==0 else C_WHITE
    pdf.tr(ws,[sname,start,end,char],bg=bg,
           colors=[SESS_COLORS[i],None,None,None])
pdf.ln(3)

pdf.sub("判定アルゴリズム")
pdf.body("以下の3条件が同時に満たされた場合に「強」判定、Meanのみの場合に「弱」判定:\n"
         "① Mean < 0（SHORT）または > 0（LONG）\n"
         "② Skewness < -0.2（SHORT）または > 0.2（LONG）\n"
         "③ 下落率 > 51%（SHORT）または 上昇率 < 49%（LONG）\n"
         "  ＋ t検定 p値 < 0.15（有意水準）")
pdf.ln(2)

pdf.sub("チャートの見方")
pdf.body("■ セッション別ヒストグラム:\n"
         "  グレー=全ブレイク / カラー=強弱差極大(≤Q10) / KDE曲線=確率密度推定\n"
         "  → カラーの分布が左シフト → SHORT有利 / 右シフト → LONG有利\n\n"
         "■ セッション別期待値棒グラフ:\n"
         "  グレー=全ブレイク / 青=強弱差大(≤Q25) / 赤=強弱差極大(≤Q10)\n"
         "  → 棒が下向き（負）= ショート有利  / 上向き（正）= ロング有利")

# ── p3: 全ペア判定マトリックス ──────────────────────────────
pdf.add_page()
pdf.sec("2  全ペア判定マトリックス（12本後 / 60分後）")

pdf.body("◎=エッジあり（強）　○=弱いエッジ　─=不明　"
         "色: 赤=LONG(逆張り)  青=SHORT(順張り)  灰=不明", c=C_AMBER)
pdf.ln(2)

# マトリックス表
wm=[28,38,38,38,38]
pdf.th(wm,["ペア","東京 09-15","欧州 15-21","NY   21-03","深夜 03-09"],h=7)

for i,row in df_jt.iterrows():
    pair = row["pair"]
    base_c,quote_c = PAIR_CURRENCIES.get(pair,("─","─"))
    bg = C_LGRAY if i%2==0 else C_WHITE
    vals = [f"{pair}\n({base_c}/{quote_c})"]
    cell_colors = [None]
    for sc in SESS_COLS:
        j = str(row.get(f"{sc}_judge","─"))
        fc,tc,short_j = judge_color(j)
        vals.append(short_j)
        cell_colors.append(fc)
    # セル描画（判定色背景）
    pdf.need(8)
    x0,y0 = 14, pdf.get_y()
    pdf.set_fill_color(*bg)
    pdf.rect(x0,y0,sum(wm),8,"F")
    cx=x0
    for wi,(v,c) in enumerate(zip(vals,cell_colors)):
        pdf.set_xy(cx,y0)
        if c: pdf.set_fill_color(*c)
        else: pdf.set_fill_color(*bg)
        pdf.rect(cx,y0,wm[wi],8,"F")
        is_dark = c in [C_LONG,C_SHORT]
        tc2 = C_WHITE if is_dark else C_BLACK
        pdf.set_text_color(*tc2)
        pdf.set_font("YG","B" if wi==0 else "",8)
        pdf.cell(wm[wi],8,v,align="C")
        pdf.set_text_color(*C_BLACK); cx+=wm[wi]
    pdf.set_xy(14,y0+8)

pdf.ln(4)

# サマリー集計
pdf.sub("判定統計（全48セル）")
all_judges=[str(df_jt[f"{sc}_judge"].values[i])
            for sc in SESS_COLS for i in range(len(df_jt))]
n_long_s=sum(1 for j in all_judges if "▲LONG"  in j)
n_long_w=sum(1 for j in all_judges if "△long"  in j)
n_sho_s =sum(1 for j in all_judges if "▼SHORT" in j)
n_sho_w =sum(1 for j in all_judges if "▽short" in j)
n_unk   =sum(1 for j in all_judges if "─" in j)
wk=[46,25,25,25,25,25,25]
pdf.th(wk,["","LONG強","long弱","SHORT強","short弱","不明","合計"],h=6)
pdf.tr(wk,["全48セル",
           f"{n_long_s}",f"{n_long_w}",
           f"{n_sho_s}", f"{n_sho_w}",
           f"{n_unk}",   f"{48}"],
       colors=[None,C_LONG,C_LONG_L,C_SHORT,C_SHORT_L,C_GRAY,None])
pdf.ln(3)
pdf.body(f"LONG系（強+弱）: {n_long_s+n_long_w}セル / "
         f"SHORT系（強+弱）: {n_sho_s+n_sho_w}セル / "
         f"不明: {n_unk}セル\n"
         f"→ LONG方向のエッジが多数（逆張り構造が優位）。\n"
         f"　SHORTは強弱フィルター適用時のみ特定セッションで出現。",c=C_AMBER)

# ── p4-15: 各ペア 1ページ ────────────────────────────────────
for pair_idx,(pair,(base_c,quote_c)) in enumerate(PAIR_CURRENCIES.items()):
    if pair not in df_jt["pair"].values: continue

    pdf.add_page()
    # ペアヘッダー
    pdf.set_fill_color(*C_NAVY); pdf.set_text_color(*C_WHITE)
    pdf.set_font("YG","B",14)
    pdf.set_x(14)
    pdf.cell(140,10,f"  {pair}  （{base_c} / {quote_c}）",fill=True)
    # 全体判定バッジ
    row = df_jt[df_jt["pair"]==pair].iloc[0]
    judges=[str(row.get(f"{sc}_judge","─")) for sc in SESS_COLS]
    n_long=sum(1 for j in judges if "LONG" in j or "long" in j)
    n_short=sum(1 for j in judges if "SHORT" in j or "short" in j)
    if n_long > n_short:
        badge_bg, badge_txt = C_LONG, "逆張り優位"
    elif n_short > n_long:
        badge_bg, badge_txt = C_SHORT, "順張り優位"
    else:
        badge_bg, badge_txt = C_GRAY, "混在"
    pdf.set_fill_color(*badge_bg)
    pdf.cell(42,10,f"  {badge_txt}",fill=True,align="C")
    pdf.ln(); pdf.set_text_color(*C_BLACK); pdf.ln(2)

    # セッション別判定テーブル
    wt=[40,24,18,18,82]
    pdf.th(wt,["セッション","判定","Mean%","Skew","コメント"],h=6)
    comments={
        "東京 09-15": {"▲LONG":"東京の押し目買いが反発を生む","△long（弱）":"弱い反発傾向",
                     "▼SHORT":"東京下落継続","─":"明確な傾向なし"},
        "欧州 15-21": {"▲LONG":"欧州オープンで反転","△long（弱）":"弱い反発傾向",
                     "▼SHORT":"欧州でトレンド継続","─":"明確な傾向なし"},
        "NY   21-03": {"▲LONG":"NY反発","△long（弱）":"弱い反発傾向",
                     "▼SHORT":"NYでモメンタム継続","─":"明確な傾向なし"},
        "深夜 03-09": {"▲LONG":"薄商いで反発","△long（弱）":"弱い反発傾向",
                     "▼SHORT":"深夜下落継続","─":"明確な傾向なし"},
    }
    for si,(sc,sname_full,scolor) in enumerate(zip(
        SESS_COLS,
        ["東京 09-15JST","欧州 15-21JST","NY 21-03JST","深夜 03-09JST"],
        SESS_COLORS
    )):
        j   = str(row.get(f"{sc}_judge","─"))
        m   = row.get(f"{sc}_mean",0)
        sk  = row.get(f"{sc}_skew",0)
        fc,tc,short_j = judge_color(j)
        # コメント検索
        sc_key = sc.strip()
        for ck in comments:
            if ck.replace(" ","") in sc_key.replace(" ",""):
                cmt = comments[ck].get(j, comments[ck].get("─","─"))
                break
        else: cmt="─"
        bg = C_LGRAY if si%2==0 else C_WHITE
        pdf.need(6)
        x0,y0=14,pdf.get_y()
        pdf.set_fill_color(*bg); pdf.rect(x0,y0,sum(wt),6,"F")
        cx=x0
        # セッション名
        pdf.set_xy(cx,y0); pdf.set_text_color(*scolor)
        pdf.set_font("YG","B",7.5); pdf.cell(wt[0],6,sname_full,align="C")
        pdf.set_text_color(*C_BLACK); cx+=wt[0]
        # 判定（背景色）
        pdf.set_xy(cx,y0); pdf.set_fill_color(*fc)
        pdf.rect(cx,y0,wt[1],6,"F")
        pdf.set_text_color(*tc); pdf.set_font("YG","B",7.5)
        pdf.cell(wt[1],6,short_j,align="C"); cx+=wt[1]
        pdf.set_text_color(*C_BLACK)
        # Mean%
        pdf.set_xy(cx,y0); pdf.set_font("YG","",7.5)
        mc = C_GREEN if m>=0 else C_RED
        pdf.set_text_color(*mc)
        pdf.cell(wt[2],6,f"{m:+.4f}",align="C"); cx+=wt[2]
        pdf.set_text_color(*C_BLACK)
        # Skew
        pdf.set_xy(cx,y0)
        sc2 = C_RED if sk<-0.2 else C_GREEN if sk>0.2 else C_BLACK
        pdf.set_text_color(*sc2)
        pdf.cell(wt[3],6,f"{sk:+.2f}",align="C"); cx+=wt[3]
        pdf.set_text_color(*C_BLACK)
        # コメント
        pdf.set_xy(cx,y0); pdf.set_font("YG","",7.5)
        pdf.cell(wt[4],6,cmt,align="L"); cx+=wt[4]
        pdf.set_xy(14,y0+6)
    pdf.ln(3)

    # ── ヒストグラム ─────────────────────────────────────────
    hist_path = CHART_DIR / f"{pair}_session_hist.png"
    mean_path = CHART_DIR / f"{pair}_session_mean.png"

    # 残りスペースを計算して画像サイズを調整
    remaining = pdf._lim - pdf.get_y()
    hist_h = img_height(hist_path, 182)
    mean_h = img_height(mean_path, 182)
    total_img_h = hist_h + mean_h + 8

    if total_img_h > remaining:
        # スケールダウン
        scale = remaining / total_img_h * 0.95
        w_use = 182 * scale
    else:
        w_use = 182

    pdf.img(hist_path, w=w_use,
            note="■ セッション別リターン分布（グレー=全ブレイク / カラー=強弱差極大Q10）")
    pdf.img(mean_path, w=w_use,
            note="■ 先行ホライゾン別期待値（グレー=全ブレイク / 青=Q25 / 赤=Q10）")

# ── 最終ページ: 総括 ─────────────────────────────────────────
pdf.add_page()
pdf.sec("3  総括・戦略活用ガイドライン")

pdf.sub("全ペア共通の発見")
findings=[
    "1. LONGエッジが全体的に優位: 48セル中、LONG系が多数。ブレイクダウン後の反発（押し目買い）は普遍的な市場構造。",
    "2. 欧州時間でJPYペアのLONGが特に強力: USDJPY・AUDJPY・NZDJPY・CHFJPYで ▲LONG判定。欧州オープンによる東京安値の消化が主因と考えられる。",
    "3. SHORTエッジは強弱フィルター適用後に出現: フィルターなしのブレイクでは全体的にLONG有利。強弱差Q10という絞り込みでSHORT方向が浮かび上がる。",
    "4. 深夜時間帯（03-09JST）は薄商い: n数が少なく統計的信頼性低下。エッジ不明が多い。",
    "5. 超過尖度が高い（ファットテール）: 強弱差が大きい条件下で尖度が低下し、よりガウス分布に近づく。予測可能性が向上するシグナル。",
]
for f in findings:
    pdf.set_font("YG","",8.5); pdf.set_x(14); pdf.multi_cell(182,5.5,f)
    pdf.ln(1)

pdf.ln(2)
pdf.sub("戦略活用の優先順位")
ws3=[8,40,60,74]
pdf.th(ws3,["優先","ペア","時間帯・判定","活用方針"],h=6)
recs=[
    ("★★★","USDJPY / AUDJPY","欧州 ▲LONG強","強弱差Q10 + BreakDown → 逆張りLONG"),
    ("★★★","NZDJPY / CHFJPY","欧州 ▲LONG強","同上"),
    ("★★☆","GBPUSD / AUDUSD","東京 ▲LONG強","USD系クロスの東京押し目ロング"),
    ("★★☆","EURGBP / AUDNZD","深夜 ▲LONG強","クロス円以外の深夜反発狙い"),
    ("★☆☆","USDJPY","NY ▲Short（強弱フィルター付き）","Q10 + BreakDown → 順張りSHORT"),
    ("─","NZDUSD","全時間帯 ─","明確エッジなし → 除外推奨"),
]
for i,r in enumerate(recs):
    bg = C_LGRAY if i%2==0 else C_WHITE
    fc = C_LONG if "LONG" in r[2] else C_SHORT if "Short" in r[2] else C_GRAY
    pdf.tr(ws3,list(r),bg=bg,colors=[None,None,fc,None])

pdf.ln(4)
pdf.sub("次のステップ", bg=C_NAVY)
steps=[
    ("Step 1 完了","12ペア × 4セッション 統計解析・分布分析"),
    ("Step 2 完了","セッション別リターン分布・期待値チャート作成"),
    ("Step 3 次",  "全ペアにデュアル戦略（LONG/SHORT）を展開 → IS期間検証"),
    ("Step 4",     "ロバストネス確認 → 上位ペア選定"),
    ("Step 5",     "統合マルチペアシステム構築（週次ランキング含む）"),
]
for i,(s,d) in enumerate(steps):
    pdf.need(6.5)
    x0,y0=14,pdf.get_y()
    pdf.set_fill_color(*(C_STRIPE if i%2==0 else C_WHITE))
    pdf.rect(x0,y0,182,6.5,"F")
    pdf.set_xy(x0,y0); pdf.set_font("YG","B",8.5); pdf.cell(38,6.5,s)
    pdf.set_font("YG","",8.5); pdf.cell(144,6.5,d,new_x=XPos.LMARGIN,new_y=YPos.NEXT)

pdf.ln(5)
pdf.set_font("YG","",7); pdf.set_text_color(*C_GRAY)
pdf.set_x(14); pdf.multi_cell(182,4.5,
    f"作成日: {date.today().strftime('%Y年%m月%d日')}  /  "
    "12通貨ペア × 時間帯別戦略分析  v1.0  /  "
    "データ: Dukascopy 5分足 2022-2024  /  スプレッド・スリッページ未考慮")

pdf.output(str(OUT_PATH))
print(f"PDF生成完了: {OUT_PATH}")
print(f"ページ数: {pdf.page}")
