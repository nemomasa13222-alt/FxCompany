"""
USDJPY 5分足 レンジブレイク パラメータサーベイ（IS期間）

コスト: DMMFX USDJPY 往復0.4pips (スプレッド0.2 + スリッページ0.2)
IS: 2022-01-01 ~ 2024-01-01

サーベイ軸:
  range_bars    : [12, 20, 30]
  range_pips    : [ 7, 10, 15]
  min_hold_bars : [ 2,  3,  5]
  → 27通り
"""
from __future__ import annotations

import itertools
import numpy as np
import pandas as pd
from pathlib import Path

from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

# ── 定数 ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path("data/dukascopy")
PAIR     = "USDJPY"
PIP      = 0.01

IS_START  = "2022-01-01"
IS_END    = "2024-01-01"
OOS_START = "2024-01-01"
OOS_END   = "2025-01-01"

# DMMFX USDJPY コスト
# スプレッドはエントリー時のみ発生。往復合計0.2pips。
ENTRY_COST_PIPS = 0.2   # スプレッド（エントリー時のみ）
EXIT_COST_PIPS  = 0.0   # エグジット時コストなし
TOTAL_COST      = ENTRY_COST_PIPS + EXIT_COST_PIPS  # = 0.2 pips 往復

STRENGTH_WINDOW = 20

# ── サーベイグリッド ─────────────────────────────────────────────────────────
RANGE_BARS_LIST    = [12, 20, 30]
RANGE_PIPS_LIST    = [ 7, 10, 15]
MIN_HOLD_BARS_LIST = [ 2,  3,  5]


# ── データ準備 ────────────────────────────────────────────────────────────────

def load_data():
    dfs = {}
    for p in PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if f.exists():
            dfs[p] = pd.read_parquet(f)
    return dfs


def compute_strength_diff(dfs, window):
    returns_dict = {p: log_returns(df["Close"]) for p, df in dfs.items()}
    strength = currency_strength(returns_dict)
    usd = strength["USD"].rolling(window).sum()
    jpy = strength["JPY"].rolling(window).sum()
    return (usd - jpy).rename("strength_diff")


# ── シグナル生成 ──────────────────────────────────────────────────────────────

def make_signals(df, strength_diff, range_bars, range_pips):
    close     = df["Close"]
    max_width = range_pips * PIP

    roll_high = close.shift(1).rolling(range_bars).max()
    roll_low  = close.shift(1).rolling(range_bars).min()
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


# ── バックテスト ──────────────────────────────────────────────────────────────

def run_backtest(signals, min_hold_bars):
    close = signals["close"].values
    open_ = signals["open"].values
    r_mid = signals["range_mid"].values
    l_sig = signals["long_signal"].values
    s_sig = signals["short_signal"].values
    n     = len(signals)

    pnls = []
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
            exit_px    = None

            # 損切り: 常時
            if direction == 1 and close[i] <= stop_px:
                exit_px = stop_px - EXIT_COST_PIPS * PIP
            elif direction == -1 and close[i] >= stop_px:
                exit_px = stop_px + EXIT_COST_PIPS * PIP

            # 利確: 最低保有 & 含み益あり
            elif held >= min_hold_bars:
                mid_exit = close[i]
                unrealized = (mid_exit - open_[entry_bar]) * direction / PIP - TOTAL_COST
                if unrealized > 0:
                    if direction == 1 and close[i] < close[i - 1]:
                        exit_px = mid_exit - EXIT_COST_PIPS * PIP
                    elif direction == -1 and close[i] > close[i - 1]:
                        exit_px = mid_exit + EXIT_COST_PIPS * PIP

            if exit_px is not None:
                pnl = (exit_px - entry_px) * direction / PIP
                pnls.append(pnl)
                in_trade  = False
                direction = 0

    return np.array(pnls)


# ── 資金換算設定 ──────────────────────────────────────────────────────────────
# 前提: 資金100万円, USDJPY 1万通貨固定
# 1pip USDJPY(1万通貨) = 100円  →  1pip = 0.01% of 100万円
CAPITAL_JPY  = 1_000_000
LOT_UNITS    = 10_000
PIP_VAL_JPY  = 100          # 1pip × 1万通貨 USDJPY ≈ 100円
PCT_PER_PIP  = PIP_VAL_JPY / CAPITAL_JPY * 100   # = 0.01%/pip


# ── 成績計算 ─────────────────────────────────────────────────────────────────

