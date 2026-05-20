# -*- coding: utf-8 -*-
"""
Daily-Open Lead-Lag 戦略 — 解析結果報告書 PDF
実行: python _make_daily_open_report_pdf.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import date
from pathlib import Path
import pandas as pd
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
OUT_DIR    = Path("docs")
CHART_DIR  = Path("docs") / "daily_open"

NAVY   = (15,  30,  70);   BLUE   = (30,  80, 160);  ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255);  WHITE  = (255, 255, 255);  DARK   = (30,  30,  40)
GRAY   = (110, 120, 135);  RED    = (180,  40,  40);  GREEN  = (20, 140,  80)
PURPLE = (100,  40, 160);  ORANGE = (200,  90,   0);  AMBER  = (200, 150,   0)


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("YG", "",  FONT_PATH)
        self.add_font("YG", "B", FONT_PATH)
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)

    def _t(self, size=9, bold=False, color=DARK):
        self.set_font("YG", "B" if bold else "", size)
        self.set_text_color(*color)

    def _reset(self):
        self.set_text_color(*DARK)
        self.set_fill_color(*WHITE)
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.2)

    def cover(self, today):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 0, 210, 5, "F")
        self.set_fill_color(200, 40, 40); self.rect(0, 292, 210, 5, "F")

        self.set_y(44)
        self._t(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self._t(20, bold=True, color=WHITE)
        self.cell(0, 13, "日足始値正規化 Lead-Lag 戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(11, bold=True, color=(255, 180, 60))
        self.cell(0, 8, "解析結果報告書 — 正直な検証",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(8, color=(160, 200, 240))
        self.cell(0, 6,
                  "Daily-Open Normalization Lead-Lag Strategy — Honest Evaluation",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # KPIボックス
        self.ln(14)
        kpis = [
            ("最良PF\n(コストあり)", "0.55"),
            ("最良PF\n(0コスト)", "0.998"),
            ("利確時勝率", "7.1%"),
            ("対象ペア", "12"),
        ]
        bw = 38; tw = bw * 4 + 6 * 3; sx = (210 - tw) / 2
        for i, (lb, val) in enumerate(kpis):
            x = sx + i * (bw + 6)
            color = (180, 40, 40) if i <= 1 else (200, 150, 0) if i == 2 else (30, 80, 160)
            self.set_fill_color(20, 45, 100)
            self.set_draw_color(60, 100, 180)
            self.rect(x, 162, bw, 26, "FD")
            self.set_xy(x, 164)
            self._t(6.5, color=(140, 170, 220))
            self.cell(bw, 5, lb, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_xy(x, 172)
            self._t(13, bold=True, color=color)
            self.cell(bw, 10, val, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(205)
        self.set_draw_color(120, 40, 40); self.line(40, 205, 170, 205)
        self._t(8, color=(255, 180, 60)); self.set_y(209)
        self.cell(0, 6, "※ この報告書は「なぜ機能しないか」を解明するための診断資料です",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(8, color=(120, 150, 200))
        self.cell(0, 6,
                  f"検証: yfinance 5分足 直近55日  /  12通貨ペア  /  18パラメータ条件",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"作成日: {today}  |  FxCompany 研究部門",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def sec(self, num, title, sub="", color=NAVY):
        self.add_page()
        self.set_fill_color(*color); self.rect(0, 0, 210, 40, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 40, 210, 2.5, "F")
        self.set_y(7)
        self._t(9, color=(120, 160, 220))
        self.cell(0, 6, f"SECTION  {num}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(17, bold=True, color=WHITE)
        self.cell(0, 12, title,
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if sub:
            self._t(8, color=(160, 195, 235))
            self.cell(0, 5, sub,
                      align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(9)
        self._reset()

    def h2(self, title):
        self.ln(4)
        self.set_fill_color(*BLUE); self._t(9, bold=True, color=WHITE)
        self.cell(4, 7, "", fill=True)
        self.set_fill_color(*LIGHT); self._t(9, bold=True, color=DARK)
        self.cell(0, 7, f"  {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._reset(); self.ln(2)

    def body(self, text, size=9):
        self._t(size, color=DARK)
        self.multi_cell(0, 6, text)
        self.ln(1); self._reset()

    def callout(self, text, color=ACCENT):
        self.set_fill_color(230, 248, 242)
        self.set_draw_color(*color); self.set_line_width(0.8)
        self.rect(self.get_x(), self.get_y(), self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._t(9, bold=True, color=color)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3); self._reset()

    def warn(self, text):
        self.set_fill_color(255, 240, 240)
        self.set_draw_color(*RED); self.set_line_width(0.8)
        self.rect(self.get_x(), self.get_y(), self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._t(9, bold=True, color=RED)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3); self._reset()

    def finding(self, text):
        self.set_fill_color(255, 250, 220)
        self.set_draw_color(*AMBER); self.set_line_width(0.8)
        self.rect(self.get_x(), self.get_y(), self.epw, 0.8, "F")
        self.set_line_width(0.2)
        self._t(9, bold=True, color=AMBER)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3); self._reset()

    def son(self, text):
        self.set_fill_color(245, 240, 255)
        self.set_draw_color(*PURPLE); self.set_line_width(1.0)
        self.rect(self.get_x(), self.get_y(), self.epw, 1.0, "F")
        self.set_line_width(0.2)
        self._t(8, bold=True, color=PURPLE)
        self.cell(0, 6, "  孫正義（AI CEO）のコメント",
                  border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_fill_color(245, 240, 255)
        self._t(9, color=DARK)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3); self._reset()

    def formula(self, title, lines):
        self.set_fill_color(248, 249, 252)
        self.set_draw_color(180, 195, 220)
        self._t(8, bold=True, color=BLUE)
        self.cell(0, 6, f"  {title}",
                  border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(8, color=DARK)
        for line in lines:
            h = 3 if line == "" else 5.5
            self.cell(0, h, f"  {line}", border="LR", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 2, "", border="LBR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3); self._reset()

    def tbl(self, headers, rows, widths, hi=None, aligns=None):
        self._t(8, bold=True, color=WHITE)
        self.set_fill_color(*NAVY)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        if hi is None: hi = set()
        if aligns is None: aligns = ["L"] + ["C"] * (len(widths) - 1)
        for i, row in enumerate(rows):
            is_hi = i in hi
            bg = (220, 245, 220) if is_hi else (
                (245, 248, 255) if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            for j, (cell, w) in enumerate(zip(row, widths)):
                self._t(8, bold=is_hi, color=GREEN if is_hi else DARK)
                self.cell(w, 6, str(cell), border=1, fill=True,
                          align=aligns[j])
            self.ln()
        self.ln(4); self._reset()

    def img(self, path, w=170, caption=""):
        p = Path(path)
        if p.exists():
            self.image(str(p), x=self.get_x(), y=self.get_y(), w=w)
            self.ln(w * 0.43 + 2)
        if caption:
            self._t(7, color=GRAY)
            self.cell(0, 5, caption, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
        self._reset()

    def divider(self):
        self.ln(3)
        self.set_draw_color(200, 210, 230)
        self.line(self.get_x(), self.get_y(),
                  self.get_x() + self.epw, self.get_y())
        self.ln(4); self._reset()


# ══════════════════════════════════════════════════════════════════════
def load_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf   = PDF()

    df_survey = load_csv(CHART_DIR / "survey_results.csv")

    # ══ 表紙 ════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: 戦略の設計 ════════════════════════════════════════════
    pdf.sec("1", "戦略の設計", "日足始値正規化 × 通貨強弱 Lead-Lag")

    pdf.callout(
        "【新アプローチの3つの変更点】\n"
        "① 対数変化率 → 日足始値を100として正規化した%変化率を使用\n"
        "② 通貨強弱インデックスも同じ%変化率ベースで再計算（B案）\n"
        "③ 閾値に達したペアをA（強弱差順）とB（スプレッド順）の2パターンで優先付け"
    )

    pdf.h2("1-1.  計算フロー")
    pdf.formula("日足始値正規化スプレッドの計算", [
        "daily_open(pair)      = その日の最初のバーの始値（UTC日付ごとにリセット）",
        "real_pct(pair, t)     = ( Close(t) - daily_open ) / daily_open × 100",
        "",
        "Strength(USD, t)      = mean of:",
        "  + real_pct(USDJPY, t)       [USD is base]",
        "  - real_pct(GBPUSD, t)       [USD is quote]",
        "  - real_pct(AUDUSD, t)       [USD is quote]  ...",
        "",
        "synthetic_pct(pair, t) = Strength(base, t) - Strength(quote, t)",
        "spread(pair, t)        = real_pct(pair, t) - synthetic_pct(pair, t)",
    ])

    pdf.h2("1-2.  エントリー / エグジット条件")
    pdf.tbl(
        headers=["条件", "設定値", "備考"],
        rows=[
            ["エントリー閾値（当初）", "3.0%", "日本株の乖離率をそのまま流用（後述の問題あり）"],
            ["エントリー閾値（再設定）", "0.10 / 0.20 / 0.30%", "FXスプレッド分布に合わせて再調整"],
            ["利確閾値", "0.03 / 0.05 / 0.10%", "スプレッドがこの値に縮小したら利確"],
            ["損切り", "-1.5%（価格ベース）", "エントリー価格から1.5%逆行したら損切り"],
            ["時間切れ", "60バー（5時間）", "5分足 × 60本"],
            ["日またぎ強制決済", "UTC日付変わりで全決済", "イントラデイ戦略として純化"],
            ["sort_mode A", "強弱差 |Str(base) - Str(quote)|", "通貨強弱の差が大きい順に優先"],
            ["sort_mode B", "|spread|", "スプレッドが大きい順に優先"],
        ],
        widths=[46, 46, 82],
        aligns=["L", "C", "L"],
    )

    # ══ Section 2: スプレッド分布の衝撃的発見 ═══════════════════════════
    pdf.sec("2", "スプレッド分布の発見",
            "なぜ3%閾値が機能しなかったか", color=(100, 20, 20))

    pdf.warn(
        "【重大な前提ズレ】\n\n"
        "日本株セクター追いつき戦略の「3%乖離」は『5日間の株価変動』を前提とする。\n"
        "FXイントラデイの real_pct - synthetic_pct は全体で最大 0.3〜1.5% 程度しかない。\n\n"
        "設定した3%は実際のFXスプレッド分布の99パーセンタイルをはるかに超えており、\n"
        "シグナルがほぼ発生しなかった（50日間で1件のみ）。"
    )

    pdf.h2("2-1.  ペア別スプレッド分布（Include-Self方式）")
    pdf.tbl(
        headers=["ペア", "99th %ile", "95th %ile", ">0.1%の頻度", ">0.3%の頻度", "特徴"],
        rows=[
            ["USDJPY", "0.494%", "0.196%", "13.2%", "1.86%", "標準的"],
            ["EURJPY", "0.594%", "0.172%", "17.5%", "1.52%", "標準的"],
            ["GBPJPY", "0.453%", "0.260%", "41.7%", "2.65%", "やや大きい"],
            ["CHFJPY", "1.547%", "0.536%", "47.5%", "13.93%", "★ 突出して大きい"],
            ["GBPUSD", "0.471%", "0.336%", "53.0%", "8.24%", "やや大きい"],
            ["EURGBP", "0.409%", "0.281%", "46.7%", "4.05%", "やや大きい"],
            ["AUDNZD", "0.213%", "0.152%", "14.3%", "0.00%", "★ 最小"],
        ],
        widths=[24, 22, 22, 28, 28, 50],
        aligns=["L", "C", "C", "C", "C", "L"],
    )

    pdf.finding(
        "スケール比較:\n\n"
        "  日本株「3%乖離」     → セクターが5日で+5%上昇、株が-1% → 差分6%\n"
        "  FXイントラデイのspread → 最大でも 0.3〜1.5%（1日を通じた全変動）\n\n"
        "FXでは1日で1%動けば大きな動きとされる。\n"
        "その日の中で real vs synthetic の差分が0.1%を超えるだけで「有意な乖離」と見なすべき。\n"
        "日本株のスケールをそのまま流用したことが当初の失敗の直接原因。"
    )

    pdf.img(str(CHART_DIR / "spread_example.png"), w=165,
            caption="USDJPY の Real% vs Synthetic% および Spread（直近3日・5分足）")

    # ══ Section 3: パラメータサーベイ結果 ════════════════════════════════
    pdf.sec("3", "パラメータサーベイ結果",
            "18通り全条件での損益（再設定後：0.10〜0.30%）", color=(100, 20, 20))

    pdf.warn(
        "結果: 18通り全条件でPF < 1.0（赤字）\n\n"
        "最良: entry=0.10% / exit=0.05% で PF = 0.55（コストあり）\n"
        "0コストでも: entry=0.10% で PF = 0.998（ほぼトントン、コスト除去でも回収不能）\n\n"
        "この戦略設計では、現時点でアルファが確認できない。"
    )

    pdf.h2("3-1.  全18条件の結果一覧")
    if not df_survey.empty:
        rows = []
        for _, r in df_survey.iterrows():
            pf_s = f"{r['pf']:.3f}" if r['pf'] < 99 else "inf"
            flag = "▲" if r['pf'] >= 1.0 else ("△" if r['pf'] >= 0.8 else "×")
            rows.append([
                f"{r['entry_threshold']}%",
                f"{r['exit_threshold']}%",
                r['sort_mode'],
                str(int(r['trades'])),
                f"{r['win_rate']*100:.1f}%",
                pf_s,
                f"{r['total_pnl']:+.1f}%",
                f"{r['max_dd']:.1f}%",
                flag,
            ])
        pdf.tbl(
            headers=["entry", "exit", "sort", "T", "win%", "PF", "Total%", "maxDD", "判定"],
            rows=rows,
            widths=[18, 16, 24, 20, 16, 18, 22, 20, 20],
        )

    pdf.h2("3-2.  コストあり vs 0コスト 比較")
    pdf.tbl(
        headers=["設定", "コストあり PF", "0コスト PF", "判定"],
        rows=[
            ["entry=0.10% exit=0.05%", "0.544", "0.998",
             "コスト除去でほぼトントン。純アルファほぼゼロ"],
            ["entry=0.20% exit=0.05%", "0.384", "0.646",
             "0コストでも大幅負け。方向性に問題あり"],
            ["entry=0.30% exit=0.10%", "0.458", "0.684",
             "0コストでも大幅負け。稀なシグナルも機能せず"],
        ],
        widths=[52, 34, 34, 54],
        aligns=["L", "C", "C", "L"],
    )

    pdf.img(str(CHART_DIR / "heatmap_spread.png"), w=100,
            caption="PFヒートマップ（sort=spread）- 全条件で赤色（PF<1）")

    # ══ Section 4: 根本原因の解明 ════════════════════════════════════════
    pdf.sec("4", "根本原因の解明",
            "なぜ spread_reduced（利確）時の勝率が7.1%しかないのか")

    pdf.h2("4-1.  エグジット理由別の分析")
    pdf.tbl(
        headers=["exit_reason", "件数", "勝率", "平均PnL", "診断"],
        rows=[
            ["spread_reduced（利確）", "311",   "7.1%",  "-0.77%",
             "★ 致命的: 利確時にほぼ確実に損失"],
            ["time_limit（5時間）",    "595",   "49.9%", "+0.09%",
             "ほぼランダム。わずかにプラス"],
            ["day_end（日付変わり）",  "270",   "24.8%", "-0.18%",
             "微負け"],
        ],
        widths=[50, 16, 16, 20, 72],
        aligns=["L", "C", "C", "C", "L"],
        hi={0},
    )

    pdf.warn(
        "【核心問題】spread_reduced の勝率が7.1%\n\n"
        "Case B（Pseudo先行・LONG）で spread < -threshold でエントリーした後、\n"
        "スプレッドが縮小（spread_reduced）するとき、価格がほとんど上がっていない。\n\n"
        "スプレッドが縮小する主因:\n"
        "  ① Real（価格）が上昇してSyntheticに追随する → LONG の利益 （期待値）\n"
        "  ② Synthetic（通貨強弱）が下落してRealに追随する → 価格変わらず（損失）\n\n"
        "実際には②が支配的: Syntheticが先に動いた後、Synthetic自体が戻ってくる。\n"
        "Realは動かず、コスト分だけ損失が出る。"
    )

    pdf.h2("4-2.  Include-Self 問題")
    pdf.body(
        "【Include-Self の仕組み】\n"
        "通貨強弱 Strength(USD) を計算するとき、USDJPY 自身のリターンも含める。\n\n"
        "  Strength(USD) = mean(USDJPY, -GBPUSD, -AUDUSD, -NZDUSD) ← USDJPY が含まれる\n"
        "  Synthetic(USDJPY) = Strength(USD) - Strength(JPY)\n\n"
        "【問題】USDJPY が動くと Strength(USD) も変わり、Synthetic(USDJPY) も同方向に動く。\n"
        "Real と Synthetic が構造的に相関してしまい、スプレッドは常に小さく収まる。\n\n"
        "【Exclude-Self との違い】\n"
        "もし USDJPY 自身を除いて Strength(USD) を計算すれば:\n"
        "  → Strength(USD) が USDJPY に「引きずられない」\n"
        "  → スプレッドがより大きく、より独立したシグナルになる\n\n"
        "しかし検証した結果、Exclude-Self でも99パーセンタイルで最大 0.5% 程度に留まる。"
    )

    pdf.h2("4-3.  スプレッドの「縮小メカニズム」")
    pdf.tbl(
        headers=["スプレッド縮小の要因", "内容", "LONG時のPnL"],
        rows=[
            ["① Real が UP（期待）",
             "Synthetic が先行した方向に価格が追随",
             "利益"],
            ["② Synthetic が DOWN（実際）",
             "通貨強弱コンセンサスが元に戻る（平均回帰）",
             "損失（コスト分）"],
            ["③ 両方が動く",
             "RealとSyntheticが歩み寄り",
             "微利益 or 損益ゼロ"],
        ],
        widths=[48, 84, 42],
        aligns=["L", "L", "C"],
        hi={1},
    )

    pdf.finding(
        "実証データが示す事実:\n"
        "FXイントラデイ（5分足）では、通貨強弱コンセンサス（Synthetic）が\n"
        "一時的に乖離しても、Synthetic自体が戻ってくる（平均回帰）のが支配的。\n\n"
        "これは元のLog-Return版 Lead-Lag の発見とも整合的:\n"
        "「伝播率76.8%」= Syntheticがそのまま追随するケースが多い（元の戦略ではプラス）\n"
        "→ 新アプローチ（日足始値正規化）でも同様の構造で、方向が逆に出ている可能性。"
    )

    # ══ Section 5: ペア別・方向別分析 ════════════════════════════════════
    pdf.sec("5", "ペア別・方向別分析",
            "どのペアが特に機能しなかったか")

    pdf.h2("5-1.  ペア別成績（entry=0.10%, exit=0.05%）")
    pdf.tbl(
        headers=["ペア", "T", "勝率", "累積PnL%", "診断"],
        rows=[
            ["CHFJPY",  "156", "26.3%", "-33.66%", "× 最悪：CHFが1ペアしかなくSyntheticが不安定"],
            ["GBPJPY",  "119", "31.1%", "-27.06%", "× 大幅負け"],
            ["EURAUD",  " 89", "33.7%", "-26.55%", "× 大幅負け"],
            ["EURGBP",  "125", "21.6%", "-25.77%", "× 特に勝率低い"],
            ["AUDJPY",  " 66", "27.3%", "-24.52%", "× 大幅負け"],
            ["NZDUSD",  "130", "42.3%", "-23.20%", "△ 勝率はやや高いが負け越し"],
            ["GBPUSD",  "147", "38.1%", "-22.77%", "△"],
            ["NZDJPY",  " 97", "34.0%", "-22.18%", "×"],
            ["AUDUSD",  "112", "41.1%", "-17.21%", "△"],
            ["AUDNZD",  " 46", "34.8%", "- 8.40%", "小幅負け"],
            ["EURJPY",  " 43", "27.9%", "- 3.30%", "小幅負け"],
            ["USDJPY",  " 46", "32.6%", "- 1.17%", "最も損失少ない"],
        ],
        widths=[24, 14, 16, 22, 98],
        aligns=["L", "C", "C", "C", "L"],
    )

    pdf.body(
        "CHFJPYが最悪の理由:\n"
        "CHFは12ペアの中でCHFJPY 1ペアしか存在しない。\n"
        "Strength(CHF) = real_pct(CHFJPY) のみ → Synthetic(CHFJPY) ≈ real_pct(CHFJPY) - Strength(JPY)\n"
        "CHF部分がほぼ自己参照になり、スプレッドが特に大きく（99th = 1.547%）なるが信頼性が低い。"
    )

    pdf.h2("5-2.  Case A vs Case B")
    pdf.tbl(
        headers=["ケース", "件数", "割合", "解説"],
        rows=[
            ["Case B（自ペアエントリー）", "1,148", "97.6%",
             "ほぼすべてCase B。自ペアのspreadが閾値超え"],
            ["Case A（遅行ペア展開）",     "   28",  "2.4%",
             "Case Aはほとんど発生しない"],
        ],
        widths=[54, 20, 20, 80],
        aligns=["L", "C", "C", "L"],
    )

    pdf.body(
        "Case A がほとんど発生しない理由:\n"
        "Case A の条件: sig_pair の spread > threshold かつ base 通貨が強い\n"
        "                かつ 遅行ペアの |spread| <= threshold\n\n"
        "Include-Self で spread が小さいため、「sig_pair だけが大きく乖離し、\n"
        "他の同一通貨ペアはまだ乖離していない」という状況がほぼ発生しない。\n"
        "すべてのペアが同時に似たスプレッドを持つため、Case A 条件に合致しない。"
    )

    # ══ Section 6: 改善案と次のステップ ══════════════════════════════════
    pdf.sec("6", "改善案と次のステップ",
            "この戦略をどう進化させるか")

    pdf.callout(
        "今回の検証で得られた価値ある発見:\n"
        "「日足始値正規化 × Include-Self通貨強弱」では FX イントラデイ戦略として機能しない\n"
        "理由が明確になった。この失敗から3つの改善方向が見えてきた。"
    )

    pdf.h2("6-1.  改善案一覧")
    pdf.tbl(
        headers=["案", "内容", "期待効果", "優先度"],
        rows=[
            ["A: Exclude-Self",
             "通貨強弱計算時に対象ペア自身を除外\n→ Syntheticの独立性を高める",
             "スプレッドの信頼性向上\nCase A が発生しやすくなる",
             "高"],
            ["B: 直接ペア比較",
             "同一通貨を含む複数ペアのreal_pctを直接比較\n例: USDJPY vs AUDUSD の差分",
             "中間計算なしで純粋な乖離を計算\nInclude-Selfの問題を根本回避",
             "高"],
            ["C: 日次足で再実装",
             "5分足ではなく日次足でreal_pct（前日比%）を使用\n50日間の日次データで検証",
             "スケールが大きくなり閾値設定が容易に\n株セクター戦略と同じ土俵で比較可能",
             "中"],
            ["D: 方向転換テスト",
             "Case B LONG → SHORT に変更してテスト\n「Syntheticが戻る」なら逆張り",
             "spread_reduced の勝率が上がるか確認\n現在の7.1%が逆転するか検証",
             "低（まず原因確認が先）"],
        ],
        widths=[18, 70, 60, 18],
        aligns=["C", "L", "L", "C"],
    )

    pdf.h2("6-2.  推奨する次のアクション")
    pdf.tbl(
        headers=["ステップ", "内容", "目標"],
        rows=[
            ["1",
             "案B（直接ペア比較）を実装\n例: 同じ通貨を含む2ペアのreal_pct差を計算",
             "Include-Self問題を回避したクリーンなシグナル"],
            ["2",
             "案C（日次足）で既存Dukascopyデータを使って\n3年間IS/OOS検証",
             "短期ノイズを除去した日次レベルのパターン確認"],
            ["3",
             "イントラデイに戻る場合はExclude-Self実装\nCHFJPYは別扱いまたは除外",
             "信頼性の高いSpreadシグナル"],
        ],
        widths=[16, 100, 58],
        aligns=["C", "L", "L"],
    )

    pdf.son(
        "この失敗は非常に重要な学びです。\n\n"
        "「Include-Selfでは Synthetic が Real を追いかける構造になる」\n"
        "これはプログラムのバグではなく、設計の本質的な問題です。\n\n"
        "株のセクター追いつき戦略でうまくいった理由は:\n"
        "  → セクター指数と個別株は完全に独立している（セクター指数は全銘柄の平均）\n"
        "  → 個別株 = セクター指数の構成要素の1つだが、銘柄固有のノイズがあるため\n"
        "     「セクターは動いたのにこの銘柄だけ遅れている」という状況が実際に起きる\n\n"
        "FXで同じことをするには:\n"
        "  → USDJPY を「セクター指数」（通貨強弱のコンセンサス）とは独立させる必要がある\n"
        "  → Exclude-Self か、あるいは完全に別軸（例: 実際のニュース・指標発表タイミング）\n\n"
        "方向性は正しい。実装方法を変えれば突破口が見えてくる可能性があります。"
    )

    pdf.divider()
    pdf._t(7, color=GRAY)
    pdf.multi_cell(0, 5.5,
                   "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
                   "投資の推奨・助言を行うものではありません。"
                   "過去の検証結果は将来の利益を保証しません。")

    out = OUT_DIR / f"daily_open_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成完了: {out}")
    return out


if __name__ == "__main__":
    generate()
