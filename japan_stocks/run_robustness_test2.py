# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 — 拡張ロバストネステスト v2
stop_dist × min_corr × risk_pct  4×3×5 マトリックス解析（有効条件のみ）
全期間: 2022-01-01 〜 2026-05-06

【有効条件の定義】
  ポジション投入額 = 資金 × risk_pct ÷ stop_dist_pct
  この値が資金の100%以上になる組み合わせは現実的でないため除外。
  → 有効条件: risk_pct < stop_dist_pct（30条件）

実行: python japan_stocks/run_robustness_test2.py
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
from fpdf import FPDF, XPos, YPos

sys.path.insert(0, str(Path(__file__).parent))
import sector_index as si
from backtest_stocks import BacktestConfig, Trade, run as bt_run
from run_backtest import (
    _load_all_sectors, compute_active_sector_dates,
    N_ACTIVE_SECTORS, SMA_WINDOW, RANKING_WINDOW,
    DATA_START,
)

RESULTS_DIR = Path(__file__).parent / "results" / "robustness2"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR  = Path(__file__).parent / "results" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH       = r"C:\Windows\Fonts\YuGothM.ttc"
INITIAL_CAPITAL = 1_000_000
ROUND_TRIP_COST = 0.20

# ── テストパラメータ ───────────────────────────────────────────────────────────
STOP_DISTS = [0.5, 1.0, 1.5, 2.0]          # 損切幅 (%)
MIN_CORRS  = [0.5, 0.6, 0.7]               # 相関係数閾値
RISK_PCTS  = [0.25, 0.5, 1.0, 1.5, 2.0]   # リスク率 (%)

# 固定（v2-f rise/gap 確定値）
FIXED_RISE = 2.0
FIXED_GAP  = 3.0

# 採用値 ★
CONF_STOP = 1.5
CONF_CORR = 0.60
CONF_RISK = 0.5

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

INVALID_COLOR = (200, 200, 200)  # 適用外セルの色


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


def _is_valid(stop: float, risk: float) -> bool:
    """ポジション投入額が資金の100%未満の組み合わせのみ有効"""
    return risk < stop


def _pos_pct(stop: float, risk: float) -> float:
    """ポジション投入額の対資金比率（%）"""
    return risk / stop * 100


def _net_stats(trades: list[Trade]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pnl": 0}
    df = pd.DataFrame([{
        "exit_date":   str(t.exit_date)[:10],
        "entry_price": t.entry_price,
        "shares":      t.shares,
        "pnl_jpy":     t.pnl_jpy,
    } for t in trades])
    df["cost_jpy"]    = df["entry_price"] * df["shares"] * ROUND_TRIP_COST / 100
    df["net_pnl_jpy"] = df["pnl_jpy"] - df["cost_jpy"]
    pnl = df["net_pnl_jpy"]
    w   = pnl[pnl > 0].sum()
    l   = abs(pnl[pnl <= 0].sum())
    pf  = round(w / l, 2) if l > 0 else 99.0
    eq, peak, max_dd = INITIAL_CAPITAL, INITIAL_CAPITAL, 0.0
    for v in df.sort_values("exit_date")["net_pnl_jpy"]:
        eq += v
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)
    return {
        "n":   len(df),
        "wr":  round((pnl > 0).mean() * 100, 1),
        "pf":  pf,
        "dd":  round(max_dd, 1),
        "pnl": round(pnl.sum()),
    }


def _is_conf(stop, corr, risk):
    return stop == CONF_STOP and corr == CONF_CORR and risk == CONF_RISK


# ── チャート1: stop × corr 構造マップ（risk=CONF_RISK固定）─────────────────────

