# -*- coding: utf-8 -*-
"""
相談役向け総括レポート — セクター追いつき戦略
IS期間別比較（2020/2021/2022）× OOS結果 — すべてコスト控除後

実行: python japan_stocks/make_advisor_report_pdf.py
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tempfile
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

ROUND_TRIP_COST_PCT = 0.20   # 往復コスト（%）
INITIAL_CAPITAL     = 1_000_000
OOS_START           = "2024-01-01"

# ── 各ISシナリオのCSVファイル ──────────────────────────────────────────────────
SCENARIOS = [
    {"label": "IS 2022-2023（採用）", "is_start": "2022-01-01",
     "is_csv": "sector_is_20260502_152452.csv",
     "oos_csv": "sector_oos_20260502_152452.csv"},
    {"label": "IS 2021-2023",         "is_start": "2021-01-01",
     "is_csv": "sector_is_20260502_174158.csv",
     "oos_csv": "sector_oos_20260502_174158.csv"},
    {"label": "IS 2020-2023",         "is_start": "2020-01-01",
     "is_csv": "sector_is_20260502_174441.csv",
     "oos_csv": "sector_oos_20260502_174441.csv"},
]
IS_END   = "2023-12-31"

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
ORANGE = (220, 100, 0)


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _pf(pnl: pd.Series) -> float:
    w = pnl[pnl > 0].sum()
    l = abs(pnl[pnl <= 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


# ── データ読み込み＆コスト控除 ────────────────────────────────────────────────

def load_with_cost(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["cost_jpy"]    = df["entry_price"] * df["shares"] * ROUND_TRIP_COST_PCT / 100
    df["net_pnl_jpy"] = df["pnl_jpy"] - df["cost_jpy"]
    return df


# ── サマリー計算（コスト控除後） ──────────────────────────────────────────────

def calc_summary(df: pd.DataFrame, label: str = "") -> dict:
    if df.empty:
        return {"label": label, "n": 0}
    pnl = df["net_pnl_jpy"]

    equity = INITIAL_CAPITAL
    peak   = equity
    max_dd = 0.0
    for v in df.sort_values("exit_date")["net_pnl_jpy"]:
        equity += v
        peak    = max(peak, equity)
        dd      = (peak - equity) / peak * 100
        max_dd  = max(max_dd, dd)

    by_sector = {}
    for sec, g in df.groupby("sector"):
        r = g["net_pnl_jpy"]
        by_sector[sec] = {
            "trades": len(g),
            "wr"    : round((r > 0).mean() * 100, 1),
            "pf"    : _pf(r),
            "pnl"   : round(r.sum()),
        }

    df2 = df.copy()
    df2["year"] = pd.to_datetime(df2["entry_date"]).dt.year
    yearly = {}
    for yr, g in df2.groupby("year"):
        r = g["net_pnl_jpy"]
        yearly[int(yr)] = {
            "trades": len(g),
            "wr"    : round((r > 0).mean() * 100, 1),
            "pf"    : _pf(r),
            "pnl"   : round(r.sum()),
        }

    wins = pnl[pnl > 0]
    loss = pnl[pnl <= 0]

    return {
        "label"     : label,
        "n"         : len(df),
        "wr"        : round((pnl > 0).mean() * 100, 1),
        "pf"        : _pf(pnl),
        "avg_win"   : round(wins.mean()) if not wins.empty else 0,
        "avg_loss"  : round(loss.mean()) if not loss.empty else 0,
        "total_pnl" : round(pnl.sum()),
        "total_cost": round(df["cost_jpy"].sum()),
        "max_dd"    : round(max_dd, 1),
        "final"     : round(INITIAL_CAPITAL + pnl.sum()),
        "by_sector" : by_sector,
        "yearly"    : yearly,
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
    }


# ── チャート ──────────────────────────────────────────────────────────────────

def make_is_comparison_chart(scenarios_stats: list[dict]) -> str:
    """IS期間別 PF / 勝率 / DD 比較（コスト控除後）"""
    labels = [s["label"].replace("IS ", "").replace("（採用）", "★") for s in scenarios_stats]
    pfs    = [s["pf"]     for s in scenarios_stats]
    wrs    = [s["wr"]     for s in scenarios_stats]
    dds    = [s["max_dd"] for s in scenarios_stats]

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.8))
    fig.patch.set_facecolor("#F5F8FF")
    colors = ["#1A4A9A", "#2288CC", "#44AADD"]

    for ax, vals, title, threshold, fmt in zip(
        axes,
        [pfs, wrs, dds],
        ["PF（コスト後）", "勝率（%）", "最大DD（%）"],
        [1.3, 50, None],
        [".2f", ".1f", ".1f"]
    ):
        ax.set_facecolor("#F5F8FF")
        bars = ax.bar(labels, vals, color=colors, alpha=0.88, width=0.5)
        if threshold:
            ax.axhline(threshold, color="#CC3333", lw=1.0, ls="--", alpha=0.7)
        ax.set_title(title, fontproperties=_jp(9.5), color="#1A3A7A", pad=6)
        ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
        ax.tick_params(labelsize=7.5)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + max(vals) * 0.02,
                    f"{v:{fmt}}", ha="center", fontsize=9, fontweight="bold", color="#1A3A7A")

    plt.tight_layout(pad=0.9)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_equity_chart(df_is: pd.DataFrame, df_oos: pd.DataFrame) -> str:
    """IS→OOS 連結エクイティカーブ（コスト控除後）"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.5),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    def _monthly(df):
        df2 = df.sort_values("exit_date").copy()
        df2["exit_date"] = pd.to_datetime(df2["exit_date"])
        df2["month"] = df2["exit_date"].dt.to_period("M")
        mo = df2.groupby("month")["net_pnl_jpy"].sum()
        cap = INITIAL_CAPITAL
        eq, lb = [cap], [str(mo.index[0] - 1)]
        for m, p in mo.items():
            cap += p
            eq.append(cap)
            lb.append(str(m))
        return eq, lb, mo

    eq_is,  lb_is,  mo_is  = _monthly(df_is)
    eq_oos, lb_oos, mo_oos = _monthly(df_oos)

    offset = eq_is[-1]
    eq_oos_adj = [v - INITIAL_CAPITAL + offset for v in eq_oos]
    x_is  = list(range(len(eq_is)))
    x_oos = list(range(len(eq_is) - 1, len(eq_is) - 1 + len(eq_oos)))
    all_lb = lb_is + lb_oos[1:]

    ax1.plot(x_is,  [v / 10000 for v in eq_is],      color="#1A3A7A", lw=2.2, label="IS（2022-2023）")
    ax1.plot(x_oos, [v / 10000 for v in eq_oos_adj], color="#FF8800", lw=2.5, label="OOS（2024~）★", ls="--")
    ax1.axvline(len(eq_is) - 1, color="#CC4444", lw=1.2, ls=":", alpha=0.8)
    ax1.axhline(INITIAL_CAPITAL / 10000, color="#888", lw=0.8, ls=":")
    ax1.set_ylabel("資産額（万円）", fontproperties=_jp(8))
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"¥{x:.0f}万"))
    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax1.set_title("エクイティカーブ（コスト控除後）  IS→OOS 連結",
                  fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax1.legend(prop=_jp(8))
    step = max(1, len(all_lb) // 8)
    ax1.set_xticks(range(0, len(all_lb), step))
    ax1.set_xticklabels(all_lb[::step], fontsize=6.5, rotation=30)

    mo_is_vals  = [0] + [v / 10000 for v in mo_is.values]
    mo_oos_vals = [v / 10000 for v in mo_oos.values]
    x_bi  = list(range(len(mo_is_vals)))
    x_bo  = list(range(len(mo_is_vals) - 1, len(mo_is_vals) - 1 + len(mo_oos_vals)))
    ax2.bar(x_bi, mo_is_vals,  color=["#2266AA" if v >= 0 else "#CC3333" for v in mo_is_vals],  alpha=0.8, width=0.7)
    ax2.bar(x_bo, mo_oos_vals, color=["#FF8800" if v >= 0 else "#CC3333" for v in mo_oos_vals], alpha=0.8, width=0.7)
    ax2.axvline(len(mo_is_vals) - 1, color="#CC4444", lw=1.2, ls=":", alpha=0.8)
    ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_ylabel("月次P&L（万円）", fontproperties=_jp(7.5))
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}万"))
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_yearly_chart(s_is: dict, s_oos: dict) -> str:
    """年別 損益（コスト控除後）IS + OOS"""
    all_years = sorted(set(list(s_is["yearly"].keys()) + list(s_oos["yearly"].keys())))
    is_pnl  = [s_is["yearly"].get(y, {}).get("pnl", 0) / 10000  for y in all_years]
    oos_pnl = [s_oos["yearly"].get(y, {}).get("pnl", 0) / 10000 for y in all_years]

    fig, ax = plt.subplots(figsize=(10, 3.8))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    x = np.arange(len(all_years))
    w = 0.35
    ax.bar(x - w/2, is_pnl,  w,
           color=["#2266AA" if v >= 0 else "#CC3333" for v in is_pnl],  alpha=0.85, label="IS")
    ax.bar(x + w/2, oos_pnl, w,
           color=["#FF8800" if v >= 0 else "#CC3333" for v in oos_pnl], alpha=0.85, label="OOS★")
    ax.axhline(0, color="#555", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in all_years], fontproperties=_jp(9))
    ax.set_ylabel("損益（万円・コスト後）", fontproperties=_jp(8))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}万"))
    ax.set_title("年別 損益（コスト控除後）— IS vs OOS",
                 fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax.legend(prop=_jp(9))
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    for xi, (iv, ov) in enumerate(zip(is_pnl, oos_pnl)):
        if iv != 0:
            ax.text(xi - w/2, iv + (max(abs(v) for v in is_pnl+oos_pnl if v) * 0.02 if iv >= 0 else -max(abs(v) for v in is_pnl+oos_pnl if v) * 0.08),
                    f"{iv:+.0f}万", ha="center", fontsize=7, color="#1A3A7A", fontweight="bold")
        if ov != 0:
            ax.text(xi + w/2, ov + (max(abs(v) for v in is_pnl+oos_pnl if v) * 0.02 if ov >= 0 else -max(abs(v) for v in is_pnl+oos_pnl if v) * 0.08),
                    f"{ov:+.0f}万", ha="center", fontsize=7, color="#CC6600", fontweight="bold")
    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_sector_oos_chart(s_oos: dict) -> str:
    """OOS業種別PF・勝率"""
    secs  = sorted(s_oos["by_sector"].items(), key=lambda x: x[1]["pf"], reverse=True)
    names = [s[0][:8] for s in secs]
    pfs   = [s[1]["pf"] for s in secs]
    wrs   = [s[1]["wr"] for s in secs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    ax1.barh(names, pfs, color=["#FF8800" if v >= 1.3 else "#CC3333" for v in pfs], alpha=0.85)
    ax1.axvline(1.3, color="#CC3333", lw=1.0, ls="--")
    ax1.set_xlabel("PF", fontproperties=_jp(8))
    ax1.set_title("業種別 PF（OOS）", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax1.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for i, v in enumerate(pfs):
        ax1.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=8)

    ax2.barh(names, wrs, color=["#FF8800" if v >= 50 else "#CC3333" for v in wrs], alpha=0.85)
    ax2.axvline(50, color="#CC3333", lw=1.0, ls="--")
    ax2.set_xlabel("勝率（%）", fontproperties=_jp(8))
    ax2.set_title("業種別 勝率（OOS）", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax2.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for i, v in enumerate(wrs):
        ax2.text(v + 0.3, i, f"{v:.1f}%", va="center", fontsize=8)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class AdvisorReport(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  fname=FONT_PATH)
        self.add_font("YG", "B", fname=FONT_PATH)
        self.set_margins(14, 14, 14)
        self.set_auto_page_break(auto=True, margin=14)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _sec(self, title, color=BLUE):
        self.set_fill_color(*color)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 8.5)
        self.cell(0, 6.5, f"  {title}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(1.5)

    def cover(self, today: str, s_adopted_is: dict, s_oos: dict):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*AMBER)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(30)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 総括レポート（相談役向け）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(19, bold=True, color=WHITE)
        self.cell(0, 12, "セクター追いつき戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(11, bold=True, color=(255, 200, 60))
        self.cell(0, 8, "IS開発 × OOS検証 最終報告",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(35, self.get_y(), 175, self.get_y())
        self.ln(4)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"報告日: {today}  |  IS採用: 2022-01-01 ~ {IS_END}  |  OOS: {OOS_START} ~ 現在",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"対象: プライム市場 上位10業種  |  コスト: 往復0.20%込み  |  Case A（完結済みのみ）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # IS KPI
        self.set_y(115)
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, "  IS パフォーマンス（採用期間: 2022-2023）— コスト控除後",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        is_years = 2.0
        for k, v in [
            ("総トレード数",  f"{s_adopted_is['n']:,}件"),
            ("勝率",          f"{s_adopted_is['wr']}%"),
            ("PF",            f"{s_adopted_is['pf']:.2f}"),
            ("最大DD",        f"{s_adopted_is['max_dd']}%"),
            ("総損益（コスト後）", f"¥{s_adopted_is['total_pnl']:+,.0f}"),
            ("控除コスト合計",f"¥{s_adopted_is['total_cost']:,.0f}"),
            ("年次リターン",  f"約{s_adopted_is['total_pnl']/INITIAL_CAPITAL/is_years*100:.1f}%（{is_years:.0f}年単純）"),
        ]:
            self._t(8.5, color=(160, 190, 230))
            self.cell(52, 6.5, k, align="R")
            self._t(9, bold=True, color=WHITE)
            self.cell(0, 6.5, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(3)

        # OOS KPI
        oos_years = round((pd.Timestamp("today") - pd.Timestamp(OOS_START)).days / 365.25, 1)
        self.set_fill_color(*AMBER)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  OOS 検証結果（{OOS_START} ~ 現在）★ — コスト控除後",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        for k, v in [
            ("総トレード数",  f"{s_oos['n']:,}件"),
            ("勝率",          f"{s_oos['wr']}%"),
            ("PF",            f"{s_oos['pf']:.2f}"),
            ("最大DD",        f"{s_oos['max_dd']}%"),
            ("総損益（コスト後）", f"¥{s_oos['total_pnl']:+,.0f}"),
            ("控除コスト合計",f"¥{s_oos['total_cost']:,.0f}"),
            ("年次リターン",  f"約{s_oos['total_pnl']/INITIAL_CAPITAL/oos_years*100:.1f}%（{oos_years:.1f}年単純）"),
        ]:
            self._t(8.5, color=(160, 190, 230))
            self.cell(52, 6.5, k, align="R")
            self._t(9, bold=True, color=WHITE)
            self.cell(0, 6.5, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(268)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本レポートは過去データに基づくシミュレーションです。将来の投資成果を保証するものではありません。",
            align="C")

    def is_comparison_page(self, all_is_stats: list[dict], cmp_img: str):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "IS期間別 パフォーマンス比較（参考）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            "IS期間の開始年を変えた場合の成績比較。OOS: 2024-01-01~ はすべて共通。"
            "★印が今回採用したIS期間（2022-2023）。すべてコスト往復0.20%控除後。")
        self.ln(3)

        self.image(cmp_img, x=14, y=self.get_y(), w=182, h=54)
        self.ln(58)

        self._sec("IS期間別 指標一覧（コスト控除後）", color=NAVY)
        headers = ["IS期間", "件数", "勝率", "PF", "最大DD", "損益（コスト後）", "控除コスト"]
        widths  = [44, 18, 18, 16, 18, 42, 26]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        for i, s in enumerate(all_is_stats):
            adopted = "★" in s["label"]
            bg = (255, 252, 220) if adopted else (LIGHT if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B" if adopted else "", 7.5)
            self.cell(widths[0], 6, s["label"], border=1, fill=True)
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 6, f"{s['n']:,}", border=1, fill=True, align="C")
            self.cell(widths[2], 6, f"{s['wr']}%",    border=1, fill=True, align="C")
            self.cell(widths[3], 6, f"{s['pf']:.2f}", border=1, fill=True, align="C")
            self.cell(widths[4], 6, f"{s['max_dd']}%",border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if s["total_pnl"] >= 0 else RED))
            self.set_font("YG", "B", 7.5)
            self.cell(widths[5], 6, f"¥{s['total_pnl']:+,.0f}", border=1, fill=True, align="R")
            self.set_text_color(*GRAY)
            self.set_font("YG", "", 7)
            self.cell(widths[6], 6, f"¥{s['total_cost']:,.0f}", border=1, fill=True, align="R")
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        # IS年別テーブル（採用IS＝2022のみ）
        adopted_s = all_is_stats[0]
        self._sec(f"IS 年別成績（採用: {adopted_s['label']}、コスト控除後）", color=BLUE)
        h2 = ["年", "件数", "勝率", "PF", "損益（コスト後）"]
        w2 = [18, 20, 22, 22, 100]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(h2, w2):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        for i, (yr, d) in enumerate(sorted(adopted_s["yearly"].items())):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(w2[0], 6, str(yr), border=1, fill=True, align="C")
            self.set_font("YG", "", 7.5)
            self.cell(w2[1], 6, str(d["trades"]), border=1, fill=True, align="C")
            self.cell(w2[2], 6, f"{d['wr']}%",    border=1, fill=True, align="C")
            self.cell(w2[3], 6, f"{d['pf']:.2f}", border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if d["pnl"] >= 0 else RED))
            self.set_font("YG", "B", 7.5)
            self.cell(w2[4], 6, f"¥{d['pnl']:+,.0f}", border=1, fill=True, align="R")
            self.ln()
        self.set_text_color(*DARK)

    def oos_result_page(self, eq_img: str, yr_img: str, s_is: dict, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "OOS 検証結果詳細（コスト控除後）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(eq_img, x=14, y=self.get_y(), w=182, h=72)
        self.ln(76)
        self.image(yr_img, x=14, y=self.get_y(), w=182, h=52)
        self.ln(56)

        # IS vs OOS 対比テーブル
        self._sec("IS vs OOS 主要指標対比（コスト控除後）", color=NAVY)
        headers = ["指標", "IS（2022-2023）", "OOS（2024~）", "差分", "判定"]
        widths  = [35, 42, 42, 28, 35]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        def _judge(key, iv, ov):
            if key == "pf":
                if ov >= 1.3 and abs(ov - iv) / max(iv, 0.01) < 0.3:
                    return "◎ 再現", GREEN
                elif ov >= 1.3:
                    return "○ 合格", TEAL
                else:
                    return "× 要確認", RED
            elif key == "wr":
                if ov >= 50 and abs(ov - iv) < 10:
                    return "◎ 再現", GREEN
                elif ov >= 50:
                    return "○ 合格", TEAL
                else:
                    return "× 要確認", RED
            elif key == "dd":
                if ov <= 20:
                    return "◎ 許容内", GREEN
                elif ov <= 30:
                    return "○ 注意", AMBER
                else:
                    return "× 超過", RED

        rows = [
            ("勝率",   "wr", s_is["wr"],     s_oos["wr"],
             f"{s_oos['wr']-s_is['wr']:+.1f}pp", "%"),
            ("PF",     "pf", s_is["pf"],     s_oos["pf"],
             f"{s_oos['pf']-s_is['pf']:+.2f}", ""),
            ("最大DD", "dd", s_is["max_dd"], s_oos["max_dd"],
             f"{s_oos['max_dd']-s_is['max_dd']:+.1f}pp", "%"),
        ]
        for i, (name, key, iv, ov, diff, unit) in enumerate(rows):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            jtext, jcolor = _judge(key, iv, ov)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, name, border=1, fill=True)
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 6, f"{iv:.2f}{unit}" if key == "pf" else f"{iv}{unit}", border=1, fill=True, align="C")
            self.cell(widths[2], 6, f"{ov:.2f}{unit}" if key == "pf" else f"{ov}{unit}", border=1, fill=True, align="C")
            self.cell(widths[3], 6, diff, border=1, fill=True, align="C")
            self.set_text_color(*jcolor)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[4], 6, jtext, border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)

    def oos_detail_page(self, sec_img: str, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "OOS 業種別・年別 詳細成績",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(sec_img, x=14, y=self.get_y(), w=182, h=58)
        self.ln(62)

        # 業種別テーブル
        self._sec("業種別 OOS成績（コスト控除後）", color=NAVY)
        headers = ["業種", "件数", "勝率", "PF", "損益（コスト後）"]
        widths  = [50, 20, 22, 20, 70]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        for i, (sec, d) in enumerate(
                sorted(s_oos["by_sector"].items(), key=lambda x: x[1]["pf"], reverse=True)):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 5.5, sec[:12], border=1, fill=True)
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 5.5, str(d["trades"]), border=1, fill=True, align="C")
            self.cell(widths[2], 5.5, f"{d['wr']}%",    border=1, fill=True, align="C")
            self.cell(widths[3], 5.5, f"{d['pf']:.2f}", border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if d["pnl"] >= 0 else RED))
            self.set_font("YG", "B", 7.5)
            self.cell(widths[4], 5.5, f"¥{d['pnl']:+,.0f}", border=1, fill=True, align="R")
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        # OOS年別テーブル
        self._sec(f"年別 OOS成績（{OOS_START}~）— コスト控除後", color=AMBER)
        h2 = ["年", "件数", "勝率", "PF", "損益（コスト後）"]
        w2 = [18, 20, 22, 22, 100]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(h2, w2):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        for i, (yr, d) in enumerate(sorted(s_oos["yearly"].items())):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(w2[0], 6, str(yr), border=1, fill=True, align="C")
            self.set_font("YG", "", 7.5)
            self.cell(w2[1], 6, str(d["trades"]), border=1, fill=True, align="C")
            self.cell(w2[2], 6, f"{d['wr']}%",    border=1, fill=True, align="C")
            self.cell(w2[3], 6, f"{d['pf']:.2f}", border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if d["pnl"] >= 0 else RED))
            self.set_font("YG", "B", 7.5)
            self.cell(w2[4], 6, f"¥{d['pnl']:+,.0f}", border=1, fill=True, align="R")
            self.ln()
        self.set_text_color(*DARK)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  相談役向け総括レポート — セクター追いつき戦略")
    print(f"  コスト: 往復{ROUND_TRIP_COST_PCT}%控除後")
    print(f"{'='*60}\n")

    # 全シナリオ読み込み
    all_is_stats = []
    for sc in SCENARIOS:
        df_is = load_with_cost(RESULTS_DIR / sc["is_csv"])
        s = calc_summary(df_is, sc["label"])
        all_is_stats.append(s)
        print(f"  {sc['label']}: {s['n']}件  勝率{s['wr']}%  PF{s['pf']}  DD{s['max_dd']}%  損益¥{s['total_pnl']:+,.0f}  コスト¥{s['total_cost']:,.0f}")

    # 採用IS（2022）と OOS（2022ベース）
    df_is_adopted = load_with_cost(RESULTS_DIR / SCENARIOS[0]["is_csv"])
    df_oos        = load_with_cost(RESULTS_DIR / SCENARIOS[0]["oos_csv"])
    s_is  = all_is_stats[0]
    s_oos = calc_summary(df_oos, "OOS")

    print(f"\n  OOS: {s_oos['n']}件  勝率{s_oos['wr']}%  PF{s_oos['pf']}  DD{s_oos['max_dd']}%  損益¥{s_oos['total_pnl']:+,.0f}  コスト¥{s_oos['total_cost']:,.0f}")

    print("\nチャート生成中...")
    cmp_img = make_is_comparison_chart(all_is_stats)
    eq_img  = make_equity_chart(df_is_adopted, df_oos)
    yr_img  = make_yearly_chart(s_is, s_oos)
    sec_img = make_sector_oos_chart(s_oos)
    print("  完了")

    print("\nPDF生成中...")
    pdf = AdvisorReport()
    pdf.cover(today, s_is, s_oos)
    pdf.is_comparison_page(all_is_stats, cmp_img)
    pdf.oos_result_page(eq_img, yr_img, s_is, s_oos)
    pdf.oos_detail_page(sec_img, s_oos)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"advisor_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [cmp_img, eq_img, yr_img, sec_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
