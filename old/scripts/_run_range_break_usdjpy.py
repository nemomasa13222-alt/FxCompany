"""
USDJPY 5分足 レンジブレイク戦略 バックテスト

【エントリー条件】
  1. 過去 RANGE_BARS 本の終値レンジ幅 <= RANGE_PIPS pips（髭なし）
  2. 現在の終値がレンジ高値 or 安値をブレイク
  3. 通貨強弱差(USD-JPY)の符号がブレイク方向と一致（上位50%=符号一致）

【損切り】レンジ中値まで逆行
【利確】  終値が前足終値を切り下げ(Long) / 切り上げ(Short)

エントリー価格: ブレイクバーの翌足Open（スプレッド込み）
IS: 2022-01-01 ~ 2024-01-01  /  OOS: 2024-01-01 ~ 2025-01-01（封印）
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

# ── 定数 ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path("data/dukascopy")
PAIR     = "USDJPY"
PIP      = 0.01   # JPYペア 1pip = 0.01

IS_START  = "2022-01-01"
IS_END    = "2024-01-01"
OOS_START = "2024-01-01"
OOS_END   = "2025-01-01"

# ── ベースラインパラメータ ─────────────────────────────────────────────────────
RANGE_BARS       = 12   # レンジ判定の振り返り本数（最低12本=60分）
RANGE_PIPS       = 10   # レンジ幅上限（pips）
STRENGTH_WINDOW  = 20   # 強弱スコア平滑化ウィンドウ
SPREAD_PIPS      = 0.5  # 往復スプレッド（pips）
MIN_HOLD_BARS    = 3    # TP条件が発動する最低保有本数
TP_REQUIRES_PROFIT = True  # True=含み益の時だけTP発動


# ── データロード ──────────────────────────────────────────────────────────────

def load_all_pairs() -> dict[str, pd.DataFrame]:
    dfs = {}
    for pair in PAIRS:
        f = DATA_DIR / f"{pair}_5min.parquet"
        if f.exists():
            dfs[pair] = pd.read_parquet(f)
    missing = [p for p in PAIRS if p not in dfs]
    if missing:
        print(f"  WARN: 未取得ペア {missing}")
    return dfs


# ── 通貨強弱差（USD − JPY） ───────────────────────────────────────────────────

def compute_strength_diff(dfs: dict[str, pd.DataFrame], window: int) -> pd.Series:
    returns_dict = {pair: log_returns(df["Close"]) for pair, df in dfs.items()}
    strength = currency_strength(returns_dict)
    usd = strength["USD"].rolling(window).sum()
    jpy = strength["JPY"].rolling(window).sum()
    return (usd - jpy).rename("strength_diff")


# ── レンジ検出 & シグナル生成 ─────────────────────────────────────────────────

def make_signals(
    df: pd.DataFrame,
    strength_diff: pd.Series,
    range_bars: int,
    range_pips: int,
) -> pd.DataFrame:
    close     = df["Close"]
    max_width = range_pips * PIP

    # 直前 range_bars 本の終値レンジ（shift(1)で当日足を含めない）
    roll_high = close.shift(1).rolling(range_bars).max()
    roll_low  = close.shift(1).rolling(range_bars).min()
    roll_mid  = (roll_high + roll_low) / 2
    roll_width = roll_high - roll_low

    in_range = roll_width <= max_width

    sd = strength_diff.reindex(df.index)

    long_sig  = in_range & (close > roll_high) & (sd > 0)
    short_sig = in_range & (close < roll_low)  & (sd < 0)

    return pd.DataFrame({
        "close":        close,
        "open":         df["Open"],
        "long_signal":  long_sig,
        "short_signal": short_sig,
        "range_high":   roll_high,
        "range_low":    roll_low,
        "range_mid":    roll_mid,
    })


# ── バックテスト ──────────────────────────────────────────────────────────────

def run_backtest(
    signals: pd.DataFrame,
    spread_pips: float,
    min_hold_bars: int = MIN_HOLD_BARS,
    tp_requires_profit: bool = TP_REQUIRES_PROFIT,
) -> pd.DataFrame:
    close  = signals["close"].values
    open_  = signals["open"].values
    r_mid  = signals["range_mid"].values
    l_sig  = signals["long_signal"].values
    s_sig  = signals["short_signal"].values
    idx    = signals.index
    n      = len(signals)

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
                entry_px  = open_[i] + spread_pips * PIP / 2
                stop_px   = r_mid[i - 1]
                entry_bar = i
                in_trade  = True
            elif s_sig[i - 1]:
                direction = -1
                entry_px  = open_[i] - spread_pips * PIP / 2
                stop_px   = r_mid[i - 1]
                entry_bar = i
                in_trade  = True
        else:
            held = i - entry_bar
            unrealized = (close[i] - entry_px) * direction / PIP
            exit_px     = None
            exit_reason = ""

            # 損切り: 常時有効
            if direction == 1 and close[i] <= stop_px:
                exit_px     = stop_px
                exit_reason = "stop"
            elif direction == -1 and close[i] >= stop_px:
                exit_px     = stop_px
                exit_reason = "stop"

            # 利確: 最低 min_hold_bars 経過 かつ 含み益あり の時だけ発動
            elif held >= min_hold_bars:
                in_profit = unrealized > 0
                if not tp_requires_profit or in_profit:
                    if direction == 1 and close[i] < close[i - 1]:
                        exit_px     = close[i]
                        exit_reason = "tp"
                    elif direction == -1 and close[i] > close[i - 1]:
                        exit_px     = close[i]
                        exit_reason = "tp"

            if exit_px is not None:
                pnl = (exit_px - entry_px) * direction / PIP - spread_pips
                trades.append({
                    "entry_time":  idx[entry_bar],
                    "exit_time":   idx[i],
                    "direction":   "Long" if direction == 1 else "Short",
                    "entry_price": round(entry_px, 5),
                    "exit_price":  round(exit_px, 5),
                    "stop_price":  round(stop_px, 5),
                    "pnl_pips":    round(pnl, 2),
                    "exit_reason": exit_reason,
                    "hold_bars":   held,
                })
                in_trade  = False
                direction = 0

    return pd.DataFrame(trades)


# ── 成績集計 ─────────────────────────────────────────────────────────────────

def analyze(trades: pd.DataFrame, label: str) -> dict:
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")

    if trades.empty:
        print("  トレードなし")
        return {}

    wins   = trades[trades["pnl_pips"] > 0]
    losses = trades[trades["pnl_pips"] <= 0]

    win_rate     = len(wins) / len(trades) * 100
    gross_profit = wins["pnl_pips"].sum()
    gross_loss   = losses["pnl_pips"].abs().sum()
    pf           = gross_profit / gross_loss if gross_loss > 0 else np.inf
    total_pips   = trades["pnl_pips"].sum()

    equity       = trades["pnl_pips"].cumsum()
    rolling_max  = equity.cummax()
    max_dd       = (equity - rolling_max).min()

    avg_win  = wins["pnl_pips"].mean()  if len(wins)   > 0 else 0.0
    avg_loss = losses["pnl_pips"].mean() if len(losses) > 0 else 0.0

    n_stop = (trades["exit_reason"] == "stop").sum()
    n_tp   = (trades["exit_reason"] == "tp").sum()

    print(f"  トレード数      : {len(trades):,}")
    print(f"  勝率            : {win_rate:.1f}%")
    print(f"  PF              : {pf:.2f}")
    print(f"  総損益          : {total_pips:+.1f} pips")
    print(f"  最大DD          : {max_dd:.1f} pips")
    print(f"  平均勝ち/負け   : {avg_win:+.1f} / {avg_loss:+.1f} pips")
    print(f"  平均保有        : {trades['hold_bars'].mean():.1f} 本")
    print(f"  損切り / 利確   : {n_stop} / {n_tp}")

    # 方向別
    for d in ["Long", "Short"]:
        sub = trades[trades["direction"] == d]
        if len(sub) == 0:
            continue
        sw  = sub[sub["pnl_pips"] > 0]
        wr  = len(sw) / len(sub) * 100
        tot = sub["pnl_pips"].sum()
        print(f"  {d:5s}: {len(sub):4d}件  勝率{wr:.0f}%  計{tot:+.1f}pips")

    # 月次
    trades2 = trades.copy()
    trades2["ym"] = trades2["exit_time"].dt.tz_localize(None).dt.to_period("M")
    monthly = trades2.groupby("ym")["pnl_pips"].sum()
    print(f"\n  月次損益 (pips):")
    for ym, v in monthly.items():
        bar = "#" * int(abs(v) / 5) if abs(v) >= 5 else ""
        sign = "+" if v >= 0 else ""
        print(f"    {ym}  {sign}{v:6.1f}  {bar}")

    return {
        "trades": len(trades),
        "win_rate": win_rate,
        "pf": pf,
        "total_pips": total_pips,
        "max_dd_pips": max_dd,
    }


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(" USDJPY 5分足 レンジブレイク戦略 IS解析")
    print(f" range_bars={RANGE_BARS}  range_pips={RANGE_PIPS}")
    print(f" strength_window={STRENGTH_WINDOW}  spread={SPREAD_PIPS}pips")
    print("=" * 55)

    # データロード
    print("\n[1] 全ペアデータ読み込み...")
    dfs = load_all_pairs()
    if PAIR not in dfs:
        print(f"ERROR: {PAIR} データなし")
        return

    # 強弱差
    print("[2] 通貨強弱差計算...")
    strength_diff = compute_strength_diff(dfs, STRENGTH_WINDOW)

    # シグナル
    print("[3] シグナル生成...")
    df_usdjpy = dfs[PAIR]
    signals   = make_signals(df_usdjpy, strength_diff, RANGE_BARS, RANGE_PIPS)

    # IS / OOS 分割
    sig_is  = signals.loc[IS_START:IS_END]
    sig_oos = signals.loc[OOS_START:OOS_END]

    print(f"    IS 期間:  {IS_START} ~ {IS_END}  ({len(sig_is):,}本)")
    print(f"    OOS期間:  {OOS_START} ~ {OOS_END}  ({len(sig_oos):,}本) ← 封印")

    n_long  = signals["long_signal"].sum()
    n_short = signals["short_signal"].sum()
    print(f"    シグナル総数: Long {n_long}  Short {n_short}")

    # バックテスト（IS のみ）
    print("\n[4] バックテスト実行（IS）...")
    trades_is = run_backtest(sig_is, SPREAD_PIPS)

    result = analyze(trades_is, f"IS: {IS_START} ~ {IS_END}")

    print(f"\n{'='*55}")
    print("  OOS は未開封。IS 結果を確認後に開封を判断してください。")
    print(f"{'='*55}\n")

    # CSV 保存
    if not trades_is.empty:
        out = Path("backtest_trades_range_break.csv")
        trades_is.to_csv(out, index=False)
        print(f"  トレード一覧: {out}")


if __name__ == "__main__":
    main()
