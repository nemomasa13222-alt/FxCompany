# -*- coding: utf-8 -*-
"""
パラメータサーベイ: MA20乖離率フィルターの効果検証
実行: python japan_stocks/backtest_param_survey.py

MA20乖離率フィルター: なし / 10% / 15% の3条件で比較。
ストップロスは -7% 固定。
"""

import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
import jpx_universe as jpx

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_START     = "2022-01-01"
BACKTEST_START = "2023-04-01"
NIKKEI_TICKER  = "^N225"
MARKET         = "prime"
WORKERS        = 30
STOP_LOSS_PCT  = 0.07    # 固定
MAX_HOLD_DAYS  = 126

# サーベイ対象パラメータ
EXT_THRESHOLDS = [None, 15.0, 10.0]   # None=フィルターなし


# ── シグナル計算 ──────────────────────────────────────────────────────────────

def build_signals(close: pd.Series, n225: pd.Series,
                  n225_ma200: pd.Series,
                  ext_threshold: float | None) -> pd.DataFrame:
    """8条件 + RS(日経対比) + ブレイクアウト + 市場フィルター + MA20乖離フィルター"""
    n225_aln     = n225.reindex(close.index, method="ffill")
    n225_ma200_a = n225_ma200.reindex(close.index, method="ffill")

    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    high_52w = close.rolling(252).max()
    low_52w  = close.rolling(252).min()

    c1 = (close > ma150) & (close > ma200)
    c2 = ma150 > ma200
    c3 = ma200 > ma200.shift(20)
    c4 = (ma50 > ma150) & (ma50 > ma200)
    c5 = close >= low_52w * 1.25
    c6 = close >= high_52w * 0.75
    c7 = (close / close.shift(252) - 1) > (n225_aln / n225_aln.shift(252) - 1)
    c8 = close > ma50

    # MA20乖離フィルター
    ext_from_ma20 = (close / ma20 - 1) * 100
    if ext_threshold is not None:
        c_ext = ext_from_ma20 <= ext_threshold
    else:
        c_ext = pd.Series(True, index=close.index)

    prev_20d_high = close.rolling(20).max().shift(1)
    breakout      = close > prev_20d_high
    market_bull   = n225_aln > n225_ma200_a

    entry_ok = c1 & c2 & c3 & c4 & c5 & c6 & c7 & c8 & breakout & market_bull & c_ext

    return pd.DataFrame({"close": close, "entry_ok": entry_ok}, index=close.index)


def simulate_trades(ticker: str, sig: pd.DataFrame) -> list[dict]:
    in_trade = False
    entry_px = 0.0
    entry_dt = None
    trades   = []
    start_ts = pd.Timestamp(BACKTEST_START)

    for dt_idx, row in sig.iterrows():
        if dt_idx < start_ts:
            continue
        if in_trade:
            cur_px = row["close"]
            hold   = (dt_idx - entry_dt).days
            if cur_px <= entry_px * (1 - STOP_LOSS_PCT):
                ret = (cur_px / entry_px - 1) * 100
                trades.append({"ticker": ticker, "entry": entry_dt,
                                "ret": round(ret, 2), "reason": "stop",
                                "hold": hold})
                in_trade = False
            elif hold >= MAX_HOLD_DAYS:
                ret = (cur_px / entry_px - 1) * 100
                trades.append({"ticker": ticker, "entry": entry_dt,
                                "ret": round(ret, 2), "reason": "time",
                                "hold": hold})
                in_trade = False
        else:
            if row["entry_ok"]:
                in_trade = True
                entry_px = row["close"]
                entry_dt = dt_idx

    return trades


def run_one(all_closes, n225, n225_ma200, ext_threshold) -> pd.DataFrame:
    """1つのパラメータ条件でバックテストを実行"""
    label = f"MA20乖離≤{ext_threshold}%" if ext_threshold else "フィルターなし"
    print(f"  [{label}] 計算中...")

    all_trades = []
    for ticker, close in all_closes.items():
        try:
            sig = build_signals(close, n225, n225_ma200, ext_threshold)
            all_trades.extend(simulate_trades(ticker, sig))
        except Exception:
            pass

    if not all_trades:
        return pd.DataFrame()
    df = pd.DataFrame(all_trades)
    df["year"] = pd.to_datetime(df["entry"]).dt.year
    return df