def make_structural_heatmap(results: dict) -> str:
    """stop × min_corr ヒートマップ（risk=0.5%固定）
    stop=0.5%はrisk=0.5%だと100%ポジションになるため N/A 表示
    """
    metrics = [
        ("pf",  "Profit Factor", ".2f", True),
        ("wr",  "勝率（%）",      ".1f", True),
        ("dd",  "最大DD（%）",    ".1f", False),
        ("pnl", "損益（万円）",   ".0f", True),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(18, 5.5))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle(
        f"構造マップ: stop_dist × min_corr（risk={CONF_RISK}%固定 / 全期間 2022〜2026）",
        fontproperties=_jp(11), color="#1A3A7A", y=1.02
    )

    for ax, (metric, label, fmt, good_high) in zip(axes, metrics):
        ax.set_facecolor("#F5F8FF")

        # マトリックス構築（stop=0.5はrisk=0.5で無効 → NaN）
        mat = np.full((len(STOP_DISTS), len(MIN_CORRS)), np.nan)
        for i, stop in enumerate(STOP_DISTS):
            for j, corr in enumerate(MIN_CORRS):
                if not _is_valid(stop, CONF_RISK):
                    continue
                val = results[(stop, corr, CONF_RISK)][metric]
                mat[i, j] = val / 10000 if metric == "pnl" else val

        # 有効セルのみでカラーレンジ設定
        valid_vals = mat[~np.isnan(mat)]
        if len(valid_vals) == 0:
            continue
        vmin = valid_vals.min() * 0.9
        vmax = valid_vals.max() * 1.1
        cmap_name = "RdYlGn" if good_high else "RdYlGn_r"
        cmap = plt.get_cmap(cmap_name).copy()
        cmap.set_bad(color="#CCCCCC")  # NaN → グレー

        masked = np.ma.masked_invalid(mat)
        im = ax.imshow(masked, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)
        plt.colorbar(im, ax=ax, shrink=0.8)

        ax.set_xticks(range(len(MIN_CORRS)))
        ax.set_yticks(range(len(STOP_DISTS)))
        ax.set_xticklabels([f"corr={c:.1f}" for c in MIN_CORRS], fontproperties=_jp(8))
        ax.set_yticklabels([f"stop={s:.1f}%" for s in STOP_DISTS], fontproperties=_jp(8))
        ax.set_title(label, fontproperties=_jp(10), color="#1A3A7A", pad=6)
        ax.set_xlabel("min_corr", fontproperties=_jp(8))
        ax.set_ylabel("stop_dist_pct", fontproperties=_jp(8))

        for i, stop in enumerate(STOP_DISTS):
            for j, corr in enumerate(MIN_CORRS):
                is_conf = (stop == CONF_STOP and corr == CONF_CORR)
                if not _is_valid(stop, CONF_RISK):
                    ax.text(j, i, "N/A\n(100%超)", ha="center", va="center",
                            fontproperties=_jp(7.5), color="#888888")
                    continue
                v = mat[i, j]
                if is_conf:
                    ax.add_patch(plt.Rectangle(
                        (j - 0.45, i - 0.45), 0.9, 0.9,
                        fill=True, facecolor="#FF8800",
                        edgecolor="#FF4400", linewidth=2, alpha=0.25
                    ))
                ax.text(j, i, f"{v:{fmt}}", ha="center", va="center",
                        fontproperties=_jp(9 if not is_conf else 10),
                        fontweight="bold" if is_conf else "normal",
                        color="#1A1A2E")

    plt.tight_layout(pad=1.0)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── チャート2: stop × risk_pct DDマップ（corr=CONF_CORR固定）────────────────────

