# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート バックテスト v3
実行: python japan_stocks/backtest_minervini_v3.py

v2からの改善点:
  エントリー: 20日高値ブレイク → ベースブレイク後エントリー
              直近N日がタイトなレンジ（保ち合い）を形成したことを確認後、
              レンジ上限をブレイクした日にエントリー
  損切り    : -7%固定 → ベース安値（レンジ下限）を割ったら決済
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

DATA_START      = "2022-01-01"
BACKTEST_START  = "2023-04-01"
NIKKEI_TICKER   = "^N225"
MARKET          = "prime"
WORKERS         = 30
MAX_HOLD_DAYS   = 126        # 最大保有6ヶ月

# ベース定義パラメータ
BASE_LOOKBACK   = 30         # ベースを探す直近日数（約6週間）
BASE_MIN_DAYS   = 15         # ベースと認定する最低日数
MAX_BASE_RANGE  = 0.20       # ベース高値/安値の最大レンジ（20%以内）


# ── ベース検出 ────────────────────────────────────────────────────────────────

def detect_base(close: pd.Series, idx: int) -> dict | None:
    """
    idx日時点でのベース（保ち合い）を検出する。
    未来データ漏れなし：idx-1までのデータのみ使用。

    Returns: {"base_high", "base_low", "range_pct"} or None（ベースなし）
    """
    if idx < BASE_LOOKBACK + 1:
        return None

    # idx日の1日前からBASE_LOOKBACK日分を参照
    window = close.iloc[idx - BASE_LOOKBACK: idx]  # idx含まず

    if len(window) < BASE_MIN_DAYS:
        return None

    base_high = float(window.max())
    base_low  = float(window.min())
    range_pct = (base_high / base_low) - 1

    if range_pct > MAX_BASE_RANGE:
        return None  # レンジが広すぎてベースではない

    return {
        "base_high" : base_high,
        "base_low"  : base_low,
        "range_pct" : range_pct,
    }


# ── シグナル計算（ベクトル化）────────────────────────────────────────────────

def build_8cond_series(close: pd.Series, n225: pd.Series,
                       n225_ma200: pd.Series) -> pd.Series:
    """
    8条件 + RS(日経対比) + 市場フィルター をすべてTrueの日付Seriesで返す。
    （ブレイクアウトとベース条件はシミュレーションループ内で別途チェック）
    """
    n225_aln     = n225.reindex(close.index, method="ffill")
    n225_ma200_a = n225_ma200.reindex(close.index, method="ffill")

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

    market_bull = n225_aln > n225_ma200_a

    return c1 & c2 & c3 & c4 & c5 & c6 & c7 & c8 & market_bull


# ── トレードシミュレーション ──────────────────────────────────────────────────

def simulate_trades(ticker: str, close: pd.Series,
                    cond8: pd.Series) -> list[dict]:
    """
    ベースブレイク後エントリー、ベース安値割れ損切り。
    """
    trades   = []
    in_trade = False
    entry_px = 0.0
    stop_px  = 0.0
    entry_dt = None
    start_ts = pd.Timestamp(BACKTEST_START)

    close_vals = close.values
    idx_map    = {ts: i for i, ts in enumerate(close.index)}

    for i, (ts, c8_ok) in enumerate(cond8.items()):
        if ts < start_ts:
            continue

        cur_px = close_vals[i]

        # ── ポジション保有中 ─────────────────────────────────────────────
        if in_trade:
            hold = (ts - entry_dt).days

            # ベース安値割れ → 損切り
            if cur_px < stop_px:
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, ts,
                                   entry_px, cur_px, ret, "stop_base",
                                   stop_px, hold))
                in_trade = False
                continue

            # 最大保有到達 → 決済
            if hold >= MAX_HOLD_DAYS:
                ret = (cur_px / entry_px - 1) * 100
                trades.append(_rec(ticker, entry_dt, ts,
                                   entry_px, cur_px, ret, "time",
                                   stop_px, hold))
                in_trade = False
                continue

        # ── エントリー判定 ────────────────────────────────────────────────
        else:
            if not c8_ok:
                continue

            base = detect_base(close, i)
            if base is None:
                continue  # ベースが形成されていない

            # ベース高値ブレイクアウト確認（当日終値 > ベース高値）
            if cur_px <= base["base_high"]:
                continue  # まだブレイクアウトしていない

            in_trade = True
            entry_px = cur_px
            stop_px  = base["base_low"]    # ベース安値を損切ラインに設定
            entry_dt = ts

    return trades


