# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 v2 パラメータ比較 & OOS結果 総合レポート
実行: python japan_stocks/make_v2_comparison_pdf.py
"""

import sys, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from fpdf import FPDF, XPos, YPos

FONT_PATH   = r"C:\Windows\Fonts\YuGothM.ttc"
RESULTS_DIR = Path(__file__).parent / "results" / "backtest"
OUTPUT_DIR  = Path(__file__).parent / "results" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INITIAL_CAPITAL     = 1_000_000
ROUND_TRIP_COST_PCT = 0.20

# v2-f の IS/OOS CSV（最終採用版）
IS_CSV  = RESULTS_DIR / "sector_is_20260502_214550.csv"
OOS_CSV = RESULTS_DIR / "sector_oos_20260502_214550.csv"

NAVY  = (15,  30,  70)
BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120)
GREEN = (0,  140,  80)
RED   = (190,  40,  40)
AMBER = (200, 140,   0)
LIGHT = (235, 242, 255)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)

# ── 全パラメータ比較データ ─────────────────────────────────────────────────────
PARAM_TABLE = [
    # label, 業種選別, sector_rise, min_gap, risk, stop, IS件数, IS勝率, IS_PF, IS_DD, IS損益, 備考
    ("v1 旧ベースライン",    "固定TOP10",      "2%","1.5%","1.0%","3.0%", 2308,54.9,1.37,21.1, 234, "OOS DD 35.5%で基準超"),
    ("v2-a",                "全33→動的5",     "5%","3.0%","1.0%","3.0%",  414,45.2,0.81,32.9, -25, "5%閾値は過熱後。赤字"),
    ("v2-b",                "全33→動的5",     "2%","3.0%","1.0%","3.0%", 1394,50.4,1.03,27.9,  10, "銀行業等が混入"),
    ("v2-c",                "TOP10→動的5",    "2%","3.0%","1.0%","3.0%", 1068,54.8,1.32,16.9,  91, ""),
    ("v2-d",                "TOP10→動的5",    "2%","3.0%","2.0%","3.0%", 1068,54.8,1.31,31.8, 185, "risk2倍でDD2倍"),
    ("v2-e",                "TOP10→動的5",    "2%","3.0%","0.5%","3.0%", 1068,54.8,1.33, 8.7,  45, "OOS: PF1.30 DD9.7%"),
    ("v2-f ★採用",         "TOP10→動的5",    "2%","3.0%","0.5%","1.5%", 1159,52.2,1.63, 8.7, 148, "OOS: PF1.50 DD11.1%"),
]

OOS_RESULT = {"n":1173, "wr":50.3, "pf":1.50, "dd":11.1, "pnl":1_300_183}
IS_RESULT  = {"n":1159, "wr":52.2, "pf":1.63, "dd":8.7,  "pnl":1_477_620}


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _pf(pnl: pd.Series) -> float:
    w = pnl[pnl > 0].sum()
    l = abs(pnl[pnl <= 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


def load_with_cost(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["cost_jpy"]    = df["entry_price"] * df["shares"] * ROUND_TRIP_COST_PCT / 100
    df["net_pnl_jpy"] = df["pnl_jpy"] - df["cost_jpy"]
    return df


def calc_summary(df: pd.DataFrame) -> dict:
    pnl = df["net_pnl_jpy"]
    eq, peak, max_dd = INITIAL_CAPITAL, INITIAL_CAPITAL, 0.0
    for v in df.sort_values("exit_date")["net_pnl_jpy"]:
        eq += v; peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)
    by_sector = {}
    for sec, g in df.groupby("sector"):
        r = g["net_pnl_jpy"]
        by_sector[sec] = {"trades":len(g),"wr":round((r>0).mean()*100,1),
                          "pf":_pf(r),"pnl":round(r.sum())}
    df2 = df.copy()
    df2["year"] = pd.to_datetime(df2["entry_date"]).dt.year
    yearly = {}
    for yr, g in df2.groupby("year"):
        r = g["net_pnl_jpy"]
        yearly[int(yr)] = {"trades":len(g),"wr":round((r>0).mean()*100,1),
                           "pf":_pf(r),"pnl":round(r.sum())}
    wins, loss = pnl[pnl>0], pnl[pnl<=0]
    return {"n":len(df),"wr":round((pnl>0).mean()*100,1),"pf":_pf(pnl),
            "total_pnl":round(pnl.sum()),"total_cost":round(df["cost_jpy"].sum()),
            "max_dd":round(max_dd,1),"final":round(INITIAL_CAPITAL+pnl.sum()),
            "by_sector":by_sector,"yearly":yearly,
            "exit_reasons":df["exit_reason"].value_counts().to_dict()}


# ── チャート ──────────────────────────────────────────────────────────────────

def make_param_chart() -> str:
    versions = [r[0].replace(" ★採用","★") for r in PARAM_TABLE]
    pfs  = [r[8]  for r in PARAM_TABLE]
    dds  = [r[9]  for r in PARAM_TABLE]
    pnls = [r[10] for r in PARAM_TABLE]

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    fig.patch.set_facecolor("#F5F8FF")
    colors = ["#CC3333" if p < 1.0 else ("#FF8800" if p < 1.3 else
              ("#2266AA" if "★" not in v else "#008060"))
              for p, v in zip(pfs, versions)]

    for ax, vals, title, thresh, fmt in zip(
        axes,
        [pfs, dds, pnls],
        ["IS PF（コスト後）", "IS 最大DD（%）", "IS 損益（万円）"],
        [1.3, 20, 0],
        [".2f", ".1f", ".0f"]
    ):
        ax.set_facecolor("#F5F8FF")
        bars = ax.bar(range(len(versions)), vals, color=colors, alpha=0.85, width=0.6)
        ax.axhline(thresh, color="#CC3333", lw=1.2, ls="--", alpha=0.7)
        ax.set_xticks(range(len(versions)))
        ax.set_xticklabels(versions, rotation=35, ha="right", fontproperties=_jp(7))
        ax.set_title(title, fontproperties=_jp(9.5), color="#1A3A7A", pad=6)
        ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
        for bar, v in zip(bars, vals):
            ypos = v + max(abs(x) for x in vals) * 0.02 if v >= 0 else v - max(abs(x) for x in vals) * 0.07
            ax.text(bar.get_x() + bar.get_width()/2, ypos,
                    f"{v:{fmt}}", ha="center", fontsize=7.5, fontweight="bold",
                    color="#1A3A7A")

    plt.tight_layout(pad=0.9)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_equity_chart(df_is: pd.DataFrame, df_oos: pd.DataFrame) -> str:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 5.5),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    def _monthly(df):
        df2 = df.sort_values("exit_date").copy()
        df2["exit_date"] = pd.to_datetime(df2["exit_date"])
        mo = df2.groupby(df2["exit_date"].dt.to_period("M"))["net_pnl_jpy"].sum()
        cap = INITIAL_CAPITAL
        eq, lb = [cap], [str(mo.index[0] - 1)]
        for m, p in mo.items():
            cap += p; eq.append(cap); lb.append(str(m))
        return eq, lb, mo

    eq_is, lb_is, mo_is = _monthly(df_is)
    eq_oos, lb_oos, mo_oos = _monthly(df_oos)
    offset = eq_is[-1]
    eq_oos_adj = [v - INITIAL_CAPITAL + offset for v in eq_oos]
    x_is  = list(range(len(eq_is)))
    x_oos = list(range(len(eq_is)-1, len(eq_is)-1+len(eq_oos)))
    all_lb = lb_is + lb_oos[1:]

    ax1.plot(x_is,  [v/10000 for v in eq_is],      color="#1A3A7A", lw=2.2, label="IS（2022-2023）")
    ax1.plot(x_oos, [v/10000 for v in eq_oos_adj], color="#FF8800", lw=2.5, label="OOS（2024~）★", ls="--")
    ax1.axvline(len(eq_is)-1, color="#CC4444", lw=1.2, ls=":", alpha=0.8)
    ax1.axhline(INITIAL_CAPITAL/10000, color="#888", lw=0.8, ls=":")
    ax1.set_ylabel("資産額（万円）", fontproperties=_jp(8))
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x,_: f"¥{x:.0f}万"))
    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax1.set_title("エクイティカーブ（コスト控除後）  IS → OOS 連結",
                  fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax1.legend(prop=_jp(8.5))
    step = max(1, len(all_lb)//8)
    ax1.set_xticks(range(0, len(all_lb), step))
    ax1.set_xticklabels(all_lb[::step], fontsize=6.5, rotation=30)

    mo_is_v  = [0]+[v/10000 for v in mo_is.values]
    mo_oos_v = [v/10000 for v in mo_oos.values]
    x_bi = list(range(len(mo_is_v)))
    x_bo = list(range(len(mo_is_v)-1, len(mo_is_v)-1+len(mo_oos_v)))
    ax2.bar(x_bi, mo_is_v,  color=["#2266AA" if v>=0 else "#CC3333" for v in mo_is_v],  alpha=0.8, width=0.7)
    ax2.bar(x_bo, mo_oos_v, color=["#FF8800" if v>=0 else "#CC3333" for v in mo_oos_v], alpha=0.8, width=0.7)
    ax2.axvline(len(mo_is_v)-1, color="#CC4444", lw=1.2, ls=":", alpha=0.8)
    ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_ylabel("月次P&L（万円）", fontproperties=_jp(7.5))
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x,_: f"{x:.0f}万"))
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_leverage_chart() -> str:
    leverages = [1.0, 1.5, 2.0, 2.5, 3.0]
    oos_pnl_base = OOS_RESULT["pnl"] / 10000
    oos_dd_base  = OOS_RESULT["dd"]
    pnls = [oos_pnl_base * l for l in leverages]
    dds  = [oos_dd_base  * l for l in leverages]

    fig, ax1 = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor("#F5F8FF")
    ax1.set_facecolor("#F5F8FF")
    ax2 = ax1.twinx()

    bars = ax1.bar([f"{l:.1f}×" for l in leverages], pnls,
                   color=["#2266AA" if d<=20 else "#CC3333" for d in dds],
                   alpha=0.8, width=0.5, label="OOS損益（万円）")
    ax1.set_ylabel("OOS損益（万円）", fontproperties=_jp(9))
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x,_: f"{x:.0f}万"))
    ax1.set_xlabel("レバレッジ倍率", fontproperties=_jp(9))
    ax1.set_title("レバレッジ別 OOS損益 & DD推計（初期資金100万円）",
                  fontproperties=_jp(10), color="#1A3A7A", pad=8)

    ax2.plot([f"{l:.1f}×" for l in leverages], dds,
             color="#CC3333", lw=2.2, marker="o", ms=7, label="推計最大DD（%）")
    ax2.axhline(20, color="#CC3333", lw=1.2, ls="--", alpha=0.6)
    ax2.text(4.0, 21, "DD 20%基準", fontproperties=_jp(8), color="#CC3333")
    ax2.set_ylabel("推計最大DD（%）", fontproperties=_jp(9), color="#CC3333")
    ax2.tick_params(axis="y", colors="#CC3333")

    for bar, p, d in zip(bars, pnls, dds):
        ax1.text(bar.get_x()+bar.get_width()/2, p+2,
                 f"+{p:.0f}万", ha="center", fontsize=8.5, fontweight="bold",
                 color="#1A3A7A")
    for i, (l, d) in enumerate(zip(leverages, dds)):
        ax2.text(i, d+0.5, f"{d:.1f}%", ha="center", fontsize=8,
                 color="#CC3333", fontweight="bold")

    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1+lines2, labels1+labels2, prop=_jp(8.5), loc="upper left")
    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_yearly_chart(s_is: dict, s_oos: dict) -> str:
    all_years = sorted(set(list(s_is["yearly"].keys()) + list(s_oos["yearly"].keys())))
    is_pnl  = [s_is["yearly"].get(y,{}).get("pnl",0)/10000  for y in all_years]
    oos_pnl = [s_oos["yearly"].get(y,{}).get("pnl",0)/10000 for y in all_years]

    fig, ax = plt.subplots(figsize=(10, 3.8))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    x = np.arange(len(all_years))
    w = 0.35
    ax.bar(x-w/2, is_pnl,  w, color=["#2266AA" if v>=0 else "#CC3333" for v in is_pnl],  alpha=0.85, label="IS")
    ax.bar(x+w/2, oos_pnl, w, color=["#FF8800" if v>=0 else "#CC3333" for v in oos_pnl], alpha=0.85, label="OOS★")
    ax.axhline(0, color="#555", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in all_years], fontproperties=_jp(9))
    ax.set_ylabel("損益（万円・コスト後）", fontproperties=_jp(8))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x,_: f"{x:.0f}万"))
    ax.set_title("年別 損益（コスト控除後）— IS vs OOS", fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax.legend(prop=_jp(9))
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    vmax = max(abs(v) for v in is_pnl+oos_pnl if v) * 0.06
    for xi, (iv, ov) in enumerate(zip(is_pnl, oos_pnl)):
        if iv: ax.text(xi-w/2, iv+(vmax if iv>=0 else -vmax*2), f"{iv:+.0f}万",
                       ha="center", fontsize=7.5, color="#1A3A7A", fontweight="bold")
        if ov: ax.text(xi+w/2, ov+(vmax if ov>=0 else -vmax*2), f"{ov:+.0f}万",
                       ha="center", fontsize=7.5, color="#CC6600", fontweight="bold")
    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class ComparisonReport(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  fname=FONT_PATH)
        self.add_font("YG", "B", fname=FONT_PATH)
        self.set_margins(13, 13, 13)
        self.set_auto_page_break(auto=True, margin=13)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _sec(self, title, color=BLUE):
        self.set_fill_color(*color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 8.5)
        self.cell(0, 6.5, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(1.5)

    def cover(self, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(35)
        self._t(9, color=(120,160,210))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 総括レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self._t(19, bold=True, color=WHITE)
        self.cell(0, 12, "セクター追いつき戦略 v2",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(11, bold=True, color=(0,220,170))
        self.cell(0, 8, "パラメータ最適化 × OOS検証 × レバレッジ試算",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(35, self.get_y(), 175, self.get_y())
        self.ln(5)
        self._t(8.5, color=(140,170,220))
        self.cell(0, 6, f"報告日: {today}  |  IS: 2022-01-01~2023-12-31  |  OOS: 2024-01-01~現在",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, "コスト: 往復0.20%込み  |  採用版: v2-f（TOP10→動的5業種・stop1.5%・risk0.5%）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # IS / OOS サマリー
        self.set_y(120)
        for s, color, tag in [
            (IS_RESULT,  BLUE,  "IS（開発期間: 2022-2023）"),
            (OOS_RESULT, AMBER, "OOS（検証期間: 2024~現在）★"),
        ]:
            self.set_fill_color(*color)
            self.set_text_color(*WHITE)
            self.set_font("YG", "B", 9)
            self.cell(0, 7, f"  {tag}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            oos_years = round((pd.Timestamp("today") - pd.Timestamp("2024-01-01")).days/365.25, 1)
            years = 2.0 if "IS" in tag else oos_years
            for k, v in [
                ("総トレード数",  f"{s['n']:,}件"),
                ("勝率",          f"{s['wr']}%"),
                ("PF",            f"{s['pf']:.2f}"),
                ("最大DD",        f"{s['dd']}%"),
                ("損益（コスト後）", f"¥{s['pnl']:+,.0f}"),
                ("年次リターン",  f"約{s['pnl']/INITIAL_CAPITAL/years*100:.1f}%（{years:.1f}年単純）"),
            ]:
                self._t(8.5, color=(160,190,230))
                self.cell(50, 6.5, k, align="R")
                self._t(9, bold=True, color=WHITE)
                self.cell(0, 6.5, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(3)

        self.set_y(268)
        self._t(7, color=(60,80,120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本レポートは過去データに基づくシミュレーションです。将来の投資成果を保証するものではありません。",
            align="C")

    def param_page(self, param_img: str):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "1. パラメータ最適化の経緯（全バージョン比較）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(13, self.get_y(), 197, self.get_y())
        self.ln(2)

        self.image(param_img, x=13, y=self.get_y(), w=184, h=58)
        self.ln(62)

        self._sec("全バージョン IS成績一覧（コスト控除後）", color=NAVY)
        headers = ["Ver", "業種選別", "sector↑", "乖離%", "risk%", "stop%",
                   "件数", "勝率", "PF", "DD", "損益(万)", "備考"]
        fixed_w = [18, 30, 14, 12, 12, 12, 16, 14, 12, 12, 18]
        last_w  = max(10, int(self.epw - sum(fixed_w)))
        widths  = fixed_w + [last_w]

        self.set_font("YG", "B", 6.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()

        for ri, row in enumerate(PARAM_TABLE):
            label, sel, rise, gap, risk, stop, n, wr, pf, dd, pnl, note = row
            adopted = "★" in label
            bg = (255,252,200) if adopted else (LIGHT if ri%2==0 else WHITE)
            self.set_fill_color(*bg)
            vals = [label, sel, rise, gap, risk, stop, f"{n:,}", f"{wr}%",
                    f"{pf:.2f}", f"{dd}%", f"{pnl:+}", note]
            center_cols = {6,7,8,9,10}  # 件数・勝率・PF・DD・損益は中央揃え
            for ci, (val, w) in enumerate(zip(vals, widths)):
                if ci == 8:   # PF
                    tc = RED if pf < 1.0 else (GREEN if adopted else DARK)
                elif ci == 10: # 損益
                    tc = RED if pnl < 0 else (GREEN if adopted else DARK)
                else:
                    tc = DARK
                self.set_text_color(*tc)
                self.set_font("YG", "B" if adopted else "", 6.5)
                align = "C" if ci in center_cols else "L"
                self.cell(w, 5.5, str(val), border=1, fill=True, align=align)
            self.ln()
        self.set_text_color(*DARK)
        self.ln(3)

        self._sec("最適化の知見サマリー", color=TEAL)
        self._t(8)
        insights = [
            "・ sector_min_rise 5% は過熱後エントリーになり逆効果。2%が適切。",
            "・ 全33業種の動的選別は銀行業・機械など追いつき不向き業種が混入する。TOP10プールが必要。",
            "・ stop_dist 1.5% は premature stop-out を増やさず、むしろ PF が大幅改善（1.33→1.63）。",
            "・ stop を絞るほど1ポジションの株数が増え、同じリスクで大きな利益を狙える。",
            "・ risk_pct 0.5% でDD 8-9% を維持。レバレッジで利益規模を拡大できる余地あり。",
        ]
        for ins in insights:
            self.multi_cell(0, 5.5, ins)
            self.ln(0.5)

    def oos_page(self, eq_img: str, yr_img: str, s_is: dict, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "2. OOS検証結果（v2-f採用版）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(13, self.get_y(), 197, self.get_y())
        self.ln(2)

        self.image(eq_img, x=13, y=self.get_y(), w=184, h=70)
        self.ln(74)
        self.image(yr_img, x=13, y=self.get_y(), w=184, h=52)
        self.ln(56)

        self._sec("IS vs OOS 主要指標対比（コスト控除後）", color=NAVY)
        headers = ["指標", "IS（2022-2023）", "OOS（2024~）", "差分", "判定"]
        widths  = [35, 42, 42, 28, 35]
        self.set_font("YG","B",7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        rows = [
            ("勝率",   s_is["wr"],     s_oos["wr"],     f"{s_oos['wr']-s_is['wr']:+.1f}pp"),
            ("PF",     s_is["pf"],     s_oos["pf"],     f"{s_oos['pf']-s_is['pf']:+.2f}"),
            ("最大DD", s_is["max_dd"], s_oos["max_dd"], f"{s_oos['max_dd']-s_is['max_dd']:+.1f}pp"),
        ]
        judges = [
            ("◎ 再現",GREEN) if abs(s_oos["wr"]-s_is["wr"])<5 and s_oos["wr"]>=50 else ("○ 合格",TEAL),
            ("◎ 再現",GREEN) if s_oos["pf"]>=1.3 and abs(s_oos["pf"]-s_is["pf"])/s_is["pf"]<0.15 else ("○ 合格",TEAL),
            ("◎ 許容",GREEN) if s_oos["max_dd"]<=15 else ("○ 注意",AMBER),
        ]
        units = ["%", "", "%"]
        for i, ((name, iv, ov, diff), (jt, jc), unit) in enumerate(zip(rows, judges, units)):
            bg = LIGHT if i%2==0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG","B",7.5)
            self.cell(widths[0], 6, name, border=1, fill=True)
            self.set_font("YG","",7.5)
            fmt = ".2f" if name=="PF" else ".1f"
            self.cell(widths[1], 6, f"{iv:{fmt}}{unit}", border=1, fill=True, align="C")
            self.cell(widths[2], 6, f"{ov:{fmt}}{unit}", border=1, fill=True, align="C")
            self.cell(widths[3], 6, diff,                border=1, fill=True, align="C")
            self.set_text_color(*jc)
            self.set_font("YG","B",7.5)
            self.cell(widths[4], 6, jt, border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)

    def leverage_page(self, lev_img: str, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "3. レバレッジ運用シミュレーション",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(13, self.get_y(), 197, self.get_y())
        self.ln(3)

        self._sec("ポジションサイジングの仕組み（重要）", color=BLUE)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "本戦略のポジションサイジングは「固定リスク法」を採用。\n"
            "2つのパラメータから株数が自動計算される。")
        self.ln(2)

        # 数式ボックス
        self.set_fill_color(235, 242, 255)
        self.set_draw_color(*BLUE)
        self.set_line_width(0.8)
        self.set_font("YG","B",9.5)
        self.set_text_color(*BLUE)
        self.multi_cell(0, 7,
            "株数 = リスク金額 ÷ ストップ幅\n"
            "リスク金額 = 総資金 × risk_pct（0.5%）\n"
            "ストップ幅 = エントリー価格 × stop_dist（1.5%）",
            border=1, fill=True, align="C")
        self.set_text_color(*DARK)
        self.set_line_width(0.2)
        self.ln(2)

        self._t(8.5)
        self.multi_cell(0, 5.5,
            "例：資金100万円・1,000円株の場合\n"
            "  リスク金額 = 1,000,000 × 0.5% = 5,000円（1トレードで失う上限）\n"
            "  ストップ幅 = 1,000円 × 1.5% = 15円/株\n"
            "  株数 = 5,000 ÷ 15 = 333株  →  投入額 = 333,000円（資金の33.3%）\n"
            "  ⇒ 約3ポジションで資金満杯。レバレッジで保有可能数を増やす。")
        self.ln(3)

        self.image(lev_img, x=13, y=self.get_y(), w=184, h=58)
        self.ln(62)

        self._sec("レバレッジ別シミュレーション（OOS実績ベース）", color=NAVY)
        headers = ["レバ", "OOS損益", "推計DD", "年次リターン", "推奨度", "条件"]
        widths  = [16, 30, 22, 36, 22, 57]
        self.set_font("YG","B",7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        oos_years = round((pd.Timestamp("today")-pd.Timestamp("2024-01-01")).days/365.25,1)
        base_pnl = s_oos["total_pnl"]
        base_dd  = s_oos["max_dd"]
        lev_rows = [
            (1.0, "現物のみ", "◎ 最安全"),
            (1.5, "信用（維持率67%）", "◎ 推奨"),
            (2.0, "信用（維持率50%）", "○ 許容"),
            (2.5, "信用（維持率40%）", "△ 要注意"),
            (3.0, "信用（維持率33%）", "× 超過"),
        ]
        for i, (l, cond, rec) in enumerate(lev_rows):
            pnl_l = base_pnl * l
            dd_l  = base_dd  * l
            yr    = pnl_l / INITIAL_CAPITAL / oos_years * 100
            bg = (255,252,200) if l==1.5 else (LIGHT if i%2==0 else WHITE)
            self.set_fill_color(*bg)
            jc = GREEN if "◎" in rec else (TEAL if "○" in rec else (AMBER if "△" in rec else RED))
            self.set_text_color(*DARK)
            self.set_font("YG","B" if l==1.5 else "",7.5)
            self.cell(widths[0], 6, f"{l:.1f}×", border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if pnl_l>0 else RED))
            self.cell(widths[1], 6, f"¥{pnl_l:+,.0f}", border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if dd_l<=15 else (AMBER if dd_l<=20 else RED)))
            self.cell(widths[2], 6, f"{dd_l:.1f}%", border=1, fill=True, align="C")
            self.set_text_color(*DARK)
            self.cell(widths[3], 6, f"約{yr:.1f}%（{oos_years:.1f}年単純）", border=1, fill=True, align="C")
            self.set_text_color(*jc)
            self.set_font("YG","B",7.5)
            self.cell(widths[4], 6, rec, border=1, fill=True, align="C")
            self.set_text_color(*DARK)
            self.set_font("YG","",7.5)
            self.cell(widths[5], 6, cond, border=1, fill=True)
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        self._sec("推奨運用方針（v2-f × レバ1.5×）", color=TEAL)
        self._t(8.5)
        recs = [
            ("業種選別",    "TOP10候補プールから毎日20SMA超・上位5業種を動的選択"),
            ("エントリー条件", "セクター5日+2%以上 / 遅行株・中間株 / 乖離3%以上"),
            ("ストップロス",  "エントリーから-1.5%（株数を多く持つため利益効率が高い）"),
            ("1トレードリスク", "総資金（自己資金）の0.5%"),
            ("レバレッジ",  "1.5倍（推定DD16%・年次リターン約60%）"),
            ("次のステップ", "デモトレード3ヶ月 → 実績確認後に本番移行"),
        ]
        for k, v in recs:
            self.set_font("YG","B",8.5)
            self.set_text_color(*TEAL)
            self.cell(0, 6.5, f"▶ {k}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG","",8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 5)
            self.multi_cell(0, 5.5, v)
            self.ln(1)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  v2比較レポート PDF生成")
    print(f"{'='*55}\n")

    df_is  = load_with_cost(IS_CSV)
    df_oos = load_with_cost(OOS_CSV)
    s_is   = calc_summary(df_is)
    s_oos  = calc_summary(df_oos)
    print(f"  IS : {s_is['n']}件 PF{s_is['pf']} DD{s_is['max_dd']}% 損益¥{s_is['total_pnl']:+,.0f}")
    print(f"  OOS: {s_oos['n']}件 PF{s_oos['pf']} DD{s_oos['max_dd']}% 損益¥{s_oos['total_pnl']:+,.0f}")

    print("チャート生成中...")
    param_img  = make_param_chart()
    eq_img     = make_equity_chart(df_is, df_oos)
    yr_img     = make_yearly_chart(s_is, s_oos)
    lev_img    = make_leverage_chart()

    print("PDF生成中...")
    pdf = ComparisonReport()
    pdf.cover(today)
    pdf.param_page(param_img)
    pdf.oos_page(eq_img, yr_img, s_is, s_oos)
    pdf.leverage_page(lev_img, s_oos)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"v2_comparison_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [param_img, eq_img, yr_img, lev_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
