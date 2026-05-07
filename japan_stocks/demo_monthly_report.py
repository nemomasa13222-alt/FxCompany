# -*- coding: utf-8 -*-
"""
デモ運用 月次集計レポート生成
1ヶ月のデモ運用結果をバックテスト実績と比較してPDFに出力する。

実行: python japan_stocks/demo_monthly_report.py
"""

import sys, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from fpdf import FPDF, XPos, YPos

DEMO_DIR    = Path(__file__).parent / "results" / "demo"
REPORT_DIR  = Path(__file__).parent / "results" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE  = DEMO_DIR / "state.json"
PNL_FILE    = DEMO_DIR / "pnl_history.csv"
TRADES_FILE = DEMO_DIR / "trades.csv"

FONT_PATH       = r"C:\Windows\Fonts\YuGothM.ttc"
INITIAL_CAPITAL = 1_000_000
ROUND_TRIP_COST = 0.20

# バックテスト実績（v2-f OOS実績）比較用
BT_PF      = 1.58
BT_WINRATE = 46.9
BT_DD      = 10.0
BT_RETURN  = 18.0   # OOS実績 +180万 / 100万 = 18%（全期間）

NAVY  = (15,  30,  70)
TEAL  = (0,  160, 120)
GREEN = (0,  140,  80)
RED   = (190,  40,  40)
AMBER = (200, 140,   0)
LIGHT = (235, 242, 255)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)
BLUE  = (30,  90, 170)


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def load_data() -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    pnl_df    = pd.read_csv(PNL_FILE,    encoding="utf-8-sig") if PNL_FILE.exists()    else pd.DataFrame()
    trades_df = pd.read_csv(TRADES_FILE, encoding="utf-8-sig") if TRADES_FILE.exists() else pd.DataFrame()
    return state, pnl_df, trades_df


def calc_demo_stats(pnl_df: pd.DataFrame, trades_df: pd.DataFrame) -> dict:
    if pnl_df.empty:
        return {}

    final_equity  = float(pnl_df["total_equity"].iloc[-1])
    total_return  = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    max_dd        = float(pnl_df["max_dd_pct"].max())
    total_days    = len(pnl_df)

    if trades_df.empty:
        return {
            "total_return": round(total_return, 2),
            "max_dd": round(max_dd, 1),
            "total_days": total_days,
            "trade_count": 0,
            "win_rate": 0.0,
            "pf": 0.0,
            "avg_win": 0,
            "avg_loss": 0,
            "avg_days": 0,
        }

    wins   = trades_df[trades_df["pnl_jpy"] > 0]
    losses = trades_df[trades_df["pnl_jpy"] <= 0]
    gross_win  = wins["pnl_jpy"].sum()
    gross_loss = abs(losses["pnl_jpy"].sum())
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0.0

    return {
        "total_return":  round(total_return, 2),
        "max_dd":        round(max_dd, 1),
        "total_days":    total_days,
        "trade_count":   len(trades_df),
        "win_rate":      round(len(wins) / len(trades_df) * 100, 1) if len(trades_df) > 0 else 0.0,
        "pf":            pf,
        "avg_win":       round(wins["pnl_jpy"].mean()) if len(wins) > 0 else 0,
        "avg_loss":      round(losses["pnl_jpy"].mean()) if len(losses) > 0 else 0,
        "avg_days":      round(trades_df["days_held"].mean(), 1) if "days_held" in trades_df.columns else 0,
        "final_equity":  round(final_equity),
    }


# ── チャート ──────────────────────────────────────────────────────────────────

