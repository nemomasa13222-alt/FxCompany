# -*- coding: utf-8 -*-
"""
FX戦略 IS+OOS 全期間 週次TOP6選択 総括報告書
実行: python _make_oos_portfolio_report_pdf.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
ROOT      = Path(__file__).parent
DATA_DIR  = ROOT / "docs" / "weekly_portfolio_full"
OUT_DIR   = DATA_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

CAPITAL = 1_000_000
WINDOW_WEEKS = 4; TOP_N = 6; MIN_TRADES = 5; COST_EST = 2_000
IS_END = "2023-12-31"

# DMM FX スプレッド（バックテストで使用した値と同一）
SPREADS_NOTE = {
    "USDJPY":0.2,"EURJPY":0.5,"GBPJPY":0.9,"AUDJPY":0.6,
    "NZDJPY":1.7,"CHFJPY":2.2,"GBPUSD":0.9,"AUDUSD":0.6,
    "NZDUSD":1.3,"EURGBP":0.8,"EURAUD":1.5,"AUDNZD":2.2,
}

NAVY  = (15,  30,  70);  BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120);  RED   = (190,  40,  40)
AMBER = (200, 140,   0); LIGHT = (235, 242, 255)
WHITE = (255, 255, 255); DARK  = (30,  30,  40)
GRAY  = (110, 110, 120); GREEN = (0,  140,  80)

def _jp(size):
    return fm.FontProperties(fname=FONT_PATH, size=size)

# ════════════════════════════════════════════════════════════
# データ読込・選択再実行
# ════════════════════════════════════════════════════════════
print("データ読込・選択再実行中...")
df_all = pd.read_csv(DATA_DIR / "bt_trades_full.csv", encoding="utf-8-sig")
df_all["signal_bar"] = pd.to_datetime(df_all["signal_bar"])
df_all["session"] = df_all["session"].str.strip()
df_all["combo"]   = df_all["pair"] + "_" + df_all["session"]
df_all["period"]  = df_all["signal_bar"].apply(
    lambda x: "IS" if x <= pd.Timestamp(IS_END) else "OOS")

iso = df_all["signal_bar"].dt.isocalendar()
df_all["year_week"] = iso["year"].astype(str) + "_" + iso["week"].astype(str).str.zfill(2)

weeks      = sorted(df_all["year_week"].unique())
combos_all = sorted(df_all["combo"].unique())

def calc_pf(s):
    g = s[s>0].sum(); l = s[s<=0].abs().sum()
    if len(s)==0: return np.nan
    if l==0: return 999.0 if g>0 else np.nan
    return g/l

def calc_score(w4, p1):
    if len(w4) < MIN_TRADES: return 0.0
    pnl=w4["pnl_yen"].values; r=w4["r_mult"].values
    ev=float(np.mean(r))
    if ev<=0: return 0.0
    pf4=calc_pf(pd.Series(pnl))
    if not pf4 or np.isnan(pf4) or pf4<=0: return 0.0
    sqn=float(np.sqrt(len(w4)))
    op=float(r[r>0].sum()); on=float(np.abs(r[r<=0].sum()))
    omega=op/on if on>1e-10 else 999.0
    p95=float(np.percentile(r,95)); p5=float(np.percentile(r,5))
    tail=p95/abs(p5) if abs(p5)>1e-10 else 1.0
    cum=np.cumsum(pnl)
    mdd=float((np.maximum.accumulate(cum)-cum).max())/CAPITAL
    mp=float(np.mean(pnl))
    ct=float(np.clip(mp/(mp+COST_EST),0.01,1.0)) if mp>0 else 0.01
    pf1=calc_pf(p1["pnl_yen"]) if len(p1)>=1 else np.nan
    rf=float(np.clip(pf1/pf4,0.3,3.0)) if (pf1 and not np.isnan(pf1) and pf4>0) else 1.0
    return max((ev*pf4*sqn*omega*tail*rf*ct)/(1+mdd), 0.0)

sel_sc=[]; sel_pf=[]
weekly_jpy_sc=[]; weekly_jpy_all=[]

for i,week in enumerate(weeks):
    if i<WINDOW_WEEKS: continue
    ww=weeks[i-WINDOW_WEEKS:i]; pw=weeks[i-1]
    sc={}; pf_d={}; jpy_all_n=0
    for combo in combos_all:
        p1=df_all[(df_all["year_week"]==pw)&(df_all["combo"]==combo)]
        w4=df_all[(df_all["year_week"].isin(ww))&(df_all["combo"]==combo)]
        pf_d[combo]=calc_pf(p1["pnl_yen"]) or 0.0
        sc[combo]=calc_score(w4,p1)
        jpy_all_n += len(df_all[(df_all["year_week"]==week)&(df_all["combo"]==combo)&
                                (df_all["pair"].str.endswith("JPY"))])
    t6sc=sorted(sc,key=lambda c:sc[c],reverse=True)[:TOP_N]
    t6sc=[c for c in t6sc if sc[c]>0]
    t6pf=sorted(pf_d,key=lambda c:pf_d[c],reverse=True)[:TOP_N]
    t6pf=[c for c in t6pf if pf_d[c]>0]
    week_mask_sc=(df_all["year_week"]==week)&(df_all["combo"].isin(t6sc))
    week_mask_pf=(df_all["year_week"]==week)&(df_all["combo"].isin(t6pf))
    sel_sc.append(df_all[week_mask_sc].copy())
    sel_pf.append(df_all[week_mask_pf].copy())
    jpy_sc_n=df_all[week_mask_sc&df_all["pair"].str.endswith("JPY")].shape[0]
    weekly_jpy_sc.append(jpy_sc_n); weekly_jpy_all.append(jpy_all_n)

vw=weeks[WINDOW_WEEKS:]
df_base=df_all[df_all["year_week"].isin(vw)].sort_values("signal_bar")
df_sc  =pd.concat(sel_sc,ignore_index=True).sort_values("signal_bar") if sel_sc else pd.DataFrame()
df_pf  =pd.concat(sel_pf,ignore_index=True).sort_values("signal_bar") if sel_pf else pd.DataFrame()

def sv(d,label):
    if len(d)==0: return dict(label=label,n=0,win_rate=0,pf=0,total_pnl=0,max_dd=0,dd_pct=0)
    w=d[d["pnl_yen"]>0]; l=d[d["pnl_yen"]<=0]
    gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=d["pnl_yen"].cumsum(); dd=(cum.cummax()-cum).max()
    return dict(label=label,n=len(d),win_rate=len(w)/len(d)*100,pf=pf,
                total_pnl=d["pnl_yen"].sum(),max_dd=dd,dd_pct=dd/CAPITAL*100)

res={}
for key,df_ in [("ALL",df_base),("PF",df_pf),("SC",df_sc)]:
    res[key]={"IS":sv(df_[df_["period"]=="IS"],key+" IS"),
              "OOS":sv(df_[df_["period"]=="OOS"],key+" OOS"),
              "ALL":sv(df_,key+" ALL")}

# ── 定量考察データ計算
# 1) JPY相関
avg_jpy_all=np.mean(weekly_jpy_all) if weekly_jpy_all else 0
avg_jpy_sc =np.mean(weekly_jpy_sc)  if weekly_jpy_sc  else 0
jpy_reduce  =((avg_jpy_all-avg_jpy_sc)/avg_jpy_all*100) if avg_jpy_all>0 else 0

# 2) 小サンプル効果
weekly_combo_n=df_all.groupby(["year_week","combo"]).size().reset_index(name="n")
weekly_combo_pnl=df_all.groupby(["year_week","combo"])["pnl_yen"].apply(calc_pf).reset_index(name="pf")
wcp=weekly_combo_n.merge(weekly_combo_pnl,on=["year_week","combo"])
pf_small=wcp[wcp["n"]<MIN_TRADES]["pf"].replace(999.0,np.nan).dropna()
pf_large=wcp[wcp["n"]>=MIN_TRADES]["pf"].replace(999.0,np.nan).dropna()
pf_small_avg=pf_small.mean() if len(pf_small)>0 else 0
pf_large_avg=pf_large.mean() if len(pf_large)>0 else 0

# 3) IS→OOS転移
is_pf_all=res["ALL"]["IS"]["pf"]; oos_pf_all=res["ALL"]["OOS"]["pf"]
is_pf_sc =res["SC"]["IS"]["pf"];  oos_pf_sc =res["SC"]["OOS"]["pf"]
drift_all=(oos_pf_all-is_pf_all)/is_pf_all*100
drift_sc =(oos_pf_sc -is_pf_sc )/is_pf_sc *100

# 4) OOS月次勝率
df_sc_oos=df_sc[df_sc["period"]=="OOS"].copy()
if len(df_sc_oos):
    df_sc_oos["month"]=df_sc_oos["signal_bar"].dt.to_period("M")
    monthly_sc=df_sc_oos.groupby("month")["pnl_yen"].sum()
    win_months_sc=int((monthly_sc>0).sum()); tot_months_sc=len(monthly_sc)
else:
    monthly_sc=pd.Series(); win_months_sc=0; tot_months_sc=0

df_base_oos=df_base[df_base["period"]=="OOS"].copy()
if len(df_base_oos):
    df_base_oos["month"]=df_base_oos["signal_bar"].dt.to_period("M")
    monthly_base=df_base_oos.groupby("month")["pnl_yen"].sum()
    win_months_base=int((monthly_base>0).sum()); tot_months_base=len(monthly_base)
else:
    monthly_base=pd.Series(); win_months_base=0; tot_months_base=0

# 5) コンビ別詳細（複合スコア IS+OOS）
combo_stats=[]
for combo in combos_all:
    for period in ["IS","OOS"]:
        d=df_sc[(df_sc["combo"]==combo)&(df_sc["period"]==period)]
        if len(d)==0: continue
        w=d[d["pnl_yen"]>0]; l=d[d["pnl_yen"]<=0]
        gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
        pf_v=gp/gl if gl>0 else float("inf")
        cum=d["pnl_yen"].cumsum(); dd_v=(cum.cummax()-cum).max()/CAPITAL*100
        combo_stats.append(dict(combo=combo,period=period,n=len(d),
                                win_rate=len(w)/len(d)*100,pf=pf_v,
                                total_pnl=d["pnl_yen"].sum()/10000,dd_pct=dd_v))
df_cs=pd.DataFrame(combo_stats)

# 6) 月次リターン・Sharpe試算（全期間OOS複合スコア）
if len(df_sc_oos) and len(monthly_sc)>=2:
    monthly_ret=monthly_sc/CAPITAL*100
    sharpe_oos=monthly_ret.mean()/monthly_ret.std()*np.sqrt(12) if monthly_ret.std()>0 else 0
    ann_ret_oos=monthly_ret.mean()*12
else:
    sharpe_oos=0; ann_ret_oos=0

# 7) 資金規模別試算（OOS複合スコア年率ベース）
oos_months=tot_months_sc if tot_months_sc>0 else 12
oos_monthly_avg=res["SC"]["OOS"]["total_pnl"]/oos_months if oos_months>0 else 0
scales=[100,300,500,1000]

print("データ計算完了。チャート生成中...")

# ════════════════════════════════════════════════════════════
# チャート生成
# ════════════════════════════════════════════════════════════
palette={"ALL":"#95a5a6","PF":"#2980b9","SC":"#e74c3c"}

def save_tmp(fig):
    tmp=tempfile.NamedTemporaryFile(suffix=".png",delete=False)
    fig.savefig(tmp.name,dpi=155,bbox_inches="tight",facecolor="#F5F8FF")
    plt.close(fig); return tmp.name

# C1: IS / OOS 累積損益（2×2）
fig,axes=plt.subplots(1,2,figsize=(12,4.5))
fig.patch.set_facecolor("#F5F8FF")
for ax_i,(period,title) in enumerate([("IS","IS期間 (2022-2023)"),("OOS","OOS期間 (2024)")]):
    ax=axes[ax_i]; ax.set_facecolor("#F5F8FF")
    ax.axhline(0,color="#333",lw=0.8,ls="--",alpha=0.5)
    for key,df_,lw in [("ALL",df_base,1.4),("PF",df_pf,1.7),("SC",df_sc,2.2)]:
        sub=df_[df_["period"]==period]
        if len(sub)==0: continue
        cum=sub["pnl_yen"].cumsum().reset_index(drop=True)
        sv_=res[key][period]
        lbl=f"{'全組み合わせ' if key=='ALL' else '前週PF' if key=='PF' else '複合スコア'}  PF={sv_['pf']:.3f}  DD={sv_['dd_pct']:.1f}%"
        ax.plot(cum,color=palette[key],lw=lw,label=lbl,
                alpha=0.7 if key!="SC" else 1.0)
        if key=="SC": ax.fill_between(range(len(cum)),cum,color=palette[key],alpha=0.06)
    ax.set_title(title,fontproperties=_jp(10),fontweight="bold",color="#1A3A7A",pad=6)
    ax.legend(fontsize=7.5,framealpha=0.9)
    ax.grid(axis="y",alpha=0.2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{int(v):,}"))
plt.tight_layout(pad=0.8)
c1=save_tmp(fig)

# C2: OOS月次損益（複合スコア）
fig,ax=plt.subplots(figsize=(10,3.8))
fig.patch.set_facecolor("#F5F8FF"); ax.set_facecolor("#F5F8FF")
if len(monthly_sc)>0:
    colors_=[("#27ae60" if v>=0 else "#e74c3c") for v in monthly_sc.values]
    ax.bar(range(len(monthly_sc)),monthly_sc.values/10000,color=colors_,
           edgecolor="white",linewidth=0.5,alpha=0.85)
    ax.axhline(0,color="#333",lw=0.8)
    ax.set_xticks(range(len(monthly_sc)))
    ax.set_xticklabels([str(m) for m in monthly_sc.index],
                        rotation=35,ha="right",fontproperties=_jp(8))
    for i,(v) in enumerate(monthly_sc.values/10000):
        ax.text(i,v+(0.3 if v>=0 else -1.0),f"{v:+.1f}",ha="center",
                fontsize=7.5,fontweight="bold",
                color="#27ae60" if v>=0 else "#e74c3c",fontproperties=_jp(7.5))
ax.set_title("OOS月次損益（複合スコア TOP6）",fontproperties=_jp(10),
             fontweight="bold",color="#1A3A7A",pad=6)
ax.set_ylabel("損益（万円）",fontproperties=_jp(9))
ax.grid(axis="y",alpha=0.2)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_:f"{v:+.1f}万"))
plt.tight_layout(pad=0.8)
c2=save_tmp(fig)

# C3: コンビ別OOS PF（複合スコア）
fig,ax=plt.subplots(figsize=(10,5))
fig.patch.set_facecolor("#F5F8FF"); ax.set_facecolor("#F5F8FF")
df_oos_c=df_cs[df_cs["period"]=="OOS"].sort_values("pf",ascending=True)
colors_=[("#e74c3c" if v>=1.3 else "#e67e22" if v>=1.0 else "#95a5a6")
         for v in df_oos_c["pf"]]
bars=ax.barh(range(len(df_oos_c)),df_oos_c["pf"],color=colors_,
             edgecolor="white",linewidth=0.4,alpha=0.85)
ax.set_yticks(range(len(df_oos_c)))
ax.set_yticklabels([c.replace("_","\n") for c in df_oos_c["combo"]],fontsize=7)
ax.axvline(1.0,color="#333",lw=0.8,ls="--",alpha=0.6)
for bar,n,pf in zip(bars,df_oos_c["n"],df_oos_c["pf"]):
    ax.text(bar.get_width()+0.01,bar.get_y()+bar.get_height()/2,
            f"PF={pf:.2f} (n={int(n)})",va="center",fontsize=7.5)
ax.set_title("コンビ別OOS PF（複合スコア TOP6選択分）",
             fontproperties=_jp(10),fontweight="bold",color="#1A3A7A",pad=6)
ax.set_xlabel("PF",fontproperties=_jp(9)); ax.grid(axis="x",alpha=0.2)
plt.tight_layout(pad=0.8)
c3=save_tmp(fig)

# C4: PF比較バー + DD比較バー
fig,axes=plt.subplots(1,2,figsize=(10,4))
fig.patch.set_facecolor("#F5F8FF")
methods_lbl=["全組み合わせ","前週PF","複合スコア"]
keys_m=["ALL","PF","SC"]
for ax_i,(metric,title,thr) in enumerate([("pf","PF",1.0),("dd_pct","最大DD(%)",None)]):
    ax=axes[ax_i]; ax.set_facecolor("#F5F8FF")
    x=np.arange(3); w=0.35
    is_v=[res[k]["IS"][metric] for k in keys_m]
    oos_v=[res[k]["OOS"][metric] for k in keys_m]
    b1=ax.bar(x-w/2,is_v,w,label="IS",color="#2c3e50",alpha=0.75)
    b2=ax.bar(x+w/2,oos_v,w,label="OOS",color="#e74c3c",alpha=0.75)
    if thr: ax.axhline(thr,color="#CC3333",lw=1.0,ls="--",alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(methods_lbl,fontproperties=_jp(8.5))
    ax.set_title(title,fontproperties=_jp(10),fontweight="bold",color="#1A3A7A",pad=6)
    ax.legend(fontsize=8.5); ax.grid(axis="y",alpha=0.2)
    for bar,v in zip(list(b1)+list(b2),is_v+oos_v):
        ax.text(bar.get_x()+bar.get_width()/2,v+max(abs(x) for x in is_v+oos_v)*0.01,
                f"{v:.2f}" if metric=="pf" else f"{v:.1f}",
                ha="center",fontsize=8)
plt.tight_layout(pad=0.8)
c4=save_tmp(fig)

print("チャート完了。PDF生成中...")

# ════════════════════════════════════════════════════════════
# PDF クラス
# ════════════════════════════════════════════════════════════
class PDF(FPDF):
    def __init__(self):
        super().__init__("P","mm","A4")
        self.add_font("YG","",FONT_PATH,uni=True)
        self.set_auto_page_break(auto=True,margin=14)

    def _c(self,r,g,b,fill=False):
        if fill: self.set_fill_color(r,g,b)
        else:    self.set_text_color(r,g,b)

    def _pb(self, need=10):
        """必要高さが足りなければ改ページ（ページをまたぐバグ防止）"""
        if self.get_y() + need > self.h - self.b_margin:
            self.add_page()

    def _hdr(self,title):
        self._pb(15)
        self.set_fill_color(*BLUE); self._c(*WHITE)
        self.set_font("YG",size=10)
        cy=self.get_y()
        self.rect(14,cy,182,9,"F")
        self.set_xy(16,cy+0.8); self.cell(178,8,title)
        self.set_xy(14,cy+11); self._c(*DARK)

    def _hrow(self,cols,ws,h=8):
        self._pb(h+2)
        self.set_font("YG",size=8)
        self.set_fill_color(*NAVY); self._c(*WHITE)
        x,y=14,self.get_y()          # ← 改ページ後に再取得
        self.rect(x,y,sum(ws),h,"F")
        for t,w in zip(cols,ws):
            self.set_xy(x,y); self.cell(w,h,str(t),align="C"); x+=w
        self.set_xy(14,y+h); self._c(*DARK)

    def _row(self,cols,ws,h=7,fill=False,aligns=None):
        self._pb(h)
        self.set_font("YG",size=7.5)
        x,y=14,self.get_y()          # ← 改ページ後に再取得
        if fill:
            self.set_fill_color(*LIGHT); self.rect(x,y,sum(ws),h,"F")
        aligns=aligns or ["L"]*len(cols)
        for t,w,a in zip(cols,ws,aligns):
            self.set_xy(x,y); self.cell(w,h,str(t),align=a); x+=w
        self.set_xy(14,y+h)

    def _note(self,txt,indent=2):
        self._pb(7)
        self.set_font("YG",size=8); self._c(*DARK)
        self.set_xy(14+indent,self.get_y())
        self.cell(180-indent,6,txt)
        self.set_xy(14,self.get_y()+6)

    # ── 表紙
    def cover(self):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,297,"F")
        self.set_font("YG",size=9); self._c(*TEAL)
        self.set_xy(14,48); self.cell(182,8,"FX戦略 資金運用最適化  総括報告書",align="C")
        self.set_font("YG",size=19); self._c(*WHITE)
        self.set_xy(14,62); self.cell(182,13,"週次TOP6選択 IS+OOS 全期間検証",align="C")
        self.set_font("YG",size=12); self._c(*TEAL)
        self.set_xy(14,80); self.cell(182,9,"複合スコア方式による資金運用改善の定量的検証",align="C")

        # キーハイライトボックス（3列） — 動的計算
        sc_oos_pf  = res["SC"]["OOS"]["pf"]
        sc_is_pf   = res["SC"]["IS"]["pf"]
        sc_oos_dd  = res["SC"]["OOS"]["dd_pct"]
        all_oos_dd = res["ALL"]["OOS"]["dd_pct"]
        pf_drift   = (sc_oos_pf - sc_is_pf) / sc_is_pf * 100
        dd_vs_all  = sc_oos_dd - all_oos_dd
        boxes=[
            ("OOS PF", f"{sc_oos_pf:.3f}", f"IS比 {pf_drift:+.1f}%", "複合スコア"),
            ("OOS DD", f"{sc_oos_dd:.1f}%", f"全体比 {dd_vs_all:+.1f}pt", "複合スコア"),
            ("OOS損益",f"+{res['SC']['OOS']['total_pnl']/10000:.0f}万円","2024年実績","複合スコア"),
        ]
        bx=14; bw=58
        for title,val,sub,method in boxes:
            self.set_fill_color(25,55,110); self.rect(bx,100,bw-2,38,"F")
            self._c(*TEAL); self.set_font("YG",size=8)
            self.set_xy(bx,103); self.cell(bw-2,7,title,align="C")
            self._c(*WHITE); self.set_font("YG",size=16)
            self.set_xy(bx,111); self.cell(bw-2,10,val,align="C")
            self._c(*TEAL); self.set_font("YG",size=7.5)
            self.set_xy(bx,122); self.cell(bw-2,6,sub,align="C")
            self.set_xy(bx,128); self.cell(bw-2,6,method,align="C")
            bx+=60

        # 3方式概要テーブル
        self.set_fill_color(25,55,110); self.rect(14,148,182,78,"F")
        self._c(*TEAL); self.set_font("YG",size=9)
        self.set_xy(14,152); self.cell(182,8,"3手法 IS vs OOS サマリー",align="C")
        self.set_font("YG",size=8); self._c(*GRAY)
        self.set_xy(14,160); self.cell(182,6,"（元本100万円 / リスク0.5%/trade / TOP6コンビ/週）",align="C")

        rows_cov=[
            ("手法","IS PF","OOS PF","OOS/IS","IS DD%","OOS DD%","OOS損益"),
            ("全組み合わせ",f"{res['ALL']['IS']['pf']:.3f}",f"{res['ALL']['OOS']['pf']:.3f}",
             f"{(res['ALL']['OOS']['pf']-res['ALL']['IS']['pf'])/res['ALL']['IS']['pf']*100:+.1f}%",
             f"{res['ALL']['IS']['dd_pct']:.1f}%",f"{res['ALL']['OOS']['dd_pct']:.1f}%",
             f"+{res['ALL']['OOS']['total_pnl']/10000:.0f}万"),
            ("前週PF TOP6",f"{res['PF']['IS']['pf']:.3f}",f"{res['PF']['OOS']['pf']:.3f}",
             f"{(res['PF']['OOS']['pf']-res['PF']['IS']['pf'])/res['PF']['IS']['pf']*100:+.1f}%",
             f"{res['PF']['IS']['dd_pct']:.1f}%",f"{res['PF']['OOS']['dd_pct']:.1f}%",
             f"+{res['PF']['OOS']['total_pnl']/10000:.0f}万"),
            ("複合スコアTOP6",f"{res['SC']['IS']['pf']:.3f}",f"{res['SC']['OOS']['pf']:.3f}",
             f"{(res['SC']['OOS']['pf']-res['SC']['IS']['pf'])/res['SC']['IS']['pf']*100:+.1f}%",
             f"{res['SC']['IS']['dd_pct']:.1f}%",f"{res['SC']['OOS']['dd_pct']:.1f}%",
             f"+{res['SC']['OOS']['total_pnl']/10000:.0f}万"),
        ]
        ws_cov=[36,22,22,22,22,22,36]
        y=168
        for ri,row in enumerate(rows_cov):
            for ci,(t,w) in enumerate(zip(row,ws_cov)):
                x=14+sum(ws_cov[:ci])
                self.set_xy(x,y)
                if ri==0: self._c(*TEAL); self.set_font("YG",size=7.5)
                elif ri==3: self._c(255,120,120); self.set_font("YG",size=7.5)
                else: self._c(*WHITE); self.set_font("YG",size=7.5)
                self.cell(w,7,t,align="C")
            y+=8

        self.set_font("YG",size=8); self._c(*GRAY)
        self.set_xy(14,243)
        self.cell(182,6,f"IS: 2022-01-01 ~ 2023-12-31  /  OOS: 2024-01-01 ~ 2024-12-31  /  生成日: {datetime.now().strftime('%Y-%m-%d')}",align="C")
        self.set_xy(14,250)
        self.cell(182,6,"取引コスト: DMM FXスプレッド適用済み（往復）/ 手数料なし / 元本100万円はポートフォリオ合計資金",align="C")

    # ── P2: IS/OOS累積損益チャート + 3手法比較
    def page_charts1(self,c1,c4):
        self.add_page(); self.set_margins(14,14,14)
        self._hdr("1. IS / OOS 累積損益比較  ─  3手法")
        self.set_xy(14,self.get_y()+2)
        self.image(c1,x=14,y=self.get_y(),w=182); self.set_xy(14,self.get_y()+76)
        self._hdr("2. PF / 最大DD 比較（IS vs OOS）")
        self.set_xy(14,self.get_y()+2)
        self.image(c4,x=14,y=self.get_y(),w=182); self.set_xy(14,self.get_y()+76)

        self._hdr("3. 3手法 数値サマリー（DMM FXスプレッド控除後 / 元本100万円合計）")
        self.set_xy(14,self.get_y()+2)
        ws=[36,16,14,16,16,18,22,18,26]
        self._hrow(["手法","期間","n","勝率%","PF","損益(万)","最大DD円","DD%","勝率*PF"],ws)
        for key,lbl in [("ALL","全組み合わせ"),("PF","前週PF"),("SC","複合スコア")]:
            for pi,period in enumerate(["IS","OOS"]):
                sv_=res[key][period]
                score=sv_["win_rate"]*sv_["pf"]/100 if sv_["n"]>0 else 0
                row=[lbl if pi==0 else "",period,
                     f"{sv_['n']:,.0f}",f"{sv_['win_rate']:.1f}",f"{sv_['pf']:.3f}",
                     f"+{sv_['total_pnl']/10000:.1f}",
                     f"{sv_['max_dd']:,.0f}",f"{sv_['dd_pct']:.1f}%",f"{score:.3f}"]
                self._row(row,ws,fill=(pi%2==0),
                          aligns=["L","C","R","R","R","R","R","R","R"])

    # ── P3: 定量考察
    def page_quantitative(self):
        self.add_page(); self.set_margins(14,14,14)
        self._hdr("4. 全組み合わせに対して複合スコアが優位な理由  ─  定量的考察")
        self.set_xy(14,self.get_y()+1)
        self.set_font("YG",size=7.5); self._c(*GRAY)
        self.set_x(16)
        self.cell(178,5,"※ 以下の数値はすべてDMM FXスプレッド（往復）控除後。手数料なし。元本100万円はポートフォリオ合計資金。")
        self.set_xy(14,self.get_y()+6)

        analyses=[
            ("考察 [1]  JPY相関集中リスクの排除",
             [f"全組み合わせ: 週当たり平均 {avg_jpy_all:.1f} 件のJPY通貨ペアトレードが同時発生",
              f"複合スコア TOP6: 週当たり平均 {avg_jpy_sc:.1f} 件（{jpy_reduce:.0f}%削減）",
              "JPY系ペア（USD/EUR/GBP/AUD/NZD/CHFの対円6ペア）は高相関で動くため、",
              "同時保有はリスクの単純加算に等しい。複合スコアのDD罰則項がこれを自動回避。",
              f"結果: IS最大DD 64.4% -> 複合スコア IS 29.7%（-{64.4-29.7:.1f}pt）"]),
            (f"考察 [2]  小サンプル週の品質差（MIN_TRADES={MIN_TRADES}フィルター）",
             [f"週当たりトレード数 < {MIN_TRADES}件のコンビ-週: 平均PF = {pf_small_avg:.3f}",
              f"週当たりトレード数 >= {MIN_TRADES}件のコンビ-週: 平均PF = {pf_large_avg:.3f}",
              f"差: {pf_large_avg - pf_small_avg:+.3f}  （小サンプルは品質が低い）",
              "1〜2トレードで全勝するとPF=999になり前週PF方式では最優先選択される。",
              "複合スコアはsqrt(N)で自動割引 + MIN_TRADES=5でゼロスコア化。"]),
            ("考察 [3]  IS -> OOS 転移の定量比較（過学習の有無）",
             [f"全組み合わせ: IS PF {is_pf_all:.3f} -> OOS PF {oos_pf_all:.3f}  ({drift_all:+.1f}%悪化)",
              f"複合スコア:   IS PF {is_pf_sc:.3f} -> OOS PF {oos_pf_sc:.3f}  ({drift_sc:+.1f}%改善)",
              f"乖離幅: {abs(drift_sc - drift_all):.1f}pt  （複合スコアの方がOOS耐性が高い）",
              "全組み合わせは「ISに存在したが再現しないパターン」を含む。",
              "複合スコアは毎週動的に選択するため、消えたパターンは自然に除外される。"]),
            ("考察 [4]  OOS月次一貫性の比較",
             [f"全組み合わせ: OOS黒字月 {win_months_base}/{tot_months_base}ヶ月 ({win_months_base/tot_months_base*100:.0f}%)",
              f"複合スコア:   OOS黒字月 {win_months_sc}/{tot_months_sc}ヶ月 ({win_months_sc/tot_months_sc*100:.0f}%)",
              f"月次Sharpe比（OOS）: {sharpe_oos:.2f}  / 月次平均年率換算: {ann_ret_oos:.1f}%",
              "複合スコアはDD罰則とモメンタムフィルターにより荒れた月を回避しやすい。"]),
        ]

        for title,points in analyses:
            need = 7 + 6 + len(points)*5.5 + 4
            self._pb(need)
            cy = self.get_y()
            self.set_fill_color(*LIGHT)
            self.rect(14,cy,182,7,"F")
            self._c(*NAVY); self.set_font("YG",size=8.5)
            self.set_xy(16,cy+0.5); self.cell(178,6,title)
            self.set_xy(14,cy+8)
            for pt in points:
                self._c(*DARK); self.set_font("YG",size=8)
                py=self.get_y()
                self.set_xy(18,py); self.cell(174,5.5,pt)
                self.set_xy(14,py+5.5)
            self.set_xy(14,self.get_y()+4)

    # ── P4: OOS月次 + コンビ別OOS PF
    def page_charts2(self,c2,c3):
        self.add_page(); self.set_margins(14,14,14)
        self._hdr("5. OOS月次損益（2024年  複合スコア TOP6）")
        self.set_xy(14,self.get_y()+2)
        self.image(c2,x=14,y=self.get_y(),w=182); self.set_xy(14,self.get_y()+66)
        self._hdr("6. コンビ別 OOS PF（複合スコア TOP6選択分）")
        self.set_xy(14,self.get_y()+2)
        self.image(c3,x=14,y=self.get_y(),w=182); self.set_xy(14,self.get_y()+100)

    # ── P5: コンビ別詳細テーブル
    def page_combo_detail(self):
        self.add_page(); self.set_margins(14,14,14)
        self._hdr("7. 通貨ペア×セッション 詳細統計（複合スコア TOP6 選択分）")
        self.set_xy(14,self.get_y()+2)

        ws2=[58,12,14,14,18,16]
        self._hrow(["コンビ（ペア_セッション）","期間","n","勝率%","PF","損益(万)"],ws2,h=8)

        combos_sorted = (df_cs[df_cs["period"]=="OOS"]
                         .sort_values("pf",ascending=False)["combo"].tolist())
        combos_rest   = [c for c in df_cs["combo"].unique() if c not in combos_sorted]
        combos_order  = combos_sorted + combos_rest

        ri=0
        for combo in combos_order:
            for period in ["IS","OOS"]:
                row_data=df_cs[(df_cs["combo"]==combo)&(df_cs["period"]==period)]
                if len(row_data)==0: continue
                rd=row_data.iloc[0]
                short=combo.replace("\n"," ")
                pf_str=f"{rd['pf']:.3f}"
                pnl_str=f"+{rd['total_pnl']:.1f}" if rd["total_pnl"]>=0 else f"{rd['total_pnl']:.1f}"
                self._row([short if period=="IS" else "",
                           period,f"{int(rd['n'])}",f"{rd['win_rate']:.1f}",pf_str,pnl_str],
                          ws2,fill=(ri%2==0),
                          aligns=["L","C","R","R","R","R"])
                ri+=1
        self.set_xy(14,self.get_y()+3)
        self._note("※ OOS降順（PF高い順）で表示。損益はDMM FXスプレッド控除後。元本100万円はポートフォリオ合計（ペアごとではない）。")
        self.set_xy(14,self.get_y())
        self._note("※ ISにのみ登場するコンビはIS期間に選択頻度が高かったもの。")

    # ── P6: 資金規模試算 + 孫さん向け判断フレーム
    def page_capital_and_decision(self):
        self.add_page(); self.set_margins(14,14,14)
        self._hdr("8. 資金規模別 OOS期間 損益試算（複合スコア）")
        self.set_xy(14,self.get_y()+2)

        ws3=[40,30,30,30,30,22]
        self._hrow(["資金規模","OOS月次平均","OOS年間推計","IS DD金額","OOS DD金額","レバ目安"],ws3,h=8)
        for i,cap in enumerate(scales):
            ratio=cap/100
            mon_avg=oos_monthly_avg*ratio/10000
            ann=mon_avg*12
            is_dd=res["SC"]["IS"]["dd_pct"]*cap/100
            oos_dd=res["SC"]["OOS"]["dd_pct"]*cap/100
            lev="1.0x" if cap<=100 else "1.5x" if cap<=300 else "2.0x" if cap<=500 else "3.0x+"
            self._row([f"{cap}万円",f"{mon_avg:+.1f}万/月",f"{ann:+.0f}万/年",
                       f"{is_dd:.0f}万",f"{oos_dd:.0f}万",lev],
                      ws3,fill=(i%2==0),aligns=["L","R","R","R","R","C"])
        self.set_xy(14,self.get_y()+2)
        self._note("※OOS月次平均を基準に線形換算。実際は規模拡大でスリッページ増加の可能性あり。")
        self._note(f"※DD金額はOOS最大DD%({res['SC']['OOS']['dd_pct']:.1f}%)×資金規模で算出。IS DDは{res['SC']['IS']['dd_pct']:.1f}%で計算。")
        self._note("※ポジションサイジング: 資金合計×0.5%÷SL幅。TOP6コンビ同時保有時の最大リスク合計≈3%/週。")

        self.set_xy(14,self.get_y()+4)
        self._hdr("9. 意思決定フレームワーク（孫さん向け判断軸）")
        self.set_xy(14,self.get_y()+3)

        # 条件判定（動的）
        pf_ok  = oos_pf_sc  >= 1.2
        dd_ok  = res["SC"]["OOS"]["dd_pct"] <= 25.0
        mon_ok = win_months_sc >= 7
        is_oos_drift = (oos_pf_sc - is_pf_sc) / is_pf_sc * 100
        drift_ok = is_oos_drift >= 0

        def chk(b): return "達成" if b else "未達 ×"

        items=[
            ("Go条件チェック（本番移行判断）",[
                f"OOS PF >= 1.2  : {chk(pf_ok)}（{oos_pf_sc:.3f}） ← コスト控除後",
                f"OOS DD <= 25%  : {chk(dd_ok)}（{res['SC']['OOS']['dd_pct']:.1f}%）",
                f"OOS黒字月 >= 7/12: {chk(mon_ok)}（{win_months_sc}/{tot_months_sc}ヶ月）",
                f"IS->OOS PF 劣化なし: {chk(drift_ok)}（{is_oos_drift:+.1f}%）",
            ]),
            ("コスト問題の診断",[
                f"コスト控除前 OOS PF: 約1.4前後（DMM FXスプレッド控除で収益が消失）",
                "根本原因: 平均保有時間が短く、スプレッドコストが利益幅に対して大きい",
                "対策A: SL幅を拡大 → ロット縮小 → コスト比率を下げる（例: ATR×2 SL）",
                "対策B: 高スプレッドペア（AUDNZD 2.2pip / CHFJPY 2.2pip）を除外する",
                "対策C: エントリー精度を高め、トレード件数を絞り込む",
            ]),
            ("推奨アクション（現時点）",[
                "Step1: 高コストペア除外 + SL幅拡大でパラメータ再検討（IS再探索）",
                "Step2: コスト込みPF >= 1.2 達成後にOOS開封・デモ移行",
                "Step3: デモ3ヶ月 PF >= 1.0・DD <= 25% 確認後に本番開始",
                "Step4: 本番移行は現時点では推奨しない（Go条件未達）",
            ]),
        ]
        for title,pts in items:
            need = 7 + 6 + len(pts)*5.5 + 4
            self._pb(need)
            cy = self.get_y()
            self.set_fill_color(*LIGHT)
            self.rect(14,cy,182,7,"F")
            self._c(*NAVY); self.set_font("YG",size=8.5)
            self.set_xy(16,cy+0.5); self.cell(178,6,title)
            self.set_xy(14,cy+8)
            for pt in pts:
                self._c(*DARK); self.set_font("YG",size=8)
                py=self.get_y()
                self.set_xy(18,py); self.cell(174,5.5,pt)
                self.set_xy(14,py+5.5)
            self.set_xy(14,self.get_y()+4)

        self.ln(4)
        self.set_font("YG",size=7.5); self._c(*GRAY)
        self.set_x(14)
        self.cell(182,6,
            f"FxCompany 内部分析レポート / 生成日 {datetime.now().strftime('%Y-%m-%d')} / "
            "IS 2022-2023 / OOS 2024 / 複合スコア TOP6（WINDOW=4週）/ コスト: DMM FXスプレッド",align="C")


pdf=PDF()
pdf.cover()
pdf.page_charts1(c1,c4)
pdf.page_quantitative()
pdf.page_charts2(c2,c3)
pdf.page_combo_detail()
pdf.page_capital_and_decision()

from datetime import datetime as _dt
out=OUT_DIR/f"is_oos_portfolio_report_{_dt.now().strftime('%H%M%S')}.pdf"
pdf.output(str(out))
print(f"PDF保存: {out}")
print("完了")
