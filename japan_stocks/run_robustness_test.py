# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 — パラメータロバストネステスト
sector_min_rise × min_gap の 3×3 マトリックス解析（全期間 2022-2026）

実行: python japan_stocks/run_robustness_test.py
"""
import sys, tempfile, json
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

sys.path.insert(0, str(Path(__file__).parent))
import sector_index as si
from backtest_stocks import BacktestConfig, Trade, run as bt_run, compute_stats
from run_backtest import (
    _load_all_sectors, compute_active_sector_dates,
    N_ACTIVE_SECTORS, SMA_WINDOW, RANKING_WINDOW,
    CANDIDATE_SECTORS, DATA_START, TRADE_START,
)

RESULTS_DIR = Path(__file__).parent / "results" / "robustness"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR  = Path(__file__).parent / "results" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH        = r"C:\Windows\Fonts\YuGothM.ttc"
INITIAL_CAPITAL  = 1_000_000
ROUND_TRIP_COST  = 0.20

# ── テストするパラメータ範囲 ──────────────────────────────────────────────────
SECTOR_MIN_RISES = [1.0, 2.0, 3.0]   # %
MIN_GAPS         = [1.0, 2.0, 3.0]   # %

# 固定パラメータ（v2-f確定値）
FIXED_RISK_PCT      = 0.5
FIXED_STOP_DIST_PCT = 1.5
FIXED_MIN_CORR      = 0.60

CONFIRMED_RISE = 2.0
CONFIRMED_GAP  = 3.0

NAVY  = (15,  30,  70);  BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120);  GREEN = (0,  140,  80)
RED   = (190,  40,  40); AMBER = (200, 140,   0)
LIGHT = (235, 242, 255); WHITE = (255, 255, 255)
DARK  = (30,  30,  40);  GRAY  = (110, 110, 120)


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _net_stats(trades: list[Trade]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pnl": 0}
    df = pd.DataFrame([{
        "entry_date": str(t.entry_date)[:10],
        "exit_date":  str(t.exit_date)[:10],
        "entry_price": t.entry_price,
        "shares":      t.shares,
        "pnl_jpy":     t.pnl_jpy,
    } for t in trades])
    df["cost_jpy"]    = df["entry_price"] * df["shares"] * ROUND_TRIP_COST / 100
    df["net_pnl_jpy"] = df["pnl_jpy"] - df["cost_jpy"]
    pnl = df["net_pnl_jpy"]
    w   = pnl[pnl > 0].sum(); l = abs(pnl[pnl <= 0].sum())
    pf  = round(w / l, 2) if l > 0 else 99.0
    eq, peak, max_dd = INITIAL_CAPITAL, INITIAL_CAPITAL, 0.0
    for v in df.sort_values("exit_date")["net_pnl_jpy"]:
        eq += v; peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)
    return {
        "n":   len(df),
        "wr":  round((pnl > 0).mean() * 100, 1),
        "pf":  pf,
        "dd":  round(max_dd, 1),
        "pnl": round(pnl.sum()),
    }


# ── チャート生成 ──────────────────────────────────────────────────────────────

def _matrix(results: dict, metric: str, label: str, fmt: str,
            good_high: bool = True, vmin=None, vmax=None) -> np.ndarray:
    mat = np.zeros((len(SECTOR_MIN_RISES), len(MIN_GAPS)))
    for i, rise in enumerate(SECTOR_MIN_RISES):
        for j, gap in enumerate(MIN_GAPS):
            mat[i, j] = results[(rise, gap)][metric]
    return mat


def make_heatmap(results: dict) -> str:
    metrics = [
        ("pf",  "Profit Factor",  ".2f", True),
        ("wr",  "勝率（%）",       ".1f", True),
        ("dd",  "最大DD（%）",     ".1f", False),
        ("pnl", "損益（万円）",    ".0f", True),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle("パラメータロバストネス マトリックス（全期間 2022〜2026）",
                 fontproperties=_jp(12), color="#1A3A7A", y=1.01)

    for ax, (metric, label, fmt, good_high) in zip(axes, metrics):
        ax.set_facecolor("#F5F8FF")
        mat = _matrix(results, metric, label, fmt, good_high)
        if metric == "pnl":
            mat_disp = mat / 10000
        else:
            mat_disp = mat
        cmap = "RdYlGn" if good_high else "RdYlGn_r"
        im = ax.imshow(mat_disp, cmap=cmap, aspect="auto",
                       vmin=np.min(mat_disp) * 0.9, vmax=np.max(mat_disp) * 1.1)
        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_xticks(range(len(MIN_GAPS)))
        ax.set_yticks(range(len(SECTOR_MIN_RISES)))
        ax.set_xticklabels([f"gap={g:.0f}%" for g in MIN_GAPS], fontproperties=_jp(8))
        ax.set_yticklabels([f"rise={r:.0f}%" for r in SECTOR_MIN_RISES], fontproperties=_jp(8))
        ax.set_title(label, fontproperties=_jp(9.5), color="#1A3A7A", pad=6)
        ax.set_xlabel("min_gap", fontproperties=_jp(8))
        ax.set_ylabel("sector_min_rise", fontproperties=_jp(8))
        for i in range(len(SECTOR_MIN_RISES)):
            for j in range(len(MIN_GAPS)):
                v = mat_disp[i, j]
                txt = f"{v:{fmt}}"
                is_confirmed = (SECTOR_MIN_RISES[i] == CONFIRMED_RISE and
                                MIN_GAPS[j] == CONFIRMED_GAP)
                fc = "white" if is_confirmed else "none"
                ec = "#FF8800" if is_confirmed else "none"
                if is_confirmed:
                    ax.add_patch(plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9,
                                               fill=True, facecolor="#FF8800",
                                               edgecolor="#FF4400", linewidth=2, alpha=0.25))
                ax.text(j, i, txt, ha="center", va="center",
                        fontproperties=_jp(9 if not is_confirmed else 10),
                        fontweight="bold" if is_confirmed else "normal",
                        color="#1A1A2E")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


def make_pf_bar(results: dict) -> str:
    labels, pfs, colors, edgecolors = [], [], [], []
    for rise in SECTOR_MIN_RISES:
        for gap in MIN_GAPS:
            labels.append(f"rise={rise:.0f}%\ngap={gap:.0f}%")
            pf = results[(rise, gap)]["pf"]
            pfs.append(pf)
            confirmed = (rise == CONFIRMED_RISE and gap == CONFIRMED_GAP)
            colors.append("#FF8800" if confirmed else ("#2266AA" if pf >= 1.3 else "#CC3333"))
            edgecolors.append("#FF4400" if confirmed else "none")

    fig, ax = plt.subplots(figsize=(13, 4))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    bars = ax.bar(range(9), pfs, color=colors, edgecolor=edgecolors,
                  linewidth=[2 if ec != "none" else 0 for ec in edgecolors],
                  alpha=0.85, width=0.65)
    ax.axhline(1.3, color="#CC3333", lw=1.5, ls="--", alpha=0.8, label="PF=1.3 基準")
    ax.axhline(1.0, color="#888", lw=1.0, ls=":", alpha=0.6)
    ax.set_xticks(range(9))
    ax.set_xticklabels(labels, fontproperties=_jp(7.5))
    ax.set_ylabel("Profit Factor", fontproperties=_jp(9))
    ax.set_title("全9条件 Profit Factor 一覧（橙色★ = 採用パラメータ v2-f）",
                 fontproperties=_jp(10), color="#1A3A7A", pad=6)
    ax.legend(prop=_jp(8.5))
    ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
    for bar, v in zip(bars, pfs):
        ax.text(bar.get_x() + bar.get_width()/2, v + 0.02,
                f"{v:.2f}", ha="center", fontproperties=_jp(8.5), fontweight="bold")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class RobustnessPDF(FPDF):
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
        self.set_fill_color(*color); self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK); self.ln(2)

    def _row(self, texts, widths, fills=None, bolds=None, aligns=None,
             row_h=11, line_h=5, font_size=8, colors=None):
        if fills  is None: fills  = [LIGHT] * len(texts)
        if bolds  is None: bolds  = [False] * len(texts)
        if aligns is None: aligns = ["C"] * len(texts)
        if colors is None: colors = [DARK] * len(texts)
        x0 = self.get_x(); y0 = self.get_y()
        if y0 + row_h > self.h - self.b_margin:
            self.add_page(); x0 = self.get_x(); y0 = self.get_y()
        x = x0
        for txt, w, fc, bold, align, tc in zip(texts, widths, fills, bolds, aligns, colors):
            self.set_fill_color(*fc); self.set_draw_color(180, 190, 210)
            self.rect(x, y0, w, row_h, "FD")
            self.set_text_color(*tc)
            self.set_font("YG", "B" if bold else "", font_size)
            lines = str(txt).split("\n")
            for li, line in enumerate(lines[:2]):
                self.set_xy(x + 1, y0 + 1 + li * line_h)
                self.cell(w - 2, line_h, str(line)[:40], align=align)
            x += w
        self.set_xy(x0, y0 + row_h)
        self.set_text_color(*DARK); self.set_draw_color(0, 0, 0)

    def _header_row(self, headers, widths):
        self.set_font("YG", "B", 8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln(); self.set_text_color(*DARK)

    # ── 表紙 ─────────────────────────────────────────────────────────────────
    def cover(self, today: str, confirmed_stats: dict):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL); self.rect(0, 0, 210, 4, "F"); self.rect(0, 293, 210, 4, "F")

        self.set_y(40)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 7, "FxCompany  |  セクター追いつき戦略 v2-f",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "パラメータ ロバストネス検証",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(11, bold=True, color=(0, 220, 170))
        self.cell(0, 8, "sector_min_rise × min_gap  3×3 マトリックス解析",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(30, self.get_y(), 180, self.get_y()); self.ln(5)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  全期間: 2022-01-01 〜 2026-05-06",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, "固定パラメータ: risk=0.5%  stop=1.5%  min_corr=0.60",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # 検証方針
        self.set_y(130)
        self._t(9, bold=True, color=(0, 200, 160))
        self.cell(0, 8, "  検証の目的と方針",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("YG", "", 8.5); self.set_text_color(190, 210, 240)
        self.multi_cell(0, 6,
            "  デモトレード移行前に、採用パラメータ（v2-f: rise=2%, gap=3%）が\n"
            "  パラメータ空間において孤立した最適解ではなく、\n"
            "  近傍のパラメータでも安定した成績を示す「ロバストな設計」であることを確認する。\n\n"
            "  【合格基準】\n"
            "    ・全9条件中7条件以上でPF ≥ 1.0（黒字）\n"
            "    ・全9条件中5条件以上でPF ≥ 1.3\n"
            "    ・採用パラメータが最良または上位3位以内\n"
            "    ・隣接セル（rise±1%, gap±1%）もPF ≥ 1.2")

        # マトリックス構造の説明
        self.set_y(210)
        self._t(9, bold=True, color=(0, 200, 160))
        self.cell(0, 8, "  パラメータグリッド（★ = 採用 v2-f）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        ws = [20, 45, 45, 45]
        self.set_font("YG", "B", 8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for h, w in zip(["↓rise / gap→", "gap=1%", "gap=2%", "gap=3%"], ws):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln(); self.set_text_color(*DARK)
        for rise in SECTOR_MIN_RISES:
            for j, (gap, w) in enumerate(zip([None] + MIN_GAPS, [20]+[45]*3)):
                if gap is None:
                    self.set_fill_color(25, 45, 95); self.set_text_color(*WHITE)
                    self.set_font("YG", "B", 8)
                    self.cell(w, 9, f"rise={rise:.0f}%", border=1, fill=True, align="C")
                else:
                    confirmed = (rise == CONFIRMED_RISE and gap == CONFIRMED_GAP)
                    bg = (255, 200, 80) if confirmed else (240, 246, 255)
                    self.set_fill_color(*bg); self.set_text_color(*DARK)
                    self.set_font("YG", "B" if confirmed else "", 8)
                    label = "★採用" if confirmed else "テスト"
                    self.cell(w, 9, label, border=1, fill=True, align="C")
            self.ln()

        # 採用パラメータの参照値
        self.set_y(258)
        self._t(8.5, color=(0, 200, 160))
        self.cell(0, 7, f"  採用パラメータ（全期間）参照:  "
                        f"PF={confirmed_stats['pf']}  "
                        f"DD={confirmed_stats['dd']}%  "
                        f"PnL=+{confirmed_stats['pnl']//10000}万円  "
                        f"勝率={confirmed_stats['wr']}%  "
                        f"件数={confirmed_stats['n']}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(272)
        self._t(7.5, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本資料はロバストネス検証を目的とした内部資料です。", align="C")

    # ── ヒートマップページ ────────────────────────────────────────────────────
    def heatmap_page(self, heatmap_img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "パラメータ マトリックス ヒートマップ",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(3)
        self.image(heatmap_img, x=14, y=self.get_y(), w=182, h=55)
        self.ln(59)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "・各セルの数値は全期間（2022-2026）のコスト控除後成績\n"
            "・橙色ハイライト = 採用パラメータ（v2-f: sector_min_rise=2%, min_gap=3%）\n"
            "・ヒートマップ色: 緑=良好（PF高・勝率高・DD低・損益高）/ 赤=不良")
        self.ln(3)

    # ── PF棒グラフページ ─────────────────────────────────────────────────────
    def pf_bar_page(self, bar_img: str, results: dict, today: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "全9条件 Profit Factor & 詳細成績表",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(2)
        self.image(bar_img, x=14, y=self.get_y(), w=182, h=52)
        self.ln(56)

        self._sec("全条件 詳細成績一覧（コスト控除後 / PF降順）", color=NAVY)
        sorted_results = sorted(results.items(), key=lambda x: -x[1]["pf"])
        ws = [32, 28, 25, 25, 25, 30, 27]
        self._header_row(["条件", "件数", "勝率", "PF", "最大DD", "損益（万円）", "判定"], ws)
        for (rise, gap), s in sorted_results:
            confirmed = (rise == CONFIRMED_RISE and gap == CONFIRMED_GAP)
            bg = (255, 250, 220) if confirmed else LIGHT
            pf_col = GREEN if s["pf"] >= 1.3 else (AMBER if s["pf"] >= 1.0 else RED)
            judge = "★採用" if confirmed else ("合格" if s["pf"] >= 1.3 else ("黒字" if s["pf"] >= 1.0 else "赤字"))
            jcol  = (255, 150, 0) if confirmed else (GREEN if s["pf"] >= 1.3 else (AMBER if s["pf"] >= 1.0 else RED))
            self._row(
                [f"rise={rise:.0f}%\ngap={gap:.0f}%",
                 str(s["n"]), f"{s['wr']}%", str(s["pf"]),
                 f"{s['dd']}%", f"{s['pnl']//10000:+.0f}万",
                 judge],
                ws,
                fills=[bg]*7,
                bolds=[confirmed]+[False]*5+[confirmed],
                aligns=["C","C","C","C","C","C","C"],
                colors=[DARK,DARK,DARK,pf_col,DARK,DARK,jcol],
                row_h=13
            )
        self.ln(4)

        # ロバストネス判定サマリー
        self._sec("ロバストネス判定サマリー", color=TEAL)
        pf_vals = [s["pf"] for s in results.values()]
        n_black = sum(1 for p in pf_vals if p >= 1.0)
        n_pass  = sum(1 for p in pf_vals if p >= 1.3)
        confirmed_rank = sorted(pf_vals, reverse=True).index(results[(CONFIRMED_RISE, CONFIRMED_GAP)]["pf"]) + 1
        adj_pfs = [results[(r, g)]["pf"]
                   for r in SECTOR_MIN_RISES for g in MIN_GAPS
                   if abs(r - CONFIRMED_RISE) <= 1 and abs(g - CONFIRMED_GAP) <= 1
                   and not (r == CONFIRMED_RISE and g == CONFIRMED_GAP)]
        adj_min = min(adj_pfs) if adj_pfs else 0

        checks = [
            (n_black >= 7,  f"黒字（PF≥1.0）の条件数: {n_black}/9",       "7/9以上が合格基準", "合格" if n_black >= 7 else "要注意"),
            (n_pass  >= 5,  f"PF≥1.3の条件数: {n_pass}/9",                 "5/9以上が合格基準", "合格" if n_pass >= 5 else "要注意"),
            (confirmed_rank <= 3, f"採用パラメータのPF順位: {confirmed_rank}位/9", "上位3位以内が合格基準", "合格" if confirmed_rank <= 3 else "要注意"),
            (adj_min >= 1.2, f"隣接セルの最低PF: {adj_min:.2f}",            "≥1.2が合格基準",    "合格" if adj_min >= 1.2 else "要注意"),
        ]
        ws2 = [55, 65, 45, 17]
        self._header_row(["チェック項目", "実測値", "基準", "判定"], ws2)
        for ok, item, criterion, judge in checks:
            jc = GREEN if "合格" in judge else AMBER
            self._row([item, "", criterion, judge], ws2,
                      fills=[LIGHT]*4, bolds=[False]*3+[True],
                      aligns=["L","L","L","C"],
                      colors=[DARK,DARK,DARK,jc])

        self.set_y(self.h - 20)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）", align="C")


# ── メイン ─────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*60}")
    print(f"  パラメータ ロバストネステスト")
    print(f"  sector_min_rise: {SECTOR_MIN_RISES}")
    print(f"  min_gap:         {MIN_GAPS}")
    print(f"  組み合わせ数:    {len(SECTOR_MIN_RISES)*len(MIN_GAPS)}")
    print(f"{'='*60}\n")

    # ── データ読み込み（1回のみ）────────────────────────────────────────────
    print("セクターデータ読み込み中（キャッシュ使用）...")
    sectors = _load_all_sectors()

    print("\nセクター指数構築中...")
    sector_indices: dict = {}
    sector_stocks:  dict = {}
    sector_opens:   dict = {}
    for name, raw in sectors.items():
        stocks_prices = raw.get("stocks", {})
        if not stocks_prices:
            continue
        idx = si.build_from_price_dict(stocks_prices, name=name)
        if idx.empty:
            continue
        sector_indices[name] = idx
        sector_stocks[name]  = {t: c.rename("Close").to_frame()
                                 for t, c in stocks_prices.items()}
        sector_opens[name]   = raw.get("opens", {})
    print(f"  {len(sector_indices)}業種のセクター指数構築完了")

    print("\n動的セクター選別を計算中（全期間・1回のみ）...")
    active_dates = compute_active_sector_dates(
        sector_indices,
        n_active       = N_ACTIVE_SECTORS,
        sma_window     = SMA_WINDOW,
        ranking_window = RANKING_WINDOW,
    )

    # ── 9条件バックテスト ──────────────────────────────────────────────────
    results = {}
    print(f"\n{'─'*60}")
    print(f"  9条件バックテスト開始")
    print(f"{'─'*60}")

    total_combos = len(SECTOR_MIN_RISES) * len(MIN_GAPS)
    combo_i = 0
    for rise in SECTOR_MIN_RISES:
        for gap in MIN_GAPS:
            combo_i += 1
            confirmed = (rise == CONFIRMED_RISE and gap == CONFIRMED_GAP)
            mark = " ★採用" if confirmed else ""
            print(f"\n  [{combo_i}/{total_combos}] rise={rise:.0f}%  gap={gap:.0f}%{mark}")

            config = BacktestConfig(
                start_date      = DATA_START,
                sector_min_rise = rise,
                min_gap         = gap,
                risk_pct        = FIXED_RISK_PCT,
                stop_dist_pct   = FIXED_STOP_DIST_PCT,
                min_corr        = FIXED_MIN_CORR,
            )

            all_trades: list[Trade] = []
            for name in sorted(sector_indices.keys()):
                allowed = active_dates.get(name, set())
                if not allowed:
                    continue
                trades = bt_run(
                    sector_indices[name],
                    sector_stocks[name],
                    config,
                    sector_name         = name,
                    allowed_entry_dates = allowed,
                    stocks_opens        = sector_opens.get(name, {}),
                )
                all_trades.extend(trades)

            # 全期間集計（IS/OOS分割なし）
            valid = [t for t in all_trades if t.exit_reason != "end"]
            s = _net_stats(valid)
            results[(rise, gap)] = s
            print(f"     → {s['n']}件  勝率{s['wr']}%  PF{s['pf']}  "
                  f"DD{s['dd']}%  損益{s['pnl']:+,}円")

    # ── CSV保存 ───────────────────────────────────────────────────────────
    rows = []
    for (rise, gap), s in results.items():
        rows.append({
            "sector_min_rise": rise, "min_gap": gap,
            "n": s["n"], "win_rate": s["wr"], "pf": s["pf"],
            "max_dd": s["dd"], "net_pnl_jpy": s["pnl"],
        })
    csv_path = RESULTS_DIR / f"robustness_{ts}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  CSV保存: {csv_path.name}")

    # ── PDF生成 ───────────────────────────────────────────────────────────
    print("\nチャート生成中...")
    heatmap_img = make_heatmap(results)
    bar_img     = make_pf_bar(results)

    print("PDF生成中...")
    confirmed_stats = results[(CONFIRMED_RISE, CONFIRMED_GAP)]
    pdf = RobustnessPDF()
    pdf.cover(today, confirmed_stats)
    pdf.heatmap_page(heatmap_img)
    pdf.pf_bar_page(bar_img, results, today)

    out = REPORT_DIR / f"robustness_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [heatmap_img, bar_img]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"\n{'='*60}")
    print("  ロバストネス結果サマリー")
    print(f"{'='*60}")
    sorted_r = sorted(results.items(), key=lambda x: -x[1]["pf"])
    for (rise, gap), s in sorted_r:
        mark = " ★採用" if (rise == CONFIRMED_RISE and gap == CONFIRMED_GAP) else ""
        print(f"  rise={rise:.0f}% gap={gap:.0f}%{mark}:  "
              f"PF={s['pf']}  DD={s['dd']}%  {s['pnl']:+,}円")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
