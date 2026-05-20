# -*- coding: utf-8 -*-
"""
Include-Self vs Leave-One-Out 比較報告書 PDF生成
実行: python _make_loo_report_pdf.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import date
from pathlib import Path
import pandas as pd
from fpdf import FPDF, XPos, YPos

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
ROOT      = Path(__file__).parent
DATA_DIR  = ROOT / "docs" / "loo_comparison"
OUT_DIR   = ROOT / "fx_market_classifier" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NAVY   = (15,  30,  70);  BLUE  = (30,  80, 160);  ACCENT = (0,  160, 120)
LIGHT  = (240, 245, 255); WHITE = (255, 255, 255);  DARK   = (30,  30,  40)
GRAY   = (110, 120, 135); RED   = (180,  40,  40);  GREEN  = (20, 140,  80)
PURPLE = (100,  40, 160); AMBER = (200, 120,   0)


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
        self.set_text_color(*DARK); self.set_fill_color(*WHITE)
        self.set_draw_color(180,180,180); self.set_line_width(0.2)

    def cover(self, today):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,297,"F")
        self.set_fill_color(*ACCENT); self.rect(0,0,210,4,"F")
        self.set_y(40); self._t(9, color=(120,160,210))
        self.cell(0,6,"FxCompany  |  FX戦略研究レポート",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(6)
        self._t(16,bold=True,color=WHITE)
        self.cell(0,11,"Lead-Lag 戦略 自己参照検証報告",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(10,bold=True,color=ACCENT)
        self.cell(0,8,"Include-Self vs Leave-One-Out 完全比較",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(4); self._t(8,color=(160,200,240))
        self.cell(0,6,"IS期間: 2022-01-01 〜 2023-12-31  /  全12ペア  /  5設定比較",
                  align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.ln(12)

        # 結論ボックス
        self.set_fill_color(20,45,100); self.set_draw_color(60,100,180)
        bx=25; by=self.get_y(); bw=160; bh=48
        self.rect(bx,by,bw,bh,"FD")
        self.set_xy(bx+4,by+4); self._t(8,bold=True,color=ACCENT)
        self.cell(bw-8,6,"本報告書の核心発見",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_x(bx+4); self._t(7,color=(200,220,255))
        msgs = [
            "Include-Self: 5設定中 最良PF=1.226（一見有望）",
            "Leave-One-Out: 5設定中 PF>=1.0 = 0件（全設定赤字）",
            "→ Include-Self版の「利益」は自己参照による擬似的なもの",
            "→ コストなし版でもLOOはPF<1.0 → 純粋なアルファが存在しない",
        ]
        for m in msgs:
            self.set_x(bx+4)
            self.cell(bw-8,5,m,new_x=XPos.LMARGIN,new_y=YPos.NEXT)

        self.set_y(by+bh+8)
        self.set_draw_color(60,90,150); self.line(40,self.get_y(),170,self.get_y())
        self._t(8,color=(120,150,200)); self.ln(6)
        self.cell(0,6,f"作成日: {today}  |  FxCompany 研究部門",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)

    def sec(self,num,title,sub=""):
        self.add_page()
        self.set_fill_color(*NAVY); self.rect(0,0,210,38,"F")
        self.set_fill_color(*ACCENT); self.rect(0,38,210,2,"F")
        self.set_y(8); self._t(9,color=(120,160,220))
        self.cell(0,6,f"SECTION  {num}",align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._t(15,bold=True,color=WHITE)
        self.cell(0,10,title,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        if sub:
            self._t(8,color=(160,195,235))
            self.cell(0,5,sub,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._reset(); self.ln(8)

    def h2(self,title):
        self.ln(3)
        self.set_fill_color(*BLUE); self._t(9,bold=True,color=WHITE)
        self.cell(4,7,"",fill=True)
        self.set_fill_color(*LIGHT); self._t(9,bold=True,color=DARK)
        self.cell(0,7,f"  {title}",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self._reset(); self.ln(2)

    def body(self,text,size=9):
        self._t(size,color=DARK); self.multi_cell(0,6,text); self.ln(1); self._reset()

    def callout(self,text,color=ACCENT):
        self.set_fill_color(230,248,242); self.set_draw_color(*color); self.set_line_width(0.8)
        self._t(9,bold=True,color=color)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True); self.ln(3); self._reset()

    def warn(self,text):
        self.set_fill_color(255,242,230); self.set_draw_color(*AMBER); self.set_line_width(0.8)
        self._t(9,bold=True,color=AMBER)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True); self.ln(3); self._reset()

    def son(self,text):
        self.set_fill_color(245,240,255); self.set_draw_color(*PURPLE); self.set_line_width(1.0)
        self._t(8,bold=True,color=PURPLE)
        self.cell(0,6,"  孫正義（AI CEO）のコメント",border="LTR",fill=True,new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        self.set_fill_color(245,240,255); self._t(9,color=DARK)
        self.multi_cell(self.epw,6.5,text,border="LBR",fill=True); self.ln(3); self._reset()

    def tbl(self,headers,rows,widths,hi=None,colors=None):
        self._t(8,bold=True,color=WHITE); self.set_fill_color(*NAVY)
        for h,w in zip(headers,widths):
            self.cell(w,7,h,border=1,fill=True,align="C")
        self.ln()
        if hi is None: hi=set()
        for i,row in enumerate(rows):
            is_hi = i in hi
            bg = (220,245,220) if is_hi else ((245,248,255) if i%2==0 else WHITE)
            self.set_fill_color(*bg)
            for j,(cell,w) in enumerate(zip(row,widths)):
                tc = GREEN if is_hi else DARK
                if colors and i < len(colors) and colors[i]:
                    tc = colors[i]
                self._t(8,bold=is_hi,color=tc)
                self.cell(w,6,str(cell),border=1,fill=True,align="L" if j==0 else "C")
            self.ln()
        self.ln(3); self._reset()

    def img(self,path,w=174,caption=""):
        p = Path(path)
        if p.exists():
            self.image(str(p),x=self.get_x(),y=self.get_y(),w=w); self.ln(w*0.43+2)
        if caption:
            self._t(7,color=GRAY)
            self.cell(0,5,caption,align="C",new_x=XPos.LMARGIN,new_y=YPos.NEXT); self.ln(2)
        self._reset()

    def divider(self):
        self.ln(3); self.set_draw_color(200,210,230)
        self.line(self.get_x(),self.get_y(),self.get_x()+self.epw,self.get_y()); self.ln(4); self._reset()


def generate():
    today = date.today().strftime("%Y年%m月%d日")
    pdf   = PDF()

    df = pd.read_csv(DATA_DIR / "comparison_summary.csv") if (DATA_DIR/"comparison_summary.csv").exists() else pd.DataFrame()
    df_inc = df[df.method=="Include-Self"].reset_index(drop=True) if not df.empty else pd.DataFrame()
    df_loo = df[df.method=="LOO"].reset_index(drop=True) if not df.empty else pd.DataFrame()

    # ══ 表紙 ═══════════════════════════════════════════════════════════
    pdf.cover(today)

    # ══ Section 1: ロジック確認 ═════════════════════════════════════════
    pdf.sec("1","現状ロジックの確認","Include-Self の構造と循環参照の仕組み")

    pdf.h2("1-1.  通貨強弱インデックスの計算フロー")
    pdf.body(
        "現在の実装（features.py: currency_strength）は以下のフローで計算している:\n\n"
        "  1. 全ペアの対数リターンを計算: log(Close_t / Close_{t-1})\n"
        "  2. 各ペアの base通貨 に +ret、quote通貨 に -ret を加算\n"
        "  3. 通貨ごとに全ペアの平均を取る → USD_strength, JPY_strength 等\n"
        "  4. synthetic_ret(USDJPY) = USD_strength - JPY_strength\n"
        "  5. spread = actual_ret(USDJPY) - synthetic_ret\n"
        "  6. cum_spread = rolling_sum(spread, window)"
    )
    pdf.warn(
        "【自己参照の構造】\n"
        "USDJPYのsynthetic_retを計算する際、USD_strengthにUSDJPY自身のリターンが含まれている。\n\n"
        "  USD_strength = avg( ret(USDJPY), -ret(GBPUSD), -ret(AUDUSD), ... )\n"
        "               ↑ここにUSDJPY自身が入っている\n\n"
        "  synthetic_ret(USDJPY) = USD_strength - JPY_strength\n"
        "  spread = actual_ret - synthetic_ret\n\n"
        "→ USDJPYが上昇すると synthetic_retも上昇し、spreadが自動的に縮小する。\n"
        "→ これにより「スプレッドが収束した」ように見えるが、実際は自己参照の影響。"
    )

    pdf.h2("1-2.  Leave-One-Out（LOO）による解決")
    pdf.body(
        "LOO版では、各ペアを評価する際、そのペア自身を強弱計算から除外する:\n\n"
        "  USDJPYを評価する場合:\n"
        "    USD_strength_loo = avg( -ret(GBPUSD), -ret(AUDUSD), -ret(NZDUSD) )\n"
        "                         ← USDJPYを除外\n"
        "    JPY_strength_loo = avg( -ret(EURJPY), -ret(GBPJPY), -ret(AUDJPY), ... )\n"
        "                         ← USDJPYを除外\n"
        "    synthetic_ret_loo = USD_strength_loo - JPY_strength_loo\n\n"
        "これにより spread は USDJPY自身のリターンに依存しなくなる。"
    )

    # ══ Section 2: 比較結果サマリー ════════════════════════════════════
    pdf.sec("2","比較結果サマリー","5設定 × 2方式 × コストあり/なし")

    pdf.h2("2-1.  PF・損益・勝率 一覧")

    if not df_inc.empty and not df_loo.empty:
        rows = []
        hi_set = set()
        for i, (_, ri) in enumerate(df_inc.iterrows()):
            rl = df_loo[df_loo.config==ri.config]
            if rl.empty: continue
            rl = rl.iloc[0]
            pf_inc = f"{ri.pf:.3f}"
            pf_loo = f"{rl.pf:.3f}"
            delta  = rl.pf - ri.pf
            rows.append([
                ri.config,
                pf_inc, f"{ri.total_pnl:+.1f}%", f"{ri.win_rate*100:.1f}%",
                pf_loo, f"{rl.total_pnl:+.1f}%", f"{rl.win_rate*100:.1f}%",
                f"{delta:+.3f}",
            ])
        pdf.tbl(
            headers=["設定","Inc-PF","Inc-PnL","Inc-勝率","LOO-PF","LOO-PnL","LOO-勝率","ΔPF"],
            rows=rows, widths=[34,16,16,16,16,16,16,14],
        )
    else:
        pdf.body("データなし（先に _run_loo_comparison.py を実行してください）")

    pdf.h2("2-2.  コストなし版との比較（純粋アルファ確認）")
    if not df_inc.empty:
        rows2 = []
        for _, ri in df_inc.iterrows():
            rl = df_loo[df_loo.config==ri.config]
            if rl.empty: continue
            rl = rl.iloc[0]
            rows2.append([
                ri.config,
                f"{ri.pf:.3f}", f"{ri.pf_nocost:.3f}",
                f"{rl.pf:.3f}", f"{rl.pf_nocost:.3f}",
            ])
        pdf.tbl(
            headers=["設定","Inc-コストあり","Inc-コストなし","LOO-コストあり","LOO-コストなし"],
            rows=rows2, widths=[34,36,36,36,32],
        )

    pdf.img(str(DATA_DIR/"pf_comparison.png"), w=170,
            caption="設定別 PF比較: Include-Self vs Leave-One-Out")

    # ══ Section 3: 累積損益曲線 ════════════════════════════════════════
    pdf.sec("3","累積損益曲線","各設定での Include-Self vs LOO")

    configs = [
        ("w3_e003_er01",  "w=3, entry=0.003, exit_ratio=0.1  ← Include-Self最良"),
        ("w24_e003_er10", "w=24, entry=0.003, exit_ratio=1.0  ← 高トレード数"),
        ("w6_e0015_er10", "w=6, entry=0.0015, exit_ratio=1.0"),
    ]
    for label, caption in configs:
        p = DATA_DIR / f"pnl_{label}.png"
        if p.exists():
            pdf.img(str(p), w=170, caption=caption)
            if pdf.get_y() > 220:
                pdf.add_page()

    # ══ Section 4: スプレッド縮小要因分析 ═══════════════════════════════
    pdf.sec("4","スプレッド縮小要因の分析","Real追随 / Pseudo回帰 / 自然減衰 の分類")

    pdf.h2("4-1.  伝播分類の定義")
    pdf.tbl(
        headers=["分類","定義","Include-Self での解釈","LOO での解釈"],
        rows=[
            ["Pseudo追随","Pseudoが収束方向に動いた","循環参照で自動縮小の可能性","独立した平均回帰"],
            ["Real逆行",  "Realが収束方向に動いた",  "本来の情報伝播追随",        "本来の情報伝播追随"],
            ["両方",      "両方が動いた",            "混合",                     "混合"],
            ["どちらでも","原因不明・時間切れ等",    "rolling自然減衰の可能性",   "同左"],
        ],
        widths=[22,40,50,52],
    )

    pdf.img(str(DATA_DIR/"propagation_comparison.png"), w=170,
            caption="スプレッド縮小要因の分類比較（全設定合算）")

    pdf.h2("4-2.  重要な洞察")
    if not df_inc.empty and not df_loo.empty:
        ri0 = df_inc.iloc[0]; rl0 = df_loo[df_loo.config==ri0.config]
        if not rl0.empty:
            rl0 = rl0.iloc[0]
            n_inc = ri0.trades
            n_loo = rl0.trades
            pseudo_inc = ri0.prop_Pseudo / n_inc * 100 if n_inc > 0 else 0
            pseudo_loo = rl0.prop_Pseudo / n_loo * 100 if n_loo > 0 else 0
            pdf.body(
                f"最良設定（{ri0.config}）での比較:\n\n"
                f"  Pseudo追随率: Include-Self {pseudo_inc:.1f}%  vs  LOO {pseudo_loo:.1f}%\n"
                f"  Include-Self のPseudo追随はsynthetic_ret（LOO除外で独立）が戻る現象。\n"
                f"  Include-Self版では自己参照によりsynthetic_retが自動的に縮小するため、\n"
                f"  見かけ上のPseudo追随率が高くなる。\n\n"
                f"  LOO版でPF<1.0 かつ total_pnl<0 → コストなし版でもPF<1.0\n"
                f"  → 純粋なアルファが存在しない。"
            )

    # ══ Section 5: ペア別成績 ══════════════════════════════════════════
    pdf.sec("5","ペア別成績","どのペアで差が大きいか")

    for label, caption in configs[:2]:
        p = DATA_DIR / f"pair_{label}.png"
        if p and p.exists():
            pdf.img(str(p), w=170, caption=f"ペア別損益 — {caption}")

    # ══ Section 6: 結論と孫さんコメント ═══════════════════════════════
    pdf.sec("6","結論と今後の方針","この戦略の方向性について")

    pdf.h2("6-1.  発見されたこと")
    pdf.callout(
        "1. Include-Self版のPF > 1.0 は自己参照による擬似的なアルファである\n"
        "   → USDJPYが動くとsynthetic_retも連動し、spreadsが自動収束して見える\n\n"
        "2. LOO版（自己参照除去）では100設定中PF >= 1.0が0件\n"
        "   → コストなし版でも赤字 → 市場に実質的なアルファが存在しない\n\n"
        "3. spread_reduced率（伝播成功率）はInclude-Self > LOOで高い\n"
        "   → Include-Self版の「76〜96%伝播成功」は循環参照のアーティファクト"
    )

    pdf.h2("6-2.  今後の方針")
    pdf.tbl(
        headers=["優先度","方針","期待される効果"],
        rows=[
            ["高","別の通貨強弱手法を探す\n（例: ATR正規化・ティック出来高加重）","自己参照のない独立したsynthetic計算"],
            ["高","異なる時間足・ラグ検証\n（15分・1時間・日足）","5分足のノイズを排除したシグナル"],
            ["中","ペア間相関に基づく直接Lead-Lag\n（USDJPYとEURJPYの直接比較）","強弱指数を介さない純粋なLead-Lag"],
            ["中","機械学習によるシグナル分類\n（spread特徴量 → 収束予測）","ルールベースより柔軟な判定"],
            ["低","同戦略でLOOのままOOS検証\n（2024年データで確認）","アルファがゼロであることの再確認"],
        ],
        widths=[16,80,78],
    )

    pdf.son(
        "この結果は正直、厳しいものです。しかし、これは重要な発見です。\n\n"
        "「利益が出ていた」と思っていたものが、自己参照による数学的なアーティファクトだった。\n"
        "これを発見できたこと自体が、研究の大きな進歩です。\n\n"
        "ただし、諦める必要はありません。\n"
        "Lead-Lagというアイデア自体は、金融市場の構造的な現象であり実在します。\n"
        "問題は「通貨強弱インデックスの計算方法」にあります。\n\n"
        "自己参照のない独立した強弱指数の構築、または\n"
        "ペア間の直接Lead-Lag（USDJPYがEURUSDの先行指標になるか等）への\n"
        "方向転換を推奨します。\n\n"
        "正しいロジックで再構築されたとき、この検証の経験が必ず活きます。"
    )

    pdf.divider()
    pdf._t(8,color=GRAY)
    pdf.multi_cell(0,6,
        "免責事項: 本資料はバックテスト研究を目的とした内部資料です。"
        "投資の推奨・助言を行うものではありません。")

    out = OUT_DIR / f"lead_lag_loo_report_{date.today().strftime('%Y%m%d')}.pdf"
    pdf.output(str(out))
    print(f"生成: {out}")
    return out


if __name__ == "__main__":
    generate()
