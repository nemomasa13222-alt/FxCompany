# -*- coding: utf-8 -*-
"""
毎日引け後 自動実行パイプライン
  1. JPX全銘柄スクリーニング（ミネルヴィニ8条件）
  2. 候補銘柄の乖離率フィルタリング
  3. 日次サマリーPDF生成

実行: python japan_stocks/run_daily.py
自動: Windowsタスクスケジューラで 平日16:00 に実行
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from fpdf import FPDF, XPos, YPos

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
import minervini_screener as mv
import jpx_universe as jpx

# ── 設定 ──────────────────────────────────────────────────────────────────────
FONT_PATH   = r"C:\Windows\Fonts\YuGothM.ttc"
RESULTS_DIR = Path(__file__).parent / "results" / "reports"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START  = "2023-01-01"
MARKET      = "prime"
WORKERS     = 30

# 乖離率フィルター: MA20からの乖離がこれ以下のみ「即買い候補」
EXT_IDEAL   = 5.0    # 理想（ベースに極めて近い）
EXT_OK      = 15.0   # 許容（やや乖離）
# 15%超は「要注意（乖離大）」として色分け表示

# ブランドカラー
NAVY  = (15,  30,  70)
BLUE  = (30,  90, 170)
TEAL  = (0,  160, 120)
GREEN = (0,  140,  80)
AMBER = (200, 140,  0)
RED   = (190,  40,  40)
LIGHT = (235, 242, 255)
WHITE = (255, 255, 255)
DARK  = (30,  30,  40)
GRAY  = (110, 110, 120)


# ── スクリーニング ────────────────────────────────────────────────────────────

def run_screening() -> list[dict]:
    print("JPX銘柄リスト取得中...")
    tickers     = jpx.get_tickers_by_market(MARKET)
    ticker_info = jpx.get_ticker_info()
    print(f"  対象: {len(tickers)} 銘柄\n")

    print(f"株価データ取得中（{WORKERS}並列）...")
    closes, done, total = {}, 0, len(tickers)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_fetch_one, t): t for t in tickers}
        for f in as_completed(futures):
            t, s = f.result()
            if s is not None:
                closes[t] = s
            done += 1
            if done % 200 == 0 or done == total:
                print(f"  {done}/{total}  有効: {len(closes)}", end="\r")
    print(f"\n  取得完了: {len(closes)} 銘柄\n")

    print("RS Rating 計算中...")
    rs_pcts = mv.calc_rs_percentiles(closes)

    print("8条件チェック中...")
    results = []
    for ticker, close in closes.items():
        res = mv.check(close, rs_pcts.get(ticker, float("nan")))
        if res and res["passed_all"]:
            info = ticker_info.get(ticker, {})
            results.append({
                "ticker": ticker,
                "name"  : info.get("name", ""),
                "market": info.get("market", ""),
                "sector": info.get("sector33", ""),
                **res,
            })

    # RS降順 → 乖離率昇順
    results.sort(key=lambda r: (-(r["rs_rating"] or 0), r["ext_from_ma20_pct"]))
    print(f"  全条件クリア: {len(results)} 銘柄\n")
    return results, len(closes)


def _fetch_one(ticker):
    try:
        df = dt.fetch(ticker, start=DATA_START)
        if len(df) >= 220:
            return ticker, df["Close"]
    except Exception:
        pass
    return ticker, None


# ── チャート生成 ──────────────────────────────────────────────────────────────

def make_mini_chart(close: pd.Series, ticker: str, name: str,
                    ma50: float, ma150: float, ma200: float) -> str:
    plot = close.iloc[-252:] if len(close) >= 252 else close
    _ma50  = close.rolling(50).mean().reindex(plot.index)
    _ma150 = close.rolling(150).mean().reindex(plot.index)
    _ma200 = close.rolling(200).mean().reindex(plot.index)

    fig, ax = plt.subplots(figsize=(7, 3))
    fig.patch.set_facecolor("#F5F8FF")
    ax.set_facecolor("#F5F8FF")
    ax.plot(plot.index, plot.values,   color="#1A3A7A", lw=1.6, label="株価")
    ax.plot(_ma50.index,  _ma50.values,  color="#E07020", lw=1.0, ls="-",  label="MA50")
    ax.plot(_ma150.index, _ma150.values, color="#8030C0", lw=1.0, ls="--", label="MA150")
    ax.plot(_ma200.index, _ma200.values, color="#C03030", lw=1.0, ls=":",  label="MA200")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.tick_params(labelsize=6)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.grid(axis="y", color="#D0D8E8", lw=0.4, ls="--")
    ax.legend(loc="upper left", fontsize=6, framealpha=0.8,
              prop=_jp(6))
    ax.set_title(f"{ticker} {name}", fontsize=7.5, color="#1A3A7A",
                 fontproperties=_jp(7.5))
    for sp in ax.spines.values():
        sp.set_edgecolor("#C0CCD8")
    plt.tight_layout(pad=0.5)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return tmp.name


def _jp(size):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=FONT_PATH, size=size)


# ── PDF クラス ────────────────────────────────────────────────────────────────

class DailyReportPDF(FPDF):
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
        self.ln(2)

    # ── 表紙 ─────────────────────────────────────────────────────────────────
    def cover(self, today: str, n_scanned: int, n_passed: int):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 4, "F")
        self.rect(0, 293, 210, 4, "F")

        self.set_y(50)
        self._t(9, color=(130, 165, 215))
        self.cell(0, 7, "FxCompany  |  日次株式スクリーニングレポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        self._t(28, bold=True, color=WHITE)
        self.cell(0, 18, today, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(13, bold=True, color=(0, 210, 160))
        self.cell(0, 10, "ミネルヴィニ・トレンドテンプレート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._t(10, color=WHITE)
        self.cell(0, 8, "全8条件クリア 候補銘柄レポート",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(8)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(50, self.get_y(), 160, self.get_y())
        self.ln(6)

        # サマリー数値
        for label, val in [
            ("対象市場", "東証プライム市場"),
            ("検査銘柄数", f"{n_scanned:,} 社"),
            ("全条件クリア", f"{n_passed} 社  （通過率 {n_passed/n_scanned*100:.1f}%）"),
            ("使用手法", "ミネルヴィニ・トレンドテンプレート（8条件）"),
        ]:
            self._t(9, color=(140, 170, 220))
            self.cell(55, 7, label, align="R")
            self._t(9, bold=True, color=WHITE)
            self.cell(0, 7, f"  {val}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_y(255)
        self._t(7, color=(60, 80, 120))
        self.multi_cell(0, 5,
            "本レポートは投資勧誘を目的とするものではありません。投資判断は自己責任でお願いします。",
            align="C")

    # ── 乖離率凡例 ────────────────────────────────────────────────────────────
    def _ext_badge(self, ext: float) -> tuple:
        """乖離率に応じた色とラベルを返す"""
        if ext <= EXT_IDEAL:
            return GREEN, f"+{ext:.1f}%  ◎"
        elif ext <= EXT_OK:
            return AMBER, f"+{ext:.1f}%  ○"
        else:
            return RED,   f"+{ext:.1f}%  △ 乖離大"

    # ── サマリーテーブルページ ────────────────────────────────────────────────
    def summary_page(self, results: list[dict], today: str):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, f"全条件クリア銘柄 一覧  （{today}）",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(3)

        # 凡例
        self._t(7.5)
        self.cell(0, 5,
            "MA50乖離率:  ◎ +10%以内（ベース付近）　○ +10〜20%（許容範囲）　△ +20%超（乖離大・注意）",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

        # ヘッダー
        headers = ["銘柄", "銘柄名", "RS", "株価", "高値比", "MA50乖離", "安値比", "セクター"]
        widths  = [18, 44, 10, 18, 16, 22, 16, 38]
        self.set_font("YG", "B", 7)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for h, w in zip(headers, widths):
            self.cell(w, 6.5, h, border=1, fill=True, align="C")
        self.ln()

        # 行
        for i, r in enumerate(results):
            bg = LIGHT if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*DARK)
            ext = r["ext_from_ma20_pct"]
            ext_color, ext_label = self._ext_badge(ext)

            self.set_font("YG", "B", 7)
            self.cell(widths[0], 6, r["ticker"], border=1, fill=True, align="C")
            self.set_font("YG", "", 7)
            self.cell(widths[1], 6, r["name"][:14], border=1, fill=True)

            # RS（90台は緑、70台は青）
            rs = r["rs_rating"] or 0
            rs_c = GREEN if rs >= 90 else BLUE if rs >= 70 else DARK
            self.set_text_color(*rs_c)
            self.set_font("YG", "B", 7)
            self.cell(widths[2], 6, str(rs), border=1, fill=True, align="C")
            self.set_text_color(*DARK)

            self.set_font("YG", "", 7)
            self.cell(widths[3], 6, f"{r['price']:,.0f}", border=1, fill=True, align="R")
            self.cell(widths[4], 6, f"{r['dist_from_high_pct']:+.1f}%", border=1, fill=True, align="C")

            # 乖離率（色付き）
            self.set_text_color(*ext_color)
            self.set_font("YG", "B", 7)
            self.cell(widths[5], 6, ext_label, border=1, fill=True, align="C")
            self.set_text_color(*DARK)

            self.set_font("YG", "", 7)
            self.cell(widths[6], 6, f"+{r['rise_from_low_pct']:.0f}%", border=1, fill=True, align="C")
            self.cell(widths[7], 6, r["sector"][:12], border=1, fill=True)
            self.ln()

        self.ln(3)
        self._t(7.5, color=GRAY)
        ideal   = sum(1 for r in results if r["ext_from_ma20_pct"] <= EXT_IDEAL)
        ok      = sum(1 for r in results if EXT_IDEAL < r["ext_from_ma20_pct"] <= EXT_OK)
        caution = sum(1 for r in results if r["ext_from_ma20_pct"] > EXT_OK)
        self.cell(0, 5,
            f"内訳 ─ ◎ ベース付近: {ideal}社  ○ 許容範囲: {ok}社  △ 乖離大: {caution}社",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── 注目銘柄チャートページ（上位N社）────────────────────────────────────
    def top_charts_page(self, top_results: list[dict], closes: dict, today: str):
        self.add_page()
        self._t(13, bold=True, color=NAVY)
        self.cell(0, 9, f"注目銘柄 詳細チャート  ─ RS90台 × 低乖離",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

        self._t(7.5, color=GRAY)
        self.cell(0, 5,
            "MA50乖離20%以内 かつ RS90以上の銘柄を優先表示。チャートのMA整列とベース位置を確認してください。",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

        chart_w, chart_h = 86, 48
        col = 0
        start_y = self.get_y()

        tmp_files = []
        for r in top_results:
            ticker = r["ticker"]
            close  = closes.get(ticker)
            if close is None:
                continue

            chart_path = make_mini_chart(
                close, ticker, r["name"],
                r["ma50"], r["ma150"], r["ma200"]
            )
            tmp_files.append(chart_path)

            x = 14 + col * (chart_w + 6)
            y = self.get_y()
            self.image(chart_path, x=x, y=y, w=chart_w, h=chart_h)

            # 銘柄情報オーバーレイ（チャート下）
            self.set_xy(x, y + chart_h + 0.5)
            ext = r["ext_from_ma20_pct"]
            ext_color, ext_label = self._ext_badge(ext)
            rs = r["rs_rating"] or 0

            self.set_font("YG", "B", 7)
            self.set_text_color(*NAVY)
            self.cell(chart_w * 0.55, 5, f"{ticker}  RS:{rs}")
            self.set_text_color(*ext_color)
            self.cell(chart_w * 0.45, 5, f"MA50乖離 {ext_label}",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(*DARK)

            col += 1
            if col == 2:
                col = 0
                self.ln(chart_h + 9)

        # 一時ファイル削除
        for f in tmp_files:
            Path(f).unlink(missing_ok=True)

    # ── 免責 ──────────────────────────────────────────────────────────────────
    def footer_note(self, today: str):
        self.add_page()
        self._sec("MA50乖離率（Extension Rate）について", color=TEAL)
        self._t(8)
        self.multi_cell(0, 6,
            "MASAYAオーナーご指摘の通り、ミネルヴィニ条件をクリアしても"
            "「ベースから大きく離れた銘柄」は追いかけリスクが高いです。\n\n"
            "MA50からの乖離率（Extension Rate）はその判断指標です：\n\n"
            "  ◎ +10%以内  ベース付近。理想的なエントリーゾーン。\n"
            "  ○ +10〜20%  許容範囲。上昇中だが慎重に。\n"
            "  △ +20%超    乖離大。押し目・新ベース形成を待つべき。\n\n"
            "特に大型株（時価総額が大きく流動性が高い銘柄）は機関投資家の売りが"
            "入りやすく、+30%以上乖離した状態でのエントリーは損切りリスクが高まります。\n\n"
            "推奨フロー:\n"
            "1. 全8条件クリア銘柄を確認\n"
            "2. MA50乖離◎〜○の銘柄に絞る\n"
            "3. 週足チャートでベース（保ち合い）の形を確認\n"
            "4. 出来高を伴うブレイクアウトでエントリー")
        self.ln(4)
        self._sec("免責事項")
        self._t(7.5)
        self.multi_cell(0, 5.5,
            f"本レポートはFxCompanyが情報提供を目的として作成したものです（{today}）。\n"
            "特定の有価証券の売買を推奨するものではありません。\n"
            "投資に関する最終的な判断はご自身の責任で行ってください。\n"
            "作成: FxCompany 調査部門（AI孫正義）")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    today    = datetime.today().strftime("%Y-%m-%d")
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*55}")
    print(f"  FxCompany 日次スクリーニング")
    print(f"  {run_time}")
    print(f"{'='*55}\n")

    # スクリーニング
    results, n_scanned = run_screening()

    if not results:
        print("本日の候補銘柄なし。レポート生成をスキップ。")
        return

    # チャート用にcloseデータを保持（再取得済みキャッシュから）
    closes = {}
    for r in results:
        try:
            df = dt.fetch(r["ticker"], start=DATA_START)
            closes[r["ticker"]] = df["Close"]
        except Exception:
            pass

    # 注目候補: RS90以上 × MA50乖離20%以内 → RS降順
    top = [r for r in results
           if (r["rs_rating"] or 0) >= 90 and r["ext_from_ma20_pct"] <= EXT_OK]
    top = top[:6]  # 最大6銘柄

    print(f"注目候補（RS90+ × 低乖離）: {len(top)} 銘柄")
    for r in top:
        print(f"  {r['ticker']} {r['name'][:15]}  RS:{r['rs_rating']}  "
              f"乖離:{r['ext_from_ma20_pct']:+.1f}%")

    # PDF生成
    print("\nPDF生成中...")
    pdf = DailyReportPDF()
    pdf.cover(today, n_scanned, len(results))
    pdf.summary_page(results, today)
    if top:
        pdf.top_charts_page(top, closes, today)
    pdf.footer_note(today)

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"daily_{today}_{ts}.pdf"
    pdf.output(str(out))
    print(f"\n✓ PDF保存: {out.name}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
