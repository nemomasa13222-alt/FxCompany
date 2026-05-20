# -*- coding: utf-8 -*-
"""バックテストエンジン：データ読み込み・走査・統計計算"""

from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np


# ── データ読み込み ────────────────────────────────────────────────────────

def load_data(data_dir: Path) -> pd.DataFrame:
    """USDJPYフォルダのXLSファイルを結合して読み込む"""
    files = sorted(data_dir.glob("*.xls"))
    if not files:
        raise FileNotFoundError(f"XLSファイルが見つかりません: {data_dir}")

    frames = []
    for f in files:
        df = pd.read_csv(str(f), header=None, encoding="utf-8", sep="\t",
                         names=["date", "time", "open", "high", "low", "close", "volume"])
        frames.append(df)

    data = pd.concat(frames, ignore_index=True)
    data["datetime"] = pd.to_datetime(data["date"].astype(str) + " " + data["time"].astype(str),
                                      format="%Y.%m.%d %H:%M")
    data = data.drop(columns=["date", "time"])
    data = data.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

    for col in ["open", "high", "low", "close"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0)

    return data


def filter_period(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df["datetime"] >= pd.Timestamp(start)]
    if end:
        df = df[df["datetime"] <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
    return df.reset_index(drop=True)


# ── バックテストループ ────────────────────────────────────────────────────

def run(df: pd.DataFrame, entry_fn, exit_fn, cfg) -> list[dict]:
    """
    1分足を1本ずつ走査してトレードを実行する。

    スプレッド処理:
        買い: エントリー = close + spread_price  決済 = close
        売り: エントリー = close                  決済 = close + spread_price
    → どちらも1スプレッド分のコストを負担する
    """
    spread_price = cfg.SPREAD_PIPS * 0.01
    lookback     = cfg.LOOKBACK
    max_pos      = cfg.MAX_POSITIONS
    lots         = cfg.LOTS

    positions: list[dict] = []
    trades:    list[dict] = []
    trade_no = 1

    for i in range(lookback, len(df)):
        candles = df.iloc[i - lookback: i + 1].copy()
        current = df.iloc[i]

        # ── エグジット判定 ──────────────────────────────────────────
        remaining = []
        for pos in positions:
            if exit_fn(candles, pos):
                exit_close = current["close"]
                if pos["side"] == "buy":
                    exit_price = exit_close
                    pips = (exit_price - pos["entry_price"]) * 100
                else:
                    exit_price = exit_close + spread_price
                    pips = (pos["entry_price"] - exit_price) * 100

                pnl_jpy = round(pips * lots * 100, 0)
                result  = "win" if pips > 0 else "loss" if pips < 0 else "even"

                trades.append({
                    "trade_no"    : trade_no,
                    "side"        : pos["side"],
                    "entry_time"  : pos["entry_time"],
                    "entry_price" : round(pos["entry_price"], 5),
                    "exit_time"   : current["datetime"],
                    "exit_price"  : round(exit_price, 5),
                    "pips"        : round(pips, 1),
                    "pnl_jpy"     : int(pnl_jpy),
                    "result"      : result,
                })
                trade_no += 1
            else:
                remaining.append(pos)
        positions = remaining

        # ── エントリー判定 ─────────────────────────────────────────
        if len(positions) < max_pos:
            should_enter, side = entry_fn(candles)
            if should_enter and side in ("buy", "sell"):
                if side == "buy":
                    entry_price = current["close"] + spread_price
                else:
                    entry_price = current["close"]

                positions.append({
                    "side"        : side,
                    "entry_price" : entry_price,
                    "entry_time"  : current["datetime"],
                    "lots"        : lots,
                })

    return trades


# ── 統計計算 ──────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict], n: int | None = None) -> dict:
    """
    trades の先頭 n 件で統計を計算する。
    n=None の場合は全件。
    """
    subset = trades[:n] if n is not None else trades
    if not subset:
        return {"count": 0, "win_rate": None, "expectancy": None,
                "pf": None, "max_dd_pips": None}

    pips_list = [t["pips"] for t in subset]
    wins      = [p for p in pips_list if p > 0]
    losses    = [p for p in pips_list if p < 0]

    win_rate   = len(wins) / len(pips_list)
    expectancy = sum(pips_list) / len(pips_list)
    gp = sum(wins)   if wins   else 0.0
    gl = abs(sum(losses)) if losses else 0.0
    pf = gp / gl if gl > 0 else float("inf")

    # 累積pipsベースの最大ドローダウン
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pips_list:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    return {
        "count"      : len(subset),
        "win_rate"   : win_rate,
        "expectancy" : expectancy,
        "pf"         : pf,
        "max_dd_pips": -max_dd,
    }


def compute_checkpoints(trades: list[dict], checkpoints: list[int]) -> list[dict]:
    """各チェックポイント時点の統計を返す"""
    results = []
    for n in checkpoints:
        if n > len(trades):
            break
        stats = compute_stats(trades, n)
        stats["checkpoint"] = n
        results.append(stats)
    # 全件も追加（チェックポイントと重複しない場合）
    total = len(trades)
    if total not in checkpoints and total > 0:
        stats = compute_stats(trades)
        stats["checkpoint"] = total
        results.append(stats)
    return results


def verdict(trades: list[dict], threshold: int) -> str:
    n = len(trades)
    if n < threshold:
        return f"検証不足（{n}回 < {threshold}回）"
    stats = compute_stats(trades)
    if stats["expectancy"] is None:
        return "判定不能（トレードなし）"
    if stats["expectancy"] > 0 and stats["pf"] > 1.0:
        return "実運用検討可能（期待値プラス・PF>1）"
    if stats["expectancy"] > 0:
        return "条件再検討（期待値プラスだがPF低い）"
    return "条件見直し推奨（期待値マイナス）"
