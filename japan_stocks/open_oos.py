# -*- coding: utf-8 -*-
"""
OOS（Out-of-Sample）開封スクリプト  ─  ミネルヴィニ v4
実行: python japan_stocks/open_oos.py

【警告】
  このスクリプトは「戦略が完全に確定した後」に1回だけ実行すること。
  パラメータ調整・条件変更の余地が残っている段階で実行すると
  OOSとしての意味が失われる。

【保有中トレードの扱い: Case A（除外）】
  OOS期間中にエントリーしたが、バックテスト末尾時点でまだ
  保有中のトレードは集計から除外する。
  理由: 途中経過を「負け」にカウントするのは不正確。
        完結したトレードだけで戦略の実力を評価する。
  実装: シミュレーション上、保有中トレードはCSVに記録されない。
        さらにEXCLUDE_INCOMPLETE_TAILで末尾の不完全エントリーも除去済み。
        → このCSVをそのまま読めばCase A適用済み。
"""

import sys
from pathlib import Path
from datetime import datetime
import tempfile

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from fpdf import FPDF, XPos, YPos

sys.path.insert(0, str(Path(__file__).parent))

FONT_PATH   = r"C:\Windows\Fonts\YuGothM.ttc"
RESULTS_DIR = Path(__file__).parent / "results"
OUTPUT_DIR  = RESULTS_DIR / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END    = "2024-12-31"
OOS_START = "2025-01-01"
POSITION_SIZE   = 100_000
INITIAL_CAPITAL = 1_000_000

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