def _rec(ticker, entry_dt, exit_dt, entry_px, exit_px,
         ret, reason, stop_px, hold):
    stop_dist = (stop_px / entry_px - 1) * 100
    return {
        "ticker"    : ticker,
        "entry_date": entry_dt.strftime("%Y-%m-%d"),
        "exit_date" : exit_dt.strftime("%Y-%m-%d"),
        "entry_px"  : round(entry_px, 1),
        "exit_px"   : round(exit_px, 1),
        "stop_px"   : round(stop_px, 1),
        "stop_dist" : round(stop_dist, 1),   # 損切幅（%）
        "ret_pct"   : round(ret, 2),
        "reason"    : reason,
        "hold_days" : hold,
    }


# ── 集計・表示 ────────────────────────────────────────────────────────────────

def _pf(ret: pd.Series) -> float:
    w = ret[ret > 0].sum()
    l = abs(ret[ret < 0].sum())
    return round(w / l, 2) if l > 0 else float("inf")


def print_stats(df: pd.DataFrame, label: str = "v3"):
    print(f"\n{'='*65}")
    print(f"  バックテスト {label}  集計結果")
    print(f"{'='*65}")

    if df.empty:
        print("  トレードなし")
        return

    ret = df["ret_pct"]
    print(f"\n  総トレード数    : {len(df)}")
    print(f"  平均リターン    : {ret.mean():+.2f}%")
    print(f"  中央値          : {ret.median():+.2f}%")
    print(f"  勝率            : {(ret > 0).mean()*100:.1f}%")
    print(f"  損切り発生率    : {(df['reason']=='stop_base').mean()*100:.1f}%")
    print(f"  平均損切幅      : {df['stop_dist'].mean():.1f}%")
    print(f"  平均保有日数    : {df['hold_days'].mean():.1f}日")
    print(f"  最大利益        : {ret.max():+.2f}%")
    print(f"  最大損失        : {ret.min():+.2f}%")
    print(f"  PF              : {_pf(ret):.2f}")

    # 年別
    df["year"] = pd.to_datetime(df["entry_date"]).dt.year
    print(f"\n  {'年':<6}{'件数':>6}{'平均':>10}{'勝率':>8}{'PF':>6}{'損切り率':>10}{'avg損切幅':>10}")
    for yr, g in df.groupby("year"):
        r = g["ret_pct"]
        print(f"  {yr:<6}{len(g):>6}  {r.mean():>+7.2f}%  "
              f"{(r>0).mean()*100:>5.0f}%  {_pf(r):>4.2f}  "
              f"{(g['reason']=='stop_base').mean()*100:>7.1f}%  "
              f"{g['stop_dist'].mean():>7.1f}%")

    # v2との比較コメント
    print(f"\n  【v2との比較】")
    print(f"  v2: PF1.71  勝率40.3%  損切り率55.7%  平均損切幅-7%(固定)")
    print(f"  v3: PF{_pf(ret):.2f}  "
          f"勝率{(ret>0).mean()*100:.1f}%  "
          f"損切り率{(df['reason']=='stop_base').mean()*100:.1f}%  "
          f"平均損切幅{df['stop_dist'].mean():.1f}%（動的）")

    # 決済理由別
    print(f"\n  {'決済理由':<12}{'件数':>6}{'平均':>10}{'勝率':>8}")
    for reason, g in df.groupby("reason"):
        r = g["ret_pct"]
        label_r = "ベース割れ損切" if reason == "stop_base" else "期間満了"
        print(f"  {label_r:<12}{len(g):>6}  {r.mean():>+7.2f}%  "
              f"{(r>0).mean()*100:>5.0f}%")


