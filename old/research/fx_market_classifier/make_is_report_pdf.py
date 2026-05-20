# -*- coding: utf-8 -*-
"""
Lead-Lag IS期間 検証報告書 PDF生成
=====================================
実行: python -m fx_market_classifier.make_is_report_pdf
"""
from datetime import date
from pathlib import Path
import pandas as pd
from fpdf import FPDF, XPos, YPos

FONT_PATH  = r"C:\Windows\Fonts\YuGothM.ttc"
ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data" / "dukascopy"
IS_DIR     = ROOT / "docs" / "lead_lag_is"
OUT_DIR    = Path(__file__).parent / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# カラーパレット
NAVY   = (15,  30,  70);  BLUE   = (30,  80, 160);  ACCENT = (0, 160, 120)
LIGHT  = (240, 245, 255); WHITE  = (255, 255, 255);  DARK   = (30,  30,  40)
GRAY   = (110, 120, 135); RED    = (180,  40,  40);  GREEN  = (20, 140,  80)
PURPLE = (100,  40, 160); ORANGE = (200,  90,   0);  TEAL   = (0,  150, 150)


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
        self.set_fill_color(*ACCENT); self.rect(0, 0, 210, 4, "F")
        self.set_y(40); self._t(9, color=(120, 160, 210))
        self.cell(0, 6, "FxCompany  |  FX戦略研究レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(17, bold=True, color=WHITE)
        self.cell(0, 12, "Lead-Lag 情報伝播戦略",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(12, bold=True, color=ACCENT)
        self.cell(0, 8, "IS期間 検証報告書",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self._t(9, color=(160, 200, 240))
        self.cell(0, 6, "In-Sample Validation  |  2022-01-01 ~ 2023-12-31",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(12)

        # データソース情報ボックス
        self.set_fill_color(20, 45, 100); self.set_draw_color(60, 100, 180)
        bx = 25; by = self.get_y(); bw = 160; bh = 38
        self.rect(bx, by, bw, bh, "FD")
        self.set_xy(bx + 4, by + 4)
        self._t(8, bold=True, color=ACCENT)
        self.cell(bw - 8, 6, "データソース", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(bx + 4)
        self._t(7, color=(200, 220, 255))
        self.cell(bw - 8, 5,
                  f"種別  : Dukascopy 5分足 OHLCV",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(bx + 4)
        self.cell(bw - 8, 5,
                  f"フォルダ: data/dukascopy/[PAIR]_5min.parquet",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(bx + 4)
        self.cell(bw - 8, 5,
                  f"対象ペア: USDJPY/EURJPY/GBPJPY/AUDJPY/NZDJPY/CHFJPY + GBPUSD/AUDUSD/NZDUSD/EURGBP/EURAUD/AUDNZD",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(bx + 4)
        self.cell(bw - 8, 5,
                  f"IS期間 : 2022-01-01 ~ 2023-12-31  （OOS: 2024-01-01 ~ 2024-12-31）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(by + bh + 10)
        self.set_draw_color(60, 90, 150)
        self.line(40, self.get_y(), 170, self.get_y())
        self._t(8, color=(120, 150, 200)); self.ln(6)
        self.cell(0, 6,
                  f"パラメータ: 100通り  /  コスト: Realistic（国内証券スプレッド基準）",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 6, f"作成日: {today}  |  FxCompany 研究部門",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def sec(self, num, title, sub=""):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0, 0, 210, 38, "F")
        self.set_fill_color(*ACCENT); self.rect(0, 38, 210, 2, "F")
        self.set_y(8); self._t(9, color=(120, 160, 220))
        self.cell(0, 6, f"SECTION  {num}", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(16, bold=True, color=WHITE)
        self.cell(0, 11, title, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if sub:
            self._t(8, color=(160, 195, 235))
            self.cell(0, 5, sub, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._reset(); self.ln(8)

    def h2(self, title):
        self.ln(3)
        self.set_fill_color(*BLUE); self._t(9, bold=True, color=WHITE)
        self.cell(4, 7, "", fill=True)
        self.set_fill_color(*LIGHT); self._t(9, bold=True, color=DARK)
        self.cell(0, 7, f"  {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._reset(); self.ln(2)

    def body(self, text, size=9):
        self._t(size, color=DARK)
        self.multi_cell(0, 6, text)
        self.ln(1)
        self._reset()

    def callout(self, text, color=ACCENT):
        self.set_fill_color(230, 248, 242); self.set_draw_color(*color)
        self.set_line_width(0.8)
        x, y = self.get_x(), self.get_y()
        self.rect(x, y, self.epw, 0.8, "F"); self.set_line_width(0.2)
        self._t(9, bold=True, color=color)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3); self._reset()

    def son(self, text):
        self.set_fill_color(245, 240, 255); self.set_draw_color(*PURPLE)
        self.set_line_width(1.0)
        x, y = self.get_x(), self.get_y()
        self.rect(x, y, self.epw, 1.0, "F"); self.set_line_width(0.2)
        self._t(8, bold=True, color=PURPLE)
        self.cell(0, 6, "  孫正義（AI CEO）のコメント",
                  border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_fill_color(245, 240, 255); self._t(9, color=DARK)
        self.multi_cell(self.epw, 6.5, text, border="LBR", fill=True)
        self.ln(3); self._reset()

    def fbox(self, title, lines, color=BLUE):
        self.set_fill_color(248, 249, 252); self.set_draw_color(180, 195, 220)
        self._t(8, bold=True, color=color)
        self.cell(0, 6, f"  {title}", border="LTR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(8, color=DARK)
        for line in lines:
            self.cell(0, 5.5, f"  {line}", border="LR", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 2, "", border="LBR", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3); self._reset()

    def tbl(self, headers, rows, widths, hi=None):
        self._t(8, bold=True, color=WHITE); self.set_fill_color(*NAVY)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        if hi is None: hi = set()
        for i, row in enumerate(rows):
            is_hi = i in hi
            bg = (220, 245, 220) if is_hi else ((245, 248, 255) if i % 2 == 0 else WHITE)
            self.set_fill_color(*bg)
            for j, (cell, w) in enumerate(zip(row, widths)):
                self._t(8, bold=is_hi, color=GREEN if is_hi else DARK)
                self.cell(w, 6, str(cell), border=1, fill=True,
                          align="L" if j == 0 else "C")
            self.ln()
        self.ln(4); self._reset()

    def tbl_wrap(self, headers, rows, widths, hi=None, line_h=5.5):
        """テキスト折り返し対応テーブル（multi_cell ベース）"""
        if hi is None: hi = set()
        # ヘッダー
        self._t(8, bold=True, color=WHITE); self.set_fill_color(*NAVY)
        for h, w in zip(headers, widths):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        # データ行
        for i, row in enumerate(rows):
            is_hi = i in hi
            bg    = (220, 245, 220) if is_hi else ((245, 248, 255) if i % 2 == 0 else WHITE)
            # 行の高さ = 最大行数 × line_h
            n_lines = max(len(str(c).split("\n")) for c in row)
            row_h   = n_lines * line_h
            x0, y0  = self.get_x(), self.get_y()
            for j, (txt, w) in enumerate(zip(row, widths)):
                self.set_xy(x0 + sum(widths[:j]), y0)
                self.set_fill_color(*bg)
                self._t(8, bold=is_hi, color=GREEN if is_hi else DARK)
                self.multi_cell(w, line_h, str(txt), border=1, fill=True,
                                align="L" if j == 0 else "C",
                                max_line_height=line_h)
                # multi_cell が複数行描くと y が進むので補正不要（次の cell で set_xy する）
            self.set_xy(x0, y0 + row_h)
        self.ln(4); self._reset()

    def img(self, path, w=170, caption=""):
        p = Path(path)
        if p.exists():
            self.image(str(p), x=self.get_x(), y=self.get_y(), w=w)
            self.ln(w * 0.43 + 2)
        else:
            self._t(8, color=GRAY)
            self.cell(0, 6, f"[チャートなし: {p.name}]",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if caption:
            self._t(7, color=GRAY)
            self.cell(0, 5, caption, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
        self._reset()

    def divider(self):
        self.ln(3); self.set_draw_color(200, 210, 230)
        self.line(self.get_x(), self.get_y(),
                  self.get_x() + self.epw, self.get_y())
        self.ln(4); self._reset()

    # ── ロジック図（テキストベース） ─────────────────────────────────────────
    def logic_diagram(self):
        """戦略ロジックのフロー図をテキストで描画"""
        self.ln(2)
        # 背景ボックス
        self.set_fill_color(18, 35, 80); self.set_draw_color(*ACCENT)
        self.set_line_width(0.8)
        bx = self.get_x(); by = self.get_y(); bw = self.epw; bh = 110
        self.rect(bx, by, bw, bh, "FD")
        self.set_line_width(0.2)

        def _row(y_off, text, size=8, bold=False, color=WHITE, align="L"):
            self.set_xy(bx + 4, by + y_off)
            self._t(size, bold=bold, color=color)
            self.cell(bw - 8, 5.5, text, align=align,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        _row(4,  "【 ロジック全体フロー 】", size=10, bold=True, color=ACCENT, align="C")
        _row(13, "┌─────────────────────────────────────────────────────────────┐", color=(80,120,180))
        _row(19, "│  STEP 1  各ペアの log-return を計算                          │", color=(180,210,255))
        _row(25, "│           actual_return(t) = log( Close(t) / Close(t-1) )   │", color=(140,170,220))
        _row(31, "├─────────────────────────────────────────────────────────────┤", color=(80,120,180))
        _row(37, "│  STEP 2  通貨強弱インデックスを算出（Include-Self方式）       │", color=(180,210,255))
        _row(43, "│           strength(USD) = 平均[ +ret(USDxxx) / -ret(xxxUSD) ]│", color=(140,170,220))
        _row(49, "│           synthetic_ret = strength(base) - strength(quote)   │", color=(140,170,220))
        _row(55, "├─────────────────────────────────────────────────────────────┤", color=(80,120,180))
        _row(61, "│  STEP 3  スプレッドを計算してローリング累積                   │", color=(180,210,255))
        _row(67, "│           spread(t)     = actual_ret(t) - synthetic_ret(t)   │", color=(140,170,220))
        _row(73, "│           cum_spread(t) = rolling_sum( spread, window )       │", color=(140,170,220))
        _row(79, "├─────────────────────────────────────────────────────────────┤", color=(80,120,180))
        _row(85, "│  STEP 4  エントリー判定 ★Case B（Pseudo先行型）のみ採用★    │", color=(255,220,100))
        _row(91, "│    cum_spread < -threshold  かつ  通貨強弱が上方向            │", color=(200,230,255))
        _row(97, "│    → Pseudoが先行UP ＝ Realがまだ追随していない               │", color=(200,230,255))
        _row(103,"│    → 対象ペアを LONG エントリー（逆方向はSHORT）              │", color=(200,230,255))

        self.set_y(by + bh + 3)
        self._reset()


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf   = PDF()

    # データ読み込み
    survey_path = IS_DIR / "survey_is.csv"
    pair_path   = IS_DIR / "pair_ranking_is.csv"
    trades_path = IS_DIR / "best_trades_is.csv"

    df_survey = pd.read_csv(survey_path,  encoding="utf-8-sig") if survey_path.exists()  else pd.DataFrame()
    df_pair   = pd.read_csv(pair_path,    encoding="utf-8-sig") if pair_path.exists()     else pd.DataFrame()
    df_trades = pd.read_csv(trades_path,  encoding="utf-8-sig") if trades_path.exists()   else pd.DataFrame()

    # ══ 表紙 ════════════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: 戦略ロジック詳細 ═════════════════════════════════════════
    pdf.sec("1", "戦略ロジック詳細",
            "Lead-Lag 情報伝播戦略 ― Case B（Pseudo先行型）")

    pdf.callout(
        "核心アイデア:\n"
        "「通貨の強弱インデックスから合成した擬似価格（Pseudo）が、\n"
        " 実際の価格（Real）より先に動いたとき、Realが追随する方向にエントリーする」\n\n"
        "市場原理: FX市場では情報が全ペアに同時に反映されない。\n"
        "流動性の高いペア（USDJPY等）が最初に動き、他ペアに遅れて伝播する。\n"
        "この伝播ラグ（数分〜数十分）を捉えるのが本戦略の本質。"
    )

    pdf.h2("1-1.  ロジック全体フロー")
    pdf.logic_diagram()

    pdf.h2("1-2.  エントリー／エグジット条件")
    pdf.tbl_wrap(
        headers=["項目", "条件", "詳細"],
        rows=[
            ["エントリー\n(LONG)",
             "cum_spread < -entry_threshold\nかつ 通貨強弱が上方向",
             "Pseudoが先行UP。Realの追随を期待してLONG。"],
            ["エントリー\n(SHORT)",
             "cum_spread > +entry_threshold\nかつ 通貨強弱が下方向",
             "Pseudoが先行DOWN。Realの追随を期待してSHORT。"],
            ["利確",
             "cum_spreadがexit_levelまで縮小\n= entry_threshold x (1-exit_ratio)",
             "スプレッド収束=追随完了。\nexit_ratio=1.0でゼロ回帰まで保有。"],
            ["損切",
             "PnL <= -risk_pct (= -0.5%)",
             "資本の0.5%を超える損失で即撤退。"],
        ],
        widths=[28, 68, 78],
        hi={0, 1},
    )

    pdf.h2("1-3.  ポジションサイジング（risk_pct/100 ÷ entry_threshold）")
    pdf.fbox("サイジング計算例（entry_threshold=0.0015, risk_pct=0.5%）", [
        "position_ratio = 0.5% / 0.15% = 3.33倍",
        "risk_amount    = 1,000,000円 × 0.5% = 5,000円",
        "PnL(% of 資本) = position_ratio × 価格変動率",
        "→ ペアが0.15%動いた場合の損益 = ±0.5%（±5,000円）",
    ])

    pdf.h2("1-4.  コストモデル（スプレッド片道のみ）")
    pdf.tbl(
        headers=["ペア", "スプレッド", "エントリーコスト(% of ポジ)", "エグジットコスト"],
        rows=[
            ["USDJPY", "0.2銭", "0.013%", "無料"],
            ["EURJPY", "0.5銭", "0.030%", "無料"],
            ["GBPJPY", "1.0銭", "0.053%", "無料"],
            ["AUDJPY", "0.5銭", "0.050%", "無料"],
            ["NZDJPY", "0.7銭", "0.078%", "無料"],
            ["CHFJPY", "0.9銭", "0.054%", "無料"],
        ],
        widths=[24, 24, 60, 66],
    )
    pdf.body("※ スリッページは考慮なし。スプレッドはエントリー時の片道のみ。エグジットは無料。\n"
             "国内証券（GMOクリック・SBI FXトレード等）通常時スプレッドを基準（pips=0.01円）。")

    # ══ Section 2: データソース ══════════════════════════════════════════════
    pdf.sec("2", "データソース・検証設計",
            "Dukascopy 3年データ × IS/OOS 分割")

    pdf.h2("2-1.  データファイル一覧")
    pdf.fbox("ファイルパス", [
        "ルート    : C:\\Users\\MAI\\OneDrive\\デスクトップ\\FxCompany\\",
        "データ    : data\\dukascopy\\[PAIR]_5min.parquet",
        "IS結果    : docs\\lead_lag_is\\survey_is.csv",
        "レポート  : fx_market_classifier\\reports\\",
    ])

    # データ期間テーブル
    file_rows = []
    for pair in ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY"]:
        path = DATA_DIR / f"{pair}_5min.parquet"
        if path.exists():
            df_tmp = pd.read_parquet(path)
            if df_tmp.index.tz is not None:
                df_tmp.index = df_tmp.index.tz_convert("UTC").tz_localize(None)
            start = df_tmp.index[0].strftime("%Y-%m-%d")
            end   = df_tmp.index[-1].strftime("%Y-%m-%d")
            cnt   = f"{len(df_tmp):,}"
        else:
            start, end, cnt = "—", "—", "—"
        file_rows.append([pair, "5分足", start, end, cnt])

    pdf.tbl(
        headers=["ペア", "種別", "データ開始", "データ終了", "バー数"],
        rows=file_rows,
        widths=[22, 14, 26, 26, 22],
    )

    pdf.h2("2-2.  IS/OOS 設計")
    pdf.tbl_wrap(
        headers=["フェーズ", "期間", "目的", "状態"],
        rows=[
            ["IS（学習期）",
             "2022-01-01\n~ 2023-12-31",
             "パラメータ最適化\n過去2年でサーベイ",
             "★ 本レポートの対象"],
            ["OOS（検証期）",
             "2024-01-01\n~ 2024-12-31",
             "IS選択パラメータの\n汎化性能を評価",
             "封印中\n（IS確定後に開封）"],
        ],
        widths=[28, 30, 58, 58],
        hi={0},
    )

    pdf.callout(
        "OOS開封のルール:\n"
        "  ① IS期間でパラメータを1セット確定する\n"
        "  ② OOSは一度だけ開封する（カーブフィッティング防止）\n"
        "  ③ OOS PF ≥ 1.0 かつ DD ≤ 20% を本番移行の目安とする"
    )

    # ══ Section 3: IS パラメータサーベイ結果 ═════════════════════════════════
    pdf.sec("3", "ISパラメータサーベイ結果",
            "Realistic Cost  /  JPYクロス6ペア  /  100通り")

    if not df_survey.empty:
        pdf.h2("3-1.  上位15件（PF降順）")
        rows = []
        hi_set = set()
        for i, (_, r) in enumerate(df_survey.head(15).iterrows()):
            pf_s = f"{r['pf']:.3f}" if r.get("pf", 0) < 99 else "inf"
            dd_s = f"{r['max_dd']:.2f}%"
            rows.append([
                f"w={int(r['window'])}",
                f"{r['entry_thr']:.4f}",
                f"{r['exit_ratio']:.1f}",
                str(int(r.get("trades", 0))),
                f"{r.get('win_rate', 0)*100:.1f}%",
                pf_s,
                f"{r.get('total_pnl', 0):.2f}%",
                dd_s,
                f"{r.get('propagation_rate', 0)*100:.0f}%",
            ])
            if i == 0:
                hi_set.add(0)
        pdf.tbl(
            headers=["window", "entry", "exit_r", "T", "win%",
                     "PF", "PnL%", "MaxDD", "prop率"],
            rows=rows,
            widths=[18, 20, 16, 14, 14, 18, 18, 18, 18],
            hi=hi_set,
        )

        # ベストパラメータ詳細
        best = df_survey.iloc[0]
        pdf.h2("3-2.  ベストパラメータ詳細")
        pdf.callout(
            f"採用候補パラメータ:\n"
            f"  spread_window   = {int(best['window'])} bars（= {int(best['window'])*5}分）\n"
            f"  entry_threshold = {best['entry_thr']:.4f}\n"
            f"  exit_ratio      = {best['exit_ratio']:.1f}\n\n"
            f"成績:\n"
            f"  PF={best['pf']:.3f}  勝率={best['win_rate']*100:.1f}%"
            f"  トレード数={int(best['trades'])}  PnL={best['total_pnl']:.2f}%"
            f"  MaxDD={best['max_dd']:.2f}%\n"
            f"  伝播率={best['propagation_rate']*100:.1f}%"
        )

        # PnL分布（伝播分類）
        pdf.h2("3-3.  伝播分類（最良設定）")
        prop_total = (int(best.get("prop_Real",0)) + int(best.get("prop_Pseudo",0))
                      + int(best.get("prop_Both",0)) + int(best.get("prop_Neither",0)))
        def pct(v): return f"{v/max(prop_total,1)*100:.1f}%" if prop_total else "—"
        pdf.tbl(
            headers=["分類", "件数", "割合", "意味"],
            rows=[
                ["Pseudo追随", str(int(best.get("prop_Pseudo",0))),
                 pct(int(best.get("prop_Pseudo",0))),
                 "Pseudoが収束方向に動いた（仮説通り）"],
                ["Real逆行",   str(int(best.get("prop_Real",0))),
                 pct(int(best.get("prop_Real",0))),
                 "Realが平均回帰した"],
                ["両方",       str(int(best.get("prop_Both",0))),
                 pct(int(best.get("prop_Both",0))),
                 "Pseudo追随＋Real逆行が同時"],
                ["どちらでも", str(int(best.get("prop_Neither",0))),
                 pct(int(best.get("prop_Neither",0))),
                 "収束要因不明（時間切れ等）"],
            ],
            widths=[24, 16, 16, 118],
        )
    else:
        pdf.body("survey_is.csv が見つかりません。\n"
                 "先に python -m fx_market_classifier.run_is_survey を実行してください。")

    # PnL曲線
    pdf.img(str(IS_DIR / "pnl_curve_is.png"), w=170,
            caption="IS期間 累積損益曲線（最良設定・Realistic Cost）")

    # ══ Section 4: ペア別分析 ════════════════════════════════════════════════
    pdf.sec("4", "ペア別分析",
            "JPYクロス6ペア 個別成績")

    if not df_pair.empty:
        pdf.h2("4-1.  ペア別 累積損益（最良設定）")
        pair_rows = []
        hi_pair   = set()
        df_pair_s = df_pair.sort_values("total_pnl", ascending=False)
        for i, (_, r) in enumerate(df_pair_s.iterrows()):
            wr  = r.get("win_rate", 0)
            pnl = r.get("total_pnl", 0)
            pair_rows.append([
                r["pair"],
                str(int(r.get("trades", 0))),
                f"{wr*100:.1f}%",
                f"{pnl:+.2f}%",
                "★" if pnl > 0 else ("△" if pnl > -1 else "✗"),
            ])
            if pnl > 0:
                hi_pair.add(i)
        pdf.tbl(
            headers=["ペア", "トレード数", "勝率", "累積PnL%", "評価"],
            rows=pair_rows,
            widths=[24, 24, 22, 24, 84],
            hi=hi_pair,
        )

    pdf.img(str(IS_DIR / "pair_pnl_is.png"), w=155,
            caption="ペア別 累積損益（最良設定・IS期間）")

    # ══ Section 5: 今後の方針 ════════════════════════════════════════════════
    pdf.sec("5", "今後の方針",
            "OOS開封 → コスト削減 → 本番準備")

    pdf.h2("5-1.  優先タスク")
    pdf.tbl(
        headers=["優先度", "タスク", "期待効果"],
        rows=[
            ["高",
             "IS確定パラメータでOOS開封\n(2024年1年分)",
             "汎化性能を確認。OOS PF≥1.0 で本番候補"],
            ["高",
             "ECN口座でスプレッド実測\n(目標: 0.005%以下/片道)",
             "コストが1/4になればPF大幅改善"],
            ["中",
             "exit_ratio の感度確認\n(1.0近辺で安定かを確認)",
             "ロングホールド効果とDDのトレードオフ"],
            ["低",
             "Case A（Real先行型）再評価\n(C3制約を緩めて検証)",
             "エントリー機会を増やし件数を増加"],
        ],
        widths=[16, 90, 68],
    )

    pdf.h2("5-2.  本番移行条件")
    pdf.fbox("デモ→本番 チェックリスト", [
        "□  IS PF ≥ 1.3  かつ  IS MaxDD ≤ 20%",
        "□  OOS PF ≥ 1.0  かつ  OOS MaxDD ≤ 20%",
        "□  ECNスプレッド確認（0.005%/片道 以下）",
        "□  デモ口座3ヶ月 PF ≥ 1.0  DD ≤ 25%",
    ])

    pdf.son(
        "IS期間の検証は正しい手順です。\n\n"
        "このアプローチで重要なのは「OOSを絶対に先に見ないこと」。\n"
        "IS最適化 → OOS一回開封 → 結果受け入れ、という手順を厳守すること。\n\n"
        "コスト問題については、前回の50日検証で\n"
        "「コストなしPF 2.07 → コストありPF 1.02」という結果が出ている。\n"
        "3年データのISで同様の傾向が確認できれば、\n"
        "ECN口座でのコスト圧縮が最大の課題だと確定する。\n\n"
        "JPYクロス絞り込みは正解方向。\n"
        "次の報告書でOOS結果を待つ。"
    )

    pdf.divider()
    pdf._t(8, color=GRAY)
    pdf.multi_cell(0, 6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。"
        "過去のバックテスト結果は将来の利益を保証するものではありません。")

    fname = f"lead_lag_is_report_{date.today().strftime('%Y%m%d')}_loo.pdf"
    out   = OUT_DIR / fname
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
