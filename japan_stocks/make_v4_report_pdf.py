# -*- coding: utf-8 -*-
"""
バックテスト v4 報告書 PDF 生成
実行: python japan_stocks/make_v4_report_pdf.py

必要ファイル: japan_stocks/results/v4A_trades_*.csv, v4B_trades_*.csv
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
RESULTS_DIR = Path(__file__).parent / "results"
OUTPUT_DIR  = RESULTS_DIR / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 運用前提
INITIAL_CAPITAL = 1_000_000
POSITION_SIZE   = 100_000    # 1ポジション10万円（資産の10%）
MAX_POSITIONS   = 8          # 最大同時保有

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


# ── 最新CSVを読み込む ─────────────────────────────────────────────────────────

def load_latest_trades() -> tuple[pd.DataFrame, pd.DataFrame]:
    files_a = sorted(RESULTS_DIR.glob("v4A_trades_*.csv"), reverse=True)
    files_b = sorted(RESULTS_DIR.glob("v4B_trades_*.csv"), reverse=True)
    if not files_a or not files_b:
        raise FileNotFoundError("v4トレードCSVが見つかりません。先にbacktest_minervini_v4.pyを実行してください。")
    dfA = pd.read_csv(files_a[0])
    dfB = pd.read_csv(files_b[0])
    print(f"  ④A: {files_a[0].name}  ({len(dfA)}件)")
    print(f"  ④B: {files_b[0].name}  ({len(dfB)}件)")
    return dfA, dfB


# ── エクイティカーブ計算 ───────────────────────────────────────────────────────

def calc_equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    """
    月次エクイティカーブを計算する。

    前提:
    - 1ポジション = POSITION_SIZE円（固定）
    - 月ごとに決済したトレードのP&Lを積算
    - 同時保有数はシミュレーションせず、全トレードの月次P&Lを加算する
      （機会コストを含むため、実際より保守的な見方）
    """
    df = df.copy()
    df["exit_dt"] = pd.to_datetime(df["exit_date"])
    df["month"]   = df["exit_dt"].dt.to_period("M")
    df["pnl_yen"] = df["ret_pct"] / 100 * POSITION_SIZE

    monthly = df.groupby("month")["pnl_yen"].sum().reset_index()
    monthly = monthly.sort_values("month")

    capital = INITIAL_CAPITAL
    records = [{"month": str(monthly["month"].iloc[0] - 1),
                "capital": capital, "pnl": 0}]
    for _, row in monthly.iterrows():
        capital += row["pnl_yen"]
        records.append({
            "month"  : str(row["month"]),
            "capital": capital,
            "pnl"    : row["pnl_yen"],
        })

    return pd.DataFrame(records)


def calc_summary(df: pd.DataFrame) -> dict:
    ret = df["ret_pct"]
    ec  = calc_equity_curve(df)
    final_cap = ec["capital"].iloc[-1]

    # 年別
    df2 = df.copy()
    df2["year"] = pd.to_datetime(df2["entry_date"]).dt.year
    yearly = {}
    for yr, g in df2.groupby("year"):
        r = g["ret_pct"]
        pnl = (r / 100 * POSITION_SIZE).sum()
        yearly[yr] = {
            "trades": len(g), "avg": r.mean(), "wr": (r>0).mean()*100,
            "pf": _pf(r), "pnl_yen": pnl,
        }

    # 月次最大ドローダウン
    eq = ec["capital"].values
    running_max = np.maximum.accumulate(eq)
    drawdown = (eq - running_max) / running_max * 100
    max_dd = drawdown.min()

    # 月次最大連勝・連敗
    monthly_sign = ec["pnl"].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

    return {
        "n_trades"  : len(df),
        "avg_ret"   : ret.mean(),
        "median_ret": ret.median(),
        "win_rate"  : (ret > 0).mean() * 100,
        "pf"        : _pf(ret),
        "max_win"   : ret.max(),
        "max_loss"  : ret.min(),
        "initial"   : INITIAL_CAPITAL,
        "final"     : final_cap,
        "total_pnl" : final_cap - INITIAL_CAPITAL,
        "total_ret" : (final_cap / INITIAL_CAPITAL - 1) * 100,
        "max_dd"    : max_dd,
        "yearly"    : yearly,
        "equity"    : ec,
        "reason_dist": df["reason"].value_counts().to_dict(),
    }


def _pf(ret: pd.Series) -> float:
    w = ret[ret > 0].sum();  l = abs(ret[ret < 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


# ── チャート ──────────────────────────────────────────────────────────────────

def make_equity_chart(sA: dict, sB: dict) -> str:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#F5F8FF")

    ecA = sA["equity"]
    ecB = sB["equity"]

    # 上段: エクイティカーブ
    ax1.set_facecolor("#F5F8FF")
    ax1.plot(range(len(ecA)), ecA["capital"] / 10000,
             color="#1A3A7A", lw=2.2, label="④A MA200決済なし", zorder=5)
    ax1.plot(range(len(ecB)), ecB["capital"] / 10000,
             color="#CC4444", lw=1.8, ls="--", label="④B MA200決済あり", zorder=4)
    ax1.axhline(INITIAL_CAPITAL / 10000, color="#888", lw=0.8, ls=":")
    ax1.set_ylabel("資産額（万円）", fontproperties=_jp(8))
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(
        lambda x, _: f"¥{x:.0f}万"))
    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax1.legend(prop=_jp(8), loc="upper left", framealpha=0.85)
    ax1.set_title(f"資金¥{INITIAL_CAPITAL//10000}万円 エクイティカーブ（ポジション¥{POSITION_SIZE//10000}万円）",
                  fontproperties=_jp(9.5), color="#1A3A7A", pad=8)
    ax1.tick_params(labelsize=7)

    # 月次ラベル（半年ごと）
    n = len(ecA)
    step = max(1, n // 6)
    ticks = list(range(0, n, step))
    labels = ecA["month"].iloc[ticks].tolist()
    ax1.set_xticks(ticks)
    ax1.set_xticklabels(labels, fontsize=6.5, rotation=30)

    # 下段: 月次P&L棒グラフ
    ax2.set_facecolor("#F5F8FF")
    pnl_A = ecA["pnl"] / 10000
    colors = ["#2266AA" if v >= 0 else "#CC3333" for v in pnl_A]
    ax2.bar(range(len(pnl_A)), pnl_A, color=colors, alpha=0.8, width=0.7)
    ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_ylabel("月次P&L（万円）", fontproperties=_jp(7.5))
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}万"))
    ax2.set_xticks(ticks)
    ax2.set_xticklabels(labels, fontsize=6.5, rotation=30)
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax2.tick_params(labelsize=7)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=170, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def make_reason_chart(sA: dict, sB: dict) -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.5))
    fig.patch.set_facecolor("#F5F8FF")

    labels_map = {
        "stop_base"     : "ベース安値損切",
        "stop_breakeven": "建値損切（①②）",
        "earnings_close": "決算前クローズ（③）",
        "ma200_breach"  : "MA200決済（④B）",
        "time"          : "期間満了",
    }
    colors_map = {
        "stop_base"     : "#CC3333",
        "stop_breakeven": "#FF8800",
        "earnings_close": "#2288CC",
        "ma200_breach"  : "#884488",
        "time"          : "#228844",
    }

    for ax, s, title in [(ax1, sA, "④A MA200決済なし"),
                          (ax2, sB, "④B MA200決済あり")]:
        ax.set_facecolor("#F5F8FF")
        rd = s["reason_dist"]
        lbls  = [labels_map.get(k, k) for k in rd.keys()]
        vals  = list(rd.values())
        clrs  = [colors_map.get(k, "#999") for k in rd.keys()]
        wedges, texts, autotexts = ax.pie(
            vals, labels=None, colors=clrs,
            autopct="%1.0f%%", startangle=90,
            pctdistance=0.75, textprops={"fontsize": 7}
        )
        for at in autotexts:
            at.set_fontproperties(_jp(7))
        ax.legend(wedges, lbls, loc="lower center", prop=_jp(6.5),
                  bbox_to_anchor=(0.5, -0.25), ncol=2, framealpha=0.8)
        ax.set_title(title, fontproperties=_jp(9), color="#1A3A7A", pad=8)

    plt.tight_layout(pad=1.0)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def make_yearly_chart(sA: dict, sB: dict) -> str:
    years = sorted(set(list(sA["yearly"].keys()) + list(sB["yearly"].keys())))
    x = np.arange(len(years))
    w = 0.35

    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    avg_A = [sA["yearly"].get(y, {}).get("avg", 0) for y in years]
    avg_B = [sB["yearly"].get(y, {}).get("avg", 0) for y in years]

    barsA = ax.bar(x - w/2, avg_A, w, label="④A MA200決済なし",
                   color=["#2266AA" if v >= 0 else "#CC4444" for v in avg_A],
                   alpha=0.85)
    barsB = ax.bar(x + w/2, avg_B, w, label="④B MA200決済あり",
                   color=["#6699CC" if v >= 0 else "#FF8877" for v in avg_B],
                   alpha=0.85, hatch="//")

    ax.axhline(0, color="#555", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], fontsize=8)
    ax.set_ylabel("平均リターン/トレード（%）", fontproperties=_jp(8))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:+.1f}%"))
    ax.legend(prop=_jp(8), framealpha=0.85)
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax.set_title("年別 平均トレードリターン比較", fontproperties=_jp(9.5),
                 color="#1A3A7A", pad=8)
    ax.tick_params(labelsize=8)
    for bars in [barsA, barsB]:
        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:+.1f}%",
                        xy=(bar.get_x() + bar.get_width()/2, h),
                        xytext=(0, 3 if h >= 0 else -10),
                        textcoords="offset points",
                        ha="center", va="bottom" if h >= 0 else "top",
                        fontsize=7)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


# ── PDF クラス ────────────────────────────────────────────────────────────────

class ReportPDF(FPDF):
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

    def cover(self, today: str, sA: dict, sB: dict):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(42)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 バックテストレポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(22, bold=True, color=WHITE)
        self.cell(0, 14, "ミネルヴィニ戦略 v4",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(13, bold=True, color=(0, 210, 160))
        self.cell(0, 9, "バックテスト検証報告書",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(6)
        self._t(9, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  検証市場: 東証プライム 1,555銘柄",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, "IS期間: 2020年1月〜2024年12月  |  OOS: 2025年〜（封印中）  |  初期資金: ¥1,000,000",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # サマリーボックス
        self.set_y(155)
        for label, s, color in [
            ("④A  MA200割れ決済なし（推奨候補）", sA, TEAL),
            ("④B  MA200割れ決済あり（比較案）",   sB, AMBER),
        ]:
            self.set_fill_color(*color)
            self.set_text_color(*WHITE)
            self.set_font("YG", "B", 9)
            self.cell(0, 7, f"  {label}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            metrics = [
                ("最終資産",       f"¥{s['final']:,.0f}  （+¥{s['total_pnl']:,.0f}）"),
                ("総リターン",     f"{s['total_ret']:+.1f}%"),
                ("PF / 勝率",      f"{s['pf']:.2f}  /  {s['win_rate']:.1f}%"),
                ("最大DD",         f"{s['max_dd']:.1f}%"),
            ]
            for k, v in metrics:
                self._t(9, color=(140, 170, 220))
                self.cell(38, 7, k, align="R")
                self._t(9, bold=True, color=WHITE)
                self.cell(0, 7, f"  {v}",
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(4)

        self.set_y(268)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            "本レポートは過去データに基づくシミュレーションです。将来の投資成果を保証するものではありません。\n"
            "投資判断はご自身の責任で行ってください。  |  FxCompany 調査部門（AI孫正義）",
            align="C")

    def equity_page(self, equity_img: str, sA: dict, sB: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "エクイティカーブ  ─  資金¥100万の推移",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self._t(8, color=GRAY)
        self.multi_cell(0, 5.5,
            f"前提: 1ポジション¥{POSITION_SIZE//10000}万円（資産の10%）・固定額。"
            "月次で決済トレードのP&Lを積算。同時保有上限は考慮せず全シグナルを使用。")
        self.ln(2)

        self.image(equity_img, x=14, y=self.get_y(), w=182, h=108)
        self.ln(112)

        # KPIテーブル
        self._sec("資金シミュレーション サマリー")
        headers = ["指標", "④A MA200決済なし", "④B MA200決済あり", "v3（参考）"]
        widths  = [42, 48, 48, 44]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        rows = [
            ("初期資金",       "¥1,000,000",          "¥1,000,000",           "¥1,000,000"),
            ("最終資産",
             f"¥{sA['final']:,.0f}",
             f"¥{sB['final']:,.0f}",
             "─"),
            ("総損益",
             f"¥{sA['total_pnl']:+,.0f}",
             f"¥{sB['total_pnl']:+,.0f}",
             "─"),
            ("総リターン",
             f"{sA['total_ret']:+.1f}%",
             f"{sB['total_ret']:+.1f}%",
             "─"),
            ("トレード数",
             f"{sA['n_trades']:,}",
             f"{sB['n_trades']:,}",
             "3,189"),
            ("平均リターン/T",
             f"{sA['avg_ret']:+.2f}%",
             f"{sB['avg_ret']:+.2f}%",
             "+4.5%"),
            ("勝率",
             f"{sA['win_rate']:.1f}%",
             f"{sB['win_rate']:.1f}%",
             "50.0%"),
            ("PF",
             f"{sA['pf']:.2f}",
             f"{sB['pf']:.2f}",
             "1.78"),
            ("最大DD（月次）",
             f"{sA['max_dd']:.1f}%",
             f"{sB['max_dd']:.1f}%",
             "─"),
        ]
        for i, row in enumerate(rows):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, row[0], border=1, fill=True)
            self.set_font("YG", "", 7.5)
            for val, w in zip(row[1:], widths[1:]):
                self.cell(w, 6, val, border=1, fill=True, align="C")
            self.ln()
        self.set_text_color(*DARK)

    def detail_page(self, reason_img: str, yearly_img: str,
                    sA: dict, sB: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "決済理由 & 年別分析",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(reason_img, x=14, y=self.get_y(), w=182, h=64)
        self.ln(67)

        self.image(yearly_img, x=14, y=self.get_y(), w=182, h=62)
        self.ln(65)

        # 年別詳細テーブル
        self._sec("年別詳細（④A MA200決済なし）", color=BLUE)
        years = sorted(sA["yearly"].keys())
        self._yearly_table(sA["yearly"], years)
        self.ln(3)

        self._sec("年別詳細（④B MA200決済あり）", color=AMBER)
        self._yearly_table(sB["yearly"], years)

    def _yearly_table(self, yearly: dict, years: list):
        headers = ["年", "件数", "平均リターン", "勝率", "PF", "年間損益（¥10万/T）"]
        widths  = [16, 18, 30, 20, 16, 82]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        for i, yr in enumerate(years):
            d = yearly.get(yr, {})
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            avg = d.get("avg", 0)
            pnl = d.get("pnl_yen", 0)
            pnl_c = GREEN if pnl >= 0 else RED
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, str(yr), border=1, fill=True, align="C")
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 6, str(d.get("trades", 0)), border=1, fill=True, align="C")
            self.cell(widths[2], 6, f"{avg:+.2f}%", border=1, fill=True, align="C")
            self.cell(widths[3], 6, f"{d.get('wr', 0):.0f}%", border=1, fill=True, align="C")
            self.cell(widths[4], 6, f"{d.get('pf', 0):.2f}", border=1, fill=True, align="C")
            self.set_text_color(*pnl_c)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[5], 6, f"¥{pnl:+,.0f}", border=1, fill=True, align="R")
            self.set_text_color(*DARK)
            self.ln()

    def discussion_page(self, today: str):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "IS期間 考察 & 次フェーズ方針",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        # v1〜v4の進化
        self._sec("v1〜v4 戦略進化の歴史")
        headers = ["Ver", "エントリー", "損切り", "追加条件", "PF(IS)", "勝率(IS)"]
        widths  = [12, 46, 40, 36, 18, 16]
        rows = [
            ("v1", "月次機械的買い",          "なし",         "─",              "1.20", "47%"),
            ("v2", "20日高値ブレイクアウト",  "-7%固定",      "─",              "1.71", "40%"),
            ("v3", "ベース高値ブレイク",       "ベース安値",   "─",              "1.78", "50%"),
            ("v4", "ベース高値ブレイク",       "建値損切①②", "決算クローズ③", "1.27", "28%"),
        ]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()
        for i, row in enumerate(rows):
            is_v4 = row[0] == "v4"
            bg = (220, 255, 235) if is_v4 else (LIGHT if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B" if is_v4 else "", 7.5)
            self.cell(widths[0], 6, row[0], border=1, fill=True, align="C")
            for val, w in zip(row[1:], widths[1:]):
                self.cell(w, 6, val, border=1, fill=True)
            self.ln()
        self.set_text_color(*DARK)
        self.ln(4)

        # IS期間の主要発見
        self._sec("IS期間（2020〜2024年）の主要発見", color=AMBER)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "【発見1: 年次バラツキが大きい】\n"
            "PF 3.06（2023年）vs PF 0.66（2024年）と年によって結果が大きく異なる。\n"
            "戦略が相場環境に強く依存していることを示す。\n\n"
            "【発見2: 2023年が突出した理由】\n"
            "2023年は日本株の大幅上昇年（外国人買い・バフェット効果・円安恩恵）。\n"
            "ミネルヴィニ戦略はトレンドフォロー型のため、明確な上昇相場で機能しやすい。\n\n"
            "【発見3: 2021・2024年が苦戦した理由】\n"
            "2021年: コロナ後の期待剥落、方向感のない横ばい相場。\n"
            "2024年: 8月の急落（令和のブラックマンデー）でシグナルが多数発生したが空振り。\n\n"
            "【発見4: ④A vs ④B（MA200決済）】\n"
            "IS全体では④A PF 1.27 vs ④B PF 1.20と差が小さい。\n"
            "悪い年の損失軽減効果と良い年の機会損失がほぼ相殺されている。判断保留継続。")
        self.ln(4)

        # 次フェーズ方針（v5）
        self._sec("v5 設計方針（IS完了後の次ステップ）", color=TEAL)
        items = [
            ("同時保有5銘柄集中",
             "現状: 全シグナルを並列実行（実運用不可）\n"
             "v5: 最大5銘柄、EPSスコア上位から選択。1銘柄¥200K（資金の20%）。\n"
             "期待効果: 質の高いトレードに集中 → PF改善・実運用可能な設計へ。"),
            ("ドローダウン制御（3層）",
             "第1層: 個別ストップ（実装済み）\n"
             "第2層: 月次損失キャップ（月-5%超で新規停止） ← 新規\n"
             "第3層: 市場環境フィルター（日経MA200割れで新規停止） ← 検証済み\n"
             "閾値はISデータで最適化してから確定する。"),
            ("OOS開封条件",
             "v5でIS PF 2.0以上・勝率35%以上・月次DDキャップ設定済み\n"
             "の3条件が揃った時点で初めてOOS（2025年分）を開封して最終検証する。"),
        ]
        for title, desc in items:
            self.set_font("YG", "B", 8.5)
            self.set_text_color(*TEAL)
            self.cell(0, 6, f"▶ {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("YG", "", 8.5)
            self.set_text_color(*DARK)
            self.set_x(self.l_margin + 4)
            self.multi_cell(0, 5.5, desc)
            self.ln(1)

        self.ln(4)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5.5,
            f"作成日: {today}  |  IS: 2020-01-01〜2024-12-31  |  OOS: 2025-01-01〜（封印中）\n"
            "FxCompany 調査部門（AI孫正義）  |  本レポートは過去データに基づくシミュレーションです。"
            "将来の投資成果を保証するものではありません。")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  v4 バックテスト 報告書 PDF 生成")
    print(f"{'='*55}\n")

    print("トレードデータ読み込み中...")
    dfA, dfB = load_latest_trades()

    print("\nサマリー計算中...")
    sA = calc_summary(dfA)
    sB = calc_summary(dfB)

    print(f"  ④A: 最終資産 ¥{sA['final']:,.0f}  (+¥{sA['total_pnl']:,.0f})")
    print(f"  ④B: 最終資産 ¥{sB['final']:,.0f}  (+¥{sB['total_pnl']:,.0f})")

    print("\nチャート生成中...")
    equity_img = make_equity_chart(sA, sB)
    reason_img = make_reason_chart(sA, sB)
    yearly_img = make_yearly_chart(sA, sB)
    print("  完了")

    print("\nPDF生成中...")
    pdf = ReportPDF()
    pdf.cover(today, sA, sB)
    pdf.equity_page(equity_img, sA, sB)
    pdf.detail_page(reason_img, yearly_img, sA, sB)
    pdf.discussion_page(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"backtest_v4_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [equity_img, reason_img, yearly_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n✓ PDF生成完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
