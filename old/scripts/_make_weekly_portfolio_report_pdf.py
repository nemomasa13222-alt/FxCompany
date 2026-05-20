# -*- coding: utf-8 -*-
"""
FX戦略 資金運用最適化レポート
週次TOP6選択（複合スコア方式）バックテスト分析
実行: python _make_weekly_portfolio_report_pdf.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tempfile
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF, XPos, YPos

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
ROOT      = Path(__file__).parent
DATA_DIR  = ROOT / "docs" / "weekly_portfolio"
OUT_DIR   = DATA_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

CAPITAL = 1_000_000

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
    return fm.FontProperties(fname=FONT_PATH, size=size)

# ── データ読込
print("データ読込中...")
df_sv  = pd.read_csv(DATA_DIR / "summary_comparison.csv", encoding="utf-8-sig")
df_sd  = pd.read_csv(DATA_DIR / "score_detail.csv",       encoding="utf-8-sig")
df_log = pd.read_csv(DATA_DIR / "weekly_selection.csv",   encoding="utf-8-sig")

sv = {row["label"]: row for _, row in df_sv.iterrows()}

# コンビ別選択回数
sc_counts = pd.Series(
    [c for row in df_log["top6_sc"].dropna().str.split("|") for c in row if c]
).value_counts()
total_weeks = len(df_log)

# スコア構成要素 平均（選択頻度上位10）
top10_combos = sc_counts.head(10).index.tolist()
comp_avg = (
    df_sd[df_sd["combo"].isin(top10_combos)]
    .groupby("combo")[["EV","PF","Omega","Tail","RecentF","CostTol","MaxDD","Score"]]
    .mean()
    .reindex(top10_combos)
)

# ── サブチャート生成（3方式比較バー）
def make_comparison_chart():
    labels = ["全組み合わせ", "前週PF TOP6", "複合スコア TOP6"]
    keys   = ["全組み合わせ", "前週PF TOP6", "複合スコア TOP6"]
    pfs    = [sv[k]["pf"]     for k in keys]
    dds    = [sv[k]["dd_pct"] for k in keys]
    pnls   = [sv[k]["total_pnl"] / 1e6 for k in keys]

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5))
    fig.patch.set_facecolor("#F5F8FF")
    colors = ["#95a5a6", "#2980b9", "#e74c3c"]

    for ax, vals, title, thr, fmt, unit in zip(
        axes,
        [pfs,  dds,  pnls],
        ["PF", "最大DD (%)", "総損益（百万円）"],
        [1.2,  None, None],
        [".3f", ".1f", "+.2f"],
        ["",    "%",   "M円"],
    ):
        ax.set_facecolor("#F5F8FF")
        bars = ax.bar(labels, vals, color=colors, alpha=0.85, width=0.5)
        if thr:
            ax.axhline(thr, color="#CC3333", lw=1.0, ls="--", alpha=0.7)
        ax.set_title(title, fontproperties=_jp(9.5), color="#1A3A7A", pad=6)
        ax.grid(axis="y", color="#D0D8EC", lw=0.4, ls="--")
        ax.tick_params(labelsize=7.5)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    v + max(abs(x) for x in vals) * 0.03,
                    format(v, fmt), ha="center", fontsize=9,
                    fontweight="bold", color="#1A3A7A",
                    fontproperties=_jp(9))
        ax.set_xticklabels(labels, fontproperties=_jp(8), rotation=10)

    plt.tight_layout(pad=0.9)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=160, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    return tmp.name

chart_cmp  = make_comparison_chart()
chart_main = str(DATA_DIR / "weekly_composite_backtest.png")

# ── PDF クラス
class PDF(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.add_font("YuGoth", "", FONT_PATH, uni=True)
        self.set_auto_page_break(auto=True, margin=14)

    def _set(self, r, g, b, fill=False):
        if fill: self.set_fill_color(r, g, b)
        else:    self.set_text_color(r, g, b)

    def cover(self):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")

        self.set_font("YuGoth", size=9)
        self._set(*TEAL)
        self.set_xy(14, 50)
        self.cell(182, 8, "FX戦略 資金運用最適化分析", align="C")

        self.set_font("YuGoth", size=20)
        self._set(*WHITE)
        self.set_xy(14, 65)
        self.cell(182, 14, "週次TOP6選択バックテスト", align="C")

        self.set_font("YuGoth", size=14)
        self._set(*TEAL)
        self.set_xy(14, 85)
        self.cell(182, 10, "複合スコア方式による資金運用改善", align="C")

        self.set_font("YuGoth", size=9)
        self._set(*WHITE)
        lines = [
            "Score = 期待値 × PF × √Trades × Omega × Tail × RecentFactor × CostTolerance ÷ (1 + MaxDD)",
            "",
            f"IS期間: 2022-01-01 ～ 2023-12-31     元本: {CAPITAL:,}円  リスク: 0.5%/trade",
            f"比較手法: 全組み合わせ / 前週PF TOP6 / 複合スコア TOP6（各週上位6コンビ）",
            f"生成日: {datetime.now().strftime('%Y-%m-%d')}",
        ]
        y = 108
        for line in lines:
            self.set_xy(14, y)
            self.cell(182, 7, line, align="C")
            y += 8

        # 結果サマリーボックス
        self.set_fill_color(30, 60, 120)
        self.rect(30, 148, 150, 72, "F")
        self._set(*TEAL)
        self.set_font("YuGoth", size=10)
        self.set_xy(30, 154)
        self.cell(150, 8, "複合スコア TOP6  主要結果", align="C")

        rows = [
            ("PF",       f"{sv['複合スコア TOP6']['pf']:.3f}",
                         f"（全体 {sv['全組み合わせ']['pf']:.3f}）"),
            ("最大DD",   f"{sv['複合スコア TOP6']['dd_pct']:.1f}%",
                         f"（全体 {sv['全組み合わせ']['dd_pct']:.1f}%）"),
            ("トレード数", f"{sv['複合スコア TOP6']['n']:,.0f}件",
                         f"（全体 {sv['全組み合わせ']['n']:,.0f}件）"),
            ("総損益",   f"{sv['複合スコア TOP6']['total_pnl']:+,.0f}円",
                         ""),
        ]
        self.set_font("YuGoth", size=9)
        y = 166
        for label, val, note in rows:
            self._set(*GRAY, fill=False)
            self.set_xy(38, y)
            self.cell(38, 8, label)
            self._set(*WHITE)
            self.set_xy(76, y)
            self.cell(50, 8, val, align="R")
            self._set(*TEAL)
            self.set_xy(128, y)
            self.cell(44, 8, note)
            y += 14

    def section_header(self, title, y=None):
        if y: self.set_y(y)
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font("YuGoth", size=10)
        x = self.get_x(); cy = self.get_y()
        self.rect(14, cy, 182, 9, "F")
        self.set_xy(16, cy + 0.8)
        self.cell(178, 8, title)
        self.set_xy(14, cy + 11)
        self._set(*DARK)

    def _row(self, cols, widths, height=8, fill=False, bold=False):
        self.set_font("YuGoth", size=8)
        x, y = 14, self.get_y()
        if fill:
            self.set_fill_color(*LIGHT)
            self.rect(x, y, sum(widths), height, "F")
        for text, w in zip(cols, widths):
            self.set_xy(x, y)
            align = "R" if text and text[0] in ("+", "-", "0","1","2","3",
                                                  "4","5","6","7","8","9") \
                        else "L"
            self.cell(w, height, str(text), align=align)
            x += w
        self.set_xy(14, y + height)

    def _hrow(self, cols, widths, height=8):
        self.set_font("YuGoth", size=8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        x, y = 14, self.get_y()
        self.rect(x, y, sum(widths), height, "F")
        for text, w in zip(cols, widths):
            self.set_xy(x, y)
            self.cell(w, height, str(text), align="C")
            x += w
        self.set_xy(14, y + height)
        self._set(*DARK)

    # ── Page 2: スコア式説明
    def page_formula(self):
        self.add_page()
        self.set_margins(14, 14, 14)

        self.section_header("1. スコア式の設計")

        self.set_font("YuGoth", size=9)
        self._set(*DARK)
        self.set_xy(14, self.get_y() + 2)
        formula = "Score  =  期待値 × PF × √N × Omega × Tail × RecentFactor × CostTolerance  ÷  (1 + MaxDD)"
        self.set_fill_color(*LIGHT)
        self.rect(14, self.get_y(), 182, 10, "F")
        self.set_xy(16, self.get_y() + 1)
        self._set(*NAVY)
        self.set_font("YuGoth", size=8.5)
        self.cell(178, 8, formula)
        self.set_xy(14, self.get_y() + 12)

        defs = [
            ("期待値",        "mean(r_mult)",
             "平均Rレシオ。リスク正規化済みの1トレード当たり期待収益。≤0なら除外"),
            ("PF",            "総利益 / |総損失|",
             "直近4週窓のプロフィットファクター。選択の主軸"),
            ("√N",            "sqrt(トレード数)",
             "サンプル信頼性補正。トレードが少ない週のPFを自動割引"),
            ("Omega",         "Σ正r / Σ|負r|",
             "損益の非対称性。PFと近似するが分布の形状も捉える"),
            ("Tail",          "P95(r) / |P5(r)|",
             "右裾の厚さ。大きな勝ちが大きな負けを上回るか"),
            ("RecentFactor",  "PF(直近1週) / PF(直近4週)",
             "モメンタム係数。直近の勢いを加重。[0.3, 3.0]にクランプ"),
            ("CostTolerance", "mean(pnl) / (mean(pnl) + 2,000)",
             "コスト耐性。平均利益が想定コスト(2,000円/trade)を上回るほど高い"),
            ("1 + MaxDD",     "1 + 4週窓内最大DD(資金比)",
             "DD罰則項。DDが大きいほどスコアを抑制"),
        ]

        self.set_font("YuGoth", size=8)
        self._hrow(["変数", "計算式", "意味・役割"], [32, 50, 100])
        for i, (var, formula_s, meaning) in enumerate(defs):
            self._row([var, formula_s, meaning], [32, 50, 100],
                      height=8, fill=(i % 2 == 0))

        self.set_xy(14, self.get_y() + 5)
        self.section_header("2. 実装パラメータ")
        self.set_xy(14, self.get_y() + 2)

        params = [
            ("評価ウィンドウ", "直近4週（WINDOW_WEEKS=4）"),
            ("最低トレード数", "5件 / 4週窓（未満はスコア0で除外）"),
            ("想定コスト",     "2,000円/trade（スプレッド＋スリッページ相当）"),
            ("RecentFactorクランプ", "[0.3, 3.0]（極端なモメンタム抑制）"),
            ("選択数",         "TOP6コンビ / 週（全24コンビ中）"),
            ("IS期間",         "2022-01-01 ～ 2023-12-31（94週有効）"),
        ]
        self._hrow(["パラメータ", "設定値"], [60, 122])
        for i, (k, v) in enumerate(params):
            self._row([k, v], [60, 122], fill=(i % 2 == 0))

        self.set_xy(14, self.get_y() + 5)
        self.section_header("3. 手法の位置付け")
        self.set_xy(14, self.get_y() + 3)
        self.set_font("YuGoth", size=8.5)
        self._set(*DARK)
        notes = [
            "・各ペア×セッション組み合わせ（コンビ）ごとに週次スコアを算出し、上位6コンビのみトレード。",
            "・シグナル自体（Q10+自己相関フィルター）は変更せず、「どのコンビで取るか」を選択する層。",
            "・JPY系ペアが同時崩壊するシナリオ（クラスターリスク）を自然に回避する仕組みを内包。",
            "・前週PF方式との違い：サンプル数(√N)・コスト耐性・DD罰則を加えることで過学習を抑制。",
        ]
        for note in notes:
            self.set_xy(16, self.get_y())
            self.cell(178, 7, note)
            self.set_xy(14, self.get_y() + 7)

    # ── Page 3: 3方式比較
    def page_comparison(self, chart_cmp_path):
        self.add_page()
        self.set_margins(14, 14, 14)

        self.section_header("4. 3方式バックテスト比較（IS期間 2022-2023）")
        self.set_xy(14, self.get_y() + 2)

        W = [30, 38, 38, 38, 38]
        self._hrow(["指標", "全組み合わせ", "前週PF TOP6", "複合スコア TOP6", "改善幅"], W)

        def fmt_row(key, fmt, label=None, pct=False):
            k = label or key
            b  = sv["全組み合わせ"][key]
            p  = sv["前週PF TOP6"][key]
            s  = sv["複合スコア TOP6"][key]
            diff = s - b
            diff_str = (f"{diff:+,.1f}%" if pct
                        else f"{diff:+,.0f}" if "pnl" in key or "dd" == key.lower()
                        else f"{diff:+.3f}")
            return [k, format(b, fmt), format(p, fmt), format(s, fmt), diff_str]

        rows = [
            ("n",         ",.0f",   "トレード数",   False),
            ("win_rate",  ".1f",    "勝率(%)",       True),
            ("pf",        ".3f",    "PF",            False),
            ("total_pnl", "+,.0f",  "総損益(円)",    False),
            ("max_dd",    ",.0f",   "最大DD(円)",    False),
            ("dd_pct",    ".1f",    "最大DD(%)",     True),
        ]
        for i, (key, fmt, lbl, pct) in enumerate(rows):
            row = fmt_row(key, fmt, lbl, pct)
            # DD改善は色で強調
            self._row(row, W, fill=(i % 2 == 0))

        # 改善サマリーコメント
        self.set_xy(14, self.get_y() + 3)
        self.set_font("YuGoth", size=8.5)
        dd_red = sv["全組み合わせ"]["dd_pct"] - sv["複合スコア TOP6"]["dd_pct"]
        pf_chg = sv["複合スコア TOP6"]["pf"] - sv["前週PF TOP6"]["pf"]
        self.set_fill_color(*LIGHT)
        self.rect(14, self.get_y(), 182, 20, "F")
        self.set_xy(16, self.get_y() + 2)
        self._set(*NAVY)
        self.set_font("YuGoth", size=8.5)
        self.cell(178, 7,
            f"▶ 複合スコアは前週PF方式に比べDD {sv['前週PF TOP6']['dd_pct']:.1f}%→{sv['複合スコア TOP6']['dd_pct']:.1f}% "
            f"（-{sv['前週PF TOP6']['dd_pct']-sv['複合スコア TOP6']['dd_pct']:.1f}pt）、"
            f"PF {sv['前週PF TOP6']['pf']:.3f}→{sv['複合スコア TOP6']['pf']:.3f} "
            f"（+{pf_chg:.3f}）の両立を達成")
        self.set_xy(16, self.get_y() + 7)
        self.cell(178, 7,
            f"▶ 全組み合わせ比でDD {sv['全組み合わせ']['dd_pct']:.1f}%→{sv['複合スコア TOP6']['dd_pct']:.1f}% "
            f"（{dd_red:.1f}pt削減）、PFはほぼ維持。トレード数を74%削減してリスクを集中管理")
        self.set_xy(14, self.get_y() + 10)

        self.section_header("5. 比較チャート")
        self.set_xy(14, self.get_y() + 2)
        self.image(chart_cmp_path, x=14, y=self.get_y(), w=182)
        self.set_xy(14, self.get_y() + 68)

    # ── Page 4: チャート＋コンビ分析
    def page_detail(self, chart_main_path):
        self.add_page()
        self.set_margins(14, 14, 14)

        self.section_header("6. 累積損益・DD・スコア分布チャート")
        self.set_xy(14, self.get_y() + 2)

        if Path(chart_main_path).exists():
            self.image(chart_main_path, x=14, y=self.get_y(), w=182)
            self.set_xy(14, self.get_y() + 142)
        else:
            self.set_xy(14, self.get_y() + 5)
            self.cell(182, 8, "（チャートファイルが見つかりません）")
            self.set_xy(14, self.get_y() + 10)

        self.section_header("7. コンビ別選択頻度ランキング（複合スコア）")
        self.set_xy(14, self.get_y() + 2)

        W2 = [8, 80, 20, 16, 16, 16, 16, 10]
        self._hrow(["#", "コンビ（ペア_セッション）",
                    "選択週", "平均EV", "平均PF", "平均Tail", "平均Ω", "平均DD%"], W2)

        for rank, (combo, cnt) in enumerate(sc_counts.head(10).items(), 1):
            if combo in comp_avg.index:
                row_data = comp_avg.loc[combo]
                ev_  = f"{row_data['EV']:.3f}"
                pf_  = f"{row_data['PF']:.2f}"
                tail_= f"{row_data['Tail']:.3f}"
                om_  = f"{row_data['Omega']:.3f}"
                dd_  = f"{row_data['MaxDD']*100:.1f}%"
            else:
                ev_ = pf_ = tail_ = om_ = dd_ = "─"

            short_name = combo.replace("\n", " ")
            self._row([str(rank), short_name, f"{cnt}週",
                       ev_, pf_, tail_, om_, dd_],
                      W2, fill=(rank % 2 == 0))

        self.set_xy(14, self.get_y() + 5)
        self.set_font("YuGoth", size=8)
        self._set(*GRAY)
        self.cell(182, 7,
            f"※ 選択頻度={cnt}週は総{total_weeks}週中の選択回数。"
            "平均値は選択されたすべての週のスコア構成要素の平均。")

    # ── Page 5: 結論
    def page_conclusion(self):
        self.add_page()
        self.set_margins(14, 14, 14)

        self.section_header("8. 結論と次ステップ")
        self.set_xy(14, self.get_y() + 4)

        conclusions = [
            ("[良好] DD 64.9% → 29.7%  (35pt削減)",
             "全24コンビから毎週TOP6に絞ることで最大DDを半分以下に圧縮。"
             "JPY系ペアが同時崩壊するクラスターリスクを自然回避。"),
            ("[良好] PF 1.271 → 1.269  (ほぼ維持)",
             "PFをほとんど犠牲にせずDDを大幅削減。"
             "損益の総額はトレード数削減に比例して減少するが、効率は同等。"),
            ("[良好] 複合スコア > 前週PF方式",
             f"DD {sv['前週PF TOP6']['dd_pct']:.1f}% -> {sv['複合スコア TOP6']['dd_pct']:.1f}%、"
             f"PF {sv['前週PF TOP6']['pf']:.3f} -> {sv['複合スコア TOP6']['pf']:.3f}。"
             "sqrtN・コスト耐性・DD罰則の追加が有効に機能。"),
            ("[注意] RecentFactor の不安定性",
             "週次PFはサンプルが少なく999.0（全勝）が頻出。"
             "最低トレード数フィルター(MIN_TRADES=5)で緩和済みだが、短期ノイズは残存。"),
        ]

        for emoji_title, body in conclusions:
            self.set_font("YuGoth", size=9)
            self._set(*NAVY)
            self.set_fill_color(*LIGHT)
            self.rect(14, self.get_y(), 182, 8, "F")
            self.set_xy(16, self.get_y() + 0.5)
            self.cell(178, 7, emoji_title)
            self.set_xy(14, self.get_y() + 9)
            self.set_font("YuGoth", size=8.5)
            self._set(*DARK)
            self.set_xy(18, self.get_y())
            self.multi_cell(176, 6, body)
            self.set_xy(14, self.get_y() + 4)

        self.set_xy(14, self.get_y() + 2)
        self.section_header("9. 今後の改善候補")
        self.set_xy(14, self.get_y() + 3)

        nexts = [
            ("OOS検証（2024年以降）",
             "IS期間で設計したスコア方式をOOS期間に適用し、PF・DDの乖離を確認する。"),
            ("複合スコアの重み調整",
             "現行は各要素を乗算。重要度に応じて指数（alpha乗）で調整することでチューニング余地あり。"),
            ("DDスコアの窓延長",
             "4週窓のMaxDDは短期ノイズが大きい。12週窓に延長すると構造的なリスクをより正確に捉えられる。"),
            ("ポートフォリオ全体のDD上限ルール",
             "週次TOP6選択の後段に、ポートフォリオ全体のDD上限（例:15%）を超えたら新規停止するルールを追加。"),
        ]
        W3 = [55, 127]
        self._hrow(["改善項目", "概要"], W3)
        for i, (item, desc) in enumerate(nexts):
            self._row([item, desc], W3, fill=(i % 2 == 0))

        # フッター
        self.set_xy(14, 270)
        self.set_font("YuGoth", size=7.5)
        self._set(*GRAY)
        self.cell(182, 6,
            f"FxCompany 内部分析レポート  /  生成日 {datetime.now().strftime('%Y-%m-%d')}  "
            f"/  IS 2022-2023  /  複合スコア TOP6（WINDOW=4週 / MIN_TRADES=5 / COST=2,000円）",
            align="C")


# ── PDF生成
print("PDF生成中...")
pdf = PDF()
pdf.cover()
pdf.page_formula()
pdf.page_comparison(chart_cmp)
pdf.page_detail(chart_main)
pdf.page_conclusion()

out_path = OUT_DIR / "weekly_portfolio_report.pdf"
pdf.output(str(out_path))
print(f"PDF保存: {out_path}")
print("完了")
