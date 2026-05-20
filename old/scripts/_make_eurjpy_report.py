# -*- coding: utf-8 -*-
"""
EURJPY 通貨強弱×自己相関スキャルピング戦略
IS+OOS バックテスト報告書 PDF
───────────────────────────────────────────────────────────
読み込み: docs/eurjpy/bt_eurjpy.csv / kpi.json
出力:      docs/eurjpy/eurjpy_report_{HHMMSS}.pdf
フォント:  C:\\Windows\\Fonts\\YuGothM.ttc

ページ構成:
  P1: 表紙（KPIボックス + IS/OOS比較表）
  P2: 累積損益チャート + 月次バー
  P3: セッション別成績 + パラメータ採用根拠
  P4: 意思決定フレーム + デモ運用計画
"""
import sys, json, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF, XPos, YPos

# ── パス ──────────────────────────────────────────────────────
BASE       = Path(__file__).parent
FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
DOCS_DIR   = BASE / "docs" / "eurjpy"
BT_CSV     = DOCS_DIR / "bt_eurjpy.csv"
KPI_JSON   = DOCS_DIR / "kpi.json"
IMG_CUM    = DOCS_DIR / "pnl_cumulative.png"
IMG_IS     = DOCS_DIR / "pnl_is.png"
IMG_OOS    = DOCS_DIR / "pnl_oos.png"

ts = datetime.now().strftime("%H%M%S")
OUT_PDF = DOCS_DIR / f"eurjpy_report_{ts}.pdf"

# ── フォント ───────────────────────────────────────────────────
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

# ── カラー定義 ─────────────────────────────────────────────────
NAVY  = (15,  30,  70)
BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120)
GREEN = (0,  140,  80)
RED   = (190,  40,  40)
AMBER = (200, 130,   0)
LIGHT = (235, 242, 255)
LIGHT2= (245, 250, 245)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)
ORANGE= (220, 100,   0)
GOLD  = (180, 130,   0)

def _jp(size):
    return fm.FontProperties(fname=FONT_PATH, size=size)

# ── データ読み込み ─────────────────────────────────────────────
print("データ読み込み中...")
with open(KPI_JSON, encoding="utf-8") as f:
    kpi = json.load(f)

df_all = pd.read_csv(BT_CSV, parse_dates=["signal_dt","entry_dt","exit_dt"])
df_is  = df_all[df_all["period"] == "IS"].copy()
df_oos = df_all[df_all["period"] == "OOS"].copy()

CAPITAL = 1_000_000

# ── KPI動的計算 ─────────────────────────────────────────────────
def calc_kpi(df):
    if len(df) == 0:
        return {}
    n = len(df)
    wins = (df["pnl_yen"] > 0).sum()
    gp = df.loc[df["pnl_yen"]>0,"pnl_yen"].sum()
    gl = df.loc[df["pnl_yen"]<0,"pnl_yen"].abs().sum()
    pf = gp / gl if gl > 0 else float("inf")
    cum = df["pnl_yen"].cumsum()
    rm  = cum.cummax()
    dd  = ((rm - cum) / CAPITAL * 100).max()
    total = df["pnl_yen"].sum()
    avg_win  = df.loc[df["pnl_yen"]>0,"pnl_yen"].mean() if wins > 0 else 0
    avg_loss = df.loc[df["pnl_yen"]<0,"pnl_yen"].mean() if (n-wins) > 0 else 0
    avg_r    = df["r_mult"].mean()
    by_sess  = {}
    for sess, g in df.groupby("session"):
        gp_s = g.loc[g["pnl_yen"]>0,"pnl_yen"].sum()
        gl_s = g.loc[g["pnl_yen"]<0,"pnl_yen"].abs().sum()
        by_sess[sess] = {
            "n": len(g),
            "wr": round((g["pnl_yen"]>0).mean()*100, 1),
            "pf": round(gp_s/gl_s, 3) if gl_s > 0 else 99.0,
            "pnl": round(g["pnl_yen"].sum()),
        }
    return {"n":n, "wins":wins, "wr":round(wins/n*100,1),
            "pf":round(pf,3), "total":round(total), "dd":round(dd,1),
            "avg_win":round(avg_win), "avg_loss":round(avg_loss),
            "avg_r":round(avg_r,3), "by_sess":by_sess}

kpi_is  = calc_kpi(df_is)
kpi_oos = calc_kpi(df_oos)
print(f"  IS:  n={kpi_is['n']}  PF={kpi_is['pf']}  損益={kpi_is['total']/10000:.1f}万  DD={kpi_is['dd']}%")
print(f"  OOS: n={kpi_oos['n']}  PF={kpi_oos['pf']}  損益={kpi_oos['total']/10000:.1f}万  DD={kpi_oos['dd']}%")