def save_report(df: pd.DataFrame, run_time: str, path: Path):
    if df.empty:
        path.write_text("トレードなし\n", encoding="utf-8")
        return

    ret = df["ret_pct"]
    df["year"] = pd.to_datetime(df["entry_date"]).dt.year

    lines = [
        "# ミネルヴィニ バックテスト v3 結果\n",
        f"実行日時: {run_time}  \n",
        f"検証期間: {df['entry_date'].min()} ～ {df['entry_date'].max()}  \n",
        f"対象市場: 東証プライム  \n",
        f"ベース定義: 直近{BASE_LOOKBACK}日・レンジ{MAX_BASE_RANGE*100:.0f}%以内  \n",
        "---\n",
        "## v2からの改善点\n",
        f"- エントリー: 20日高値ブレイク → ベース（直近{BASE_LOOKBACK}日・レンジ≤{MAX_BASE_RANGE*100:.0f}%）ブレイク",
        "- 損切り: -7%固定 → ベース安値割れ（動的）\n",
        "---\n",
        "## 全体サマリー\n",
        "| 指標 | v2 | v3 |",
        "|------|-----|-----|",
        f"| 総トレード数 | 4,198 | {len(df)} |",
        f"| 平均リターン | +3.69% | {ret.mean():+.2f}% |",
        f"| 中央値 | -7.15% | {ret.median():+.2f}% |",
        f"| 勝率 | 40.3% | {(ret>0).mean()*100:.1f}% |",
        f"| 損切り率 | 55.7% | {(df['reason']=='stop_base').mean()*100:.1f}% |",
        f"| 平均損切幅 | -7.0%（固定） | {df['stop_dist'].mean():.1f}%（動的） |",
        f"| PF | 1.71 | {_pf(ret):.2f} |\n",
        "## 年別内訳\n",
        "| 年 | 件数 | 平均リターン | 勝率 | PF | 損切り率 | avg損切幅 |",
        "|-----|------|------------|------|-----|---------|---------|",
    ]

    for yr, g in df.groupby("year"):
        r = g["ret_pct"]
        lines.append(
            f"| {yr} | {len(g)} | {r.mean():+.2f}% "
            f"| {(r>0).mean()*100:.0f}% | {_pf(r):.2f} "
            f"| {(g['reason']=='stop_base').mean()*100:.1f}% "
            f"| {g['stop_dist'].mean():.1f}% |"
        )

    lines += [
        "\n## 上位トレード（リターン順）\n",
        "| 銘柄 | エントリー | 決済 | リターン | 損切ライン | 保有日数 | 理由 |",
        "|------|-----------|------|---------|-----------|---------|------|",
    ]
    for _, r in df.nlargest(30, "ret_pct").iterrows():
        lines.append(
            f"| {r['ticker']} | {r['entry_date']} | {r['exit_date']} "
            f"| {r['ret_pct']:+.1f}% | {r['stop_dist']:.1f}% "
            f"| {r['hold_days']}日 | {'ベース割れ' if r['reason']=='stop_base' else '期間'} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*65}")
    print(f"  ミネルヴィニ バックテスト v3")
    print(f"  実行日時: {run_time}")
    print(f"  エントリー: ベースブレイク後（直近{BASE_LOOKBACK}日・レンジ≤{MAX_BASE_RANGE*100:.0f}%）")
    print(f"  損切り    : ベース安値割れ（動的）")
    print(f"  最大保有  : {MAX_HOLD_DAYS}日")
    print(f"{'='*65}\n")

    # ── 日経225 ──────────────────────────────────────────────────────────
    print("日経225取得中...")
    n225_df    = dt.fetch(NIKKEI_TICKER, start=DATA_START)
    n225       = n225_df["Close"]
    n225_ma200 = n225.rolling(200).mean()

    # ── 全銘柄取得 ────────────────────────────────────────────────────────
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

    # ── シグナル計算 + シミュレーション ──────────────────────────────────
    print("ベース検出 + トレードシミュレーション中...")
    all_trades = []

    for i, (ticker, close) in enumerate(all_closes.items()):
        if i % 300 == 0:
            print(f"  {i}/{len(all_closes)} 銘柄...", end="\r")
        try:
            cond8  = build_8cond_series(close, n225, n225_ma200)
            trades = simulate_trades(ticker, close, cond8)
            all_trades.extend(trades)
        except Exception:
            pass

    print(f"\n  完了: {len(all_trades)} トレード検出\n")

    if not all_trades:
        print("トレードなし。ベースのパラメータを調整してください。")
        return

    df = pd.DataFrame(all_trades)
    print_stats(df, "v3")

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"backtest_v3_{ts}.md"
    save_report(df, run_time, path)
    print(f"\n結果保存: {path.name}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