def make_dd_risk_heatmap(results: dict) -> str:
    """stop × risk_pct の DD & PnL ヒートマップ（corr=0.6固定）
    無効セル（ポジション100%以上）は N/A 表示
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle(
        f"リスク管理マップ: stop_dist × risk_pct（min_corr={CONF_CORR}固定 / 全期間）\n"
        "灰色セル = ポジション投入額が資金の100%以上（適用外）",
        fontproperties=_jp(10), color="#1A3A7A", y=1.04
    )

    for ax, (metric, label, fmt, good_high) in zip(
        axes,
        [("dd", "最大DD（%）", ".1f", False), ("pnl", "損益（万円）", ".0f", True)]
    ):
        ax.set_facecolor("#F5F8FF")
        mat = np.full((len(STOP_DISTS), len(RISK_PCTS)), np.nan)
        for i, stop in enumerate(STOP_DISTS):
            for j, risk in enumerate(RISK_PCTS):
                if not _is_valid(stop, risk):
                    continue
                val = results[(stop, CONF_CORR, risk)][metric]
                mat[i, j] = val / 10000 if metric == "pnl" else val

        valid_vals = mat[~np.isnan(mat)]
        vmin = valid_vals.min() * 0.9 if len(valid_vals) else 0
        vmax = valid_vals.max() * 1.1 if len(valid_vals) else 1
        cmap = plt.get_cmap("RdYlGn" if good_high else "RdYlGn_r").copy()
        cmap.set_bad(color="#CCCCCC")

        masked = np.ma.masked_invalid(mat)
        im = ax.imshow(masked, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)
        plt.colorbar(im, ax=ax, shrink=0.8)

        ax.set_xticks(range(len(RISK_PCTS)))
        ax.set_yticks(range(len(STOP_DISTS)))
        ax.set_xticklabels([f"risk={r:.2f}%" for r in RISK_PCTS], fontproperties=_jp(8))
        ax.set_yticklabels([f"stop={s:.1f}%" for s in STOP_DISTS], fontproperties=_jp(8))
        ax.set_title(label, fontproperties=_jp(10), color="#1A3A7A", pad=6)
        ax.set_xlabel("risk_pct", fontproperties=_jp(8))
        ax.set_ylabel("stop_dist_pct", fontproperties=_jp(8))

        for i, stop in enumerate(STOP_DISTS):
            for j, risk in enumerate(RISK_PCTS):
                is_conf = (stop == CONF_STOP and risk == CONF_RISK)
                if not _is_valid(stop, risk):
                    pos = _pos_pct(stop, risk)
                    ax.text(j, i, f"N/A\n({pos:.0f}%)", ha="center", va="center",
                            fontproperties=_jp(7), color="#888888")
                    continue
                v = mat[i, j]
                pos_str = f"\n[{_pos_pct(stop, risk):.0f}%]"
                if is_conf:
                    ax.add_patch(plt.Rectangle(
                        (j - 0.45, i - 0.45), 0.9, 0.9,
                        fill=True, facecolor="#FF8800",
                        edgecolor="#FF4400", linewidth=2, alpha=0.25
                    ))
                ax.text(j, i, f"{v:{fmt}}", ha="center", va="center",
                        fontproperties=_jp(9 if not is_conf else 10),
                        fontweight="bold" if is_conf else "normal",
                        color="#1A1A2E")

    plt.tight_layout(pad=1.0)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── チャート3: ポジション投入額マトリックス（参考表）────────────────────────────

def make_position_size_chart() -> str:
    """stop × risk のポジション投入額（%）参考表"""
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    mat = np.zeros((len(STOP_DISTS), len(RISK_PCTS)))
    for i, stop in enumerate(STOP_DISTS):
        for j, risk in enumerate(RISK_PCTS):
            mat[i, j] = _pos_pct(stop, risk)

    # 100%未満=緑、100%以上=赤
    cmap = plt.get_cmap("RdYlGn_r")
    im = ax.imshow(mat, cmap=cmap, aspect="auto", vmin=0, vmax=400)
    plt.colorbar(im, ax=ax, shrink=0.8, label="ポジション投入額（対資金比 %）")

    ax.set_xticks(range(len(RISK_PCTS)))
    ax.set_yticks(range(len(STOP_DISTS)))
    ax.set_xticklabels([f"risk={r:.2f}%" for r in RISK_PCTS], fontproperties=_jp(9))
    ax.set_yticklabels([f"stop={s:.1f}%" for s in STOP_DISTS], fontproperties=_jp(9))
    ax.set_title(
        "ポジション投入額マトリックス（資金対比 %）\n"
        "= risk_pct ÷ stop_dist_pct × 100  |  赤色（100%以上）= 適用外",
        fontproperties=_jp(10), color="#1A3A7A", pad=8
    )
    ax.set_xlabel("risk_pct", fontproperties=_jp(9))
    ax.set_ylabel("stop_dist_pct", fontproperties=_jp(9))

    for i, stop in enumerate(STOP_DISTS):
        for j, risk in enumerate(RISK_PCTS):
            v = mat[i, j]
            is_conf = (stop == CONF_STOP and risk == CONF_RISK)
            invalid = not _is_valid(stop, risk)
            label = f"{v:.0f}%"
            if invalid:
                label += "\n(適用外)"
            if is_conf:
                ax.add_patch(plt.Rectangle(
                    (j - 0.45, i - 0.45), 0.9, 0.9,
                    fill=True, facecolor="#0044FF",
                    edgecolor="#0022CC", linewidth=2, alpha=0.2
                ))
                label += "\n★採用"
            fc = "white" if invalid else ("#003399" if is_conf else "#1A1A2E")
            ax.text(j, i, label, ha="center", va="center",
                    fontproperties=_jp(7.5 if invalid else 8),
                    fontweight="bold" if (invalid or is_conf) else "normal",
                    color=fc)

    # 100%境界線を引く（ポジション投入額=100%のライン）
    # stop=0.5: risk < 0.5 → risk[0]=0.25 が境界
    # stop=1.0: risk < 1.0 → risk[1]=0.5 が境界
    # stop=1.5: risk < 1.5 → risk[2]=1.0 が境界
    # stop=2.0: risk < 2.0 → risk[3]=1.5 が境界
    boundary_x = [0.5, 1.5, 2.5, 3.5]
    boundary_y = [0.5, 1.5, 2.5, 3.5]
    for k in range(4):
        ax.plot([boundary_x[k], boundary_x[k]],
                [k - 0.5, k + 0.5],
                color="white", lw=3, zorder=5)

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── チャート4: 全有効条件 PF vs DD 散布図 ─────────────────────────────────────

def make_pf_scatter(results: dict) -> str:
    fig, ax = plt.subplots(figsize=(13, 5))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    colors_map = {0.5: "#2266CC", 1.0: "#22AA66", 1.5: "#FF8800", 2.0: "#CC2222"}
    added_labels = set()

    for stop in STOP_DISTS:
        for risk in RISK_PCTS:
            if not _is_valid(stop, risk):
                continue
            for corr in MIN_CORRS:
                s = results[(stop, corr, risk)]
                is_conf = _is_conf(stop, corr, risk)
                label = f"stop={stop:.1f}%" if stop not in added_labels else None
                ax.scatter(s["dd"], s["pf"],
                           c=colors_map[stop], s=220 if is_conf else 45,
                           alpha=0.85, zorder=4 if is_conf else 2,
                           label=label)
                if stop not in added_labels and label:
                    added_labels.add(stop)

    # 採用パラメータを★マークで強調
    conf_s = results[(CONF_STOP, CONF_CORR, CONF_RISK)]
    ax.scatter([conf_s["dd"]], [conf_s["pf"]], c="#FF8800", s=280,
               marker="*", zorder=6, label="★採用", edgecolors="#FF4400", linewidths=1.5)

    ax.axhline(1.3, color="#CC3333", lw=1.5, ls="--", alpha=0.8, label="PF=1.3")
    ax.axhline(1.0, color="#888",    lw=1.0, ls=":",  alpha=0.6)
    ax.set_xlabel("最大DD（%）", fontproperties=_jp(10))
    ax.set_ylabel("Profit Factor", fontproperties=_jp(10))
    ax.set_title("全有効条件（30条件）PF vs DD 分布（stop_dist 色分け）",
                 fontproperties=_jp(11), color="#1A3A7A", pad=6)
    ax.legend(prop=_jp(8.5), ncol=3)
    ax.grid(color="#D0D8EC", lw=0.4, ls="--")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name


# ── PDF ───────────────────────────────────────────────────────────────────────

class RobustnessPDF2(FPDF):
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

    def _row(self, texts, widths, fills=None, bolds=None, aligns=None,
             row_h=10, line_h=5, font_size=7.5, colors=None):
        if fills  is None: fills  = [LIGHT] * len(texts)
        if bolds  is None: bolds  = [False] * len(texts)
        if aligns is None: aligns = ["C"]   * len(texts)
        if colors is None: colors = [DARK]  * len(texts)
        x0 = self.get_x(); y0 = self.get_y()
        if y0 + row_h > self.h - self.b_margin:
            self.add_page(); x0 = self.get_x(); y0 = self.get_y()
        x = x0
        for txt, w, fc, bold, align, tc in zip(texts, widths, fills, bolds, aligns, colors):
            self.set_fill_color(*fc)
            self.set_draw_color(180, 190, 210)
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
        self.set_font("YG", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln(); self.set_text_color(*DARK)

    # ── 表紙 ─────────────────────────────────────────────────────────────────
    def cover(self, today: str, conf_stats: dict):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL); self.rect(0, 0, 210, 4, "F"); self.rect(0, 293, 210, 4, "F")

        self.set_y(35)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 7, "FxCompany  |  セクター追いつき戦略 v2-f",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self._t(18, bold=True, color=WHITE)
        self.cell(0, 13, "拡張ロバストネス検証",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(9.5, bold=True, color=(0, 220, 170))
        self.cell(0, 8, "stop_dist × min_corr × risk_pct  4×3×5 マトリックス（有効30条件）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(30, self.get_y(), 180, self.get_y()); self.ln(5)
        self._t(8.5, color=(140, 170, 220))
        self.cell(0, 6, f"作成日: {today}  |  全期間: 2022-01-01 〜 2026-05-06",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"固定パラメータ: sector_min_rise={FIXED_RISE}%  min_gap={FIXED_GAP}%",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # ポジションサイジングの説明（重要）
        self.set_y(112)
        self._t(9, bold=True, color=(0, 200, 160))
        self.cell(0, 8, "  【重要】ポジション投入額とパラメータ適用範囲",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_fill_color(20, 40, 80)
        self.rect(14, self.get_y(), 182, 48, "F")
        self.set_xy(17, self.get_y() + 3)
        self.set_font("YG", "", 8)
        self.set_text_color(200, 220, 255)
        self.multi_cell(176, 6,
            "  ポジション投入額（対資金比）= risk_pct ÷ stop_dist_pct × 100\n\n"
            "  例） risk=0.5%、stop=1.5% → 0.5÷1.5×100 = 33%（採用値）\n"
            "      risk=1.0%、stop=0.5% → 1.0÷0.5×100 = 200%（レバ2倍相当）\n\n"
            "  → ポジション投入額が資金の100%以上になる組み合わせは\n"
            "    実運用上、証拠金・レバレッジの観点から成立しないため「適用外」とする。\n"
            "    レポート内の灰色セルはすべて適用外（N/A）。")
        self.ln(3)

        # テストパラメータ
        self.set_y(178)
        self._t(9, bold=True, color=(0, 200, 160))
        self.cell(0, 8, "  テストパラメータ範囲",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("YG", "", 8.5); self.set_text_color(190, 210, 240)
        self.multi_cell(0, 7,
            f"  損切幅 stop_dist_pct : {STOP_DISTS}  （採用: {CONF_STOP}%）\n"
            f"  相関係数 min_corr    : {MIN_CORRS}    （採用: {CONF_CORR}）\n"
            f"  リスク率 risk_pct    : {RISK_PCTS}  （採用: {CONF_RISK}%）\n"
            f"  有効条件数: 30 / 60（ポジション100%未満のみ）")

        # 採用パラメータ参照値
        self.set_y(222)
        self._t(9, bold=True, color=(0, 200, 160))
        self.cell(0, 8, "  採用パラメータ（全期間）参照値",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("YG", "", 8.5); self.set_text_color(190, 210, 240)
        self.multi_cell(0, 7,
            f"  stop={CONF_STOP}%  corr={CONF_CORR}  risk={CONF_RISK}%"
            f"（ポジション投入額={_pos_pct(CONF_STOP,CONF_RISK):.0f}%）\n"
            f"  PF={conf_stats['pf']}  DD={conf_stats['dd']}%  "
            f"PnL=+{conf_stats['pnl']//10000}万円  "
            f"勝率={conf_stats['wr']}%  件数={conf_stats['n']}")

        self.set_y(272)
        self._t(7.5, color=(60, 80, 120))
        self.multi_cell(0, 5,
            f"FxCompany 調査部門（AI孫正義）  |  {today}\n"
            "本資料はロバストネス検証を目的とした内部資料です。", align="C")

    # ── ポジション投入額マトリックスページ ───────────────────────────────────
    def position_size_page(self, img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "① ポジション投入額マトリックス（適用範囲の定義）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(3)
        self.image(img, x=14, y=self.get_y(), w=182, h=72)
        self.ln(76)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "・各セルの値 = risk_pct ÷ stop_dist_pct × 100（%）\n"
            "・赤色セル（100%以上）は1トレードで資金全額以上を投入することを意味し、実運用上成立しないため適用外。\n"
            "・青色★セル = 採用パラメータ（stop=1.5%、risk=0.5%）→ ポジション33%（資金の3分の1）\n"
            "・有効範囲は左上の下三角領域（ポジション<100%）に限定。")

    # ── 構造マップページ ─────────────────────────────────────────────────────
    def structural_page(self, img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "② 構造マップ: stop_dist × min_corr（risk=0.5%固定）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(3)
        self.image(img, x=9, y=self.get_y(), w=192, h=65)
        self.ln(70)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            f"・risk_pct={CONF_RISK}%固定で stop_dist × min_corr を変化させた構造分析。\n"
            "・PFはrisk_pctに依存しないため、この図が戦略の本質的な有効性を表す。\n"
            "・stop=0.5%はrisk=0.5%でポジション100%になるため灰色（N/A）。\n"
            "・橙色ハイライト = 採用パラメータ（stop=1.5%、corr=0.60）")

    # ── リスク管理マップページ ───────────────────────────────────────────────
    def risk_page(self, img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "③ リスク管理マップ: stop_dist × risk_pct（corr=0.6固定）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(3)
        self.image(img, x=9, y=self.get_y(), w=192, h=65)
        self.ln(70)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            f"・min_corr={CONF_CORR}固定で stop × risk を変化させた資金管理分析。\n"
            "・灰色セル（右下領域）= ポジション投入額100%以上 → 適用外（N/A）。\n"
            "・DDはrisk_pctにほぼ比例。stop小×risk大は高DDリスクに注意。\n"
            "・橙色ハイライト = 採用パラメータ（stop=1.5%、risk=0.5%）")

    # ── 散布図ページ ─────────────────────────────────────────────────────────
    def scatter_page(self, img: str):
        self.add_page()
        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, "④ 全有効条件（30条件）PF vs DD 分布",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(3)
        self.image(img, x=9, y=self.get_y(), w=192, h=65)
        self.ln(70)
        self._t(8, color=GRAY)
        self.multi_cell(0, 5,
            "・各点は1条件（stop、corr、riskの組み合わせ）。色はstop_dist。\n"
            "・PF=1.3ラインより上に集中しているほどロバスト性が高い。\n"
            "・点群の密度と分布でパラメータ感度を確認。")

    # ── ランキングページ ─────────────────────────────────────────────────────
    def ranking_page(self, results: dict, today: str):
        self.add_page()
        valid_results = {k: v for k, v in results.items()
                         if _is_valid(k[0], k[2])}
        n_valid = len(valid_results)

        self._t(14, bold=True, color=NAVY)
        self.cell(0, 9, f"⑤ 全{n_valid}条件 詳細成績一覧（PF降順）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL); self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y()); self.ln(3)

        sorted_r = sorted(valid_results.items(), key=lambda x: -x[1]["pf"])
        ws = [24, 22, 24, 18, 18, 20, 20, 22, 14]
        self._header_row(
            ["stop_dist", "min_corr", "risk_pct", "投入額", "件数", "勝率", "PF", "最大DD", "損益(万円)"],
            ws
        )
        for (stop, corr, risk), s in sorted_r:
            confirmed = _is_conf(stop, corr, risk)
            bg = (255, 250, 220) if confirmed else LIGHT
            pf_col = GREEN if s["pf"] >= 1.3 else (AMBER if s["pf"] >= 1.0 else RED)
            self._row(
                [f"{stop:.1f}%", f"{corr:.1f}", f"{risk:.2f}%",
                 f"{_pos_pct(stop,risk):.0f}%",
                 str(s["n"]), f"{s['wr']}%", str(s["pf"]),
                 f"{s['dd']}%", f"{s['pnl']//10000:+.0f}万"],
                ws,
                fills=[bg] * 9,
                bolds=[confirmed] * 3 + [False] * 6,
                aligns=["C"] * 9,
                colors=[DARK]*5 + [DARK, pf_col, DARK, DARK],
                row_h=9, font_size=7
            )
        self.ln(4)

        # ロバストネス判定（stop×corr 9条件 @ CONF_RISK）
        self._sec("ロバストネス判定（構造パラメータ: stop×corr 9条件 @ risk=0.5%）", color=TEAL)
        base = {(s, c): valid_results[(s, c, CONF_RISK)]
                for s in STOP_DISTS for c in MIN_CORRS
                if _is_valid(s, CONF_RISK) and (s, c, CONF_RISK) in valid_results}
        pf_vals   = [v["pf"] for v in base.values()]
        n_base    = len(pf_vals)
        n_black   = sum(1 for p in pf_vals if p >= 1.0)
        n_pass    = sum(1 for p in pf_vals if p >= 1.3)
        conf_pf   = base.get((CONF_STOP, CONF_CORR), {}).get("pf", 0)
        conf_rank = sorted(pf_vals, reverse=True).index(conf_pf) + 1 if conf_pf in pf_vals else 99
        adj_pfs   = [base[(s, c)]["pf"]
                     for s in STOP_DISTS for c in MIN_CORRS
                     if _is_valid(s, CONF_RISK) and (s, c) in base
                     and abs(s - CONF_STOP) <= 0.5 and abs(c - CONF_CORR) <= 0.1
                     and not (s == CONF_STOP and c == CONF_CORR)]
        adj_min   = min(adj_pfs) if adj_pfs else 0.0
        conf_dd   = base.get((CONF_STOP, CONF_CORR), {}).get("dd", 0)

        checks = [
            (n_black >= n_base - 1,
             f"黒字（PF≥1.0）条件数: {n_black}/{n_base}",
             f"{n_base-1}/{n_base}以上が合格",
             "合格" if n_black >= n_base - 1 else "要注意"),
            (n_pass >= round(n_base * 0.7),
             f"PF≥1.3の条件数: {n_pass}/{n_base}",
             f"{round(n_base*0.7)}/{n_base}以上が合格",
             "合格" if n_pass >= round(n_base * 0.7) else "要注意"),
            (conf_rank <= 3,
             f"採用パラメータPF順位: {conf_rank}位/{n_base}",
             "上位3位以内が合格",
             "合格" if conf_rank <= 3 else "要注意"),
            (adj_min >= 1.2,
             f"隣接セル最低PF: {adj_min:.2f}",
             "≥1.2が合格",
             "合格" if adj_min >= 1.2 else "要注意"),
            (conf_dd <= 15.0,
             f"採用パラメータDD（risk=0.5%）: {conf_dd}%",
             "≤15%が合格",
             "合格" if conf_dd <= 15.0 else "要注意"),
        ]
        ws2 = [58, 62, 45, 17]
        self._header_row(["チェック項目", "実測値", "基準", "判定"], ws2)
        for ok, item, criterion, judge in checks:
            jc = GREEN if "合格" in judge else AMBER
            self._row([item, "", criterion, judge], ws2,
                      fills=[LIGHT] * 4, bolds=[False] * 3 + [True],
                      aligns=["L", "L", "L", "C"],
                      colors=[DARK, DARK, DARK, jc])

        all_pass = all(ok for ok, *_ in checks)
        self.ln(4)
        self._t(10, bold=True, color=GREEN if all_pass else AMBER)
        verdict = "全5項目合格 → ロバストネス確認済み" if all_pass else "要注意項目あり → 追加検討推奨"
        self.cell(0, 8, f"  総合判定: {verdict}",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(self.h - 20)
        self._t(7.5, color=GRAY)
        self.multi_cell(0, 5,
            f"作成日: {today}  |  FxCompany 調査部門（AI孫正義）", align="C")


# ── メイン ─────────────────────────────────────────────────────────────────────

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 有効条件を事前計算
    valid_combos = [
        (stop, corr, risk)
        for stop in STOP_DISTS
        for corr in MIN_CORRS
        for risk in RISK_PCTS
        if _is_valid(stop, risk)
    ]
    n_valid = len(valid_combos)

    print(f"\n{'='*65}")
    print(f"  拡張ロバストネステスト v2")
    print(f"  stop_dist : {STOP_DISTS}")
    print(f"  min_corr  : {MIN_CORRS}")
    print(f"  risk_pct  : {RISK_PCTS}")
    print(f"  有効条件  : {n_valid}条件（ポジション投入額<100%のみ）")
    print(f"  除外条件  : {60 - n_valid}条件（ポジション100%以上）")
    print(f"{'='*65}\n")
    print("  有効条件一覧（投入額 = risk÷stop×100）:")
    for stop, corr, risk in valid_combos:
        mark = " ★採用" if _is_conf(stop, corr, risk) else ""
        print(f"    stop={stop:.1f}% corr={corr:.1f} risk={risk:.2f}% "
              f"→ {_pos_pct(stop,risk):.0f}%{mark}")

    # ── データ読み込み ──────────────────────────────────────────────────────
    print("\nセクターデータ読み込み中...")
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
    print(f"  {len(sector_indices)}業種構築完了")

    print("\n動的セクター選別計算中（1回のみ）...")
    active_dates = compute_active_sector_dates(
        sector_indices,
        n_active       = N_ACTIVE_SECTORS,
        sma_window     = SMA_WINDOW,
        ranking_window = RANKING_WINDOW,
    )

    # ── バックテスト（有効条件のみ）─────────────────────────────────────────
    results = {}
    print(f"\n{'─'*65}")
    print(f"  {n_valid}条件バックテスト開始")
    print(f"{'─'*65}")

    for combo_i, (stop, corr, risk) in enumerate(valid_combos, 1):
        mark = " ★採用" if _is_conf(stop, corr, risk) else ""
        print(f"\n  [{combo_i}/{n_valid}] stop={stop:.1f}%  corr={corr:.1f}  "
              f"risk={risk:.2f}%  (投入額{_pos_pct(stop,risk):.0f}%){mark}")

        config = BacktestConfig(
            start_date      = DATA_START,
            sector_min_rise = FIXED_RISE,
            min_gap         = FIXED_GAP,
            risk_pct        = risk,
            stop_dist_pct   = stop,
            min_corr        = corr,
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

        valid = [t for t in all_trades if t.exit_reason != "end"]
        s = _net_stats(valid)
        results[(stop, corr, risk)] = s
        print(f"     → {s['n']}件  勝率{s['wr']}%  PF{s['pf']}  "
              f"DD{s['dd']}%  損益{s['pnl']:+,}円")

    # ── CSV保存 ───────────────────────────────────────────────────────────
    rows = []
    for (stop, corr, risk), s in results.items():
        rows.append({
            "stop_dist_pct": stop, "min_corr": corr, "risk_pct": risk,
            "pos_pct": round(_pos_pct(stop, risk), 0),
            "n": s["n"], "win_rate": s["wr"], "pf": s["pf"],
            "max_dd": s["dd"], "net_pnl_jpy": s["pnl"],
        })
    csv_path = RESULTS_DIR / f"robustness2_{ts}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  CSV保存: {csv_path.name}")

    # ── チャート生成 ──────────────────────────────────────────────────────
    print("\nチャート生成中...")
    img_pos_size   = make_position_size_chart()
    img_structural = make_structural_heatmap(results)
    img_risk       = make_dd_risk_heatmap(results)
    img_scatter    = make_pf_scatter(results)

    # ── PDF生成 ───────────────────────────────────────────────────────────
    print("PDF生成中...")
    conf_stats = results[(CONF_STOP, CONF_CORR, CONF_RISK)]
    pdf = RobustnessPDF2()
    pdf.cover(today, conf_stats)
    pdf.position_size_page(img_pos_size)
    pdf.structural_page(img_structural)
    pdf.risk_page(img_risk)
    pdf.scatter_page(img_scatter)
    pdf.ranking_page(results, today)

    out = REPORT_DIR / f"robustness2_report_{ts}.pdf"
    pdf.output(str(out))

    for f in [img_pos_size, img_structural, img_risk, img_scatter]:
        Path(f).unlink(missing_ok=True)

    print(f"\n完了: {out}")
    print(f"\n{'='*65}")
    print(f"  採用パラメータ★ の成績")
    s = results[(CONF_STOP, CONF_CORR, CONF_RISK)]
    print(f"  stop={CONF_STOP}%  corr={CONF_CORR}  risk={CONF_RISK}%  "
          f"投入額{_pos_pct(CONF_STOP,CONF_RISK):.0f}%:  "
          f"PF={s['pf']}  DD={s['dd']}%  {s['pnl']:+,}円")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