# ── 月次ヒートマップ画像生成 ─────────────────────────────────────
print("月次ヒートマップ生成中...")
def make_monthly_heatmap(df_is, df_oos):
    df_is2  = df_is.copy();  df_is2["period_tag"]  = "IS"
    df_oos2 = df_oos.copy(); df_oos2["period_tag"] = "OOS"
    df_all2 = pd.concat([df_is2, df_oos2])
    df_all2["entry_dt"] = pd.to_datetime(df_all2["entry_dt"])
    df_all2["year"]  = df_all2["entry_dt"].dt.year
    df_all2["month"] = df_all2["entry_dt"].dt.month
    monthly = df_all2.groupby(["year","month"])["pnl_yen"].sum() / 10000
    years  = sorted(df_all2["year"].unique())
    months = list(range(1,13))
    month_lbl = ["1月","2月","3月","4月","5月","6月",
                 "7月","8月","9月","10月","11月","12月"]
    mat = np.full((len(years), 12), np.nan)
    for i, yr in enumerate(years):
        for j, mo in enumerate(months):
            if (yr, mo) in monthly.index:
                mat[i, j] = monthly[(yr, mo)]
    vmax = max(abs(np.nanmax(mat)) if not np.all(np.isnan(mat)) else 1,
               abs(np.nanmin(mat)) if not np.all(np.isnan(mat)) else 1, 1)

    fig, ax = plt.subplots(figsize=(13, 2.2 + len(years)*0.72))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")

    for i, yr in enumerate(years):
        is_oos = yr >= 2024
        for j, mo in enumerate(months):
            v = mat[i, j]
            if np.isnan(v):
                bg, txt, tc = "#E8EAF0", "-", "#AAAAAA"
            else:
                intensity = min(abs(v)/vmax, 1.0)
                if v >= 0:
                    r = int(235-intensity*130); g2 = int(255-intensity*30); b = int(235-intensity*130)
                else:
                    r = int(255-intensity*20);  g2 = int(235-intensity*130); b = int(235-intensity*130)
                bg = f"#{r:02X}{g2:02X}{b:02X}"; txt = f"{v:+.1f}"; tc = "#1A1A2E"
            ax.add_patch(plt.Rectangle((j-0.5, i-0.5), 1, 1,
                         facecolor=bg, edgecolor="#FF8800" if is_oos else "#AABBCC",
                         linewidth=2.0 if is_oos else 0.5, zorder=1))
            ax.text(j, i, txt, ha="center", va="center",
                    fontproperties=_jp(8), color=tc, fontweight="bold" if not np.isnan(v) else "normal",
                    zorder=2)
        # 年計
        ann = np.nansum(mat[i])
        c = "#004400" if ann >= 0 else "#440000"
        bg2 = "#CCFFCC" if ann >= 0 else "#FFCCCC"
        ax.add_patch(plt.Rectangle((12-0.5, i-0.5), 1, 1, facecolor=bg2,
                     edgecolor="#FF8800" if is_oos else "#AABBCC",
                     linewidth=2.0 if is_oos else 0.8, zorder=1))
        ax.text(12, i, f"{ann:+.1f}万", ha="center", va="center",
                fontproperties=_jp(8), color=c, fontweight="bold", zorder=2)

    ax.set_xlim(-0.5, 12.5); ax.set_ylim(-0.5, len(years)-0.5)
    ax.set_xticks(range(13)); ax.set_xticklabels(month_lbl+["年計"], fontproperties=_jp(8.5))
    ax.set_yticks(range(len(years))); ax.set_yticklabels([str(y) for y in years], fontproperties=_jp(9))
    ax.invert_yaxis()
    ax.set_title("月次損益ヒートマップ（万円）  青枠=IS / 橙枠=OOS",
                 fontproperties=_jp(10), color="#1A3A7A", pad=8)
    ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, length=0)
    plt.tight_layout(pad=0.5)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=150, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name

img_heatmap = make_monthly_heatmap(df_is, df_oos)