def metrics(pnls):
    if len(pnls) == 0:
        return dict(n=0, wr=0, pf=0, total_pips=0, total_jpy=0, dd_pct=0)

    wins   = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    wr         = len(wins) / len(pnls) * 100
    gp         = wins.sum()
    gl         = abs(losses.sum())
    pf         = gp / gl if gl > 0 else np.inf
    total_pips = pnls.sum()
    total_jpy  = total_pips * PIP_VAL_JPY

    eq       = np.cumsum(pnls)
    roll_max = np.maximum.accumulate(np.maximum(eq, 0))  # 0スタート基準
    dd_pips  = (eq - roll_max).min()
    dd_pct   = dd_pips * PCT_PER_PIP   # %表示（負値）

    return dict(n=len(pnls), wr=wr, pf=pf,
                total_pips=total_pips, total_jpy=total_jpy, dd_pct=dd_pct)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(f" USDJPY 5min レンジブレイク パラメータサーベイ  IS:{IS_START}~{IS_END}")
    print(f" コスト: DMMFX 往復{TOTAL_COST}pips (spread0.2+slip0.2)")
    print("=" * 70)

    print("\n[1] データ読み込み...")
    dfs = load_data()
    assert PAIR in dfs, f"{PAIR} データなし"

    print("[2] 強弱差計算...")
    strength_diff = compute_strength_diff(dfs, STRENGTH_WINDOW)

    df_is  = dfs[PAIR].loc[IS_START:IS_END]
    df_oos = dfs[PAIR].loc[OOS_START:OOS_END]

    print(f"[3] 27通りサーベイ開始（IS）...\n")

    results = []
    combos  = list(itertools.product(
        RANGE_BARS_LIST, RANGE_PIPS_LIST, MIN_HOLD_BARS_LIST
    ))

    for rb, rp, mh in combos:
        sig  = make_signals(df_is, strength_diff, rb, rp)
        pnls = run_backtest(sig, mh)
        m    = metrics(pnls)
        results.append({
            "range_bars": rb,
            "range_pips": rp,
            "min_hold":   mh,
            "n":          m["n"],
            "wr":         m["wr"],
            "pf":         m["pf"],
            "total_pips": m["total_pips"],
            "total_jpy":  m["total_jpy"],
            "dd_pct":     m["dd_pct"],
        })

    df_res = pd.DataFrame(results).sort_values("pf", ascending=False)

    # ── IS結果表示 ────────────────────────────────────────────────────────────
    print(f"  前提: 資金{CAPITAL_JPY//10000}万円 / USDJPY {LOT_UNITS//10000}万通貨固定 / 1pip={PIP_VAL_JPY}円")
    print(f"  {'bars':>4} {'pips':>4} {'hold':>4} | {'N':>5} {'WR%':>6} {'PF':>5} "
          f"{'損益(万円)':>10} {'DD%':>7}")
    print("  " + "-" * 62)

    for _, row in df_res.iterrows():
        flag = " <-- 採用" if _ == df_res.index[0] else ""
        print(
            f"  {int(row.range_bars):>4} {int(row.range_pips):>4} {int(row.min_hold):>4} | "
            f"{int(row.n):>5} {row.wr:>6.1f} {row.pf:>5.2f} "
            f"{row.total_jpy/10000:>+10.1f} {row.dd_pct:>+7.2f}%{flag}"
        )

    # ── OOS開封（採用パラメータのみ） ─────────────────────────────────────────
    best = df_res.iloc[0]
    rb_best = int(best["range_bars"])
    rp_best = int(best["range_pips"])
    mh_best = int(best["min_hold"])

    print(f"\n{'=' * 70}")
    print(f"  OOS開封: bars={rb_best} pips={rp_best} hold={mh_best}")
    print(f"  期間: {OOS_START} ~ {OOS_END}")
    print(f"{'=' * 70}")

    sig_oos   = make_signals(df_oos, strength_diff, rb_best, rp_best)
    pnls_oos  = run_backtest(sig_oos, mh_best)
    m_oos     = metrics(pnls_oos)

    sig_is2   = make_signals(df_is, strength_diff, rb_best, rp_best)
    pnls_is2  = run_backtest(sig_is2, mh_best)
    m_is2     = metrics(pnls_is2)

    def _row(label, m):
        return (
            f"  {label:<6} | "
            f"N={m['n']:>5}  "
            f"WR={m['wr']:>5.1f}%  "
            f"PF={m['pf']:>5.2f}  "
            f"損益={m['total_jpy']/10000:>+6.1f}万円  "
            f"DD={m['dd_pct']:>+6.2f}%"
        )

    print(_row("IS", m_is2))
    print(_row("OOS", m_oos))

    # IS/OOS乖離チェック
    pf_diff = abs(m_is2["pf"] - m_oos["pf"])
    print(f"\n  IS/OOS PF乖離: {pf_diff:.2f}  (基準: <= 0.30)")

    # 判定
    print(f"\n  [採否判定]")
    checks = [
        ("OOS PF >= 1.10",        m_oos["pf"] >= 1.10),
        ("OOS 損益 > 0",          m_oos["total_jpy"] > 0),
        ("OOS DD <= IS×1.5",      abs(m_oos["dd_pct"]) <= abs(m_is2["dd_pct"]) * 1.5),
        ("IS/OOS PF乖離 <= 0.30", pf_diff <= 0.30),
    ]
    all_pass = all(ok for _, ok in checks)
    for label, ok in checks:
        mark = "OK" if ok else "NG"
        print(f"    [{mark}] {label}")
    print(f"\n  --> {'採用' if all_pass else '不採用'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
