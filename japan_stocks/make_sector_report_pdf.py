# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 バックテスト報告書 PDF生成
実行: python japan_stocks/make_sector_report_pdf.py
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

INITIAL_CAPITAL = 1_000_000
IS_END    = "2023-12-31"
OOS_START = "2024-01-01"

# --is-start で上書き可能（run_backtest.py と合わせる）
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--is-start", default="2022-01-01")
_args, _ = _parser.parse_known_args()
IS_START = _args.is_start

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


def _pf(ret_series: pd.Series) -> float:
    w = ret_series[ret_series > 0].sum()
    l = abs(ret_series[ret_series <= 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


# ── データ読み込み ─────────────────────────────────────────────────────────────

def load_latest() -> tuple[pd.DataFrame, pd.DataFrame]:
    is_files  = sorted(RESULTS_DIR.glob("sector_is_*.csv"),  reverse=True)
    oos_files = sorted(RESULTS_DIR.glob("sector_oos_*.csv"), reverse=True)
    if not is_files:
        raise FileNotFoundError("sector_is_*.csv が見つかりません")
    df_is  = pd.read_csv(is_files[0])
    df_oos = pd.read_csv(oos_files[0]) if oos_files else pd.DataFrame()
    print(f"  IS : {is_files[0].name}  ({len(df_is)}件)")
    if not df_oos.empty:
        print(f"  OOS: {oos_files[0].name} ({len(df_oos)}件）※封印中")
    return df_is, df_oos


def calc_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    pnl  = df["pnl_jpy"]
    wins = df[pnl > 0]
    loss = df[pnl <= 0]

    equity = INITIAL_CAPITAL
    peak   = equity
    max_dd = 0.0
    for _, row in df.sort_values("exit_date").iterrows():
        equity += row["pnl_jpy"]
        peak    = max(peak, equity)
        dd      = (peak - equity) / peak * 100
        max_dd  = max(max_dd, dd)

    # 業種別
    by_sector = {}
    for sec, g in df.groupby("sector"):
        r = g["pnl_jpy"]
        by_sector[sec] = {
            "trades": len(g),
            "wr"    : round((r > 0).mean() * 100, 1),
            "pf"    : _pf(r),
            "pnl"   : round(r.sum()),
        }

    return {
        "n"       : len(df),
        "wr"      : round((pnl > 0).mean() * 100, 1),
        "pf"      : _pf(pnl),
        "avg_win" : round(wins["pnl_jpy"].mean()) if not wins.empty else 0,
        "avg_loss": round(loss["pnl_jpy"].mean()) if not loss.empty else 0,
        "total_pnl"  : round(pnl.sum()),
        "total_cost" : round(df["pnl_jpy"].sum() - df["pnl_jpy"].sum()),  # net = gross here
        "max_dd"  : round(max_dd, 1),
        "final"   : round(INITIAL_CAPITAL + pnl.sum()),
        "by_sector": by_sector,
    }


# ── チャート ──────────────────────────────────────────────────────────────────

def make_equity_chart(df: pd.DataFrame, title: str) -> str:
    df2 = df.sort_values("exit_date").copy()
    df2["exit_date"] = pd.to_datetime(df2["exit_date"])
    df2["month"] = df2["exit_date"].dt.to_period("M")
    monthly = df2.groupby("month")["pnl_jpy"].sum()

    capital = INITIAL_CAPITAL
    eq = [capital]
    labels = [str(monthly.index[0] - 1)]
    for mo, pnl in monthly.items():
        capital += pnl
        eq.append(capital)
        labels.append(str(mo))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.5),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    ax1.plot(range(len(eq)), [v / 10000 for v in eq],
             color="#1A3A7A", lw=2.2, zorder=5)
    ax1.axhline(INITIAL_CAPITAL / 10000, color="#888", lw=0.8, ls=":")
    ax1.set_ylabel("資産額（万円）", fontproperties=_jp(8))
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"¥{x:.0f}万"))
    ax1.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax1.set_title(title, fontproperties=_jp(10), color="#1A3A7A", pad=8)
    step = max(1, len(eq) // 6)
    ax1.set_xticks(range(0, len(eq), step))
    ax1.set_xticklabels(labels[::step], fontsize=6.5, rotation=30)
    ax1.tick_params(labelsize=7)

    monthly_pnl = [0] + [v / 10000 for v in monthly.values]
    clrs = ["#2266AA" if v >= 0 else "#CC3333" for v in monthly_pnl]
    ax2.bar(range(len(monthly_pnl)), monthly_pnl, color=clrs, alpha=0.8, width=0.7)
    ax2.axhline(0, color="#888", lw=0.8)
    ax2.set_ylabel("月次P&L（万円）", fontproperties=_jp(7.5))
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}万"))
    ax2.set_xticks(range(0, len(monthly_pnl), step))
    ax2.set_xticklabels(labels[::step], fontsize=6.5, rotation=30)
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax2.tick_params(labelsize=7)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_sector_bar(by_sector: dict) -> str:
    secs = sorted(by_sector.items(), key=lambda x: x[1]["pf"], reverse=True)
    names = [s[0][:8] for s in secs]
    pfs   = [s[1]["pf"] for s in secs]
    wrs   = [s[1]["wr"] for s in secs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
    fig.patch.set_facecolor("#F5F8FF")
    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    clrs_pf = ["#2266AA" if v >= 1.0 else "#CC3333" for v in pfs]
    ax1.barh(names, pfs, color=clrs_pf, alpha=0.85)
    ax1.axvline(1.0, color="#555", lw=1.0, ls="--")
    ax1.set_xlabel("PF", fontproperties=_jp(8))
    ax1.set_title("業種別 PF", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax1.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for i, v in enumerate(pfs):
        ax1.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=7.5)
    ax1.tick_params(labelsize=7.5)

    clrs_wr = ["#2266AA" if v >= 50 else "#CC3333" for v in wrs]
    ax2.barh(names, wrs, color=clrs_wr, alpha=0.85)
    ax2.axvline(50, color="#555", lw=1.0, ls="--")
    ax2.set_xlabel("勝率（%）", fontproperties=_jp(8))
    ax2.set_title("業種別 勝率", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax2.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for i, v in enumerate(wrs):
        ax2.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=7.5)
    ax2.tick_params(labelsize=7.5)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class SectorReportPDF(FPDF):
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

    def cover(self, s: dict, today: str, n_sectors: int, is_years: float = 2.0):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(38)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 バックテストレポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "セクター追いつき戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(11, bold=True, color=(0, 210, 160))
        self.cell(0, 8, "Sector Catch-Up Strategy",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(5)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  IS期間: {IS_START} ~ {IS_END}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"対象業種: 上位{n_sectors}業種（IS成績選定）  |  OOS: {OOS_START}~ 封印中",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # KPIボックス
        self.set_y(145)
        self.set_fill_color(*TEAL)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, "  IS パフォーマンス サマリー（コスト0.20%込み）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        metrics = [
            ("総トレード数",   f"{s['n']:,}件"),
            ("勝率",           f"{s['wr']}%"),
            ("PF",             f"{s['pf']:.2f}"),
            ("最大DD",         f"{s['max_dd']}%"),
            ("総損益",         f"¥{s['total_pnl']:+,.0f}"),
            ("最終資産",       f"¥{s['final']:,.0f}（初期¥{INITIAL_CAPITAL:,.0f}）"),
            ("年次リターン",   f"約{s['total_pnl']/INITIAL_CAPITAL/is_years*100:.1f}%（{is_years}年単純）"),
        ]
        for k, v in metrics:
            self._t(8.5, color=(160, 190, 230))
            self.cell(45, 6.5, k, align="R")
            self._t(9, bold=True, color=WHITE)
            self.cell(0, 6.5, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(268)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本レポートは過去データに基づくシミュレーションです。将来の投資成果を保証するものではありません。",
            align="C")

    def equity_page(self, equity_img: str, sector_img: str, s: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "エクイティカーブ  &  業種別成績",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            "前提: 1業種あたり最大3ポジション・リスク1%固定。"
            "各業種で乖離の大きい銘柄上位3件を保有。コスト往復0.20%込み。")
        self.ln(2)

        self.image(equity_img, x=14, y=self.get_y(), w=182, h=82)
        self.ln(86)
        self.image(sector_img, x=14, y=self.get_y(), w=182, h=60)
        self.ln(64)

        # 業種別テーブル
        self._sec("業種別 詳細成績（IS期間）", color=NAVY)
        headers = ["業種", "件数", "勝率", "PF", "損益（円）"]
        widths  = [50, 20, 22, 20, 70]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()

        secs = sorted(s["by_sector"].items(), key=lambda x: x[1]["pf"], reverse=True)
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

    def discussion_page(self, today: str):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "戦略概要 & 次フェーズ方針",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        self._sec("戦略ロジック", color=BLUE)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            "【仮説】セクター全体が上昇した後、まだ動いていない遅行株・中間株は"
            "セクター指数に向かって「追いつく」動きをする。\n\n"
            "【エントリー条件（3条件すべて）】\n"
            "  1. セクター指数が直近5日間で +2.0% 以上上昇\n"
            "  2. 銘柄がクロスコリレーション分析で「中間株」または「遅行株」に分類\n"
            "  3. 銘柄の乖離（セクター上昇率 - 銘柄上昇率）>= +1.5%\n\n"
            "【エグジット条件】\n"
            "  A. 利確: 乖離が 0.5% 以下に縮小\n"
            "  B. 損切: エントリー価格から -3%\n"
            "  C. 時間切れ: 10営業日経過\n\n"
            "【業種選定】IS成績（PF順）上位10業種に絞り込み。"
            "残り23業種は監視し、成績が乖離したら再選定する。")
        self.ln(3)

        self._sec("IS / OOS 設計", color=AMBER)
        self._t(8.5)
        self.multi_cell(0, 5.5,
            f"IS（開発期間）: {IS_START} ~ {IS_END}  ← パラメータ固定済み\n"
            f"OOS（検証期間）: {OOS_START} ~ 現在  ← 封印中（戦略確定後に1回開封）\n\n"
            "保有中トレードの扱い: Case A（除外）— 完結済みトレードのみ集計。")
        self.ln(3)

        self._sec("次フェーズ方針", color=TEAL)
        items = [
            ("OOS開封条件",
             "IS PF 1.3以上かつDD 20%以内が維持されている状態で1回だけ開封。\n"
             "OOS結果がIS比較で大幅に劣化した場合は戦略の見直しを検討する。"),
            ("同時保有数の最適化",
             "現在は1業種あたり最大3ポジション（10業種で最大30）。\n"
             "IS結果を基に最適な同時保有数を検討する。"),
            ("実運用移行条件",
             "OOS開封後、PF 1.3以上・勝率50%以上が確認できた段階で\n"
             "デモトレード（3ヶ月）→ 本番の順で移行する。"),
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
        self._t(7, color=GRAY)
        is_yr_start = IS_START[:4]
        is_yr_end   = IS_END[:4]
        self.multi_cell(0, 5,
            f"作成日: {today}  |  IS: {is_yr_start}-{is_yr_end}  |  OOS: 2024~（封印中）\n"
            "FxCompany 調査部門（AI孫正義）  |"
            "本レポートは過去データに基づくシミュレーションです。",
            align="C")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  セクター追いつき戦略 報告書 PDF生成")
    print(f"{'='*55}\n")

    print("データ読み込み中...")
    df_is, df_oos = load_latest()

    print("\nサマリー計算中...")
    s = calc_summary(df_is)
    n_sectors = df_is["sector"].nunique() if not df_is.empty else 0
    print(f"  件数:{s['n']}  勝率:{s['wr']}%  PF:{s['pf']}  DD:{s['max_dd']}%")
    print(f"  損益: ¥{s['total_pnl']:+,.0f}  業種数: {n_sectors}")

    print("\nチャート生成中...")
    eq_img  = make_equity_chart(df_is, f"IS エクイティカーブ（{n_sectors}業種）")
    sec_img = make_sector_bar(s["by_sector"])
    print("  完了")

    is_years = round((pd.Timestamp(IS_END) - pd.Timestamp(IS_START)).days / 365.25, 1)

    print("\nPDF生成中...")
    pdf = SectorReportPDF()
    pdf.cover(s, today, n_sectors, is_years=is_years)
    pdf.equity_page(eq_img, sec_img, s)
    pdf.discussion_page(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"sector_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [eq_img, sec_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