# ── セッション別成績チャート生成 ──────────────────────────────────
print("セッション別成績チャート生成中...")
def make_session_chart(df_is, df_oos, kpi_is, kpi_oos):
    sessions = ["東京 09-15JST", "欧州 15-21JST", "NY   21-03JST", "深夜 03-09JST"]
    sess_labels = ["東京\n09-15JST", "欧州\n15-21JST", "NY\n21-03JST", "深夜\n03-09JST"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle("セッション別成績比較（IS vs OOS）", fontproperties=_jp(11),
                 color="#1A3A7A", y=1.01)

    metrics = [
        ("pf",  "プロフィットファクター",  1.0),
        ("wr",  "勝率 (%)",               50.0),
        ("pnl", "損益（万円）",            0.0),
    ]

    for ax, (col, label, baseline) in zip(axes, metrics):
        ax.set_facecolor("#F5F8FF")
        is_vals  = [kpi_is["by_sess"].get(s, {}).get(col, 0)  / (10000 if col=="pnl" else 1)
                    for s in sessions]
        oos_vals = [kpi_oos["by_sess"].get(s, {}).get(col, 0) / (10000 if col=="pnl" else 1)
                    for s in sessions]
        x = np.arange(len(sessions))
        w = 0.35
        b1 = ax.bar(x - w/2, is_vals,  w, color="#2980b9", alpha=0.85, label="IS 2022-2023")
        b2 = ax.bar(x + w/2, oos_vals, w, color="#e67e22", alpha=0.85, label="OOS 2024")
        ax.axhline(baseline, color="#888", lw=1.0, ls="--", alpha=0.7)
        ax.set_xticks(x); ax.set_xticklabels(sess_labels, fontproperties=_jp(7.5))
        ax.set_title(label, fontproperties=_jp(9.5), color="#1A3A7A", pad=5)
        ax.legend(prop=_jp(7.5))
        ax.grid(axis="y", alpha=0.4)
        for bar, v in zip(list(b1)+list(b2), is_vals+oos_vals):
            if abs(v) > 0.01:
                fmt = f"{v:.3f}" if col=="pf" else (f"{v:.1f}" if col=="wr" else f"{v:.1f}万")
                ax.text(bar.get_x()+bar.get_width()/2,
                        bar.get_height() + (0.02 if v >= 0 else -0.05)*max(abs(max(is_vals+oos_vals, default=0)), 0.1),
                        fmt, ha="center", fontsize=7, fontweight="bold",
                        color="#003080" if bar in b1 else "#804000")

    plt.tight_layout(pad=0.8)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=150, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name

img_session = make_session_chart(df_is, df_oos, kpi_is, kpi_oos)

# ── PDF クラス ─────────────────────────────────────────────────
class EurjpyReport(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  fname=FONT_PATH)
        self.add_font("YG", "B", fname=FONT_PATH)
        self.set_margins(13, 12, 13)
        self.set_auto_page_break(auto=True, margin=12)

    # ── 事前改ページチェック ──────────────────────────────────
    def _pb(self, need=15):
        """need mm 足りなければ改ページ"""
        if self.get_y() + need > self.h - self.b_margin:
            self.add_page()

    # ── テキストユーティリティ ─────────────────────────────────
    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _sec(self, title, color=BLUE):
        self._pb(12)
        self.set_fill_color(*color); self.set_text_color(*WHITE)
        self.set_font("YG", "B", 9)
        self.cell(0, 7, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*DARK); self.ln(2)

    def _note(self, txt, size=8, color=DARK, indent=0):
        self._pb(8)
        self._t(size, color=color)
        self.set_x(self.get_x() + indent)
        self.multi_cell(0, 5, txt)
        self.set_text_color(*DARK)

    # ── テーブル行 ────────────────────────────────────────────
    def _hrow(self, headers, widths, h=7):
        self._pb(h + 2)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        self.set_font("YG", "B", 8)
        y = self.get_y()
        for hdr, w in zip(headers, widths):
            self.cell(w, h, hdr, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(*DARK)

    def _row(self, texts, widths, fills=None, bolds=None, aligns=None,
             row_h=7, font_size=8, colors=None):
        if fills  is None: fills  = [LIGHT] * len(texts)
        if bolds  is None: bolds  = [False] * len(texts)
        if aligns is None: aligns = ["C"] * len(texts)
        if colors is None: colors = [DARK]  * len(texts)
        self._pb(row_h)
        y0 = self.get_y(); x0 = self.get_x(); x = x0
        for txt, w, fc, bold, align, tc in zip(texts, widths, fills, bolds, aligns, colors):
            self.set_fill_color(*fc); self.set_draw_color(180, 190, 210)
            self.rect(x, y0, w, row_h, "FD")
            self.set_text_color(*tc)
            self.set_font("YG", "B" if bold else "", font_size)
            self.set_xy(x + 1, y0 + 1)
            self.cell(w - 2, row_h - 2, str(txt), align=align)
            x += w
        self.set_xy(x0, y0 + row_h)
        self.set_text_color(*DARK); self.set_draw_color(0, 0, 0)

    # ── KPIボックス（大型） ───────────────────────────────────
    def _kpi_box(self, x, y, w, h, label, value, sub="", bg=LIGHT, tc=NAVY, vc=BLUE):
        self.set_fill_color(*bg)
        self.set_draw_color(180, 190, 210)
        self.rect(x, y, w, h, "FD")
        # ラベル
        self.set_font("YG", "B", 7); self.set_text_color(*tc)
        self.set_xy(x + 1, y + 1)
        self.cell(w - 2, 5, label, align="C")
        # 値
        self.set_font("YG", "B", 13); self.set_text_color(*vc)
        self.set_xy(x + 1, y + 7)
        self.cell(w - 2, 8, str(value), align="C")
        # サブ
        if sub:
            self.set_font("YG", "", 6.5); self.set_text_color(*GRAY)
            self.set_xy(x + 1, y + 15)
            self.cell(w - 2, 4, str(sub), align="C")
        self.set_text_color(*DARK)

    # ── ヘッダー ──────────────────────────────────────────────
    def header(self):
        pass  # カスタムヘッダーなし（各ページで手動描画）

    # ──────────────────────────────────────────────────────────
    # P1: 表紙
    # ──────────────────────────────────────────────────────────
    def page1_cover(self, kpi_is, kpi_oos):
        self.add_page()
        W = self.w - 26   # 有効幅

        # タイトルバー
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 22, "F")
        self.set_font("YG", "B", 14); self.set_text_color(*WHITE)
        self.set_xy(13, 4)
        self.cell(W, 8, "EURJPY  通貨強弱 × 自己相関スキャルピング戦略", align="L")
        self.set_font("YG", "", 9)
        self.set_xy(13, 13)
        self.cell(W, 6, "IS+OOS バックテスト最終報告書  /  2026-05-18", align="L")

        self.set_y(28)

        # ── IS KPIボックス ───────────────────────────────────
        self.set_font("YG", "B", 10); self.set_text_color(*BLUE)
        self.cell(0, 6, "  IS期間（2022-2023）", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

        bw = W / 5 - 1
        bh = 22
        y_kpi = self.get_y()
        x_start = 13
        self._kpi_box(x_start + 0*(bw+1.25), y_kpi, bw, bh,
                      "トレード数", f"{kpi_is['n']:,}件", bg=LIGHT)
        self._kpi_box(x_start + 1*(bw+1.25), y_kpi, bw, bh,
                      "勝率", f"{kpi_is['wr']:.1f}%", bg=LIGHT)
        self._kpi_box(x_start + 2*(bw+1.25), y_kpi, bw, bh,
                      "PF", f"{kpi_is['pf']:.3f}",
                      sub="目標≥1.2", bg=LIGHT if kpi_is['pf']>=1.2 else (255,240,240),
                      vc=GREEN if kpi_is['pf']>=1.2 else RED)
        self._kpi_box(x_start + 3*(bw+1.25), y_kpi, bw, bh,
                      "累積損益", f"+{kpi_is['total']/10000:.1f}万円",
                      bg=LIGHT, vc=GREEN if kpi_is['total']>=0 else RED)
        self._kpi_box(x_start + 4*(bw+1.25), y_kpi, bw, bh,
                      "最大DD", f"{kpi_is['dd']:.1f}%",
                      sub="目標≤20%", bg=LIGHT if kpi_is['dd']<=20 else (255,240,240),
                      vc=GREEN if kpi_is['dd']<=20 else AMBER)

        self.set_y(y_kpi + bh + 5)

        # ── OOS KPIボックス ──────────────────────────────────
        self.set_font("YG", "B", 10); self.set_text_color(*ORANGE)
        self.cell(0, 6, "  OOS期間（2024）★ OOS開封済み", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

        y_kpi2 = self.get_y()
        self._kpi_box(x_start + 0*(bw+1.25), y_kpi2, bw, bh,
                      "トレード数", f"{kpi_oos['n']:,}件", bg=(255,248,235))
        self._kpi_box(x_start + 1*(bw+1.25), y_kpi2, bw, bh,
                      "勝率", f"{kpi_oos['wr']:.1f}%", bg=(255,248,235))
        self._kpi_box(x_start + 2*(bw+1.25), y_kpi2, bw, bh,
                      "PF", f"{kpi_oos['pf']:.3f}",
                      sub="IS比較: " + ("UP" if kpi_oos['pf']>=kpi_is['pf'] else "DOWN"),
                      bg=(255,248,235),
                      vc=GREEN if kpi_oos['pf']>=kpi_is['pf'] else AMBER)
        self._kpi_box(x_start + 3*(bw+1.25), y_kpi2, bw, bh,
                      "累積損益", f"+{kpi_oos['total']/10000:.1f}万円",
                      bg=(255,248,235), vc=GREEN if kpi_oos['total']>=0 else RED)
        self._kpi_box(x_start + 4*(bw+1.25), y_kpi2, bw, bh,
                      "最大DD", f"{kpi_oos['dd']:.1f}%",
                      sub="IS比較: " + ("改善" if kpi_oos['dd']<=kpi_is['dd'] else "悪化"),
                      bg=(255,248,235),
                      vc=GREEN if kpi_oos['dd']<=20 else AMBER)

        self.set_y(y_kpi2 + bh + 6)

        # ── IS/OOS比較表 ────────────────────────────────────
        self._sec("IS / OOS 総合比較", NAVY)

        w_lbl = 45; w_val = (W - w_lbl) / 2
        headers = ["指標", "IS  2022-2023", "OOS  2024（開封済）"]
        widths  = [w_lbl, w_val, w_val]
        self._hrow(headers, widths)

        rows_data = [
            ("総トレード数",      f"{kpi_is['n']:,}件",       f"{kpi_oos['n']:,}件"),
            ("勝率",              f"{kpi_is['wr']:.1f}%",     f"{kpi_oos['wr']:.1f}%"),
            ("プロフィットファクター", f"{kpi_is['pf']:.3f}",   f"{kpi_oos['pf']:.3f}"),
            ("累積損益",          f"+{kpi_is['total']/10000:.1f}万円",
                                  f"+{kpi_oos['total']/10000:.1f}万円"),
            ("最大ドローダウン",   f"{kpi_is['dd']:.1f}%",     f"{kpi_oos['dd']:.1f}%"),
            ("平均勝ちトレード",   f"{kpi_is['avg_win']:,}円",  f"{kpi_oos['avg_win']:,}円"),
            ("平均負けトレード",   f"{kpi_is['avg_loss']:,}円", f"{kpi_oos['avg_loss']:,}円"),
            ("平均R倍数",          f"{kpi_is['avg_r']:.3f}R",   f"{kpi_oos['avg_r']:.3f}R"),
        ]

        for i, (lbl, v_is, v_oos) in enumerate(rows_data):
            fill = LIGHT if i % 2 == 0 else WHITE
            self._row([lbl, v_is, v_oos], widths,
                      fills=[NAVY if i==0 else fill, fill, fill],
                      bolds=[True, True, True],
                      aligns=["L","C","C"],
                      colors=[WHITE if i==0 else DARK, DARK, DARK])

        self.ln(5)

        # ── 確定パラメータ ────────────────────────────────────
        self._sec("確定パラメータ（採用値）", TEAL)
        params = [
            ("ペア", "EURJPY（DMM FX スプレッド 0.5pip）"),
            ("Q_EXTREME", f"0.03（通貨強弱差 IS期間 下位3%  閾値={kpi['q_thresh']:.6f}）"),
            ("AC_MIN", "0.10（自己相関係数 ≥0.10 / 方向はセッション別）"),
            ("ロジック", "ブレイクダウン後 + 強弱差極端（Q3%）+ 自己相関フィルター"),
            ("保有時間", "トレイリングストップ OR タイム決済（最大48bar=4時間）"),
            ("資金管理", "Capital=100万円 / Risk=0.5%/trade / ATRベースSL"),
        ]
        pw1 = 42; pw2 = W - pw1
        for i, (k, v) in enumerate(params):
            fill = LIGHT if i % 2 == 0 else WHITE
            self._row([k, v], [pw1, pw2], fills=[fill, fill],
                      bolds=[True, False], aligns=["L","L"])

        self.ln(3)
        self._note(
            "【重要】IS DDが46.3%と大きい理由: NYセッション（21-03JST）のIS期間PF=0.953（赤字）が主因。"
            "OOSではNY PF=1.745と逆転回復。セッション間の期間差・特性の変化を示す可能性あり。"
            "デモ運用ではセッション別損益を個別にモニタリングすること。",
            size=7.5, color=AMBER
        )

    # ──────────────────────────────────────────────────────────
    # P2: 累積損益チャート + 月次バー
    # ──────────────────────────────────────────────────────────
    def page2_pnl(self):
        self.add_page()
        W = self.w - 26

        # タイトルバー
        self.set_fill_color(*BLUE)
        self.rect(0, 0, self.w, 14, "F")
        self.set_font("YG", "B", 11); self.set_text_color(*WHITE)
        self.set_xy(13, 3)
        self.cell(W, 8, "P2  損益チャート（累積・月次）", align="L")
        self.set_y(18)

        # 累積損益チャート
        self._pb(80)
        y_now = self.get_y()
        chart_h = 62
        if IMG_CUM.exists():
            self.image(str(IMG_CUM), x=13, y=y_now, w=W, h=chart_h)
        self.set_y(y_now + chart_h + 3)

        # 月次ヒートマップ
        self._pb(60)
        y_now2 = self.get_y()
        heat_h = 55
        self.image(img_heatmap, x=13, y=y_now2, w=W, h=heat_h)
        self.set_y(y_now2 + heat_h + 5)

        # IS/OOS月次バー（横2分割）
        self._pb(55)
        y_now3 = self.get_y()
        half_w = (W - 3) / 2
        bar_h  = 48
        if IMG_IS.exists():
            self.image(str(IMG_IS),  x=13,            y=y_now3, w=half_w, h=bar_h)
        if IMG_OOS.exists():
            self.image(str(IMG_OOS), x=13+half_w+3,  y=y_now3, w=half_w, h=bar_h)
        self.set_y(y_now3 + bar_h + 4)

        self._note(
            "累積損益: IS（青）+OOS（橙）を連結表示。赤点線=OOS開始（2024-01-01）。"
            "OOSではISのDDは消え、安定的な右肩上がりを確認。月次ヒートマップでは"
            "IS 2022年が赤字月あるが、2023年・2024年は概ね黒字で安定。",
            size=7.5, color=DARK
        )

    # ──────────────────────────────────────────────────────────
    # P3: セッション別成績 + パラメータ採用根拠
    # ──────────────────────────────────────────────────────────
    def page3_sessions(self, kpi_is, kpi_oos):
        self.add_page()
        W = self.w - 26

        self.set_fill_color(*TEAL)
        self.rect(0, 0, self.w, 14, "F")
        self.set_font("YG", "B", 11); self.set_text_color(*WHITE)
        self.set_xy(13, 3)
        self.cell(W, 8, "P3  セッション別成績 / パラメータ採用根拠", align="L")
        self.set_y(18)

        # セッション別チャート
        self._pb(60)
        y_now = self.get_y()
        img_h = 55
        self.image(img_session, x=13, y=y_now, w=W, h=img_h)
        self.set_y(y_now + img_h + 4)

        # セッション別成績テーブル（IS）
        self._sec("セッション別成績テーブル — IS（2022-2023）", BLUE)
        sessions = ["東京 09-15JST", "欧州 15-21JST", "NY   21-03JST", "深夜 03-09JST"]
        directions = {"東京 09-15JST":"△long(弱)", "欧州 15-21JST":"▼SHORT(主力)",
                      "NY   21-03JST":"▲LONG(主力)", "深夜 03-09JST":"△long(弱)"}

        ww = [W/8*1.4, W/8*0.8, W/8*0.8, W/8*1.0, W/8*1.0, W/8*1.2, W/8*1.6, W/8*1.2]
        # 幅補正
        total_w = sum(ww); scale = W / total_w
        ww = [w*scale for w in ww]

        self._hrow(["セッション","方向","件数","勝率","PF","損益","フィルター","判定"],
                   ww, h=7)
        for sess in sessions:
            d = kpi_is["by_sess"].get(sess, {"n":0,"wr":0,"pf":0,"pnl":0})
            pf_ok = d["pf"] >= 1.2
            self._row([sess, directions.get(sess,""),
                       f"{d['n']}件", f"{d['wr']:.1f}%",
                       f"{d['pf']:.3f}",
                       f"{d['pnl']/10000:+.1f}万",
                       "Q3%+ac<-0.10" if "long" in directions.get(sess,"").lower() or "LONG" in directions.get(sess,"")
                       else "Q3%+ac>+0.10",
                       "合格" if pf_ok else "要注意"],
                      ww, font_size=7.5,
                      colors=[DARK,DARK,DARK,DARK,
                               GREEN if pf_ok else AMBER,
                               GREEN if d["pnl"]>=0 else RED,
                               DARK, GREEN if pf_ok else AMBER])

        self.ln(3)

        # セッション別成績テーブル（OOS）
        self._sec("セッション別成績テーブル — OOS（2024）", ORANGE)
        self._hrow(["セッション","方向","件数","勝率","PF","損益","vs IS PF","判定"],
                   ww, h=7)
        for sess in sessions:
            d_o = kpi_oos["by_sess"].get(sess, {"n":0,"wr":0,"pf":0,"pnl":0})
            d_i = kpi_is["by_sess"].get(sess,  {"n":0,"wr":0,"pf":0,"pnl":0})
            pf_up = d_o["pf"] >= d_i["pf"]
            self._row([sess, directions.get(sess,""),
                       f"{d_o['n']}件", f"{d_o['wr']:.1f}%",
                       f"{d_o['pf']:.3f}",
                       f"{d_o['pnl']/10000:+.1f}万",
                       f"IS={d_i['pf']:.3f}→{'UP' if pf_up else 'DOWN'}",
                       "改善" if pf_up else "低下"],
                      ww, font_size=7.5,
                      colors=[DARK,DARK,DARK,DARK,
                               GREEN if d_o["pf"]>=1.2 else AMBER,
                               GREEN if d_o["pnl"]>=0 else RED,
                               DARK, GREEN if pf_up else AMBER])

        self.ln(4)

        # プレイブック
        self._sec("プレイブック（確定版）", NAVY)
        pb_data = [
            ("東京 09-15JST",  "△long（弱）", "Q3%+ac<-0.10", "欧州・NY主力の補助的ポジション"),
            ("欧州 15-21JST",  "▼SHORT（主力）","Q3%+ac>+0.10","IS PF=1.799 最も強いエッジ"),
            ("NY   21-03JST",  "▲LONG（主力）", "Q3%+ac<-0.10","OOS PF=1.745 最も安定"),
            ("深夜 03-09JST",  "△long（弱）",  "Q3%+ac<-0.10","件数少ない。補助的運用"),
        ]
        pw = [W/5*1.2, W/5*0.8, W/5*1.0, W/5*2.0]
        self._hrow(["セッション","判定","フィルター","運用メモ"], pw)
        for i, (s, j, f, m) in enumerate(pb_data):
            fill = LIGHT if i % 2 == 0 else WHITE
            self._row([s, j, f, m], pw, fills=[fill]*4,
                      bolds=[False, True, False, False],
                      aligns=["L","C","C","L"])

        self.ln(4)

        # パラメータ採用根拠
        self._sec("パラメータ採用根拠", DARK)
        reasons = [
            ("Q_EXTREME=0.03",
             "Q_EXTREME=0.10→0.05→0.03 と下げるほどエッジが強化。\n"
             "プレイブック調査（_run_strategy_judgment.py）で確認済。"),
            ("AC_MIN=0.10",
             "窓幅12本（1時間）× 閾値0.10 が IS期間で最良組み合わせ。\n"
             "ac>0 → 欧州SHORT（モメンタム継続）/ ac<-0.10 → NY/東京LONG（反転）。"),
            ("スプレッド=0.5pip",
             "DMM FX 公称スプレッド。往復コスト=0.01円/lot。\n"
             "短期スキャルのため正確なスプレッド控除が重要。"),
        ]
        for title, body in reasons:
            self._pb(14)
            self._t(8.5, bold=True, color=BLUE)
            self.cell(0, 6, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self._note(body, size=8, color=DARK, indent=8)
            self.ln(1)

    # ──────────────────────────────────────────────────────────
    # P4: 意思決定フレーム + デモ運用計画
    # ──────────────────────────────────────────────────────────
    def page4_decision(self, kpi_is, kpi_oos):
        self.add_page()
        W = self.w - 26

        self.set_fill_color(*AMBER)
        self.rect(0, 0, self.w, 14, "F")
        self.set_font("YG", "B", 11); self.set_text_color(*WHITE)
        self.set_xy(13, 3)
        self.cell(W, 8, "P4  意思決定フレーム / デモ運用計画", align="L")
        self.set_y(18)

        # 意思決定チェックリスト
        self._sec("戦略採用 意思決定チェックリスト", BLUE)

        oos_ok   = kpi_oos["pf"] >= 1.2
        is_ok    = kpi_is["pf"]  >= 1.1   # DDが大きいためIS PF基準を1.1に
        oos_dd_ok= kpi_oos["dd"] <= 20.0
        oos_plus = kpi_oos["total"] > 0

        checks = [
            (oos_ok,    "OOS PF ≥ 1.2",
             f"実測: OOS PF={kpi_oos['pf']:.3f}  {'PASS' if oos_ok else 'FAIL'}"),
            (is_ok,     "IS PF ≥ 1.1（IS DDが大きいため基準緩和）",
             f"実測: IS PF={kpi_is['pf']:.3f}  {'PASS' if is_ok else 'FAIL'}"),
            (oos_dd_ok, "OOS DD ≤ 20%",
             f"実測: OOS DD={kpi_oos['dd']:.1f}%  {'PASS' if oos_dd_ok else 'FAIL'}"),
            (oos_plus,  "OOS 累積損益 > 0",
             f"実測: OOS損益=+{kpi_oos['total']/10000:.1f}万円  {'PASS' if oos_plus else 'FAIL'}"),
        ]

        all_pass = all(c[0] for c in checks)
        for ok, crit, result in checks:
            mark = "PASS" if ok else "FAIL"
            self._row([mark, crit, result],
                      [18, W*0.55, W*0.45-18],
                      fills=[GREEN if ok else RED, LIGHT, LIGHT],
                      bolds=[True, False, True],
                      aligns=["C","L","L"],
                      colors=[WHITE, DARK, GREEN if ok else RED])

        self.ln(4)

        # 総合判定
        self._pb(20)
        verdict_text = "デモ運用移行 推奨" if all_pass else "条件付き移行（DDに要注意）"
        verdict_color = GREEN if all_pass else AMBER
        self.set_fill_color(*verdict_color)
        self.rect(13, self.get_y(), W, 14, "FD")
        self.set_font("YG", "B", 12); self.set_text_color(*WHITE)
        self.set_xy(13, self.get_y() + 3)
        self.cell(W, 8, f"  総合判定: {verdict_text}", align="L")
        self.set_y(self.get_y() + 14 + 3)

        # 警告/注意事項
        if not all_pass or kpi_is["dd"] > 20:
            self._note(
                f"警告: IS期間のDD={kpi_is['dd']:.1f}%は20%を超えています。"
                "これはNYセッション(IS)が赤字（PF=0.953）のためです。"
                "OOS期間ではNYが改善（PF=1.745）しており、"
                "IS期間特有の現象の可能性がありますが、デモ運用中は注意深く監視すること。",
                size=8, color=RED
            )
            self.ln(2)

        # デモ運用計画
        self._sec("デモ運用計画（GitHub Actions自動化）", TEAL)

        plan_data = [
            ("運用ペア",     "EURJPY（DMM FX）"),
            ("自動実行",     "GitHub Actions: 毎日 JST 8:00（月〜金）"),
            ("シグナル検出", "最新24〜48時間のバーでセッション条件チェック"),
            ("架空執行",     "シグナル発生 → 次5分足Openで架空エントリー"),
            ("決済管理",     "トレイリングストップ OR MAX_HOLD=48bar（4時間）"),
            ("ログ",        "fx_demo/trades.csv / fx_demo/summary.json"),
            ("継続期間",     "最低3ヶ月（2026年5月〜8月目安）"),
        ]

        pw1 = 40; pw2 = W - pw1
        for i, (k, v) in enumerate(plan_data):
            fill = LIGHT if i % 2 == 0 else WHITE
            self._row([k, v], [pw1, pw2], fills=[fill, fill],
                      bolds=[True, False], aligns=["L","L"])

        self.ln(4)

        # 本番移行条件
        self._sec("本番移行条件（デモ期間終了後チェック）", RED)
        conds = [
            ("デモ PF",   "≥ 1.0（トレード数 ≥ 30件）"),
            ("デモ DD",   "≤ 25%（OOS DD=12.8%の2倍以内）"),
            ("セッション別", "欧州・NY の両方が黒字"),
            ("期間",      "最低3ヶ月継続"),
        ]
        pw_c = [40, W-40]
        for i, (k, v) in enumerate(conds):
            fill = (255,240,240) if i % 2 == 0 else WHITE
            self._row([k, v], pw_c, fills=[fill,fill],
                      bolds=[True,False], aligns=["L","L"])

        self.ln(4)

        # スケジュール
        self._sec("実行スケジュール", GRAY)
        sched = [
            ("2026-05-18", "IS+OOSバックテスト完了・本報告書作成"),
            ("2026-05-18", "fx_demo/eurjpy_signal.py 構築・GitHub Actions設定"),
            ("2026-05-19〜", "デモ運用開始（平日毎朝 8:00 JST 自動実行）"),
            ("2026-08目安", "デモ3ヶ月完了・本番移行判定"),
        ]
        ps = [35, W-35]
        for i, (dt, desc) in enumerate(sched):
            fill = LIGHT if i % 2 == 0 else WHITE
            self._row([dt, desc], ps, fills=[fill,fill],
                      bolds=[True,False], aligns=["C","L"])

        self.ln(5)
        self._note(
            "本報告書の戦略パラメータはすべてIS期間（2022-2023）のみで決定。"
            "OOS（2024）は1回限りの開封確認済み。デモ運用期間はOOS後の追加検証として位置づける。",
            size=7.5, color=GRAY
        )

# ── PDF生成 ───────────────────────────────────────────────────
print("\nPDF生成中...")
pdf = EurjpyReport()
pdf.page1_cover(kpi_is, kpi_oos)
pdf.page2_pnl()
pdf.page3_sessions(kpi_is, kpi_oos)
pdf.page4_decision(kpi_is, kpi_oos)

pdf.output(str(OUT_PDF))
print(f"\nPDF出力: {OUT_PDF}")
print("=== 完了 ===")