def _pf(ret: pd.Series) -> float:
    w = ret[ret > 0].sum()
    l = abs(ret[ret < 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


def _equity(df: pd.DataFrame) -> float:
    """1トレードあたり資金の10%を投入した場合の最終資産（初期100万円）"""
    capital = 1_000_000
    pos_size = 0.10
    for ret in df["ret"]:
        capital += capital * pos_size * (ret / 100)
    return capital


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*65}")
    print(f"  パラメータサーベイ: MA20乖離率フィルター")
    print(f"  実行日時: {run_time}")
    print(f"  ストップロス: -{STOP_LOSS_PCT*100:.0f}%（固定）")
    print(f"  サーベイ条件: {EXT_THRESHOLDS}")
    print(f"{'='*65}\n")

    # ── データ取得（1回だけ）────────────────────────────────────────────
    print("日経225取得中...")
    n225_df    = dt.fetch(NIKKEI_TICKER, start=DATA_START)
    n225       = n225_df["Close"]
    n225_ma200 = n225.rolling(200).mean()

    print("JPX銘柄リスト取得中...")
    tickers = jpx.get_tickers_by_market(MARKET)

    print(f"株価データ取得中（{WORKERS}並列・キャッシュ優先）...")
    all_closes = {}
    done = 0

    def _fetch(t):
        try:
            df = dt.fetch(t, start=DATA_START)
            if len(df) >= 300:
                return t, df["Close"]
        except Exception:
            pass
        return t, None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_fetch, t): t for t in tickers}
        for f in as_completed(futures):
            t, s = f.result()
            if s is not None:
                all_closes[t] = s
            done += 1
            if done % 500 == 0 or done == len(tickers):
                print(f"  {done}/{len(tickers)}  有効: {len(all_closes)}", end="\r")
    print(f"\n  有効: {len(all_closes)} 銘柄\n")

    # ── 各パラメータで実行 ────────────────────────────────────────────────
    results = {}
    for thr in EXT_THRESHOLDS:
        df = run_one(all_closes, n225, n225_ma200, thr)
        results[thr] = df

    # ── 比較表示 ──────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  サーベイ結果比較")
    print(f"{'='*65}\n")

    summary = []
    for thr, df in results.items():
        label = f"≤{thr}%" if thr else "なし"
        if df.empty:
            summary.append({"条件": label, "件数": 0})
            continue
        ret = df["ret"]
        stop_r = (df["reason"] == "stop").mean() * 100
        final  = _equity(df)
        summary.append({
            "MA20乖離フィルター": label,
            "トレード数"        : len(df),
            "平均リターン"      : f"{ret.mean():+.2f}%",
            "中央値"            : f"{ret.median():+.2f}%",
            "勝率"              : f"{(ret>0).mean()*100:.1f}%",
            "損切り率"          : f"{stop_r:.1f}%",
            "PF"                : _pf(ret),
            "最終資産(10%ポジ)" : f"¥{final:,.0f}",
        })

    sdf = pd.DataFrame(summary)
    print(sdf.to_string(index=False))

    # ── 年別詳細 ──────────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print("  年別内訳（各パラメータ）")
    print(f"{'─'*65}")

    for thr, df in results.items():
        label = f"MA20乖離≤{thr}%" if thr else "フィルターなし"
        print(f"\n  【{label}】")
        if df.empty:
            print("  トレードなし")
            continue
        print(f"  {'年':<6}{'件数':>6}{'平均':>10}{'勝率':>8}{'PF':>6}{'損切り率':>10}")
        for yr, g in df.groupby("year"):
            r = g["ret"]
            print(f"  {yr:<6}{len(g):>6}  {r.mean():>+7.2f}%  "
                  f"{(r>0).mean()*100:>5.0f}%  {_pf(r):>4.2f}  "
                  f"{(g['reason']=='stop').mean()*100:>7.1f}%")

    # ── Markdown保存 ──────────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"param_survey_ma20ext_{ts}.md"
    _save(results, sdf, run_time, path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*65}\n")


def _save(results, sdf, run_time, path):
    lines = [
        "# パラメータサーベイ: MA20乖離率フィルター\n",
        f"実行日時: {run_time}  \n",
        f"ストップロス: -7%（固定）  最大保有: 126日  \n",
        "---\n",
        "## サーベイ結果比較\n",
        sdf.to_markdown(index=False), "\n",
        "---\n",
        "## 年別内訳\n",
    ]

    for thr, df in results.items():
        label = f"MA20乖離≤{thr}%" if thr else "フィルターなし"
        lines.append(f"\n### {label}\n")
        if df.empty:
            lines.append("トレードなし\n")
            continue
        lines += [
            "| 年 | 件数 | 平均リターン | 勝率 | PF | 損切り率 |",
            "|-----|------|------------|------|-----|---------|",
        ]
        for yr, g in df.groupby("year"):
            r = g["ret"]
            lines.append(
                f"| {yr} | {len(g)} | {r.mean():+.2f}% "
                f"| {(r>0).mean()*100:.0f}% | {_pf(r):.2f} "
                f"| {(g['reason']=='stop').mean()*100:.1f}% |"
            )

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
