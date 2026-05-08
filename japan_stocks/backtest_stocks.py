# -*- coding: utf-8 -*-
"""
株式バックテストエンジン — セクター追いつき戦略

戦略ロジック:
  エントリー条件（全て満たす日の引けで買い）
    1. セクター指数が直近 sector_lookback 日で sector_min_rise % 以上上昇
    2. 銘柄がクロスコリレーション分析で「中間株」または「遅行株」に分類
    3. 銘柄の上昇率がセクターより min_gap % 以上低い（乖離あり）

  エグジット条件（いずれか先に発生した日の引けで決済）
    A. 利確: セクター指数との乖離が target_gap_exit % 以下に縮んだ
    B. 損切: 保有株が エントリー価格 × (1 - stop_dist_pct) % を下回った
    C. 時間切れ: max_hold_days 日経過

  ポジションサイジング:
    リスク金額 = 資金 × risk_pct / 100
    株数      = floor(リスク金額 ÷ (エントリー価格 × stop_dist_pct / 100))
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from analyzer import cross_correlation, best_lag, classify as classify_lag

RESULTS_DIR = Path(__file__).parent / "results" / "backtest"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ── 設定 ──────────────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    start_date: str               = "2023-01-01"
    end_date:   Optional[str]     = None

    # 分類
    classification_window:  int   = 252   # 先行/中間/遅行の分類ウィンドウ（営業日）
    reclassify_interval:    int   = 21    # 分類を再計算する間隔（営業日）

    # セクタートレンド判定
    sector_lookback:   int        = 5     # トレンド判定日数
    sector_min_rise:   float      = 2.0   # セクター上昇閾値（%）

    # シグナル条件
    min_gap:           float      = 1.5   # 最低乖離率（%）
    min_corr:          float      = 0.30  # 最低相関係数
    target_classes:    list       = field(default_factory=lambda: ["遅行株", "中間株"])

    # エグジット条件
    target_gap_exit:   float      = 0.5   # 利確乖離閾値（%）
    stop_dist_pct:     float      = 3.0   # ストップロス距離（エントリー比%）
    max_hold_days:     int        = 10    # 最大保有日数

    # 資金管理
    initial_capital:   float      = 1_000_000
    risk_pct:          float      = 1.0   # 1トレードのリスク（資金の%）
    max_positions:     int        = 3

    # DD管理（ドローダウン制限）
    # portfolio_dd_limit_pct > 0 のとき、資金がピークから X% 超下落したら新規エントリー停止
    portfolio_dd_limit_pct: float = 0.0   # 0=無効, 例: 15.0 → 15%超DDで新規停止

    # 売買コスト（往復）
    # スプレッド0.1%×2 + スリッページ0.0% = 0.20%（手数料はゼロ想定）
    round_trip_cost_pct: float    = 0.20


# ── データ構造 ────────────────────────────────────────────────────────────────

@dataclass
class _PendingEntry:
    ticker:           str
    close_price:      float   # 開値なし時のフォールバック
    sector_at_signal: float   # シグナル日のセクター指数


@dataclass
class _Position:
    ticker:           str
    entry_date:       pd.Timestamp
    entry_price:      float
    shares:           int
    stop_price:       float
    sector_at_entry:  float        # エントリー時のセクター指数値
    days_held:        int = 0


@dataclass
class Trade:
    ticker:       str
    sector_name:  str
    entry_date:   pd.Timestamp
    entry_price:  float
    exit_date:    pd.Timestamp
    exit_price:   float
    shares:       int
    exit_reason:  str        # "target" / "stop" / "time" / "end"
    cost_jpy:     float = 0.0  # 往復売買コスト（スプレッド＋スリッページ）

    @property
    def pnl_jpy(self) -> float:
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def net_pnl_jpy(self) -> float:
        return self.pnl_jpy - self.cost_jpy

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price / self.entry_price - 1) * 100


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def _get_close(df: pd.DataFrame) -> pd.Series:
    col = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
    return pd.to_numeric(df[col], errors="coerce")


def _precompute_classifications(
    sector_idx: pd.Series,
    closes:     dict[str, pd.Series],
    window:     int,
    step:       int,
) -> dict[int, dict[str, tuple[str, float]]]:
    """
    毎 step 営業日ごとに銘柄分類を再計算してキャッシュする。
    Returns: {bar_index: {ticker: (classification, corr)}}
    """
    result: dict[int, dict[str, tuple[str, float]]] = {}
    checkpoints = list(range(window, len(sector_idx), step))

    for n, i in enumerate(checkpoints, 1):
        if len(checkpoints) > 4 and n % max(1, len(checkpoints) // 4) == 0:
            print(f"    分類計算 {n}/{len(checkpoints)}...")

        s_win = sector_idx.iloc[i - window: i + 1]
        day:  dict[str, tuple[str, float]] = {}

        for ticker, close in closes.items():
            k_win = close.iloc[i - window: i + 1].dropna()
            if len(k_win) < 60:
                day[ticker] = (None, 0.0)
                continue
            corr_dict = cross_correlation(s_win, k_win)
            lag  = best_lag(corr_dict)
            cls  = classify_lag(lag)
            corr = float(corr_dict.get(lag, 0.0) or 0.0)
            day[ticker] = (cls, corr)

        result[i] = day
    return result


def _latest_classification(
    cache: dict[int, dict[str, tuple[str, float]]],
    bar_idx: int,
) -> dict[str, tuple[str, float]]:
    keys = [k for k in cache if k <= bar_idx]
    return cache[max(keys)] if keys else {}


# ── メインエンジン ─────────────────────────────────────────────────────────────

def run(
    sector_index: pd.Series,
    stocks_df:    dict[str, pd.DataFrame],
    config:       BacktestConfig,
    sector_name:  str = "",
    allowed_entry_dates: set | None = None,
    stocks_opens: dict[str, pd.Series] | None = None,
) -> list[Trade]:
    """
    セクター追いつき戦略のバックテストを実行する。

    Args:
        sector_index: 合成セクター指数 (DatetimeIndex、等加重)
        stocks_df:    {ticker: OHLCV DataFrame (DatetimeIndex)}
        config:       BacktestConfig
        sector_name:  セクター名（レポート用）
        stocks_opens: {ticker: 始値Series}  翌日寄り付きエントリー用

    Returns:
        list[Trade]
    """
    all_dates  = sector_index.index.sort_values()
    sector_idx = sector_index.reindex(all_dates)

    closes: dict[str, pd.Series] = {
        t: _get_close(df).reindex(all_dates)
        for t, df in stocks_df.items()
    }

    opens: dict[str, pd.Series] = {}
    if stocks_opens:
        for t, s in stocks_opens.items():
            opens[t] = pd.to_numeric(s, errors="coerce").reindex(all_dates)

    print(f"  [{sector_name}] 分類事前計算中"
          f"（ウィンドウ={config.classification_window}日、"
          f"更新間隔={config.reclassify_interval}日）...")
    class_cache = _precompute_classifications(
        sector_idx, closes,
        config.classification_window,
        config.reclassify_interval,
    )

    trades:          list[Trade]        = []
    positions:       list[_Position]    = []
    pending_entries: list[_PendingEntry] = []
    capital      = config.initial_capital
    peak_capital = config.initial_capital   # DDチェック用ピーク資金
    lookback     = config.sector_lookback

    for i in range(config.classification_window, len(all_dates)):
        today = all_dates[i]

        # ── 前日シグナルの翌日寄り付きエントリー ──────────────────────────────
        for pending in pending_entries:
            if len(positions) >= config.max_positions:
                break
            t = pending.ticker
            if t in opens and not pd.isna(opens[t].iat[i]):
                entry_price = float(opens[t].iat[i])
            else:
                entry_price = pending.close_price
            if entry_price <= 0:
                continue
            risk_amount   = capital * config.risk_pct / 100
            stop_dist_jpy = entry_price * config.stop_dist_pct / 100
            shares        = int(risk_amount / stop_dist_jpy)
            if shares < 1:
                continue
            positions.append(_Position(
                ticker=t,
                entry_date=today,
                entry_price=entry_price,
                shares=shares,
                stop_price=entry_price * (1 - config.stop_dist_pct / 100),
                sector_at_entry=pending.sector_at_signal,
            ))
        pending_entries = []

        # ── 保有ポジションの決済チェック ──────────────────────────────────────
        still_open: list[_Position] = []
        for pos in positions:
            price_now = closes[pos.ticker].iat[i]
            if pd.isna(price_now):
                still_open.append(pos)
                continue

            pos.days_held += 1
            reason:     Optional[str] = None
            exit_price: float         = float(price_now)

            # ストップロス
            if price_now <= pos.stop_price:
                reason     = "stop"
                exit_price = pos.stop_price

            # 最大保有日数
            elif pos.days_held >= config.max_hold_days:
                reason = "time"

            # 利確: 直近5日間の乖離が縮小
            else:
                sec_now = sector_idx.iat[i]
                if not pd.isna(sec_now) and i >= lookback:
                    sec_5d_ago   = sector_idx.iat[i - lookback]
                    stock_5d_ago = closes[pos.ticker].iat[i - lookback]
                    if (not pd.isna(sec_5d_ago) and not pd.isna(stock_5d_ago)
                            and sec_5d_ago > 0 and stock_5d_ago > 0):
                        sec_chg_5d   = (sec_now   / sec_5d_ago   - 1) * 100
                        stock_chg_5d = (price_now / stock_5d_ago  - 1) * 100
                        if sec_chg_5d - stock_chg_5d <= config.target_gap_exit:
                            reason = "target"

            if reason:
                cost = pos.entry_price * pos.shares * config.round_trip_cost_pct / 100
                t = Trade(
                    ticker=pos.ticker,       sector_name=sector_name,
                    entry_date=pos.entry_date, entry_price=pos.entry_price,
                    exit_date=today,           exit_price=exit_price,
                    shares=pos.shares,         exit_reason=reason,
                    cost_jpy=cost,
                )
                trades.append(t)
                capital += t.net_pnl_jpy
                peak_capital = max(peak_capital, capital)
            else:
                still_open.append(pos)

        positions = still_open

        # ── 新規シグナルチェック ───────────────────────────────────────────────
        # ポートフォリオDDが制限を超えていたら新規エントリー停止
        if (config.portfolio_dd_limit_pct > 0
                and peak_capital > 0
                and capital / peak_capital < 1 - config.portfolio_dd_limit_pct / 100):
            continue

        # 動的セクター選択: この日にこのセクターが選別対象外ならスキップ
        if allowed_entry_dates is not None and today not in allowed_entry_dates:
            continue

        if len(positions) >= config.max_positions or i < lookback:
            continue

        sec_past = sector_idx.iat[i - lookback]
        sec_now  = sector_idx.iat[i]
        if pd.isna(sec_past) or pd.isna(sec_now) or sec_past == 0:
            continue

        sec_change = (sec_now / sec_past - 1) * 100
        if sec_change < config.sector_min_rise:
            continue

        class_today  = _latest_classification(class_cache, i)
        open_tickers = {p.ticker for p in positions}

        candidates: list[tuple[str, float, float]] = []
        for ticker, (cls, corr) in class_today.items():
            if ticker in open_tickers:
                continue
            if cls not in config.target_classes or corr < config.min_corr:
                continue

            past_close = closes[ticker].iat[i - lookback]
            now_close  = closes[ticker].iat[i]
            if pd.isna(past_close) or pd.isna(now_close) or past_close == 0:
                continue

            stock_chg = (now_close / past_close - 1) * 100
            gap       = sec_change - stock_chg
            if gap < config.min_gap:
                continue

            candidates.append((ticker, gap, float(now_close)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        slots = config.max_positions - len(positions)

        # シグナル確定: 翌日寄り付きでエントリーするためpendingに積む
        for ticker, _gap, close_price in candidates[:slots]:
            if close_price <= 0:
                continue
            pending_entries.append(_PendingEntry(
                ticker=ticker,
                close_price=close_price,
                sector_at_signal=float(sec_now),
            ))

    # 残ポジションを最終日に強制決済
    last_date = all_dates[-1]
    last_i    = len(all_dates) - 1
    for pos in positions:
        lc = closes[pos.ticker].iat[last_i]
        if pd.isna(lc):
            continue
        cost = pos.entry_price * pos.shares * config.round_trip_cost_pct / 100
        trades.append(Trade(
            ticker=pos.ticker,       sector_name=sector_name,
            entry_date=pos.entry_date, entry_price=pos.entry_price,
            exit_date=last_date,       exit_price=float(lc),
            shares=pos.shares,         exit_reason="end",
            cost_jpy=cost,
        ))

    return trades


# ── 統計計算 ──────────────────────────────────────────────────────────────────

def compute_stats(trades: list[Trade], initial_capital: float) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "total_pnl_jpy": 0,
            "profit_factor": 0.0, "max_drawdown_pct": 0.0,
            "final_capital": initial_capital,
        }

    # コスト控除後の損益で勝ち負けを判定
    wins   = [t for t in trades if t.net_pnl_jpy > 0]
    losses = [t for t in trades if t.net_pnl_jpy <= 0]

    gross_profit = sum(t.net_pnl_jpy for t in wins)
    gross_loss   = abs(sum(t.net_pnl_jpy for t in losses))
    pf           = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    equity = initial_capital
    peak   = equity
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.exit_date):
        equity += t.net_pnl_jpy
        peak    = max(peak, equity)
        dd      = (peak - equity) / peak * 100
        max_dd  = max(max_dd, dd)

    total_cost = sum(t.cost_jpy for t in trades)

    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

    hold_days = [(t.exit_date - t.entry_date).days for t in trades]

    return {
        "total_trades":     len(trades),
        "win_rate":         round(len(wins) / len(trades) * 100, 1),
        "total_pnl_jpy":    round(sum(t.net_pnl_jpy for t in trades)),
        "total_cost_jpy":   round(total_cost),
        "avg_win_jpy":      round(gross_profit / len(wins))   if wins   else 0,
        "avg_loss_jpy":     round(-gross_loss  / len(losses)) if losses else 0,
        "profit_factor":    round(pf, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "final_capital":    round(initial_capital + sum(t.net_pnl_jpy for t in trades)),
        "exit_reasons":     reasons,
        "avg_hold_days":    round(sum(hold_days) / len(hold_days), 1) if hold_days else 0,
    }


def split_is_oos(trades: list[Trade], is_end_date: str) -> tuple[list[Trade], list[Trade]]:
    """
    トレードをIS（インサンプル）とOOS（アウトオブサンプル）に分割する。
    is_end_date: ISの最終日（YYYY-MM-DD）。それ以降のエントリーがOOS。
    """
    cutoff = pd.Timestamp(is_end_date)
    is_trades  = [t for t in trades if t.entry_date <= cutoff]
    oos_trades = [t for t in trades if t.entry_date >  cutoff]
    return is_trades, oos_trades


# ── レポート保存 ───────────────────────────────────────────────────────────────

def save_report(
    trades:      list[Trade],
    stats:       dict,
    config:      BacktestConfig,
    path:        Path,
    sector_name: str = "",
    is_end_date: str | None = None,
) -> None:
    exit_label = {
        "target": "利確（追いつき）",
        "stop":   "ストップロス",
        "time":   "時間切れ",
        "end":    "期間終了強制",
    }

    def _stats_rows(s: dict) -> list[str]:
        return [
            f"| 総トレード数 | {s['total_trades']} |",
            f"| 勝率 | {s['win_rate']}% |",
            f"| 損益合計 | {s['total_pnl_jpy']:+,.0f}円 |",
            f"| 平均利益 | {s.get('avg_win_jpy', 0):+,.0f}円 |",
            f"| 平均損失 | {s.get('avg_loss_jpy', 0):,.0f}円 |",
            f"| PF | {s['profit_factor']} |",
            f"| 最大DD | {s['max_drawdown_pct']}% |",
            f"| 最終資金 | {s['final_capital']:,.0f}円 |",
            f"| 平均保有日数 | {s.get('avg_hold_days', 0)}日 |",
        ]

    lines = [
        f"# 株式バックテスト — セクター追いつき戦略\n",
        f"セクター: {sector_name or '全セクター'}  "
        f"期間: {config.start_date} 〜 {config.end_date or '現在'}\n",
        "---\n",
        "## 設定パラメータ\n",
        "| パラメータ | 値 |",
        "|-----------|-----|",
        f"| セクター上昇閾値 | {config.sector_min_rise}%（{config.sector_lookback}日） |",
        f"| 最低乖離率 | {config.min_gap}% |",
        f"| 利確乖離閾値 | {config.target_gap_exit}% |",
        f"| ストップロス距離 | {config.stop_dist_pct}% |",
        f"| 最大保有日数 | {config.max_hold_days}日 |",
        f"| 初期資金 | {config.initial_capital:,.0f}円 |",
        f"| 1トレードリスク | {config.risk_pct}%（={config.initial_capital * config.risk_pct / 100:,.0f}円） |",
        "",
        "## 全期間 集計結果\n",
        "| 指標 | 値 |",
        "|------|-----|",
    ] + _stats_rows(stats) + [""]

    # IS/OOS比較テーブル
    if is_end_date and trades:
        is_t, oos_t = split_is_oos(trades, is_end_date)
        is_s  = compute_stats(is_t,  config.initial_capital)
        oos_s = compute_stats(oos_t, config.initial_capital)

        lines += [
            f"## IS / OOS 比較\n",
            f"IS期間（学習）: {config.start_date} 〜 {is_end_date}  "
            f"OOS期間（検証）: {is_end_date} 〜 {config.end_date or '現在'}\n",
            "| 指標 | IS（学習） | OOS（検証） | 判定 |",
            "|------|-----------|------------|------|",
        ]
        metrics = [
            ("総トレード数", "total_trades",     lambda a, b: ""),
            ("勝率",         "win_rate",         lambda a, b: "✅" if b >= a * 0.9 else "⚠️"),
            ("損益（円）",   "total_pnl_jpy",    lambda a, b: "✅" if b > 0 else "❌"),
            ("PF",           "profit_factor",    lambda a, b: "✅" if b >= 1.2 else ("⚠️" if b >= 1.0 else "❌")),
            ("最大DD",       "max_drawdown_pct", lambda a, b: "✅" if b <= a * 1.5 else "⚠️"),
            ("平均保有日数", "avg_hold_days",     lambda a, b: ""),
        ]
        for label, key, judge in metrics:
            iv = is_s.get(key, 0)
            ov = oos_s.get(key, 0)
            jd = judge(iv, ov)
            fmt = "{:+,.0f}" if "損益" in label else ("{:.1f}" if isinstance(iv, float) else "{}")
            lines.append(f"| {label} | {fmt.format(iv)} | {fmt.format(ov)} | {jd} |")
        lines.append("")

        lines += [
            "### IS決済理由\n", "| 理由 | 件数 |", "|------|------|"
        ]
        for r, c in is_s.get("exit_reasons", {}).items():
            lines.append(f"| {exit_label.get(r, r)} | {c} |")
        lines += [
            "", "### OOS決済理由\n", "| 理由 | 件数 |", "|------|------|"
        ]
        for r, c in oos_s.get("exit_reasons", {}).items():
            lines.append(f"| {exit_label.get(r, r)} | {c} |")
        lines.append("")

    elif stats.get("exit_reasons"):
        lines += ["### 決済理由\n", "| 理由 | 件数 |", "|------|------|"]
        for reason, cnt in stats["exit_reasons"].items():
            lines.append(f"| {exit_label.get(reason, reason)} | {cnt} |")
        lines.append("")

    if trades:
        lines += [
            "## トレード一覧\n",
            "| # | 区分 | セクター | 銘柄 | エントリー日 | 単価 | 決済日 | 単価 | 株数 | 損益（円） | 理由 |",
            "|---|------|---------|------|------------|------|-------|------|------|-----------|------|",
        ]
        cutoff = pd.Timestamp(is_end_date) if is_end_date else None
        for n, t in enumerate(sorted(trades, key=lambda x: x.entry_date), 1):
            zone = "IS" if (cutoff and t.entry_date <= cutoff) else "OOS"
            lines.append(
                f"| {n} | {zone} | {t.sector_name} | {t.ticker} "
                f"| {t.entry_date.date()} | {t.entry_price:.1f} "
                f"| {t.exit_date.date()} | {t.exit_price:.1f} "
                f"| {t.shares} | {t.pnl_jpy:+,.0f} "
                f"| {exit_label.get(t.exit_reason, t.exit_reason)} |"
            )

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  レポート保存: {path.name}")


# ── クロスセクター版 ─────────────────────────────────────────────────────────

@dataclass
class _PositionCS:
    ticker:          str
    sector:          str
    entry_date:      pd.Timestamp
    entry_price:     float
    shares:          int
    stop_price:      float
    sector_at_entry: float
    days_held:       int = 0


@dataclass
class _PendingEntryCS:
    ticker:           str
    sector:           str
    close_price:      float
    sector_at_signal: float
    gap_at_signal:    float


def _gap_cs(sec_idx: pd.Series, stock_close: pd.Series, i: int, lookback: int) -> float:
    """bar i 時点のセクター-銘柄 5日乖離率"""
    try:
        sn = float(sec_idx.iat[i]);     sp = float(sec_idx.iat[i - lookback])
        cn = float(stock_close.iat[i]); cp = float(stock_close.iat[i - lookback])
        if any(pd.isna(v) for v in (sn, sp, cn, cp)) or sp <= 0 or cp <= 0:
            return -999.0
        return (sn/sp - 1)*100 - (cn/cp - 1)*100
    except Exception:
        return -999.0


def run_cross_sector(
    sector_indices:      dict[str, pd.Series],
    sector_stocks_all:   dict[str, dict[str, pd.DataFrame]],
    sector_opens_all:    dict[str, dict[str, pd.Series]],
    active_sector_dates: dict[str, set],
    class_caches:        dict[str, dict],
    unified_dates:       "list[pd.Timestamp]",
    config:              BacktestConfig,
) -> "list[Trade]":
    """
    クロスセクター共有資本プール版バックテスト。
    全セクターで MAX_POSITIONS を共有し、乖離率比較によるポジション回転を行う。
    """
    # 各セクターの系列をunified_datesにリインデックス
    sec_aligned:    dict[str, pd.Series]              = {}
    closes_aligned: dict[str, dict[str, pd.Series]]   = {}
    opens_aligned:  dict[str, dict[str, pd.Series]]   = {}

    for name, idx in sector_indices.items():
        sec_aligned[name] = idx.reindex(unified_dates)

    for name, stocks in sector_stocks_all.items():
        closes_aligned[name] = {}
        for ticker, df in stocks.items():
            col = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
            closes_aligned[name][ticker] = (
                pd.to_numeric(df[col], errors="coerce").reindex(unified_dates)
            )

    for name, opens in sector_opens_all.items():
        opens_aligned[name] = {}
        for ticker, s in opens.items():
            opens_aligned[name][ticker] = (
                pd.to_numeric(s, errors="coerce").reindex(unified_dates)
            )

    trades:   list[Trade]          = []
    positions: list[_PositionCS]   = []
    pending:   list[_PendingEntryCS] = []
    capital      = config.initial_capital
    peak_capital = config.initial_capital
    lookback     = config.sector_lookback
    n            = len(unified_dates)

    for i in range(config.classification_window, n):
        today = unified_dates[i]

        # ── Step 1: pending → 今日の寄りでエントリー ────────────────────────
        new_pending: list[_PendingEntryCS] = []
        for pend in pending:
            if len(positions) >= config.max_positions:
                new_pending.append(pend)
                continue
            op_s = opens_aligned.get(pend.sector, {}).get(pend.ticker)
            if op_s is not None and not pd.isna(op_s.iat[i]):
                ep = float(op_s.iat[i])
            else:
                ep = pend.close_price
            if ep <= 0:
                continue
            risk    = capital * config.risk_pct / 100
            sd_jpy  = ep * config.stop_dist_pct / 100
            shares  = int(risk / sd_jpy)
            if shares < 1:
                continue
            positions.append(_PositionCS(
                ticker=pend.ticker, sector=pend.sector,
                entry_date=today, entry_price=ep, shares=shares,
                stop_price=ep * (1 - config.stop_dist_pct / 100),
                sector_at_entry=pend.sector_at_signal,
            ))
        pending = new_pending

        # ── Step 2: 保有ポジション決済チェック ──────────────────────────────
        still_open: list[_PositionCS] = []
        for pos in positions:
            cs = closes_aligned.get(pos.sector, {}).get(pos.ticker)
            if cs is None or pd.isna(cs.iat[i]):
                still_open.append(pos); continue
            price_now = float(cs.iat[i])
            pos.days_held += 1
            reason     = None
            exit_price = price_now

            if price_now <= pos.stop_price:
                reason = "stop"; exit_price = pos.stop_price
            elif pos.days_held >= config.max_hold_days:
                reason = "time"
            elif i >= lookback:
                si2   = sec_aligned[pos.sector]
                sn    = float(si2.iat[i])
                sp2   = float(si2.iat[i - lookback])
                stk_p = float(cs.iat[i - lookback])
                if (not pd.isna(sp2) and not pd.isna(stk_p)
                        and sp2 > 0 and stk_p > 0):
                    if ((sn/sp2 - 1)*100 - (price_now/stk_p - 1)*100
                            <= config.target_gap_exit):
                        reason = "target"

            if reason:
                cost = pos.entry_price * pos.shares * config.round_trip_cost_pct / 100
                t = Trade(
                    ticker=pos.ticker, sector_name=pos.sector,
                    entry_date=pos.entry_date, entry_price=pos.entry_price,
                    exit_date=today, exit_price=exit_price,
                    shares=pos.shares, exit_reason=reason, cost_jpy=cost,
                )
                trades.append(t)
                capital += t.net_pnl_jpy
                peak_capital = max(peak_capital, capital)
            else:
                still_open.append(pos)
        positions = still_open

        # ── DD制限 ──────────────────────────────────────────────────────────
        if (config.portfolio_dd_limit_pct > 0 and peak_capital > 0
                and capital / peak_capital < 1 - config.portfolio_dd_limit_pct / 100):
            continue
        if i < lookback:
            continue

        # ── Step 3: 全アクティブセクターからシグナル収集 ────────────────────
        open_tickers    = {p.ticker for p in positions}
        pending_tickers = {p.ticker for p in pending}

        all_cands: list[dict] = []
        for name, si2 in sec_aligned.items():
            if today not in (active_sector_dates.get(name) or set()):
                continue
            sn = si2.iat[i]; sp2 = si2.iat[i - lookback]
            if pd.isna(sn) or pd.isna(sp2) or sp2 <= 0:
                continue
            sec_chg = (sn / sp2 - 1) * 100
            if sec_chg < config.sector_min_rise:
                continue
            cache      = class_caches.get(name, {})
            cls_today  = _latest_classification(cache, i) if cache else {}
            for ticker, cs2 in closes_aligned.get(name, {}).items():
                if ticker in open_tickers or ticker in pending_tickers:
                    continue
                cls, corr = cls_today.get(ticker, (None, 0.0))
                if cls not in config.target_classes or corr < config.min_corr:
                    continue
                cn2 = cs2.iat[i]; cp2 = cs2.iat[i - lookback]
                if pd.isna(cn2) or pd.isna(cp2) or cp2 <= 0:
                    continue
                gap = sec_chg - (cn2 / cp2 - 1) * 100
                if gap < config.min_gap:
                    continue
                all_cands.append(dict(
                    ticker=ticker, sector=name, gap=gap,
                    close=float(cn2), sec_now=float(sn),
                ))

        all_cands.sort(key=lambda x: x["gap"], reverse=True)

        # ── スロットを埋める ─────────────────────────────────────────────────
        slots = config.max_positions - len(positions) - len(pending)
        added_tickers: set[str] = set()
        for cand in all_cands[:slots]:
            if cand["ticker"] not in pending_tickers and cand["ticker"] not in added_tickers:
                pending.append(_PendingEntryCS(
                    ticker=cand["ticker"], sector=cand["sector"],
                    close_price=cand["close"], sector_at_signal=cand["sec_now"],
                    gap_at_signal=cand["gap"],
                ))
                added_tickers.add(cand["ticker"])

        # ── 回転候補チェック ─────────────────────────────────────────────────
        remaining = [c for c in all_cands[slots:] if c["ticker"] not in pending_tickers]
        if remaining and positions:
            pos_gaps = sorted(
                [
                    (pos, _gap_cs(
                        sec_aligned[pos.sector],
                        closes_aligned[pos.sector][pos.ticker],
                        i, lookback,
                    ))
                    for pos in positions
                    if pos.ticker in closes_aligned.get(pos.sector, {})
                ],
                key=lambda x: x[1],
            )
            pending_tickers2 = {p.ticker for p in pending}
            for cand in remaining:
                if not pos_gaps:
                    break
                weakest_pos, weakest_gap = pos_gaps[0]
                if cand["gap"] <= weakest_gap:
                    break  # sorted descending by cand gap, no point continuing
                if cand["ticker"] in pending_tickers2:
                    continue
                cs2 = closes_aligned.get(weakest_pos.sector, {}).get(weakest_pos.ticker)
                if cs2 is None or pd.isna(cs2.iat[i]):
                    pos_gaps.pop(0); continue
                ep_rot = float(cs2.iat[i])
                cost   = weakest_pos.entry_price * weakest_pos.shares * config.round_trip_cost_pct / 100
                t = Trade(
                    ticker=weakest_pos.ticker, sector_name=weakest_pos.sector,
                    entry_date=weakest_pos.entry_date, entry_price=weakest_pos.entry_price,
                    exit_date=today, exit_price=ep_rot,
                    shares=weakest_pos.shares, exit_reason="rotate", cost_jpy=cost,
                )
                trades.append(t)
                capital += t.net_pnl_jpy
                peak_capital = max(peak_capital, capital)
                positions.remove(weakest_pos)
                pos_gaps.pop(0)
                pending.append(_PendingEntryCS(
                    ticker=cand["ticker"], sector=cand["sector"],
                    close_price=cand["close"], sector_at_signal=cand["sec_now"],
                    gap_at_signal=cand["gap"],
                ))
                pending_tickers2.add(cand["ticker"])

    # ── 最終日強制決済 ──────────────────────────────────────────────────────────
    last_i, last_date = n - 1, unified_dates[-1]
    for pos in positions:
        cs = closes_aligned.get(pos.sector, {}).get(pos.ticker)
        if cs is None: continue
        lc = cs.iat[last_i]
        if pd.isna(lc): continue
        cost = pos.entry_price * pos.shares * config.round_trip_cost_pct / 100
        trades.append(Trade(
            ticker=pos.ticker, sector_name=pos.sector,
            entry_date=pos.entry_date, entry_price=pos.entry_price,
            exit_date=last_date, exit_price=float(lc),
            shares=pos.shares, exit_reason="end", cost_jpy=cost,
        ))
    return trades