REASON_LABEL = {
    "stop_base"      : "ベース安値損切",
    "stop_breakeven" : "建値損切（①②）",
    "earnings_close" : "決算前クローズ（③）",
    "ma200_breach"   : "MA200決済（④B）",
    "time"           : "期間満了",
}


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _pf(ret: pd.Series) -> float:
    w = ret[ret > 0].sum()
    l = abs(ret[ret < 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


# ── データ読み込み ─────────────────────────────────────────────────────────────

def load_oos_and_is() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """IS CSV と OOS CSV を読み込む。最新ファイルを使用。"""
    is_files  = sorted(RESULTS_DIR.glob("v4A_trades_*.csv"), reverse=True)
    oos_files = sorted(RESULTS_DIR.glob("v4A_oos_*.csv"),    reverse=True)
    is_b_files  = sorted(RESULTS_DIR.glob("v4B_trades_*.csv"), reverse=True)
    oos_b_files = sorted(RESULTS_DIR.glob("v4B_oos_*.csv"),    reverse=True)

    if not is_files or not oos_files:
        raise FileNotFoundError(
            "IS/OOS CSVが見つかりません。先に backtest_minervini_v4.py を実行してください。"
        )

    dfA_is  = pd.read_csv(is_files[0])
    dfA_oos = pd.read_csv(oos_files[0])
    dfB_is  = pd.read_csv(is_b_files[0])  if is_b_files  else pd.DataFrame()
    dfB_oos = pd.read_csv(oos_b_files[0]) if oos_b_files else pd.DataFrame()

    print(f"  IS  ④A: {is_files[0].name}  ({len(dfA_is)}件)")
    print(f"  OOS ④A: {oos_files[0].name} ({len(dfA_oos)}件)")
    print()
    print(f"  ※ 保有中トレードの扱い: Case A（除外）")
    print(f"    保有中トレードはCSV未記録のため、自動的に集計対象外")

    return dfA_is, dfA_oos, dfB_is, dfB_oos


# ── サマリー計算 ──────────────────────────────────────────────────────────────

def calc_summary(df: pd.DataFrame, label: str) -> dict:
    if df.empty:
        return {}
    ret = df["ret_pct"]
    pnl = ret / 100 * POSITION_SIZE

    df2 = df.copy()
    df2["year"] = pd.to_datetime(df2["entry_date"]).dt.year
    yearly = {}
    for yr, g in df2.groupby("year"):
        r = g["ret_pct"]
        yearly[yr] = {
            "trades": len(g),
            "avg"   : r.mean(),
            "wr"    : (r > 0).mean() * 100,
            "pf"    : _pf(r),
            "pnl"   : (r / 100 * POSITION_SIZE).sum(),
        }

    return {
        "label"     : label,
        "n"         : len(df),
        "avg"       : ret.mean(),
        "median"    : ret.median(),
        "wr"        : (ret > 0).mean() * 100,
        "pf"        : _pf(ret),
        "max_win"   : ret.max(),
        "max_loss"  : ret.min(),
        "total_pnl" : pnl.sum(),
        "yearly"    : yearly,
        "reason"    : df["reason"].value_counts().to_dict(),
    }


# ── チャート ──────────────────────────────────────────────────────────────────

def make_comparison_chart(s_is: dict, s_oos: dict) -> str:
    """IS vs OOS の主要指標比較バーチャート"""
    metrics = ["avg", "wr", "pf"]
    labels  = ["平均リターン（%）", "勝率（%）", "PF"]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5))
    fig.patch.set_facecolor("#F5F8FF")

    for ax, key, lbl in zip(axes, metrics, labels):
        ax.set_facecolor("#F5F8FF")
        vals   = [s_is.get(key, 0), s_oos.get(key, 0)]
        colors = ["#2266AA", "#CC4444"]
        bars   = ax.bar(["IS", "OOS"], vals, color=colors, alpha=0.85, width=0.5)
        ax.axhline(0, color="#555", lw=0.8)
        ax.set_title(lbl, fontproperties=_jp(9), color="#1A3A7A", pad=6)
        ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
        ax.tick_params(labelsize=8)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    v + (abs(v) * 0.03 if v >= 0 else -abs(v) * 0.08),
                    f"{v:+.2f}" if key != "pf" else f"{v:.2f}",
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5,
                    fontweight="bold",
                    color="#2266AA" if vals.index(v) == 0 else "#CC4444")

    plt.suptitle("IS vs OOS 主要指標比較  ④A MA200決済なし",
                 fontproperties=_jp(10), color="#1A3A7A", y=1.02)
    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def make_yearly_chart(s_is: dict, s_oos: dict) -> str:
    """年別 平均リターン（IS + OOS 合算表示）"""
    all_years = sorted(set(list(s_is["yearly"].keys()) + list(s_oos["yearly"].keys())))
    is_avgs  = [s_is["yearly"].get(y, {}).get("avg", None) for y in all_years]
    oos_avgs = [s_oos["yearly"].get(y, {}).get("avg", None) for y in all_years]

    fig, ax = plt.subplots(figsize=(9, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    x = np.arange(len(all_years))
    w = 0.35

    def _bar(xs, vals, color, label, hatch=None):
        filtered = [(xi, v) for xi, v in zip(xs, vals) if v is not None]
        if not filtered:
            return
        xi_list, vi_list = zip(*filtered)
        clrs = [f"{color}" if v >= 0 else "#CC4444" for v in vi_list]
        ax.bar(list(xi_list), list(vi_list), w, color=clrs, label=label,
               alpha=0.85, hatch=hatch)

    _bar(x - w / 2, is_avgs,  "#2266AA", "IS（開発期間）")
    _bar(x + w / 2, oos_avgs, "#FF8800", "OOS（検証期間）", hatch="//")

    ax.axhline(0, color="#555", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in all_years], fontsize=8)
    ax.set_ylabel("平均リターン/T（%）", fontproperties=_jp(8))
    ax.set_title("年別 平均トレードリターン — IS vs OOS", fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax.legend(prop=_jp(8), framealpha=0.85)
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    ax.tick_params(labelsize=8)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class OosReportPDF(FPDF):
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

        self.set_y(38)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  株式投資戦略 OOS検証レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "ミネルヴィニ v4",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(12, bold=True, color=(255, 200, 60))
        self.cell(0, 9, "Out-of-Sample 検証結果",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(45, self.get_y(), 165, self.get_y())
        self.ln(5)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"開封日: {today}  |  IS: {IS_END}まで  |  OOS: {OOS_START}〜",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, "保有中トレード: Case A（除外）— 完結済みトレードのみ集計",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # IS サマリー
        self.set_y(135)
        for s, color, tag in [(s_is, BLUE, "IS（開発期間）"), (s_oos, AMBER, "OOS（検証期間）★")]:
            self.set_fill_color(*color)
            self.set_text_color(*WHITE)
            self.set_font("YG", "B", 9)
            self.cell(0, 7, f"  ④A MA200決済なし  —  {tag}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            rows = [
                ("件数",       f"{s['n']}件"),
                ("平均リターン", f"{s['avg']:+.2f}%"),
                ("勝率",        f"{s['wr']:.1f}%"),
                ("PF",          f"{s['pf']:.2f}"),
                ("最大利益/損失", f"{s['max_win']:+.1f}%  /  {s['max_loss']:+.1f}%"),
                ("総損益（¥10万/T）", f"¥{s['total_pnl']:+,.0f}"),
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

    def result_page(self, cmp_img: str, yr_img: str, s_is: dict, s_oos: dict):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, "IS vs OOS 比較分析",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*AMBER)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self.image(cmp_img, x=14, y=self.get_y(), w=182, h=56)
        self.ln(60)
        self.image(yr_img,  x=14, y=self.get_y(), w=182, h=58)
        self.ln(62)

        # 指標比較テーブル
        self._sec("主要指標  IS vs OOS 対比", color=NAVY)
        headers = ["指標", "IS（開発期間）", "OOS（検証期間）", "乖離", "判定"]
        widths  = [38, 42, 42, 28, 32]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        def _judge(is_val, oos_val, key):
            if key == "pf":
                ok = oos_val >= 1.3
                close = abs(oos_val - is_val) / max(abs(is_val), 0.01) < 0.3
            elif key == "wr":
                ok = oos_val >= 30
                close = abs(oos_val - is_val) < 10
            else:
                ok = oos_val > 0
                close = abs(oos_val - is_val) / max(abs(is_val), 0.01) < 0.3
            if ok and close:
                return "◎ 再現", GREEN
            elif ok:
                return "○ 合格", TEAL
            else:
                return "× 要確認", RED

        rows_data = [
            ("平均リターン", f"{s_is['avg']:+.2f}%", f"{s_oos['avg']:+.2f}%",
             f"{s_oos['avg']-s_is['avg']:+.2f}%", "avg"),
            ("勝率",         f"{s_is['wr']:.1f}%",   f"{s_oos['wr']:.1f}%",
             f"{s_oos['wr']-s_is['wr']:+.1f}pp",    "wr"),
            ("PF",           f"{s_is['pf']:.2f}",    f"{s_oos['pf']:.2f}",
             f"{s_oos['pf']-s_is['pf']:+.2f}",      "pf"),
            ("最大損失",     f"{s_is['max_loss']:+.1f}%", f"{s_oos['max_loss']:+.1f}%",
             f"{s_oos['max_loss']-s_is['max_loss']:+.1f}%", "loss"),
        ]
        for i, (name, iv, ov, diff, key) in enumerate(rows_data):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[0], 6, name, border=1, fill=True)
            self.set_font("YG", "", 7.5)
            self.cell(widths[1], 6, iv,   border=1, fill=True, align="C")
            self.cell(widths[2], 6, ov,   border=1, fill=True, align="C")
            self.cell(widths[3], 6, diff, border=1, fill=True, align="C")
            judge_text, judge_color = _judge(
                float(iv.replace("%","").replace("+","").replace("pp","")),
                float(ov.replace("%","").replace("+","").replace("pp","")),
                key
            )
            self.set_text_color(*judge_color)
            self.set_font("YG", "B", 7.5)
            self.cell(widths[4], 6, judge_text, border=1, fill=True, align="C")
            self.set_text_color(*DARK)
            self.ln()

        self.ln(4)
        # 年別テーブル（OOS）
        self._sec(f"年別詳細  OOS期間（{OOS_START}〜）", color=AMBER)
        headers2 = ["年", "件数", "平均リターン", "勝率", "PF", "損益（¥10万/T）"]
        widths2  = [18, 18, 30, 20, 16, 80]
        self.set_font("YG", "B", 7.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers2, widths2):
            self.cell(w, 6, h, border=1, fill=True, align="C")
        self.ln()
        for i, (yr, d) in enumerate(sorted(s_oos["yearly"].items())):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            self.set_font("YG", "B", 7.5)
            self.cell(widths2[0], 6, str(yr), border=1, fill=True, align="C")
            self.set_font("YG", "", 7.5)
            self.cell(widths2[1], 6, str(d["trades"]), border=1, fill=True, align="C")
            self.cell(widths2[2], 6, f"{d['avg']:+.2f}%", border=1, fill=True, align="C")
            self.cell(widths2[3], 6, f"{d['wr']:.0f}%",   border=1, fill=True, align="C")
            self.cell(widths2[4], 6, f"{d['pf']:.2f}",    border=1, fill=True, align="C")
            self.set_text_color(*(GREEN if d["pnl"] >= 0 else RED))
            self.set_font("YG", "B", 7.5)
            self.cell(widths2[5], 6, f"¥{d['pnl']:+,.0f}", border=1, fill=True, align="R")
            self.ln()
        self.set_text_color(*DARK)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  ★ OOS 開封  ミネルヴィニ v4")
    print(f"  IS: {IS_END}まで  /  OOS: {OOS_START}〜")
    print(f"  保有中トレード: Case A（除外）")
    print(f"{'='*60}\n")

    print("データ読み込み中...")
    dfA_is, dfA_oos, _, _ = load_oos_and_is()

    print("\nサマリー計算中...")
    s_is  = calc_summary(dfA_is,  "IS")
    s_oos = calc_summary(dfA_oos, "OOS")

    print(f"\n  IS  : {s_is['n']}件  平均{s_is['avg']:+.2f}%  勝率{s_is['wr']:.1f}%  PF{s_is['pf']:.2f}")
    print(f"  OOS : {s_oos['n']}件  平均{s_oos['avg']:+.2f}%  勝率{s_oos['wr']:.1f}%  PF{s_oos['pf']:.2f}")

    print("\nチャート生成中...")
    cmp_img = make_comparison_chart(s_is, s_oos)
    yr_img  = make_yearly_chart(s_is, s_oos)

    print("\nPDF生成中...")
    pdf = OosReportPDF()
    pdf.cover(today, s_is, s_oos)
    pdf.result_page(cmp_img, yr_img, s_is, s_oos)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"oos_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [cmp_img, yr_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