def make_equity_curve(pnl_df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(14, 5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    dates  = pd.to_datetime(pnl_df["date"])
    equity = pnl_df["total_equity"] / 10000   # 万円

    ax.plot(dates, equity, color="#1A3A7A", lw=2.0, label="デモ評価額")
    ax.fill_between(dates, INITIAL_CAPITAL / 10000, equity,
                    where=(equity >= INITIAL_CAPITAL / 10000),
                    alpha=0.15, color="#22AA66")
    ax.fill_between(dates, INITIAL_CAPITAL / 10000, equity,
                    where=(equity < INITIAL_CAPITAL / 10000),
                    alpha=0.15, color="#CC3333")
    ax.axhline(INITIAL_CAPITAL / 10000, color="#888", lw=1.0, ls="--",
               alpha=0.7, label="初期資金")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}"))
    ax.set_ylabel("評価額（万円）", fontproperties=_jp(9))
    ax.set_title("デモ運用 資産推移（万円）", fontproperties=_jp(11), color="#1A3A7A", pad=6)
    ax.legend(prop=_jp(8.5))
    ax.grid(color="#D0D8EC", lw=0.4, ls="--")
    plt.xticks(rotation=30)
    plt.tight_layout(pad=0.8)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_dd_chart(pnl_df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(14, 3))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    dates = pd.to_datetime(pnl_df["date"])
    dd    = pnl_df["max_dd_pct"]

    ax.fill_between(dates, 0, -dd, color="#CC3333", alpha=0.5)
    ax.plot(dates, -dd, color="#CC3333", lw=1.2)
    ax.axhline(-10.0, color="#FF8800", lw=1.0, ls="--", alpha=0.8, label="DD 10%")
    ax.axhline(-20.0, color="#CC3333", lw=1.0, ls="--", alpha=0.8, label="DD 20%（本番停止ライン）")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{abs(x):.0f}"))
    ax.set_ylabel("DD（%）", fontproperties=_jp(9))
    ax.set_title("ドローダウン推移", fontproperties=_jp(11), color="#1A3A7A", pad=6)
    ax.legend(prop=_jp(8), loc="lower left")
    ax.grid(color="#D0D8EC", lw=0.4, ls="--")
    plt.xticks(rotation=30)
    plt.tight_layout(pad=0.8)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_trade_histogram(trades_df: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    fig.patch.set_facecolor("#F5F8FF")

    # 損益分布
    ax = axes[0]
    ax.set_facecolor("#F5F8FF")
    if not trades_df.empty:
        pnl_vals = trades_df["pnl_jpy"] / 10000
        colors = ["#22AA66" if v > 0 else "#CC3333" for v in pnl_vals]
        ax.bar(range(len(pnl_vals)), pnl_vals, color=colors, alpha=0.8, width=0.7)
        ax.axhline(0, color="#888", lw=0.8, ls="--")
        ax.set_xlabel("トレード番号", fontproperties=_jp(8))
        ax.set_ylabel("損益（万円）", fontproperties=_jp(8))
    ax.set_title("トレード別 損益", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")

    # 決済理由別集計
    ax2 = axes[1]
    ax2.set_facecolor("#F5F8FF")
    if not trades_df.empty and "exit_reason" in trades_df.columns:
        reason_counts = trades_df["exit_reason"].value_counts()
        reason_colors = {"target": "#22AA66", "stop": "#CC3333", "time": "#FF8800"}
        colors2 = [reason_colors.get(r, "#2266AA") for r in reason_counts.index]
        bars = ax2.bar(reason_counts.index, reason_counts.values,
                       color=colors2, alpha=0.85, width=0.5)
        for bar, v in zip(bars, reason_counts.values):
            ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.1,
                     str(v), ha="center", fontproperties=_jp(9), fontweight="bold")
    ax2.set_title("決済理由別 件数", fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax2.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class MonthlyReportPDF(FPDF):
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
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK)
        self.ln(2)

    def _kv(self, label: str, value: str, label_w=55, val_color=DARK):
        self._t(8.5, color=GRAY)
        self.cell(label_w, 7, label)
        self._t(9, bold=True, color=val_color)
        self.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def cover(self, today: str, period_start: str, period_end: str,
              stats: dict, state: dict):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(35)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 7, "FxCompany  |  セクター追いつき戦略 v2-f  デモ運用",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "月次運用レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(10, bold=True, color=(0, 220, 170))
        self.cell(0, 8, f"{period_start}  〜  {period_end}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(30, self.get_y(), 180, self.get_y())
        self.ln(6)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  初期資金: {INITIAL_CAPITAL:,}円",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # 主要指標
        self.set_y(118)
        ret   = stats.get("total_return", 0)
        dd    = stats.get("max_dd", 0)
        pf    = stats.get("pf", 0)
        wr    = stats.get("win_rate", 0)
        n     = stats.get("trade_count", 0)
        eq    = stats.get("final_equity", INITIAL_CAPITAL)
        days  = stats.get("total_days", 0)

        ret_color = (0, 200, 100) if ret >= 0 else (220, 80, 80)
        items = [
            ("評価額",     f"{eq:,}円"),
            ("総リターン", f"{ret:+.2f}%"),
            ("最大DD",     f"{dd:.1f}%"),
            ("PF",         f"{pf:.2f}"),
            ("勝率",       f"{wr:.1f}%"),
            ("トレード数", f"{n}件  /  {days}営業日"),
        ]
        for label, val in items:
            self._t(9, color=(160, 185, 220))
            self.cell(55, 8, label, align="R")
            ic = ret_color if label == "総リターン" else WHITE
            self._t(10, bold=True, color=ic)
            self.cell(0, 8, f"  {val}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # vs バックテスト比較ライン
        self.set_y(240)
        self._t(9, bold=True, color=(0, 200, 160))
        self.cell(0, 8, "  バックテスト実績（v2-f 全期間）との比較",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("YG", "", 8.5)
        self.set_text_color(170, 195, 230)
        self.multi_cell(0, 6,
            f"  PF: デモ {pf:.2f}  vs  BT {BT_PF}  |  "
            f"勝率: デモ {wr:.1f}%  vs  BT {BT_WINRATE}%  |  "
            f"最大DD: デモ {dd:.1f}%  vs  BT {BT_DD}%")

        self.set_y(272)
        self._t(7.5, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本資料は内部デモ運用の記録です。", align="C")

    def equity_page(self, img_equity: str, img_dd: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "① 資産推移 / ドローダウン推移",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)
        self.image(img_equity, x=12, y=self.get_y(), w=186, h=65)
        self.ln(69)
        self.image(img_dd,     x=12, y=self.get_y(), w=186, h=42)
        self.ln(46)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "・緑塗り: 初期資金比プラス  ／  赤塗り: 初期資金比マイナス\n"
            "・DD 20%ライン到達 → 本番移行時の停止基準")

    def stats_page(self, stats: dict, trades_df: pd.DataFrame, img_trades: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "② 運用成績詳細 / バックテスト比較",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        # BT vs Demo 比較表
        self._sec("デモ実績 vs バックテスト実績（v2-f）", color=NAVY)
        headers = ["指標", "デモ実績", "バックテスト（全期間）", "判定"]
        ws = [40, 45, 60, 37]
        self.set_font("YG", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, ws):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(*DARK)

        rows = [
            ("総リターン",  f"{stats.get('total_return', 0):+.2f}%",    "—（月次相当）",         None),
            ("PF",          f"{stats.get('pf', 0):.2f}",                f"{BT_PF}",              stats.get("pf", 0) >= 1.0),
            ("勝率",        f"{stats.get('win_rate', 0):.1f}%",         f"{BT_WINRATE}%",        stats.get("win_rate", 0) >= 40.0),
            ("最大DD",      f"{stats.get('max_dd', 0):.1f}%",           f"{BT_DD}%",             stats.get("max_dd", 0) <= 25.0),
            ("トレード数",  f"{stats.get('trade_count', 0)}件",         f"—",                     None),
            ("平均保有日数",f"{stats.get('avg_days', 0)}日",            "—",                      None),
            ("平均勝ちPnL", f"{stats.get('avg_win', 0):,}円",           "—",                      None),
            ("平均負けPnL", f"{stats.get('avg_loss', 0):,}円",          "—",                      None),
        ]
        for label, demo_val, bt_val, ok in rows:
            bg = (240, 255, 240) if ok is True else (255, 240, 240) if ok is False else LIGHT
            jc = GREEN if ok is True else RED if ok is False else GRAY
            judge = ("合格" if ok is True else "要注意" if ok is False else "—")
            self.set_fill_color(*bg)
            self.set_font("YG", "", 8)
            for txt, w in zip([label, demo_val, bt_val], ws[:3]):
                self.set_fill_color(*bg)
                self.set_draw_color(180, 190, 210)
                self.set_text_color(*DARK)
                self.cell(w, 8, txt, border=1, fill=True, align="C")
            self.set_fill_color(*bg)
            self.set_font("YG", "B", 8)
            self.set_text_color(*jc)
            self.cell(ws[3], 8, judge, border=1, fill=True, align="C")
            self.ln()
        self.ln(3)

        # トレードチャート
        self.image(img_trades, x=12, y=self.get_y(), w=186, h=52)
        self.ln(56)

    def trades_page(self, trades_df: pd.DataFrame, today: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "③ 全決済トレード一覧",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        if trades_df.empty:
            self._t(10, color=GRAY)
            self.cell(0, 10, "決済トレードなし",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            return

        ws = [18, 14, 20, 18, 18, 18, 20, 14, 22]
        headers = ["銘柄", "日数", "業種", "取得", "決済", "損益", "リターン", "理由", "取得日"]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, ws):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(*DARK)

        total_pnl = 0
        for _, row in trades_df.iterrows():
            pnl    = row["pnl_jpy"]
            ok     = pnl > 0
            bg     = (235, 255, 235) if ok else (255, 235, 235)
            pf_col = GREEN if ok else RED
            total_pnl += pnl
            reason_ja = {"target": "利確", "stop": "損切", "time": "時間"}.get(
                row.get("exit_reason", ""), str(row.get("exit_reason", "")))

            self.set_font("YG", "", 7.5)
            for txt, w, color in zip(
                [row["ticker"], str(int(row.get("days_held", 0))),
                 str(row.get("sector", ""))[:8],
                 f"{row['entry_price']:,.0f}", f"{row['exit_price']:,.0f}",
                 f"{pnl:+,.0f}", f"{row['return_pct']:+.2f}%",
                 reason_ja, str(row.get("entry_date", ""))],
                ws,
                [DARK, DARK, DARK, DARK, DARK, pf_col, pf_col, DARK, DARK]
            ):
                self.set_fill_color(*bg)
                self.set_draw_color(180, 190, 210)
                self.set_text_color(*color)
                self.cell(w, 7, str(txt), border=1, fill=True, align="C")
            self.ln()

        # 合計行
        self.set_font("YG", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        total_col = GREEN if total_pnl > 0 else RED
        self.cell(sum(ws[:5]), 7, "合計", border=1, fill=True, align="C")
        self.set_text_color(*total_col)
        self.cell(ws[5], 7, f"{total_pnl:+,.0f}", border=1, fill=True, align="C")
        self.set_text_color(*WHITE)
        for w in ws[6:]:
            self.cell(w, 7, "", border=1, fill=True, align="C")
        self.ln()

        self.set_y(self.h - 20)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）", align="C")


# ── メイン ─────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*55}")
    print(f"  デモ運用 月次レポート生成")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    if not STATE_FILE.exists():
        print("state.json が見つかりません。先に demo_signal.py を実行してください。")
        return
    if not PNL_FILE.exists():
        print("pnl_history.csv が見つかりません。")
        return

    state, pnl_df, trades_df = load_data()

    period_start = pnl_df["date"].iloc[0]  if not pnl_df.empty else today
    period_end   = pnl_df["date"].iloc[-1] if not pnl_df.empty else today
    stats        = calc_demo_stats(pnl_df, trades_df)

    print(f"  集計期間: {period_start} 〜 {period_end}（{stats.get('total_days', 0)}営業日）")
    print(f"  総リターン: {stats.get('total_return', 0):+.2f}%")
    print(f"  PF: {stats.get('pf', 0):.2f}  勝率: {stats.get('win_rate', 0):.1f}%  "
          f"最大DD: {stats.get('max_dd', 0):.1f}%")
    print(f"  トレード数: {stats.get('trade_count', 0)}件\n")

    print("チャート生成中...")
    img_equity = make_equity_curve(pnl_df) if not pnl_df.empty else None
    img_dd     = make_dd_chart(pnl_df)     if not pnl_df.empty else None
    img_trades = make_trade_histogram(trades_df)

    print("PDF生成中...")
    pdf = MonthlyReportPDF()
    pdf.cover(today, period_start, period_end, stats, state)
    if img_equity and img_dd:
        pdf.equity_page(img_equity, img_dd)
    pdf.stats_page(stats, trades_df, img_trades)
    pdf.trades_page(trades_df, today)

    out = REPORT_DIR / f"demo_monthly_{period_start}_{period_end}_{ts}.pdf"
    pdf.output(str(out))

    for f in [img_equity, img_dd, img_trades]:
        if f:
            Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out.name}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
