# -*- coding: utf-8 -*-
"""CSV・Markdown・PDF レポート出力"""

import os
import csv
import tempfile
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fpdf import FPDF, XPos, YPos


# ── CSV ───────────────────────────────────────────────────────────────────

def save_trades_csv(trades: list[dict], path: Path):
    if not trades:
        return
    fieldnames = ["trade_no", "side", "entry_time", "entry_price",
                  "exit_time", "exit_price", "pips", "pnl_jpy", "result"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(trades)


# ── チャート生成 ──────────────────────────────────────────────────────────

def _make_cumulative_chart(trades: list[dict], checkpoints: list[int]) -> str | None:
    if not trades:
        return None

    pips = [t["pips"] for t in trades]
    cum  = []
    s = 0.0
    for p in pips:
        s += p
        cum.append(s)

    plt.rcParams["font.family"] = "Yu Gothic"
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(range(1, len(cum) + 1), cum, color="#2980b9", linewidth=1.2)
    ax.axhline(0, color="#555", linewidth=0.8, linestyle="--")

    colors = ["#e74c3c", "#e67e22", "#27ae60", "#8e44ad"]
    for cp, color in zip(checkpoints, colors):
        if cp <= len(trades):
            ax.axvline(cp, color=color, linewidth=1.0, linestyle=":",
                       label=f"{cp}回時点")
    if any(cp <= len(trades) for cp in checkpoints):
        ax.legend(fontsize=8)

    ax.set_xlabel("トレード回数", fontsize=9)
    ax.set_ylabel("累積損益（pips）", fontsize=9)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0f}"))
    fig.tight_layout()

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    path = tmp.name
    tmp.close()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ── Markdown ─────────────────────────────────────────────────────────────

