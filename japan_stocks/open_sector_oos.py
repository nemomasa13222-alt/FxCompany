# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 OOS開封スクリプト
実行: python japan_stocks/open_sector_oos.py

【警告】
  戦略・パラメータが完全に確定した後に1回だけ実行すること。
  IS: 2022-01-01 ~ 2023-12-31 (10業種選定済み)
  OOS: 2024-01-01 ~ 現在
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
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

IS_START        = "2022-01-01"
IS_END          = "2023-12-31"
OOS_START       = "2024-01-01"
INITIAL_CAPITAL = 1_000_000
ROUND_TRIP_COST_PCT = 0.20

# v2-f: TOP10候補プール→動的5業種選別・risk0.5%・stop1.5%・min_gap3%
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


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _pf(pnl: pd.Series) -> float:
    w = pnl[pnl > 0].sum()
    l = abs(pnl[pnl <= 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


# ── データ読み込み ─────────────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    df_is  = pd.read_csv(IS_CSV)
    df_oos = pd.read_csv(OOS_CSV)
    # コスト控除（往復0.20%）
    for df in [df_is, df_oos]:
        df["cost_jpy"]    = df["entry_price"] * df["shares"] * ROUND_TRIP_COST_PCT / 100
        df["net_pnl_jpy"] = df["pnl_jpy"] - df["cost_jpy"]
    print(f"  IS : {IS_CSV.name}  ({len(df_is)}件)")
    print(f"  OOS: {OOS_CSV.name}  ({len(df_oos)}件)")
    return df_is, df_oos


# ── サマリー計算（コスト控除後） ───────────────────────────────────────────────

def calc_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    pnl = df["net_pnl_jpy"]   # コスト控除後

    equity = INITIAL_CAPITAL
    peak   = equity
    max_dd = 0.0
    for _, row in df.sort_values("exit_date").iterrows():
        equity += row["net_pnl_jpy"]
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
        "n"        : len(df),
        "wr"       : round((pnl > 0).mean() * 100, 1),
        "pf"       : _pf(pnl),
        "avg_win"  : round(wins.mean()) if not wins.empty else 0,
        "avg_loss" : round(loss.mean()) if not loss.empty else 0,
        "total_pnl": round(pnl.sum()),
        "max_dd"   : round(max_dd, 1),
        "final"    : round(INITIAL_CAPITAL + pnl.sum()),
        "by_sector": by_sector,
        "yearly"   : yearly,
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
    }


# ── チャート ──────────────────────────────────────────────────────────────────

def make_equity_chart(df_is: pd.DataFrame, df_oos: pd.DataFrame) -> str:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.5),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    def _equity_series(df):
        df2 = df.sort_values("exit_date").copy()
        df2["exit_date"] = pd.to_datetime(df2["exit_date"])
        df2["month"] = df2["exit_date"].dt.to_period("M")
        monthly = df2.groupby("month")["net_pnl_jpy"].sum()
        capital = INITIAL_CAPITAL
        eq, labels = [capital], [str(monthly.index[0] - 1)]
        for mo, pnl in monthly.items():
            capital += pnl
            eq.append(capital)
            labels.append(str(mo))
        return eq, labels, monthly

    eq_is,  lb_is,  mo_is  = _equity_series(df_is)
    eq_oos, lb_oos, mo_oos = _equity_series(df_oos)

    # IS → OOS 連結
    offset = eq_is[-1]
    eq_oos_adj = [v - INITIAL_CAPITAL + offset for v in eq_oos]

    x_is  = list(range(len(eq_is)))
    x_oos = list(range(len(eq_is) - 1, len(eq_is) - 1 + len(eq_oos)))
    all_labels = lb_is + lb_oos[1:]

    ax1.plot(x_is,  [v / 10000 for v in eq_is],      color="#1A3A7A", lw=2.2, label="IS", zorder=5)
    ax1.plot(x_oos, [v / 10000 for v in eq_oos_adj], color="#FF8800", lw=2.2, label="OOS★", zorder=5, ls="--")
    ax1.axvline(len(eq_is) - 1, color="#CC4444", lw=1.2, ls=":", alpha=0.8)
    ax1.axhline(INITIAL_CAPITAL / 10000, color="#888", lw=0.8, ls=":")
    ax1.set_ylabel("資産額（万円）", fontproperties=_jp(8))
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"¥{x:.0f}万"))
    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax1.set_title("エクイティカーブ  IS（青）vs OOS（橙）", fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax1.legend(prop=_jp(8))
    step = max(1, len(all_labels) // 8)
    ax1.set_xticks(list(range(0, len(all_labels), step)))
    ax1.set_xticklabels(all_labels[::step], fontsize=6.5, rotation=30)

    # 月次P&L（IS青・OOS橙）
    mo_vals_is  = [0] + [v / 10000 for v in mo_is.values]
    mo_vals_oos = [v / 10000 for v in mo_oos.values]
    x_bar_is  = list(range(len(mo_vals_is)))
    x_bar_oos = list(range(len(mo_vals_is) - 1, len(mo_vals_is) - 1 + len(mo_vals_oos)))

    ax2.bar(x_bar_is,  mo_vals_is,  color=["#2266AA" if v >= 0 else "#CC3333" for v in mo_vals_is],  alpha=0.8, width=0.7)
    ax2.bar(x_bar_oos, mo_vals_oos, color=["#FF8800" if v >= 0 else "#CC3333" for v in mo_vals_oos], alpha=0.8, width=0.7)
    ax2.axvline(len(mo_vals_is) - 1, color="#CC4444", lw=1.2, ls=":", alpha=0.8)
    ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_ylabel("月次P&L（万円）", fontproperties=_jp(7.5))
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}万"))
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_sector_compare_chart(s_is: dict, s_oos: dict) -> str:
    """業種別 IS vs OOS PF比較"""
    all_secs = sorted(set(list(s_is["by_sector"].keys()) + list(s_oos["by_sector"].keys())))
    pf_is  = [s_is["by_sector"].get(s, {}).get("pf", 0) for s in all_secs]
    pf_oos = [s_oos["by_sector"].get(s, {}).get("pf", 0) for s in all_secs]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    x = np.arange(len(all_secs))
    w = 0.35
    ax.barh(x + w/2, pf_is,  w, color="#2266AA", alpha=0.85, label="IS")
    ax.barh(x - w/2, pf_oos, w, color="#FF8800", alpha=0.85, label="OOS★")
    ax.axvline(1.0, color="#555", lw=1.0, ls="--")
    ax.set_yticks(x)
    ax.set_yticklabels([s[:10] for s in all_secs], fontproperties=_jp(8))
    ax.set_xlabel("PF", fontproperties=_jp(8))
    ax.set_title("業種別 PF  IS vs OOS", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax.legend(prop=_jp(8))
    ax.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for i, (vi, vo) in enumerate(zip(pf_is, pf_oos)):
        ax.text(vi + 0.02, i + w/2, f"{vi:.2f}", va="center", fontsize=7)
        ax.text(vo + 0.02, i - w/2, f"{vo:.2f}", va="center", fontsize=7, color="#FF8800")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class SectorOosReport(FPDF):
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

    def cover(self, today: str, s_is: dict, s_oos: dict):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*AMBER)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(35)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 OOS開封レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "セクター追いつき戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(12, bold=True, color=(255, 200, 60))
        self.cell(0, 9, "Out-of-Sample 開封結果",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(5)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"開封日: {today}  |  IS: {IS_START}~{IS_END}  |  OOS: {OOS_START}~現在",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, "保有中トレード: Case A（除外）— 完結済みトレードのみ集計",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # IS / OOS KPI 並列
        self.set_y(130)
        for s, color, tag in [(s_is, BLUE, "IS（開発期間）"), (s_oos, AMBER, "OOS（検証期間）★")]:
            self.set_fill_color(*color)
            self.set_text_color(*WHITE)
            self.set_font("YG", "B", 9)
            self.cell(0, 7, f"  {tag}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            rows = [
                ("総トレード数", f"{s['n']:,}件"),
                ("勝率",         f"{s['wr']}%"),
                ("PF",           f"{s['pf']:.2f}"),
                ("最大DD",       f"{s['max_dd']}%"),
                ("総損益",       f"¥{s['total_pnl']:+,.0f}"),
                ("最終資産",     f"¥{s['final']:,.0f}（初期¥{INITIAL_CAPITAL:,.0f}）"),
            ]
            for k, v in rows:
                self._t(8.5, color=(160, 190, 230))
                self.cell(48, 6.5, k, align="R")
                self._t(9, bold=True, color=WHITE)
                self.cell(0, 6.5, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(3)

        self.set_y(268)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本レポートは過去データに基づくシミュレーションです。将来の投資成果を保証するものではありません。",
            align="C")

    def result_page(self, eq_img: str, sec_img: str, s_is: dict, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "IS vs OOS 比較分析",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(eq_img,  x=14, y=self.get_y(), w=182, h=70)
        self.ln(74)
        self.image(sec_img, x=14, y=self.get_y(), w=182, h=58)
        self.ln(62)

        # 指標比較テーブル
        self._sec("主要指標  IS vs OOS 対比（コスト控除前）", color=NAVY)
        headers = ["指標", "IS（2022-2023）", "OOS（2024~）", "差分", "判定"]
        widths  = [35, 42, 42, 28, 35]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        def _judge(key, is_val, oos_val):
            if key == "pf":
                if oos_val >= 1.3 and abs(oos_val - is_val) / max(is_val, 0.01) < 0.3:
                    return "◎ 再現", GREEN
                elif oos_val >= 1.3:
                    return "○ 合格", TEAL
                else:
                    return "× 要確認", RED
            elif key == "wr":
                if oos_val >= 50 and abs(oos_val - is_val) < 10:
                    return "◎ 再現", GREEN
                elif oos_val >= 50:
                    return "○ 合格", TEAL
                else:
                    return "× 要確認", RED
            elif key == "dd":
                if oos_val <= 20:
                    return "◎ 許容内", GREEN
                elif oos_val <= 30:
                    return "○ 注意", AMBER
                else:
                    return "× 要確認", RED

        rows_data = [
            ("勝率",   "wr",  f"{s_is['wr']}%",        f"{s_oos['wr']}%",        f"{s_oos['wr']-s_is['wr']:+.1f}pp"),
            ("PF",     "pf",  f"{s_is['pf']:.2f}",     f"{s_oos['pf']:.2f}",     f"{s_oos['pf']-s_is['pf']:+.2f}"),
            ("最大DD", "dd",  f"{s_is['max_dd']}%",    f"{s_oos['max_dd']}%",    f"{s_oos['max_dd']-s_is['max_dd']:+.1f}pp"),
        ]
        for i, (name, key, iv, ov, diff) in enumerate(rows_data):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            is_num  = float(iv.replace("%", "").replace("+", ""))
            oos_num = float(ov.replace("%", "").replace("+", ""))
            jtext, jcolor = _judge(key, is_num, oos_num)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, name, border=1, fill=True)
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 6, iv,   border=1, fill=True, align="C")
            self.cell(widths[2], 6, ov,   border=1, fill=True, align="C")
            self.cell(widths[3], 6, diff, border=1, fill=True, align="C")
            self.set_text_color(*jcolor)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[4], 6, jtext, border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        # OOS 年別テーブル
        self._sec(f"OOS 年別詳細（{OOS_START}~）", color=AMBER)
        h2 = ["年", "件数", "勝率", "PF", "損益（円）"]
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

    def sector_detail_page(self, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "OOS 業種別詳細成績",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("業種別 OOS成績（PF順）", color=NAVY)
        headers = ["業種", "件数", "勝率", "PF", "損益（円）"]
        widths  = [50, 20, 22, 20, 70]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()

        secs = sorted(s_oos["by_sector"].items(), key=lambda x: x[1]["pf"], reverse=True)
        for i, (sec, d) in enumerate(secs):
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

        # 決済理由
        self._sec("OOS 決済理由", color=TEAL)
        label_map = {
            "target": "利確（追いつき）",
            "stop":   "ストップロス",
            "time":   "時間切れ",
            "end":    "期間終了強制",
        }
        headers2 = ["決済理由", "件数", "割合"]
        widths2  = [60, 30, 92]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers2, widths2):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        total = sum(s_oos["exit_reasons"].values())
        for i, (reason, cnt) in enumerate(sorted(s_oos["exit_reasons"].items(),
                                                   key=lambda x: x[1], reverse=True)):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths2[0], 6, label_map.get(reason, reason), border=1, fill=True)
            self.set_font("YG", "", 7.5)
            self.cell(widths2[1], 6, str(cnt), border=1, fill=True, align="C")
            self.cell(widths2[2], 6, f"{cnt/total*100:.1f}%", border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  ★ OOS 開封  セクター追いつき戦略")
    print(f"  IS: {IS_START} ~ {IS_END}")
    print(f"  OOS: {OOS_START} ~ 現在")
    print(f"  保有中トレード: Case A（除外）")
    print(f"{'='*60}\n")

    print("データ読み込み中...")
    df_is, df_oos = load_data()

    print("\nサマリー計算中...")
    s_is  = calc_summary(df_is)
    s_oos = calc_summary(df_oos)

    print(f"  IS  : {s_is['n']}件  勝率{s_is['wr']}%  PF{s_is['pf']}  DD{s_is['max_dd']}%  損益¥{s_is['total_pnl']:+,.0f}")
    print(f"  OOS : {s_oos['n']}件  勝率{s_oos['wr']}%  PF{s_oos['pf']}  DD{s_oos['max_dd']}%  損益¥{s_oos['total_pnl']:+,.0f}")

    print("\nチャート生成中...")
    eq_img  = make_equity_chart(df_is, df_oos)
    sec_img = make_sector_compare_chart(s_is, s_oos)
    print("  完了")

    print("\nPDF生成中...")
    pdf = SectorOosReport()
    pdf.cover(today, s_is, s_oos)
    pdf.result_page(eq_img, sec_img, s_is, s_oos)
    pdf.sector_detail_page(s_oos)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"sector_oos_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [eq_img, sec_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
