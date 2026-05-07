# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート バックテスト v4
実行: python japan_stocks/backtest_minervini_v4.py

v3からの改善点:
  ①② 建値損切  : +5%上昇確認後、ストップをエントリー価格に引き上げ
  ③  決算前クローズ: yfinanceの決算カレンダーから取得、前日引けで決済
  ④  MA200割れ決済: A（なし）vs B（あり）を比較
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
import jpx_universe as jpx
from jquants import JQuantsClient

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR   = Path(__file__).parent / "results" / "cache"

DATA_START     = "2018-01-01"   # MA200計算に200営業日（≒10ヶ月）分の余裕を持たせる
BACKTEST_START = "2020-01-01"   # コロナ急落から現在まで（約6年）
NIKKEI_TICKER  = "^N225"
MARKET         = "prime"
WORKERS        = 30
MAX_HOLD_DAYS  = 126
BASE_LOOKBACK  = 30
MAX_BASE_RANGE = 0.20
BREAKEVEN_TRIGGER = 0.05   # +5%上昇でストップを建値に引き上げ

# ── IS / OOS 分割 ────────────────────────────────────────────────────────────
# IS (In-Sample) : 戦略開発・パラメータ最適化に使う期間
# OOS (Out-of-Sample): 最終検証まで封印する期間。絶対にパラメータ調整に使わない。
IS_END    = "2024-12-31"   # IS終端（この日以前のエントリーのみ集計）
OOS_START = "2025-01-01"   # OOS開始（封印中 — 戦略確定後に1回だけ開封）

# 末尾から MAX_HOLD_DAYS 以内のエントリーは「未完了」として集計除外
# （バックテスト期末での強制終了による歪みを防ぐ）
EXCLUDE_INCOMPLETE_TAIL = True


# ── 決算カレンダー取得 ────────────────────────────────────────────────────────

def fetch_earnings_calendar(tickers: list[str]) -> dict[str, list[pd.Timestamp]]:
    """
    J-Quants API（優先）→ yfinance（フォールバック）で決算日を取得。
    戻り値: {ticker: [決算日, ...]}
    """
    # J-Quants を試みる
    try:
        client = JQuantsClient()
        cal = client.get_earnings_calendar(from_date=DATA_START)
        if cal:
            covered = sum(1 for t in tickers if t in cal)
            print(f"  J-Quants カバー率: {covered}/{len(tickers)} 銘柄 ({covered/len(tickers)*100:.1f}%)")
            return cal
        print("  J-Quants: データなし、yfinanceにフォールバック")
    except Exception as e:
        print(f"  J-Quants エラー ({e})、yfinanceにフォールバック")

    # yfinance フォールバック
    cache_path = CACHE_DIR / "earnings_calendar.parquet"
    if cache_path.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if age.days < 7:
            df = pd.read_parquet(cache_path)
            cal = {}
            for _, row in df.iterrows():
                cal.setdefault(row["ticker"], []).append(pd.Timestamp(row["date"]))
            print(f"  決算カレンダー（yfinance キャッシュ）: {len(cal)} 銘柄")
            return cal

    print(f"  yfinance 決算カレンダー取得中（{WORKERS}並列）...")
    records = []
    done = 0

    def _fetch_one(ticker):
        try:
            t  = yf.Ticker(ticker)
            ed = t.earnings_dates
            if ed is None or ed.empty:
                return []
            dates = []
            for ts in ed.index:
                try:
                    d = pd.Timestamp(ts).normalize().tz_localize(None)
                    dates.append((ticker, d))
                except Exception:
                    pass
            return dates
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_fetch_one, t): t for t in tickers}
        for f in as_completed(futures):
            results = f.result()
            records.extend(results)
            done += 1
            if done % 200 == 0 or done == len(tickers):
                print(f"    {done}/{len(tickers)}", end="\r")

    print()
    if not records:
        return {}

    df = pd.DataFrame(records, columns=["ticker", "date"])
    df.to_parquet(cache_path)

    cal = {}
    for _, row in df.iterrows():
        cal.setdefault(row["ticker"], []).append(row["date"])
    covered = sum(1 for t in tickers if t in cal)
    print(f"  yfinance カバー率: {covered}/{len(tickers)} ({covered/len(tickers)*100:.1f}%)")
    return cal


