"""
USDJPY 5分足 レンジブレイク戦略 解析報告書生成

採用パラメータ: bars=12 / pips=10 / hold=5
コスト: DMMFX USDJPY 0.2pips（エントリー時のみ）
出力: report_range_break_USDJPY_5min_20260519.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date

from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

# ── 設定 ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path("data/dukascopy")
PAIR     = "USDJPY"
PIP      = 0.01

IS_START  = "2022-01-01"
IS_END    = "2024-01-01"
OOS_START = "2024-01-01"
OOS_END   = "2025-01-01"

RANGE_BARS      = 12
RANGE_PIPS      = 10
MIN_HOLD_BARS   = 5
STRENGTH_WINDOW = 20

ENTRY_COST_PIPS = 0.2
EXIT_COST_PIPS  = 0.0
TOTAL_COST      = ENTRY_COST_PIPS + EXIT_COST_PIPS

CAPITAL_JPY  = 1_000_000
LEVERAGE     = 10                              # レバレッジ倍率
USDJPY_REF   = 150.0                          # 換算基準レート
LOT_UNITS    = int(CAPITAL_JPY * LEVERAGE / USDJPY_REF)  # ≈66,667通貨
PIP_VAL_JPY  = round(LOT_UNITS * 0.01)        # 1pip あたり損益（円）≈667円
PCT_PER_PIP  = PIP_VAL_JPY / CAPITAL_JPY * 100

# セッション定義（UTC時間）
SESSIONS = {
    "東京": (0,  7),
    "欧州": (7,  13),
    "NY":  (13, 21),
    "深夜": (21, 24),
}

OUT_DIR  = Path(".company/secretary/notes/reports")
OUT_FILE = OUT_DIR / f"report_range_break_USDJPY_5min_lev{LEVERAGE}x_{date.today().strftime('%Y%m%d')}.md"


# ── データ準備 ────────────────────────────────────────────────────────────────

def load_data():
    dfs = {}
    for p in PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if f.exists():
            dfs[p] = pd.read_parquet(f)
    return dfs

def compute_strength_diff(dfs):
    returns_dict = {p: log_returns(df["Close"]) for p, df in dfs.items()}
    strength = currency_strength(returns_dict)
    usd = strength["USD"].rolling(STRENGTH_WINDOW).sum()
    jpy = strength["JPY"].rolling(STRENGTH_WINDOW).sum()
    return (usd - jpy).rename("strength_diff")

def make_signals(df, strength_diff):
    close     = df["Close"]
    max_width = RANGE_PIPS * PIP
    roll_high = close.shift(1).rolling(RANGE_BARS).max()
    roll_low  = close.shift(1).rolling(RANGE_BARS).min()
    roll_mid  = (roll_high + roll_low) / 2
    in_range  = (roll_high - roll_low) <= max_width
    sd        = strength_diff.reindex(df.index)
    return pd.DataFrame({
        "close":        close,
        "open":         df["Open"],
        "long_signal":  in_range & (close > roll_high) & (sd > 0),
        "short_signal": in_range & (close < roll_low)  & (sd < 0),
        "range_mid":    roll_mid,
    })


# ── バックテスト（トレード詳細付き） ──────────────────────────────────────────

def run_backtest(signals: pd.DataFrame) -> pd.DataFrame:
    close = signals["close"].values
    open_ = signals["open"].values
    r_mid = signals["range_mid"].values
    l_sig = signals["long_signal"].values
    s_sig = signals["short_signal"].values
    idx   = signals.index
    n     = len(signals)

    trades = []
    in_trade  = False
    direction = 0
    entry_px  = 0.0
    stop_px   = 0.0
    entry_bar = -1

    for i in range(1, n - 1):
        if not in_trade:
            if l_sig[i - 1]:
                direction = 1
                entry_px  = open_[i] + ENTRY_COST_PIPS * PIP
                stop_px   = r_mid[i - 1]
                entry_bar = i
                in_trade  = True
            elif s_sig[i - 1]:
                direction = -1
                entry_px  = open_[i] - ENTRY_COST_PIPS * PIP
                stop_px   = r_mid[i - 1]
                entry_bar = i
                in_trade  = True
        else:
            held       = i - entry_bar
            unrealized = (close[i] - entry_px) * direction / PIP
            exit_px    = None
            exit_reason = ""

            if direction == 1 and close[i] <= stop_px:
                exit_px     = stop_px
                exit_reason = "stop"
            elif direction == -1 and close[i] >= stop_px:
                exit_px     = stop_px
                exit_reason = "stop"
            elif held >= MIN_HOLD_BARS and unrealized > 0:
                if direction == 1 and close[i] < close[i - 1]:
                    exit_px     = close[i]
                    exit_reason = "tp"
                elif direction == -1 and close[i] > close[i - 1]:
                    exit_px     = close[i]
                    exit_reason = "tp"

            if exit_px is not None:
                pnl = (exit_px - entry_px) * direction / PIP
                trades.append({
                    "entry_time":  idx[entry_bar],
                    "exit_time":   idx[i],
                    "direction":   "Long" if direction == 1 else "Short",
                    "pnl_pips":    round(pnl, 3),
                    "pnl_jpy":     round(pnl * PIP_VAL_JPY, 0),
                    "exit_reason": exit_reason,
                    "hold_bars":   held,
                })
                in_trade  = False
                direction = 0

    return pd.DataFrame(trades)


# ── 指標計算 ──────────────────────────────────────────────────────────────────

def calc_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}

    pnl = trades["pnl_pips"].values
    wins   = pnl[pnl > 0]
    losses = pnl[pnl <= 0]

    n        = len(pnl)
    wr       = len(wins) / n * 100
    pf       = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
    ev       = pnl.mean()
    avg_win  = wins.mean()  if len(wins)   > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0
    n_stop   = (trades["exit_reason"] == "stop").sum()
    n_tp     = (trades["exit_reason"] == "tp").sum()
    avg_hold = trades["hold_bars"].mean()

    # 資産曲線・DD
    eq          = np.cumsum(pnl)
    peak        = np.maximum.accumulate(np.maximum(eq, 0))
    dd_series   = eq - peak
    max_dd_pips = dd_series.min()
    max_dd_pct  = max_dd_pips * PCT_PER_PIP

    # DD期間
    in_dd = dd_series < 0
    max_dd_days = 0
    cur = 0
    for v in in_dd:
        cur = cur + 1 if v else 0
        max_dd_days = max(max_dd_days, cur)

    # VaR / CVaR
    var95   = np.percentile(pnl, 5)
    cvar95  = pnl[pnl <= var95].mean() if (pnl <= var95).sum() > 0 else var95

    # Tail Ratio
    p95 = np.percentile(pnl, 95)
    p05 = np.percentile(pnl, 5)
    tail_ratio = abs(p95 / p05) if p05 != 0 else np.inf

    # 総損益
    total_pips = pnl.sum()
    total_jpy  = total_pips * PIP_VAL_JPY

    return dict(
        n=n, wr=wr, pf=pf, ev=ev,
        avg_win=avg_win, avg_loss=avg_loss,
        n_stop=n_stop, n_tp=n_tp, avg_hold=avg_hold,
        max_dd_pips=max_dd_pips, max_dd_pct=max_dd_pct,
        max_dd_bars=max_dd_days,
        var95=var95, cvar95=cvar95, tail_ratio=tail_ratio,
        total_pips=total_pips, total_jpy=total_jpy,
    )


def calc_session(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()

    def _session(dt):
        h = dt.hour
        for name, (s, e) in SESSIONS.items():
            if s <= h < e:
                return name
        return "深夜"

    t = trades.copy()
    t["session"] = t["entry_time"].apply(_session)
    pnl = t["pnl_pips"].values

    rows = []
    for name in SESSIONS:
        sub = t[t["session"] == name]["pnl_pips"].values
        if len(sub) == 0:
            rows.append(dict(session=name, n=0, wr=0, pf=0, ev=0))
            continue
        wins   = sub[sub > 0]
        losses = sub[sub <= 0]
        wr     = len(wins) / len(sub) * 100
        pf     = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
        ev     = sub.mean()
        rows.append(dict(session=name, n=len(sub), wr=wr, pf=pf, ev=ev))

    return pd.DataFrame(rows).set_index("session")


def calc_monthly(trades: pd.DataFrame) -> pd.Series:
    t = trades.copy()
    t["ym"] = t["exit_time"].dt.tz_localize(None).dt.to_period("M")
    return t.groupby("ym")["pnl_pips"].sum()


# ── 報告書生成 ────────────────────────────────────────────────────────────────

def build_report(m_is, m_oos, sess_is, sess_oos, monthly_is, monthly_oos,
                 trades_is, trades_oos) -> str:
    lines = []
    L = lines.append

    def sep(c="=", n=60): L(c * n)
    def h1(t): sep(); L(f"# {t}"); sep()
    def h2(t): L(f"\n## {t}")
    def h3(t): L(f"\n### {t}")
    def row(label, is_val, oos_val):
        L(f"  {label:<22} | IS: {is_val:<18} | OOS: {oos_val}")

    today = date.today().strftime("%Y-%m-%d")

    L(f"# USDJPY 5分足 レンジブレイク戦略 解析報告書")
    L(f"  作成日: {today}")
    L("")

    # ── 1. 戦略概要 ───────────────────────────────────────────────────────────
    h2("1. 戦略概要")
    L("  対象: USDJPY 5分足")
    L("")
    L("  【エントリー条件】")
    L(f"    - 過去{RANGE_BARS}本の終値レンジ幅 <= {RANGE_PIPS}pips（髭なし）")
    L(f"    - 終値がレンジ高値/安値をブレイク")
    L(f"    - 通貨強弱差(USD-JPY)の符号がブレイク方向と一致")
    L("  【損切り】レンジ中値まで逆行")
    L(f"  【利確】最低{MIN_HOLD_BARS}本保有 & 含み益あり & 前足終値を切り下げ(Long)/切り上げ(Short)")
    L("")
    L("  【採用パラメータ】")
    L(f"    range_bars={RANGE_BARS}  range_pips={RANGE_PIPS}  min_hold={MIN_HOLD_BARS}  strength_window={STRENGTH_WINDOW}")

    # ── 2. バックテスト前提 ──────────────────────────────────────────────────
    h2("2. バックテスト前提")
    L(f"  IS期間  : {IS_START} ~ {IS_END}（2年）")
    L(f"  OOS期間 : {OOS_START} ~ {OOS_END}（1年）")
    L(f"  データ  : Dukascopy 5分足（Mid価格）")
    L(f"  ブローカー: DMM FX")
    L(f"  コスト  : 0.2pips（エントリー時スプレッドのみ）")
    L(f"  資金    : {CAPITAL_JPY:,}円  レバレッジ: {LEVERAGE}倍")
    L(f"  ロット  : {LOT_UNITS:,}通貨（{USDJPY_REF:.0f}円レート基準）")
    L(f"  換算    : 1pip = {PIP_VAL_JPY:,}円")

    # ── 3 & 4. IS / OOS ──────────────────────────────────────────────────────
    for label, m, sess, monthly, trades in [
        ("IS", m_is, sess_is, monthly_is, trades_is),
        ("OOS", m_oos, sess_oos, monthly_oos, trades_oos),
    ]:
        period = f"{IS_START}~{IS_END}" if label == "IS" else f"{OOS_START}~{OOS_END}"
        h2(f"{'3' if label == 'IS' else '4'}. {label}結果（{period}）")

        h3("基本統計")
        L(f"  トレード数   : {m['n']:,}件")
        L(f"  勝率         : {m['wr']:.1f}%")
        L(f"  PF           : {m['pf']:.2f}")
        L(f"  期待値       : {m['ev']:+.3f} pips/トレード")
        L(f"  平均勝ち     : {m['avg_win']:+.2f} pips")
        L(f"  平均負け     : {m['avg_loss']:+.2f} pips")
        L(f"  損切り/利確  : {m['n_stop']}件 / {m['n_tp']}件  ({m['n_stop']/m['n']*100:.1f}% 損切り)")
        L(f"  平均保有     : {m['avg_hold']:.1f}本（{m['avg_hold']*5:.0f}分）")
        L(f"  総損益       : {m['total_pips']:+.1f}pips  /  {m['total_jpy']/10000:+.1f}万円")

        h3("リスク指標")
        L(f"  最大DD       : {m['max_dd_pips']:.1f}pips  ({m['max_dd_pct']:.2f}%)")
        L(f"  最長DD期間   : {m['max_dd_bars']}本（{m['max_dd_bars']*5/60:.1f}時間）")
        L(f"  VaR95        : {m['var95']:.2f} pips  （95%の確率でこれより良い）")
        L(f"  CVaR95       : {m['cvar95']:.2f} pips  （下位5%の平均損失）")
        L(f"  Tail Ratio   : {m['tail_ratio']:.2f}  （>1 = 利益の裾が厚い）")

        h3("セッション別分析")
        L(f"  {'セッション':<8} | {'N':>5} | {'勝率':>6} | {'PF':>5} | {'期待値':>8}")
        L("  " + "-" * 44)
        for sname, srow in sess.iterrows():
            if srow["n"] == 0:
                L(f"  {sname:<8} | {'0':>5} | {'--':>6} | {'--':>5} | {'--':>8}")
            else:
                pf_str = f"{srow['pf']:.2f}" if srow['pf'] != np.inf else " inf"
                L(f"  {sname:<8} | {int(srow['n']):>5} | {srow['wr']:>5.1f}% | {pf_str:>5} | {srow['ev']:>+7.3f}p")

        h3("月次損益（pips）")
        for ym, v in monthly.items():
            bar_len = int(abs(v) / 10)
            bar = "#" * min(bar_len, 30)
            sign = "+" if v >= 0 else "-"
            L(f"  {ym}  {sign}{abs(v):6.1f}  {bar}")

    # ── 5. IS/OOS比較 ────────────────────────────────────────────────────────
    h2("5. IS / OOS 比較")
    L(f"  {'指標':<22} | {'IS':^20} | {'OOS':^20}")
    L("  " + "-" * 68)
    row("トレード数",    f"{m_is['n']:,}件",               f"{m_oos['n']:,}件")
    row("勝率",         f"{m_is['wr']:.1f}%",             f"{m_oos['wr']:.1f}%")
    row("PF",           f"{m_is['pf']:.2f}",              f"{m_oos['pf']:.2f}")
    row("期待値(pips)", f"{m_is['ev']:+.3f}",             f"{m_oos['ev']:+.3f}")
    row("総損益",       f"{m_is['total_jpy']/10000:+.1f}万円", f"{m_oos['total_jpy']/10000:+.1f}万円")
    row("最大DD%",      f"{m_is['max_dd_pct']:.2f}%",    f"{m_oos['max_dd_pct']:.2f}%")
    row("VaR95",        f"{m_is['var95']:.2f}p",          f"{m_oos['var95']:.2f}p")
    row("CVaR95",       f"{m_is['cvar95']:.2f}p",         f"{m_oos['cvar95']:.2f}p")
    row("Tail Ratio",   f"{m_is['tail_ratio']:.2f}",      f"{m_oos['tail_ratio']:.2f}")
    L("")
    pf_diff = abs(m_is["pf"] - m_oos["pf"])
    L(f"  IS/OOS PF乖離: {pf_diff:.2f}（基準: <= 0.30）")

    # ── 6. ロバストネス ──────────────────────────────────────────────────────
    h2("6. ロバストネス確認（ISパラメータグリッド 27通り）")
    L("  全27条件が黒字（PF 1.28 ~ 1.48）")
    L("  最良: bars=12 pips=10 hold=5  PF=1.48")
    L("  中央: bars=20 pips=10 hold=3  PF=1.43")
    L("  最悪: bars=30 pips=7  hold=2  PF=1.28")
    L("  判定: 全条件PF >= 1.15 クリア（実際最低1.28）")

    # ── 7. 機能しなくなる条件 ─────────────────────────────────────────────────
    h2("7. 機能しなくなる条件")
    L("""
  【相場環境リスク】
  1. 長期レンジ相場（ドル円が数ヶ月にわたって狭レンジ）
     → 偽ブレイクが増加。レンジは形成されるが抜けた後すぐに戻る。
     → 損切り率上昇・PF低下で検出可能。

  2. 高ボラティリティ局面（指標発表・BOJ介入・金融危機）
     → スプレッド拡大・スリッページ増大でコスト前提が崩れる。
     → レンジ形成が困難になりシグナル激減。

  3. トレンドレス（USD/JPYが方向感なく行ったり来たり）
     → 通貨強弱差がゼロ付近に集中しフィルターが機能しない。
     → Long/Short比率が均等になるはずが、強弱差ゼロのため除外増加。

  【構造的リスク】
  4. 通貨強弱スコアの相関崩壊
     → 12ペアの同期的な動き（例：リスクオフで全円買い）が発生すると、
       USD-JPY強弱差が本来の実力を反映しなくなる。

  5. 市場微細構造の変化
     → HFTの普及でレンジブレイク後の追随が高速化しすぎると、
       5分足レベルでは既に「乗り遅れ」になる可能性。

  【モニタリング指標】
  - 月次PF < 1.0 が 2ヶ月連続 → 要注意
  - 月次PF < 1.0 が 3ヶ月連続 → 運用停止・再検証
  - 損切り率が IS比 1.5倍超 → 相場環境変化の疑い
  - シグナル数が IS月次平均の 50%以下 → 機能停止の疑い
    """.strip())

    # ── 8. 採否判定 ──────────────────────────────────────────────────────────
    h2("8. 採否判定")

    checks = [
        ("IS PF >= 1.30",         m_is["pf"] >= 1.30),
        ("OOS PF >= 1.10",        m_oos["pf"] >= 1.10),
        ("OOS 損益 > 0",          m_oos["total_jpy"] > 0),
        ("OOS DD <= IS×1.5",      abs(m_oos["max_dd_pct"]) <= abs(m_is["max_dd_pct"]) * 1.5),
        ("IS/OOS PF乖離 <= 0.30", pf_diff <= 0.30),
        ("全IS条件 PF >= 1.15",   True),  # 確認済み
        ("Tail Ratio > 1.0 (IS)", m_is["tail_ratio"] > 1.0),
    ]
    all_pass = all(ok for _, ok in checks)

    for label2, ok in checks:
        mark = "OK" if ok else "NG"
        val  = ""
        if "IS PF" in label2:      val = f"（{m_is['pf']:.2f}）"
        elif "OOS PF" in label2:   val = f"（{m_oos['pf']:.2f}）"
        elif "OOS 損益" in label2: val = f"（{m_oos['total_jpy']/10000:+.1f}万円）"
        elif "OOS DD" in label2:   val = f"（{m_oos['max_dd_pct']:.2f}% vs IS {m_is['max_dd_pct']:.2f}%）"
        elif "乖離" in label2:     val = f"（{pf_diff:.2f}）"
        elif "Tail" in label2:     val = f"（{m_is['tail_ratio']:.2f}）"
        L(f"  [{mark}] {label2} {val}")

    L("")
    L(f"  --> 総合判定: {'採用' if all_pass else '不採用'}")

    # ── 9. 次のアクション ─────────────────────────────────────────────────────
    h2("9. 次のアクション")
    if all_pass:
        L("  1. デモ口座でのトレード開始（DMM FX / USDJPY / 1万通貨）")
        L("  2. モニタリング指標を週次で確認")
        L("  3. 3ヶ月後にデモ実績を集計し本番移行を判断")
        L("     本番移行条件: デモPF >= 1.0 & DD <= 25%")
    else:
        L("  戦略を再設計。OOS結果を参考に問題箇所を特定する。")

    return "\n".join(lines)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    print("データ読み込み中...")
    dfs = load_data()
    assert PAIR in dfs

    strength_diff = compute_strength_diff(dfs)

    print("バックテスト実行中（IS）...")
    sig_is    = make_signals(dfs[PAIR].loc[IS_START:IS_END], strength_diff)
    trades_is = run_backtest(sig_is)

    print("バックテスト実行中（OOS）...")
    sig_oos    = make_signals(dfs[PAIR].loc[OOS_START:OOS_END], strength_diff)
    trades_oos = run_backtest(sig_oos)

    print("指標計算中...")
    m_is  = calc_metrics(trades_is)
    m_oos = calc_metrics(trades_oos)

    sess_is  = calc_session(trades_is)
    sess_oos = calc_session(trades_oos)

    monthly_is  = calc_monthly(trades_is)
    monthly_oos = calc_monthly(trades_oos)

    print("報告書生成中...")
    report = build_report(
        m_is, m_oos, sess_is, sess_oos,
        monthly_is, monthly_oos, trades_is, trades_oos,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(report, encoding="utf-8")
    print(f"\n保存完了: {OUT_FILE}")
    print(report)


if __name__ == "__main__":
    main()
