# -*- coding: utf-8 -*-
"""
2026年 全エントリー・エグジット詳細 PDF 生成
実行: python japan_stocks/make_2026_trades_pdf.py
"""

import sys
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

FONT_PATH   = r"C:\Windows\Fonts\YuGothM.ttc"
RESULTS_DIR = Path(__file__).parent / "results"
OUTPUT_DIR  = RESULTS_DIR / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

POSITION_SIZE = 100_000

NAVY  = (15,  30,  70)
BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120)
RED   = (190,  40,  40)
AMBER = (200, 140,   0)
GREEN = (0,  140,  80)
LIGHT = (235, 242, 255)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)

REASON_LABEL = {
    "stop_base"      : "ベース安値損切",
    "stop_breakeven" : "建値損切（①②）",
    "earnings_close" : "決算前クローズ（③）",
    "ma200_breach"   : "MA200決済（④B）",
    "time"           : "期間満了",
}
REASON_COLOR = {
    "stop_base"      : "#CC3333",
    "stop_breakeven" : "#FF8800",
    "earnings_close" : "#2288CC",
    "ma200_breach"   : "#884488",
    "time"           : "#228844",
}


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _pf(ret: pd.Series) -> float:
    w = ret[ret > 0].sum()
    l = abs(ret[ret < 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


# ── データ読み込み ─────────────────────────────────────────────────────────────

def load_2026_trades() -> pd.DataFrame:
    files = sorted(RESULTS_DIR.glob("v4A_trades_*.csv"), reverse=True)
    if not files:
        raise FileNotFoundError("v4A_trades_*.csv が見つかりません。先にbacktest_minervini_v4.pyを実行してください。")
    df = pd.read_csv(files[0])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"]  = pd.to_datetime(df["exit_date"])
    # 2026年にエントリーしたトレードを対象とする（レポートの年別集計と同口）
    df26 = df[df["entry_date"].dt.year == 2026].copy()
    print(f"  ソース: {files[0].name}")
    print(f"  全期間: {len(df)}件  →  2026年エントリー: {len(df26)}件")
    return df26


# ── チャート ──────────────────────────────────────────────────────────────────

def make_return_hist(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    ret = df["ret_pct"]
    bins = np.arange(ret.min() - 1, ret.max() + 2, 1)
    # 色分けは負のビンを赤、正を青
    n, bins_out, patches = ax.hist(ret, bins=bins, edgecolor="white", linewidth=0.4, alpha=0.9)
    for patch, left in zip(patches, bins_out[:-1]):
        patch.set_facecolor("#CC3333" if left < 0 else "#2266AA")
    ax.axvline(0,         color="#333", lw=1.2, ls="--")
    ax.axvline(ret.mean(), color="#FF8800", lw=1.5, ls="-", label=f"平均 {ret.mean():+.2f}%")
    ax.set_xlabel("リターン（%）", fontproperties=_jp(8.5))
    ax.set_ylabel("トレード数", fontproperties=_jp(8.5))
    ax.set_title("2026年 リターン分布", fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax.legend(prop=_jp(8.5), framealpha=0.85)
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax.tick_params(labelsize=7.5)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def make_reason_pie(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    rc  = df["reason"].value_counts()
    lbls  = [REASON_LABEL.get(k, k) for k in rc.index]
    clrs  = [REASON_COLOR.get(k, "#999") for k in rc.index]
    wedges, _, autotexts = ax.pie(
        rc.values, labels=None, colors=clrs,
        autopct="%1.0f%%", startangle=90,
        pctdistance=0.75
    )
    for at in autotexts:
        at.set_fontproperties(_jp(8))
    ax.legend(wedges, lbls, loc="lower center", prop=_jp(7.5),
              bbox_to_anchor=(0.5, -0.2), ncol=2, framealpha=0.8)
    ax.set_title("2026年 決済理由内訳", fontproperties=_jp(10), color="#1A3A7A", pad=8)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def make_timeline(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    df_s = df.sort_values("exit_date")
    xs   = df_s["exit_date"]
    ys   = df_s["ret_pct"]
    clrs = ["#CC3333" if r < 0 else "#2266AA" for r in ys]

    ax.scatter(xs, ys, c=clrs, s=18, alpha=0.7, zorder=3)
    ax.axhline(0, color="#555", lw=0.8, ls="--")

    # 月次平均ライン
    df_s["month"] = df_s["exit_date"].dt.to_period("M")
    monthly_avg = df_s.groupby("month")["ret_pct"].mean()
    month_dates = [p.to_timestamp(how="end") for p in monthly_avg.index]
    ax.plot(month_dates, monthly_avg.values, color="#FF8800", lw=2,
            label="月次平均", marker="o", markersize=5, zorder=5)

    ax.set_xlabel("決済日", fontproperties=_jp(8.5))
    ax.set_ylabel("リターン（%）", fontproperties=_jp(8.5))
    ax.set_title("2026年 決済日別リターン推移", fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax.legend(prop=_jp(8.5), framealpha=0.85)
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax.tick_params(axis="x", labelsize=7, rotation=25)
    ax.tick_params(axis="y", labelsize=7.5)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def make_reason_return_bar(df: pd.DataFrame) -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.5))
    fig.patch.set_facecolor("#F5F8FF")

    for ax in [ax1, ax2]:
        ax.set_facecolor("#F5F8FF")

    grp = df.groupby("reason")["ret_pct"]
    reasons = list(grp.groups.keys())
    avg_ret = [grp.get_group(r).mean() for r in reasons]
    cnt     = [len(grp.get_group(r)) for r in reasons]
    lbls    = [REASON_LABEL.get(r, r) for r in reasons]
    clrs    = [REASON_COLOR.get(r, "#999") for r in reasons]

    # 件数
    bars = ax1.barh(lbls, cnt, color=clrs, alpha=0.85)
    ax1.set_xlabel("件数", fontproperties=_jp(8))
    ax1.set_title("決済理由別 件数", fontproperties=_jp(9.5), color="#1A3A7A", pad=6)
    ax1.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for bar, v in zip(bars, cnt):
        ax1.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                 str(v), va="center", fontsize=7.5)
    ax1.tick_params(labelsize=7.5)

    # 平均リターン
    clrs2 = ["#CC3333" if v < 0 else "#2266AA" for v in avg_ret]
    bars2 = ax2.barh(lbls, avg_ret, color=clrs2, alpha=0.85)
    ax2.axvline(0, color="#555", lw=0.8)
    ax2.set_xlabel("平均リターン（%）", fontproperties=_jp(8))
    ax2.set_title("決済理由別 平均リターン", fontproperties=_jp(9.5), color="#1A3A7A", pad=6)
    ax2.grid(axis="x", color="#D0D8EC", lw=0.4, ls="--")
    for bar, v in zip(bars2, avg_ret):
        ax2.text(v + (0.1 if v >= 0 else -0.1),
                 bar.get_y() + bar.get_height()/2,
                 f"{v:+.1f}%", va="center", ha="left" if v >= 0 else "right", fontsize=7.5)
    ax2.tick_params(labelsize=7.5)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class TradePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  fname=FONT_PATH)
        self.add_font("YG", "B", fname=FONT_PATH)
        self.set_margins(12, 12, 12)
        self.set_auto_page_break(auto=True, margin=12)

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

    # ── カバー ──────────────────────────────────────────────────────────────

    def cover(self, df: pd.DataFrame, today: str):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*RED)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(40)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 バックテスト 詳細調査",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(22, bold=True, color=WHITE)
        self.cell(0, 14, "2026年 全トレード",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(13, bold=True, color=(255, 120, 100))
        self.cell(0, 9, "エントリー・エグジット 詳細レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self.set_draw_color(*RED)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(6)

        self._t(9, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  対象: ④A MA200決済なし  |  2026年エグジット分",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # サマリーボックス
        ret = df["ret_pct"]
        rc  = df["reason"].value_counts()
        self.set_y(140)
        self.set_fill_color(*RED)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, "  2026年 パフォーマンス サマリー",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)

        metrics = [
            ("総トレード数",   f"{len(df)} 件"),
            ("平均リターン",   f"{ret.mean():+.2f}%"),
            ("中央値",         f"{ret.median():+.2f}%"),
            ("勝率",           f"{(ret > 0).mean()*100:.1f}%"),
            ("PF",             f"{_pf(ret):.2f}"),
            ("最大利益/損失", f"{ret.max():+.1f}%  /  {ret.min():+.1f}%"),
            ("総損益（¥10万/T）",
             f"¥{(ret / 100 * POSITION_SIZE).sum():+,.0f}"),
        ]
        for k, v in metrics:
            self._t(9, color=(160, 190, 230))
            self.cell(50, 7, k, align="R")
            self._t(10, bold=True, color=WHITE)
            self.cell(0, 7, f"  {v}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # 決済理由
        self.ln(4)
        self.set_fill_color(*AMBER)
        self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, "  決済理由別 内訳",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        for reason, cnt in rc.items():
            sub = df[df["reason"] == reason]["ret_pct"]
            lbl = REASON_LABEL.get(reason, reason)
            self._t(8.5, color=(160, 190, 230))
            self.cell(60, 6.5, lbl, align="R")
            self._t(8.5, bold=True, color=WHITE)
            self.cell(0, 6.5,
                      f"  {cnt}件   平均 {sub.mean():+.2f}%",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(268)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"本レポートは過去データに基づくシミュレーションです。  |  FxCompany 調査部門（AI孫正義）  |  {today}",
            align="C")

    # ── 分析チャートページ ──────────────────────────────────────────────────

    def analysis_page(self, hist_img: str, pie_img: str,
                      timeline_img: str, bar_img: str, df: pd.DataFrame):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "2026年 トレード分析",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RED)
        self.set_line_width(0.5)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(2)

        # ヒストグラム + パイチャート
        self.image(hist_img, x=12, y=self.get_y(), w=118, h=48)
        self.image(pie_img,  x=133, y=self.get_y(), w=65, h=50)
        self.ln(54)

        # 決済理由別 件数・平均
        self.image(bar_img, x=12, y=self.get_y(), w=186, h=58)
        self.ln(62)

        # タイムライン
        self.image(timeline_img, x=12, y=self.get_y(), w=186, h=52)
        self.ln(56)

        # 月別サマリー小テーブル（エントリー月基準）
        self._sec("月別サマリー（エントリー月基準）", color=NAVY)
        df2 = df.copy()
        df2["month"] = df2["entry_date"].dt.to_period("M")
        mgrp = df2.groupby("month")

        headers = ["月", "件数", "平均リターン", "勝率", "PF", "損益（¥10万/T）"]
        widths  = [22, 18, 32, 20, 16, 78]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()

        for i, (mo, g) in enumerate(mgrp):
            r   = g["ret_pct"]
            pnl = (r / 100 * POSITION_SIZE).sum()
            bg  = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, str(mo), border=1, fill=True, align="C")
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 6, str(len(g)), border=1, fill=True, align="C")
            self.cell(widths[2], 6, f"{r.mean():+.2f}%", border=1, fill=True, align="C")
            self.cell(widths[3], 6, f"{(r>0).mean()*100:.0f}%", border=1, fill=True, align="C")
            self.cell(widths[4], 6, f"{_pf(r):.2f}", border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if pnl >= 0 else RED))
            self.set_font("YG", "B", 7.5)
            self.cell(widths[5], 6, f"¥{pnl:+,.0f}", border=1, fill=True, align="R")
            self.ln()
        self.set_text_color(*DARK)

    # ── トレード一覧ページ ──────────────────────────────────────────────────

    def trades_pages(self, df: pd.DataFrame):
        df_s = df.sort_values("exit_date").reset_index(drop=True)
        headers = ["#", "銘柄", "エントリー日", "決済日", "保有日", "エントリー値", "決済値", "ストップ", "リターン", "決済理由"]
        widths  = [8, 16, 22, 22, 14, 20, 20, 20, 18, 26]

        ROWS_PER_PAGE = 36

        total = len(df_s)
        pages = (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE

        for p in range(pages):
            self.add_page()
            chunk = df_s.iloc[p*ROWS_PER_PAGE : (p+1)*ROWS_PER_PAGE]

            self._t(11, bold=True, color=NAVY)
            self.cell(0, 8, f"全トレード一覧  ({p*ROWS_PER_PAGE+1}〜{min((p+1)*ROWS_PER_PAGE, total)} / {total}件)",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(*RED)
            self.set_line_width(0.4)
            self.line(12, self.get_y(), 198, self.get_y())
            self.ln(2)

            # ヘッダー
            self.set_font("YG", "B", 6.5)
            self.set_fill_color(*NAVY)
            self.set_text_color(*WHITE)
            for h, w in zip(headers, widths):
                self.cell(w, 6, h, border=1, fill=True, align="C")
            self.ln()

            for i, (_, row) in enumerate(chunk.iterrows()):
                ret  = row["ret_pct"]
                bg   = LIGHT if i % 2 == 0 else WHITE
                self.set_fill_color(*bg)
                self.set_text_color(*DARK)

                # リターン色分け
                ret_color = GREEN if ret > 0 else (RED if ret < 0 else GRAY)
                reason_lbl = REASON_LABEL.get(row["reason"], row["reason"])

                # 行番号・銘柄・日付
                self.set_font("YG", "", 6.5)
                self.cell(widths[0], 5.5, str(p*ROWS_PER_PAGE + i + 1), border=1, fill=True, align="C")

                ticker_short = row["ticker"].replace("_T", "").replace(".T", "")
                self.cell(widths[1], 5.5, ticker_short, border=1, fill=True, align="C")
                self.cell(widths[2], 5.5, str(row["entry_date"])[:10], border=1, fill=True, align="C")
                self.cell(widths[3], 5.5, str(row["exit_date"])[:10],  border=1, fill=True, align="C")
                self.cell(widths[4], 5.5, f"{row['hold_days']}日", border=1, fill=True, align="C")
                self.cell(widths[5], 5.5, f"¥{row['entry_px']:,.0f}", border=1, fill=True, align="R")
                self.cell(widths[6], 5.5, f"¥{row['exit_px']:,.0f}",  border=1, fill=True, align="R")
                self.cell(widths[7], 5.5, f"¥{row['stop_px']:,.0f}",  border=1, fill=True, align="R")

                # リターンセル（色付き）
                self.set_text_color(*ret_color)
                self.set_font("YG", "B", 6.5)
                self.cell(widths[8], 5.5, f"{ret:+.2f}%", border=1, fill=True, align="C")

                self.set_text_color(*DARK)
                self.set_font("YG", "", 6)
                self.cell(widths[9], 5.5, reason_lbl, border=1, fill=True, align="C")
                self.ln()

            self.set_text_color(*DARK)
            # ページフッター
            self.set_y(-16)
            self._t(7, color=GRAY)
            self.cell(0, 5,
                      f"FxCompany 調査部門（AI孫正義）  |  2026年 全トレード一覧  |  {p+1}/{pages}ページ",
                      align="C")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  2026年 全トレード詳細 PDF 生成")
    print(f"{'='*55}\n")

    print("データ読み込み中...")
    df = load_2026_trades()
    ret = df["ret_pct"]
    print(f"\n  2026年 サマリー:")
    print(f"  件数: {len(df)}  平均: {ret.mean():+.2f}%  勝率: {(ret>0).mean()*100:.1f}%  PF: {_pf(ret):.2f}")

    print("\nチャート生成中...")
    hist_img     = make_return_hist(df)
    pie_img      = make_reason_pie(df)
    timeline_img = make_timeline(df)
    bar_img      = make_reason_return_bar(df)
    print("  完了")

    print("\nPDF生成中...")
    pdf = TradePDF()
    pdf.cover(df, today)
    pdf.analysis_page(hist_img, pie_img, timeline_img, bar_img, df)
    pdf.trades_pages(df)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"2026_trades_detail_{ts}.pdf"
    pdf.output(str(out))

    for f in [hist_img, pie_img, timeline_img, bar_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