# ── シグナル計算 ──────────────────────────────────────────────────────────────

def build_8cond(close: pd.Series, n225: pd.Series,
                n225_ma200: pd.Series) -> pd.Series:
    n225_aln     = n225.reindex(close.index, method="ffill")
    n225_ma200_a = n225_ma200.reindex(close.index, method="ffill")
    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    h52   = close.rolling(252).max()
    l52   = close.rolling(252).min()
    c1 = (close > ma150) & (close > ma200)
    c2 = ma150 > ma200
    c3 = ma200 > ma200.shift(20)
    c4 = (ma50 > ma150) & (ma50 > ma200)
    c5 = close >= l52 * 1.25
    c6 = close >= h52 * 0.75
    c7 = (close / close.shift(252) - 1) > (n225_aln / n225_aln.shift(252) - 1)
    c8 = close > ma50
    market_bull = n225_aln > n225_ma200_a
    return c1 & c2 & c3 & c4 & c5 & c6 & c7 & c8 & market_bull


def detect_base(close: pd.Series, idx: int):
    if idx < BASE_LOOKBACK + 1:
        return None
    window = close.iloc[idx - BASE_LOOKBACK: idx]
    if len(window) < 15:
        return None
    bh = float(window.max())
    bl = float(window.min())
    if (bh / bl - 1) > MAX_BASE_RANGE:
        return None
    return {"base_high": bh, "base_low": bl}


# ── トレードシミュレーション ──────────────────────────────────────────────────

def simulate_trades(ticker: str, close: pd.Series, cond8: pd.Series,
                    earnings_dates: list[pd.Timestamp],
                    n225_ma200_breach: pd.Series,   # True の日は日経MA200割れ
                    use_ma200_exit: bool) -> list[dict]:
    trades   = []
    in_trade = False
    entry_px = 0.0
    stop_px  = 0.0      # 初期値 = ベース安値
    entry_dt = None
    be_raised = False   # 建値にストップを引き上げたか

    # 決算日セット（日付のみ）
    earn_set = {d.date() for d in earnings_dates}

    start_ts = pd.Timestamp(BACKTEST_START)

    for i, (ts, c8_ok) in enumerate(cond8.items()):
        if ts < start_ts:
            continue

        cur_px = float(close.iloc[i])
        today  = ts.date()

        # ── ポジション保有中 ─────────────────────────────────────────────
        if in_trade:
            hold = (ts - entry_dt).days

            # ① 決算前日 → 引けで強制クローズ
            tomorrow = (ts + pd.Timedelta(days=1)).date()
            if tomorrow in earn_set:
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, ts,
                                   entry_px, cur_px, ret,
                                   "earnings_close", stop_px, hold))
                in_trade = False
                be_raised = False
                continue

            # ④-B 日経MA200割れ → 全ポジション強制決済
            if use_ma200_exit and n225_ma200_breach.get(ts, False):
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, ts,
                                   entry_px, cur_px, ret,
                                   "ma200_breach", stop_px, hold))
                in_trade = False
                be_raised = False
                continue

            # ①② 建値ストップ引き上げ（+5%達成後）
            if not be_raised and cur_px >= entry_px * (1 + BREAKEVEN_TRIGGER):
                stop_px  = entry_px   # ストップを建値に引き上げ
                be_raised = True

            # ストップ発火
            if cur_px < stop_px:
                reason = "stop_breakeven" if be_raised else "stop_base"
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, ts,
                                   entry_px, cur_px, ret,
                                   reason, stop_px, hold))
                in_trade = False
                be_raised = False
                continue

            # 最大保有
            if hold >= MAX_HOLD_DAYS:
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, ts,
                                   entry_px, cur_px, ret,
                                   "time", stop_px, hold))
                in_trade = False
                be_raised = False
                continue

        # ── エントリー判定 ────────────────────────────────────────────────
        else:
            if not c8_ok:
                continue
            # 決算当日・翌日はエントリーしない
            if today in earn_set:
                continue
            base = detect_base(close, i)
            if base is None:
                continue
            if cur_px <= base["base_high"]:
                continue
            in_trade = True
            entry_px = cur_px
            stop_px  = base["base_low"]
            entry_dt = ts
            be_raised = False

    return trades