def save_markdown(result: dict, path: Path):
    cfg        = result["config"]
    trades     = result["trades"]
    is_trades  = result.get("is_trades")
    oos_trades = result.get("oos_trades")
    checkpoints = result["checkpoint_stats"]
    vd         = result["verdict"]
    strategy_hash = result["strategy_hash"]
    run_time   = result["run_time"]

    lines = []
    lines.append(f"# バックテストレポート\n")
    lines.append(f"実行日時: {run_time}  |  条件ハッシュ: `{strategy_hash}`\n")
    lines.append("---\n")

    # 設定
    lines.append("## 設定\n")
    lines.append(f"| 項目 | 値 |")
    lines.append(f"|------|-----|")
    lines.append(f"| スプレッド | {cfg.SPREAD_PIPS} pips |")
    lines.append(f"| ロット | {cfg.LOTS} |")
    lines.append(f"| 同時保有上限 | {cfg.MAX_POSITIONS} |")
    lines.append(f"| ルックバック本数 | {cfg.LOOKBACK} |")
    s = cfg.START_DATE or "全期間開始"
    e = cfg.END_DATE   or "全期間終了"
    lines.append(f"| 検証期間 | {s} 〜 {e} |")
    if cfg.IS_END_DATE:
        lines.append(f"| IS終了日 | {cfg.IS_END_DATE} |")
    lines.append("")

    # サマリー
    lines.append("## 全体サマリー\n")
    n = len(trades)
    insufficient = n < cfg.INSUFFICIENT_THRESHOLD
    lines.append(f"| 項目 | 値 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 総エントリー回数 | {n}回 |")
    lines.append(f"| 検証判定 | {'**検証不足**' if insufficient else '**検証十分**'} |")
    lines.append(f"| 判定コメント | {vd} |")
    lines.append("")

    # チェックポイント統計
    lines.append("## チェックポイント統計\n")
    lines.append("| 時点 | 勝率 | 期待値(pips) | PF | 最大DD(pips) |")
    lines.append("|------|------|------------|-----|------------|")
    for s in checkpoints:
        wr  = f"{s['win_rate']*100:.1f}%"  if s['win_rate']   is not None else "-"
        ev  = f"{s['expectancy']:+.2f}"    if s['expectancy'] is not None else "-"
        pf  = f"{s['pf']:.2f}"            if s['pf'] is not None and s['pf'] != float('inf') else ("∞" if s['pf'] == float('inf') else "-")
        dd  = f"{s['max_dd_pips']:.1f}"   if s['max_dd_pips'] is not None else "-"
        lines.append(f"| {s['checkpoint']}回 | {wr} | {ev} | {pf} | {dd} |")
    lines.append("")

    # IS/OOS
    if is_trades is not None and oos_trades is not None:
        lines.append("## IS / OOS 比較\n")
        lines.append("| | IS（条件作成期間） | OOS（未使用期間） |")
        lines.append("|--|--|--|")
        for label, tr in [("回数", None), ]:
            pass
        from engine import compute_stats
        is_s  = compute_stats(is_trades)
        oos_s = compute_stats(oos_trades)
        for key, label in [("count","回数"),("win_rate","勝率"),("expectancy","期待値(pips)"),("pf","PF"),("max_dd_pips","最大DD")]:
            iv = is_s[key]
            ov = oos_s[key]
            def fmt(v):
                if v is None: return "-"
                if isinstance(v, float) and v == float("inf"): return "∞"
                if key == "win_rate": return f"{v*100:.1f}%"
                if key in ("expectancy","max_dd_pips"): return f"{v:+.2f}"
                if key == "pf": return f"{v:.2f}"
                return str(v)
            lines.append(f"| {label} | {fmt(iv)} | {fmt(ov)} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ── PDF ───────────────────────────────────────────────────────────────────

class _PDF(FPDF):
    def __init__(self, font_path: str):
        super().__init__()
        self.add_font("YuGoth", style="",  fname=font_path)
        self.add_font("YuGoth", style="B", fname=font_path)

    def dark_header(self, title: str):
        self.set_fill_color(40, 40, 40)
        self.set_text_color(255, 255, 255)
        self.set_font("YuGoth", "B", 11)
        self.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def kv_table(self, rows: list[tuple], col_label=60, col_value=120):
        for label, value, *color in rows:
            self.set_fill_color(235, 235, 235)
            self.set_font("YuGoth", "B", 9)
            self.cell(col_label, 7, label, border=1, fill=True, align="C")
            self.set_fill_color(252, 252, 252)
            self.set_font("YuGoth", "", 9)
            if color:
                self.set_text_color(*color[0])
            self.cell(col_value, 7, str(value), border=1, fill=True, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(0, 0, 0)
        self.ln(4)


def save_pdf(result: dict, path: Path):
    cfg           = result["config"]
    trades        = result["trades"]
    is_trades     = result.get("is_trades")
    oos_trades    = result.get("oos_trades")
    checkpoints   = result["checkpoint_stats"]
    vd            = result["verdict"]
    strategy_hash = result["strategy_hash"]
    run_time      = result["run_time"]

    chart_path = _make_cumulative_chart(trades, cfg.STATS_CHECKPOINTS)

    pdf = _PDF(cfg.FONT_PATH)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)

    # タイトル
    pdf.set_font("YuGoth", "B", 16)
    pdf.cell(0, 10, "バックテストレポート", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("YuGoth", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, f"実行: {run_time}  |  条件ハッシュ: {strategy_hash}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # 設定
    pdf.dark_header("■ 設定")
    s_date = cfg.START_DATE or "全期間開始"
    e_date = cfg.END_DATE   or "全期間終了"
    period = f"{s_date} 〜 {e_date}"
    if cfg.IS_END_DATE:
        period += f"  （IS〜{cfg.IS_END_DATE} / OOS{cfg.IS_END_DATE}〜）"
    pdf.kv_table([
        ("検証期間",       period),
        ("スプレッド",     f"{cfg.SPREAD_PIPS} pips"),
        ("ロット",         str(cfg.LOTS)),
        ("同時保有上限",   f"{cfg.MAX_POSITIONS}"),
        ("ルックバック",   f"{cfg.LOOKBACK} 本"),
    ])

    # サマリー
    pdf.dark_header("■ 全体サマリー")
    n = len(trades)
    insufficient = n < cfg.INSUFFICIENT_THRESHOLD
    vd_color = (180, 0, 0) if "不足" in vd or "マイナス" in vd else \
               (0, 120, 0) if "検討可能" in vd else (0, 0, 0)
    judge_str = f"{'検証不足' if insufficient else '検証十分'}（{n}回）"
    pdf.kv_table([
        ("総エントリー回数", f"{n} 回"),
        ("検証判定",         judge_str,
         (180, 0, 0) if insufficient else (0, 120, 0)),
        ("コメント",         vd, vd_color),
    ], col_label=50, col_value=130)

    # チェックポイント統計テーブル
    pdf.dark_header("■ チェックポイント統計（勝率・期待値・PF・最大DD）")
    col_w   = [24, 26, 34, 26, 30, 40]
    headers = ["時点", "勝率", "期待値(pips)", "PF", "最大DD(pips)", "安定性"]
    pdf.set_font("YuGoth", "B", 9)
    pdf.set_fill_color(220, 220, 220)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    prev_ev = None
    pdf.set_font("YuGoth", "", 9)
    for s in checkpoints:
        wr  = f"{s['win_rate']*100:.1f}%"   if s['win_rate']   is not None else "-"
        ev  = f"{s['expectancy']:+.2f}"      if s['expectancy'] is not None else "-"
        pf_ = (f"{s['pf']:.2f}" if s['pf'] != float("inf") else "∞") if s['pf'] is not None else "-"
        dd  = f"{s['max_dd_pips']:.1f}"     if s['max_dd_pips'] is not None else "-"

        # 安定性（前チェックポイントとの期待値差）
        if prev_ev is not None and s['expectancy'] is not None:
            diff = abs(s['expectancy'] - prev_ev)
            stability = "安定" if diff < 0.5 else ("やや不安定" if diff < 1.5 else "不安定")
        else:
            stability = "-"
        prev_ev = s['expectancy']

        fill = (240, 255, 240) if s.get("expectancy", 0) and s["expectancy"] > 0 \
               else (255, 240, 240) if s.get("expectancy", 0) and s["expectancy"] < 0 \
               else (250, 250, 250)
        pdf.set_fill_color(*fill)
        for w, v in zip(col_w, [f"{s['checkpoint']}回", wr, ev, pf_, dd, stability]):
            pdf.cell(w, 6, v, border=1, fill=True, align="C")
        pdf.ln()
    pdf.ln(4)

    # IS/OOS 比較
    if is_trades is not None and oos_trades is not None:
        from engine import compute_stats
        is_s  = compute_stats(is_trades)
        oos_s = compute_stats(oos_trades)

        pdf.dark_header("■ IS / OOS 比較")
        col_w2   = [40, 65, 65]
        headers2 = ["指標", "IS（条件作成期間）", "OOS（未使用期間）"]
        pdf.set_font("YuGoth", "B", 9)
        pdf.set_fill_color(220, 220, 220)
        for w, h in zip(col_w2, headers2):
            pdf.cell(w, 7, h, border=1, fill=True, align="C")
        pdf.ln()

        def fmt(key, v):
            if v is None: return "-"
            if v == float("inf"): return "∞"
            if key == "win_rate":    return f"{v*100:.1f}%"
            if key == "expectancy":  return f"{v:+.2f} pips"
            if key == "pf":          return f"{v:.2f}"
            if key == "max_dd_pips": return f"{v:.1f} pips"
            return str(v)

        rows_data = [
            ("回数",      "count"),
            ("勝率",      "win_rate"),
            ("期待値",    "expectancy"),
            ("PF",        "pf"),
            ("最大DD",    "max_dd_pips"),
        ]
        pdf.set_font("YuGoth", "", 9)
        for label, key in rows_data:
            iv = fmt(key, is_s[key])
            ov = fmt(key, oos_s[key])
            pdf.set_fill_color(248, 248, 248)
            pdf.cell(col_w2[0], 6, label, border=1, fill=True, align="C")
            pdf.cell(col_w2[1], 6, iv,    border=1, fill=True, align="C")
            pdf.cell(col_w2[2], 6, ov,    border=1, fill=True, align="C",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

    # 累積損益グラフ
    if chart_path:
        pdf.dark_header("■ 累積損益グラフ（pips）")
        pdf.image(chart_path, x=15, w=180)
        pdf.ln(4)
        os.remove(chart_path)

    pdf.output(str(path))
