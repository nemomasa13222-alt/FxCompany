# -*- coding: utf-8 -*-
"""
USDJPY IS+OOS 報告書 PDF生成
実行: python _make_usdjpy_report.py
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
ROOT    = Path(__file__).parent
IN_DIR  = ROOT / "docs" / "usdjpy_is_oos"
OUT_DIR = IN_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

CAPITAL   = 1_000_000
IS_END    = "2023-12-31"
Q_EXT     = 0.04; AC_MIN = 0.20; SPREAD = 0.2
NAVY  = (15,30,70);  BLUE  = (30,90,170);   TEAL  = (0,160,120)
RED   = (190,40,40); GREEN = (0,140,80);     AMBER = (200,140,0)
LIGHT = (235,242,255); WHITE = (255,255,255)
DARK  = (30,30,40);  GRAY  = (110,110,120)

def _jp(sz): return fm.FontProperties(fname=FONT_PATH, size=sz)

# ════════════════════════════
# データ読込
# ════════════════════════════
print("データ読込中...")
df = pd.read_csv(IN_DIR/"bt_usdjpy.csv", encoding="utf-8-sig")
df["signal_bar"] = pd.to_datetime(df["signal_bar"])
df["session"]    = df["session"].str.strip()

df_is  = df[df["period"]=="IS"].copy()
df_oos = df[df["period"]=="OOS"].copy()

def sv(d):
    if len(d)==0: return dict(n=0,wr=0,pf=float("nan"),pnl=0,dd=0,dd_pct=0,exp=0)
    w=d[d["pnl_yen"]>0]; l=d[d["pnl_yen"]<=0]
    gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=d["pnl_yen"].cumsum(); dd=(cum.cummax()-cum).max()
    return dict(n=len(d),wr=len(w)/len(d)*100,pf=pf,
                pnl=d["pnl_yen"].sum(),dd=dd,dd_pct=dd/CAPITAL*100,
                exp=float(d["pnl_yen"].mean()))

st_is  = sv(df_is);  st_oos = sv(df_oos); st_all = sv(df)

# セッション別
SESS_LABELS = ["東京\n09-15JST","欧州\n15-21JST"]
sess_st = {}
for sl in SESS_LABELS:
    d = df[df["session"]==sl]
    sess_st[sl] = {"IS":sv(d[d["period"]=="IS"]),"OOS":sv(d[d["period"]=="OOS"])}

# 月次（OOS）
df_oos["month"] = df_oos["signal_bar"].dt.to_period("M")
monthly_oos = df_oos.groupby("month")["pnl_yen"].sum()
df_is["month"]  = df_is["signal_bar"].dt.to_period("M")
monthly_is  = df_is.groupby("month")["pnl_yen"].sum()

print(f"IS  : n={st_is['n']} PF={st_is['pf']:.3f} {st_is['pnl']/10000:+.1f}万")
print(f"OOS : n={st_oos['n']} PF={st_oos['pf']:.3f} {st_oos['pnl']/10000:+.1f}万")

# ════════════════════════════
# チャート生成
# ════════════════════════════
def save_tmp(fig):
    t = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(t.name, dpi=150, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig); return t.name

print("チャート生成中...")

# C1: IS / OOS 累積損益（横並び）
fig, axes = plt.subplots(1,2,figsize=(12,4))
fig.patch.set_facecolor("#F5F8FF")
for ax,(period,d_p,color,title) in zip(axes,[
    ("IS", df_is, "#2980b9","IS期間 2022-2023（採用パラメータ）"),
    ("OOS",df_oos,"#e74c3c","OOS期間 2024（未開封 → 開封）")]):
    ax.set_facecolor("#F5F8FF"); ax.axhline(0,color="#333",lw=0.8,ls="--",alpha=0.5)
    cum = d_p["pnl_yen"].cumsum().reset_index(drop=True)
    st  = sv(d_p)
    lbl = f"PF={st['pf']:.3f}  DD={st['dd_pct']:.1f}%  {st['pnl']/10000:+.1f}万"
    ax.plot(cum, color=color, lw=2.2, label=lbl)
    ax.fill_between(range(len(cum)), cum, color=color, alpha=0.08)
    ax.set_title(title, fontproperties=_jp(9.5), fontweight="bold", color="#1A3A7A", pad=5)
    ax.legend(fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))
plt.tight_layout(pad=0.8)
c1 = save_tmp(fig)

# C2: 月次損益バー（IS + OOS 並列）
fig, axes = plt.subplots(1,2,figsize=(12,4))
fig.patch.set_facecolor("#F5F8FF")
for ax, (monthly, title, base_color) in zip(axes,[
    (monthly_is,  "IS期間 月次損益（万円）","#2980b9"),
    (monthly_oos, "OOS期間 月次損益（万円）","#e74c3c")]):
    ax.set_facecolor("#F5F8FF")
    if len(monthly)==0:
        ax.text(0.5,0.5,"データなし",ha="center",va="center",transform=ax.transAxes)
        continue
    colors_ = ["#27ae60" if v>=0 else "#e74c3c" for v in monthly.values]
    ax.bar(range(len(monthly)), monthly.values/10000, color=colors_,
           edgecolor="white", linewidth=0.5, alpha=0.85)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels([str(m) for m in monthly.index],
                        rotation=40, ha="right", fontproperties=_jp(7))
    for i,v in enumerate(monthly.values/10000):
        ax.text(i, v+(0.15 if v>=0 else -0.5), f"{v:+.1f}",
                ha="center", fontsize=6.5, fontweight="bold",
                color="#27ae60" if v>=0 else "#c0392b", fontproperties=_jp(6.5))
    ax.set_title(title, fontproperties=_jp(9.5), fontweight="bold", color="#1A3A7A", pad=5)
    ax.set_ylabel("損益（万円）", fontproperties=_jp(8))
    ax.grid(axis="y", alpha=0.2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{v:+.1f}万"))
plt.tight_layout(pad=0.8)
c2 = save_tmp(fig)

# C3: セッション別 IS vs OOS PF バー
fig, ax = plt.subplots(figsize=(8,4))
fig.patch.set_facecolor("#F5F8FF"); ax.set_facecolor("#F5F8FF")
sess_names = [s.replace("\n"," ") for s in SESS_LABELS]
is_pf  = [sess_st[s]["IS"]["pf"]  if not np.isnan(sess_st[s]["IS"]["pf"])  else 0 for s in SESS_LABELS]
oos_pf = [sess_st[s]["OOS"]["pf"] if not np.isnan(sess_st[s]["OOS"]["pf"]) else 0 for s in SESS_LABELS]
x = np.arange(len(sess_names)); w = 0.35
b1 = ax.bar(x-w/2, is_pf,  w, label="IS",  color="#2c3e50", alpha=0.8)
b2 = ax.bar(x+w/2, oos_pf, w, label="OOS", color="#e74c3c", alpha=0.8)
ax.axhline(1.0, color="#cc3333", lw=1.2, ls="--", alpha=0.7, label="PF=1.0")
ax.set_xticks(x); ax.set_xticklabels(sess_names, fontproperties=_jp(9))
ax.set_title("セッション別 IS/OOS PF比較", fontproperties=_jp(10), fontweight="bold", color="#1A3A7A")
ax.legend(fontsize=9); ax.grid(axis="y", alpha=0.2)
for bar,v in zip(list(b1)+list(b2), is_pf+oos_pf):
    ax.text(bar.get_x()+bar.get_width()/2, v+0.02, f"{v:.3f}",
            ha="center", fontsize=9, fontweight="bold")
plt.tight_layout(pad=0.8)
c3 = save_tmp(fig)

print("PDF生成中...")

# ════════════════════════════
# PDF クラス
# ════════════════════════════
class PDF(FPDF):
    def __init__(self):
        super().__init__("P","mm","A4")
        self.add_font("YG","",FONT_PATH,uni=True)
        self.set_auto_page_break(auto=True, margin=14)

    def _c(self,r,g,b): self.set_text_color(r,g,b)
    def _pb(self, need=10):
        if self.get_y()+need > self.h-self.b_margin: self.add_page()

    def _hdr(self, title):
        self._pb(15)
        self.set_fill_color(*BLUE); self._c(*WHITE); self.set_font("YG",size=10)
        cy=self.get_y()
        self.rect(14,cy,182,9,"F")
        self.set_xy(16,cy+0.8); self.cell(178,8,title)
        self.set_xy(14,cy+11); self._c(*DARK)

    def _hrow(self,cols,ws,h=8):
        self._pb(h+2)
        self.set_font("YG",size=8)
        self.set_fill_color(*NAVY); self._c(*WHITE)
        x,y=14,self.get_y()
        self.rect(x,y,sum(ws),h,"F")
        for t,w in zip(cols,ws):
            self.set_xy(x,y); self.cell(w,h,str(t),align="C"); x+=w
        self.set_xy(14,y+h); self._c(*DARK)

    def _row(self,cols,ws,h=7,fill=False,aligns=None):
        self._pb(h)
        self.set_font("YG",size=7.5)
        x,y=14,self.get_y()
        if fill: self.set_fill_color(*LIGHT); self.rect(x,y,sum(ws),h,"F")
        aligns=aligns or ["C"]*len(cols)
        for t,w,a in zip(cols,ws,aligns):
            self.set_xy(x,y); self.cell(w,h,str(t),align=a); x+=w
        self.set_xy(14,y+h)

    def _note(self,txt,indent=2):
        self._pb(7)
        self.set_font("YG",size=7.5); self._c(*DARK)
        self.set_xy(14+indent,self.get_y())
        self.cell(180-indent,5.5,txt)
        self.set_xy(14,self.get_y()+5.5)

    # ── 表紙
    def cover(self):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,297,"F")
        self.set_font("YG",size=9); self._c(*TEAL)
        self.set_xy(14,44); self.cell(182,8,"USDJPY 通貨強弱×自己相関 スキャルピング戦略",align="C")
        self.set_font("YG",size=20); self._c(*WHITE)
        self.set_xy(14,56); self.cell(182,14,"IS+OOS 全期間検証 報告書",align="C")
        self.set_font("YG",size=11); self._c(*TEAL)
        self.set_xy(14,76); self.cell(182,9,"DMM FXスプレッド控除済み / パラメータ: q=0.04 / AC≥0.20",align="C")

        # 3つのKPIボックス
        boxes=[
            ("IS PF", f"{st_is['pf']:.3f}", f"+{st_is['pnl']/10000:.1f}万円", "2022-2023"),
            ("OOS PF", f"{st_oos['pf']:.3f}", f"{st_oos['pnl']/10000:+.1f}万円", "2024"),
            ("全期間 PF", f"{st_all['pf']:.3f}", f"+{st_all['pnl']/10000:.1f}万円", "2022-2024"),
        ]
        bx=14; bw=58
        for title,val,sub,period in boxes:
            self.set_fill_color(25,55,110); self.rect(bx,100,bw-2,40,"F")
            self._c(*TEAL); self.set_font("YG",size=8)
            self.set_xy(bx,103); self.cell(bw-2,7,title,align="C")
            col = (255,120,120) if (title=="OOS PF" and st_oos["pf"]<1.2) else WHITE
            self._c(*col); self.set_font("YG",size=17)
            self.set_xy(bx,111); self.cell(bw-2,11,val,align="C")
            self._c(*TEAL); self.set_font("YG",size=8)
            self.set_xy(bx,123); self.cell(bw-2,6,sub,align="C")
            self.set_xy(bx,129); self.cell(bw-2,6,period,align="C")
            bx+=60

        # IS/OOS比較テーブル
        self.set_fill_color(25,55,110); self.rect(14,152,182,80,"F")
        self._c(*TEAL); self.set_font("YG",size=9)
        self.set_xy(14,156); self.cell(182,8,"IS vs OOS サマリー",align="C")
        self.set_font("YG",size=8); self._c(*GRAY)
        self.set_xy(14,164); self.cell(182,6,"元本100万円 / リスク0.5%/trade / 1ペア集中運用",align="C")

        hdr_data=[("期間","件数","勝率%","PF","損益(万)","最大DD%","1T期待値(円)")]
        rows_data=[
            ("IS 2022-2023", f"{st_is['n']}", f"{st_is['wr']:.1f}",
             f"{st_is['pf']:.3f}", f"+{st_is['pnl']/10000:.1f}",
             f"{st_is['dd_pct']:.1f}%", f"{st_is['exp']:+.0f}"),
            ("OOS 2024★", f"{st_oos['n']}", f"{st_oos['wr']:.1f}",
             f"{st_oos['pf']:.3f}", f"{st_oos['pnl']/10000:+.1f}",
             f"{st_oos['dd_pct']:.1f}%", f"{st_oos['exp']:+.0f}"),
            ("全期間 合計", f"{st_all['n']}", f"{st_all['wr']:.1f}",
             f"{st_all['pf']:.3f}", f"+{st_all['pnl']/10000:.1f}",
             f"{st_all['dd_pct']:.1f}%", f"{st_all['exp']:+.0f}"),
        ]
        ws_c=[34,18,16,16,18,18,22]
        y=172
        for ri,row in enumerate([hdr_data[0]]+rows_data):
            for ci,(t,w) in enumerate(zip(row,ws_c)):
                self.set_xy(14+sum(ws_c[:ci]),y)
                if ri==0: self._c(*TEAL); self.set_font("YG",size=7.5)
                elif ri==2: self._c(255,120,120); self.set_font("YG",size=7.5)
                else: self._c(*WHITE); self.set_font("YG",size=7.5)
                self.cell(w,8,t,align="C")
            y+=9

        # 判定バナー
        pf_ok = st_oos["pf"] >= 1.2
        dd_ok = st_oos["dd_pct"] <= 15.0
        verdict_color = (0,140,80) if (pf_ok and dd_ok) else (190,40,40)
        verdict_text  = "Go条件 達成" if (pf_ok and dd_ok) else "Go条件 未達 — 追加観察推奨"
        self.set_fill_color(*verdict_color); self.rect(14,244,182,18,"F")
        self._c(*WHITE); self.set_font("YG",size=12)
        self.set_xy(14,249); self.cell(182,10,verdict_text,align="C")

        self._c(*GRAY); self.set_font("YG",size=7.5)
        self.set_xy(14,268)
        self.cell(182,6,f"生成日: {datetime.now().strftime('%Y-%m-%d')}  /  "
                  f"IS 2022-2023 / OOS 2024 / USDJPY 5分足 / DMM FXスプレッド 0.2pip",align="C")

    # ── P2: 累積損益チャート
    def page_charts(self, c1, c2):
        self.add_page()
        self._hdr("1. IS / OOS 累積損益（採用パラメータ: q=0.04 / AC≥0.20）")
        self.set_xy(14,self.get_y()+2)
        self.image(c1, x=14, y=self.get_y(), w=182); self.set_xy(14,self.get_y()+72)
        self._hdr("2. 月次損益バー（左: IS / 右: OOS）")
        self.set_xy(14,self.get_y()+2)
        self.image(c2, x=14, y=self.get_y(), w=182); self.set_xy(14,self.get_y()+72)

    # ── P3: セッション別 + 統計テーブル
    def page_session(self, c3):
        self.add_page()
        self._hdr("3. セッション別 IS/OOS PF比較")
        self.set_xy(14,self.get_y()+2)
        self.image(c3, x=14, y=self.get_y(), w=120); self.set_xy(14,self.get_y()+75)

        self._hdr("4. セッション別 詳細統計")
        self.set_xy(14,self.get_y()+2)
        ws=[52,14,14,16,18,16,24]
        self._hrow(["セッション","期間","件数","勝率%","PF","損益(万)","1T期待値(円)"],ws,h=8)
        ri=0
        for sl in SESS_LABELS:
            sname=sl.replace("\n"," ")
            for period_k,period_l in [("IS","IS"),("OOS","OOS")]:
                st=sess_st[sl][period_k]
                if st["n"]==0: continue
                pnl_str=f"{st['pnl']/10000:+.1f}"
                self._row([sname if period_k=="IS" else "",period_l,
                           f"{st['n']}",f"{st['wr']:.1f}",f"{st['pf']:.3f}",
                           pnl_str,f"{st['exp']:+.0f}"],
                          ws, fill=(ri%2==0),
                          aligns=["L","C","C","C","C","C","C"])
                ri+=1
        self.set_xy(14,self.get_y()+3)
        self._note("※ 損益・統計はDMM FXスプレッド0.2pip（往復）控除後。元本100万円。")

        # パラメータ採用根拠
        self._pb(60)
        self.set_xy(14,self.get_y()+4)
        self._hdr("5. パラメータ採用根拠（ISサーベイ結果より）")
        self.set_xy(14,self.get_y()+3)
        ws2=[44,12,12,16,18,12]
        self._hrow(["条件（q / AC≥）","件数","勝率%","PF","IS損益(万)","DD%"],ws2,h=8)
        survey_rows=[
            ("q=0.03 / AC≥0.20",149,"38.9","1.515","+17.1","8.8"),
            ("q=0.04 / AC≥0.20 ★採用",207,"38.6","1.444","+21.8","10.9"),
            ("q=0.05 / AC≥0.20",269,"36.8","1.375","+24.8","10.1"),
            ("q=0.04 / AC≥0.15",264,"39.8","1.359","+22.0","13.6"),
            ("q=0.10 / AC≥0.00（旧）",1260,"38.9","1.034","+9.9","25.2"),
        ]
        for ri,(row) in enumerate(survey_rows):
            fill=(ri%2==0)
            self._row(list(row),ws2,fill=fill,
                      aligns=["L","C","C","C","C","C"])
        self.set_xy(14,self.get_y()+2)
        self._note("※ q=0.03は件数149件と少なく統計的信頼性に不安。q=0.04をバランス点として採用。")
        self._note("※ AC閾値を上げるほどPFが改善 → 自己相関が明確な局面への絞り込みが有効。")

    # ── P4: 意思決定フレーム
    def page_decision(self):
        self.add_page()
        self._hdr("6. 意思決定フレームワーク（判断軸）")
        self.set_xy(14,self.get_y()+3)

        pf_ok  = st_oos["pf"] >= 1.2
        dd_ok  = st_oos["dd_pct"] <= 15.0
        mon_ok = (monthly_oos > 0).sum() >= 7 if len(monthly_oos) >= 10 else None
        drift  = (st_oos["pf"] - st_is["pf"]) / st_is["pf"] * 100
        drift_ok = drift >= -20

        def chk(b):
            if b is None: return "判定不能"
            return "達成 ✓" if b else "未達 ×"

        items = [
            ("Go条件チェック（本番移行基準）", [
                f"OOS PF >= 1.2    : {chk(pf_ok)}（{st_oos['pf']:.3f}）",
                f"OOS DD <= 15%   : {chk(dd_ok)}（{st_oos['dd_pct']:.1f}%）",
                f"OOS黒字月 >= 7/12 : {chk(mon_ok)}（{(monthly_oos>0).sum()}/{len(monthly_oos)}ヶ月）",
                f"IS→OOS PF乖離 <= -20% : {chk(drift_ok)}（{drift:+.1f}%）",
            ]),
            ("現状の考察", [
                f"OOS PF={st_oos['pf']:.3f}（+0.7万）: 黒字だが弱い。Go基準PF=1.2には届かず。",
                f"セッション逆転: 欧州IS PF=2.044 → OOS PF=0.898 / 東京IS PF=0.859 → OOS PF=1.258",
                "2024年のUSD/JPY相場: 介入・大幅変動あり。欧州時間帯に影響の可能性。",
                f"全期間 PF={st_all['pf']:.3f}（+22.5万/3年）は黒字で安定的な傾向は維持。",
            ]),
            ("推奨アクション", [
                "Step1: デモトレード3ヶ月継続（採用パラメータで実運用を模擬）",
                "Step2: 欧州セッション単独 vs 東京セッション単独を2025年データで別途評価",
                "Step3: デモPF >= 1.2・DD <= 15%達成後に本番100万円で開始",
                "Step4: 本番開始後は月次でPF・DDをモニタリング。連続3ヶ月赤字なら停止。",
            ]),
            ("リスク認識", [
                "1ペア集中リスク: USD/JPY固有の政策・介入リスクに全資金がさらされる。",
                "セッション不安定: IS/OOSで優位セッションが入れ替わっており再現性が不明確。",
                "サンプル数: OOS 123件（1年）は統計的に十分だが、月次では10件程度と少ない。",
                "スリッページ: DMM FXのスプレッドは原則固定だが、重要指標発表時は変動する。",
            ]),
        ]

        for title, pts in items:
            need = 7+6+len(pts)*5.5+4
            self._pb(need)
            cy=self.get_y()
            self.set_fill_color(*LIGHT); self.rect(14,cy,182,7,"F")
            self._c(*NAVY); self.set_font("YG",size=8.5)
            self.set_xy(16,cy+0.5); self.cell(178,6,title)
            self.set_xy(14,cy+8)
            for pt in pts:
                self._c(*DARK); self.set_font("YG",size=8)
                py=self.get_y()
                self.set_xy(18,py); self.cell(174,5.5,pt)
                self.set_xy(14,py+5.5)
            self.set_xy(14,self.get_y()+4)

        self.ln(3)
        self.set_font("YG",size=7.5); self._c(*GRAY); self.set_x(14)
        self.cell(182,6,
            f"FxCompany 内部分析レポート / 生成日 {datetime.now().strftime('%Y-%m-%d')} / "
            "USDJPY / IS 2022-2023 / OOS 2024 / q=0.04 / AC>=0.20 / DMM FXスプレッド",align="C")


pdf = PDF()
pdf.cover()
pdf.page_charts(c1, c2)
pdf.page_session(c3)
pdf.page_decision()

from datetime import datetime as _dt
out = OUT_DIR / f"usdjpy_is_oos_report_{_dt.now().strftime('%H%M%S')}.pdf"
pdf.output(str(out))
print(f"PDF保存: {out}")
print("完了")