def _rec(ticker, entry_dt, exit_dt, entry_px, exit_px,
         ret, reason, stop_px, hold):
    return {
        "ticker"    : ticker,
        "entry_date": entry_dt.strftime("%Y-%m-%d"),
        "exit_date" : exit_dt.strftime("%Y-%m-%d"),
        "entry_px"  : round(entry_px, 1),
        "exit_px"   : round(exit_px, 1),
        "stop_px"   : round(stop_px, 1),
        "ret_pct"   : round(ret, 2),
        "reason"    : reason,
        "hold_days" : hold,
    }


# ── 集計 ─────────────────────────────────────────────────────────────────────

def _pf(ret: pd.Series) -> float:
    w = ret[ret > 0].sum()
    l = abs(ret[ret < 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


def print_stats(df: pd.DataFrame, label: str):
    print(f"\n  ── {label} ──")
    if df.empty:
        print("  トレードなし")
        return
    ret = df["ret_pct"]
    print(f"  総トレード数    : {len(df)}")
    print(f"  平均リターン    : {ret.mean():+.2f}%")
    print(f"  中央値          : {ret.median():+.2f}%")
    print(f"  勝率            : {(ret > 0).mean()*100:.1f}%")
    print(f"  PF              : {_pf(ret):.2f}")

    reason_counts = df["reason"].value_counts()
    print(f"  決済理由:")
    labels = {
        "stop_base"       : "ベース安値損切り",
        "stop_breakeven"  : "建値損切り（①②）",
        "earnings_close"  : "決算前クローズ（③）",
        "ma200_breach"    : "日経MA200割れ決済（④B）",
        "time"            : "期間満了",
    }
    for reason, cnt in reason_counts.items():
        sub = df[df["reason"] == reason]["ret_pct"]
        lbl = labels.get(reason, reason)
        print(f"    {lbl:<24}: {cnt:>4}件  平均{sub.mean():>+7.2f}%")

    # 年別
    df2 = df.copy()
    df2["year"] = pd.to_datetime(df2["entry_date"]).dt.year
    print(f"  年別:")
    for yr, g in df2.groupby("year"):
        r = g["ret_pct"]
        print(f"    {yr}: {len(g):>4}件  平均{r.mean():>+7.2f}%  "
              f"勝率{(r>0).mean()*100:>4.0f}%  PF{_pf(r):.2f}")


def save_report(results: dict, run_time: str, path: Path):
    lines = [
        "# ミネルヴィニ バックテスト v4 結果\n",
        f"実行日時: {run_time}  \n",
        "---\n",
        "## 改善内容\n",
        f"- ①② 建値損切: +{BREAKEVEN_TRIGGER*100:.0f}%上昇後、ストップを建値に引き上げ",
        "- ③ 決算前クローズ: yfinance決算カレンダー使用、前日引けで決済",
        "- ④A: MA200割れ決済なし（比較対象）",
        "- ④B: MA200割れで既存ポジションも強制決済\n",
        "---\n",
        "## 比較サマリー\n",
        "| 条件 | 件数 | 平均 | 勝率 | PF | ベース損切 | 建値損切 | 決算ｸﾛｰｽﾞ | MA200決済 | 期間満了 |",
        "|-----|------|------|------|-----|---------|---------|---------|---------|--------|",
    ]

    for label, df in results.items():
        if df.empty:
            lines.append(f"| {label} | 0 | - | - | - | - | - | - | - | - |")
            continue
        ret = df["ret_pct"]
        rc  = df["reason"].value_counts()
        lines.append(
            f"| {label} | {len(df)} | {ret.mean():+.2f}% "
            f"| {(ret>0).mean()*100:.0f}% | {_pf(ret):.2f} "
            f"| {rc.get('stop_base',0)} | {rc.get('stop_breakeven',0)} "
            f"| {rc.get('earnings_close',0)} | {rc.get('ma200_breach',0)} "
            f"| {rc.get('time',0)} |"
        )

    lines += [
        "\n---\n",
        "## v3との比較\n",
        "| バージョン | 件数 | 平均リターン | 勝率 | PF | 損切り率 |",
        "|-----------|------|------------|------|-----|---------|",
        "| v3（ベース安値損切り）    | 3,189 | +4.5% | 50% | 1.78 | 39.3% |",
    ]
    for label, df in results.items():
        if df.empty:
            continue
        ret  = df["ret_pct"]
        stop = df["reason"].isin(["stop_base", "stop_breakeven", "ma200_breach"])
        lines.append(
            f"| v4 {label} | {len(df)} | {ret.mean():+.2f}% "
            f"| {(ret>0).mean()*100:.0f}% | {_pf(ret):.2f} "
            f"| {stop.mean()*100:.1f}% |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*65}")
    print(f"  ミネルヴィニ バックテスト v4")
    print(f"  実行日時: {run_time}")
    print(f"  ① 建値損切 (+{BREAKEVEN_TRIGGER*100:.0f}%達成後ストップ引き上げ)")
    print(f"  ③ 決算前クローズ（yfinanceカレンダー）")
    print(f"  ④ MA200割れ決済 A（なし）vs B（あり）を比較")
    print(f"{'='*65}\n")

    # ── 日経225 ──────────────────────────────────────────────────────────
    print("日経225データ取得中...")
    n225_df    = dt.fetch(NIKKEI_TICKER, start=DATA_START)
    n225       = n225_df["Close"]
    n225_ma200 = n225.rolling(200).mean()
    # MA200割れ（前日はOKで当日割れ）
    ma200_breach_days = set(
        n225.index[(n225 < n225_ma200) &
                   (n225.shift(1) >= n225_ma200.shift(1))]
        .strftime("%Y-%m-%d")
    )
    print(f"  MA200割れ発生日数: {len(ma200_breach_days)} 日\n")

    # ── 全銘柄取得 ────────────────────────────────────────────────────────
    print("JPX銘柄リスト取得中...")
    tickers = jpx.get_tickers_by_market(MARKET)

    print(f"株価データ取得中（{WORKERS}並列）...")
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

    # ── 決算カレンダー取得 ────────────────────────────────────────────────
    print("決算カレンダー取得中...")
    earnings_cal = fetch_earnings_calendar(list(all_closes.keys()))

    # MA200割れ日をSeriesに変換（日付→bool）
    n225_breach_series = pd.Series(False, index=n225.index)
    for d_str in ma200_breach_days:
        try:
            n225_breach_series[pd.Timestamp(d_str)] = True
        except KeyError:
            pass

    # ── シミュレーション（④A: MA200決済なし / ④B: あり）────────────────
    print("\nシミュレーション中...")
    trades_A = []  # ④A: MA200決済なし
    trades_B = []  # ④B: MA200決済あり

    for i, (ticker, close) in enumerate(all_closes.items()):
        if i % 300 == 0:
            print(f"  {i}/{len(all_closes)} 銘柄...", end="\r")
        try:
            cond8       = build_8cond(close, n225, n225_ma200)
            earn_dates  = earnings_cal.get(ticker, [])
            breach_ser  = n225_breach_series.reindex(close.index).fillna(False)
            breach_dict = breach_ser.to_dict()

            tA = simulate_trades(ticker, close, cond8, earn_dates,
                                 breach_dict, use_ma200_exit=False)
            tB = simulate_trades(ticker, close, cond8, earn_dates,
                                 breach_dict, use_ma200_exit=True)
            trades_A.extend(tA)
            trades_B.extend(tB)
        except Exception:
            pass

    print(f"\n  ④A: {len(trades_A)} トレード")
    print(f"  ④B: {len(trades_B)} トレード")

    dfA = pd.DataFrame(trades_A) if trades_A else pd.DataFrame()
    dfB = pd.DataFrame(trades_B) if trades_B else pd.DataFrame()

    # ── 末尾未完了トレードの除外 ──────────────────────────────────────
    if EXCLUDE_INCOMPLETE_TAIL and not dfA.empty:
        data_end = n225.index.max()
        cutoff   = data_end - pd.Timedelta(days=MAX_HOLD_DAYS + 30)
        raw_A, raw_B = len(dfA), len(dfB)
        dfA = dfA[pd.to_datetime(dfA["entry_date"]) <= cutoff].copy()
        dfB = dfB[pd.to_datetime(dfB["entry_date"]) <= cutoff].copy() if not dfB.empty else dfB
        print(f"\n  末尾除外: ④A {raw_A}→{len(dfA)}件  ④B {raw_B}→{len(dfB)}件")
        print(f"  有効エントリー期間: {BACKTEST_START} 〜 {cutoff.date()}")

    # ── IS / OOS 分割 ────────────────────────────────────────────────────
    def split_is_oos(df: pd.DataFrame):
        if df.empty:
            return df.copy(), df.copy()
        entry = pd.to_datetime(df["entry_date"])
        return df[entry <= IS_END].copy(), df[entry >= OOS_START].copy()

    dfA_is, dfA_oos = split_is_oos(dfA)
    dfB_is, dfB_oos = split_is_oos(dfB)

    # ── 結果表示（ISのみ） ───────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  バックテスト v4 結果  [IS: {BACKTEST_START} 〜 {IS_END}]")
    print(f"{'='*65}")
    print_stats(dfA_is, "④A: MA200割れ決済なし（推奨）")
    print_stats(dfB_is, "④B: MA200割れ決済あり（比較）")

    print(f"\n  ── v3との比較 ──")
    print(f"  v3:  3,189件  平均+4.5%  勝率50%  PF1.78  損切り39.3%")

    print(f"\n{'='*65}")
    print(f"  OOS: {OOS_START} 〜 現在  [封印中 -- 戦略確定後に開封]")
    print(f"  OOS(A) トレード数: {len(dfA_oos)}件（未集計）")
    print(f"  OOS(B) トレード数: {len(dfB_oos)}件（未集計）")
    print(f"{'='*65}")

    # ── 保存 ──────────────────────────────────────────────────────────────
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"backtest_v4_{ts}.md"
    save_report({"④A MA200決済なし": dfA_is, "④B MA200決済あり": dfB_is},
                run_time, path)

    # CSV保存（IS / OOS 別）
    if not dfA_is.empty:
        dfA_is.to_csv(RESULTS_DIR / f"v4A_trades_{ts}.csv",     index=False, encoding="utf-8-sig")
    if not dfB_is.empty:
        dfB_is.to_csv(RESULTS_DIR / f"v4B_trades_{ts}.csv",     index=False, encoding="utf-8-sig")
    if not dfA_oos.empty:
        dfA_oos.to_csv(RESULTS_DIR / f"v4A_oos_{ts}.csv", index=False, encoding="utf-8-sig")
    if not dfB_oos.empty:
        dfB_oos.to_csv(RESULTS_DIR / f"v4B_oos_{ts}.csv", index=False, encoding="utf-8-sig")
    print(f"\n結果保存: {path.name}")
    print(f"  IS CSV : v4A_trades_{ts}.csv / v4B_trades_{ts}.csv")
    print(f"  OOS CSV: v4A_oos_{ts}.csv / v4B_oos_{ts}.csv  ← 開封厳禁")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
