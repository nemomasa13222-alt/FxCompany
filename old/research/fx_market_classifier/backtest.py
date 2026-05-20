"""
Event-driven backtest engine v2 — bar-by-bar, single position.

Entry rules
-----------
TOP-1 selection:
  At each bar, only the pair with the largest |strength_diff| is eligible for entry.
  Only 1 position open at a time across all pairs.

TREND:
  - Enter on BB 1σ breakout in strength direction.

MEAN_REVERSION:
  - Enter on BB 3σ touch (oversold/overbought).

Exit rules
----------
TREND:
  1. BB 3σ hit in trade direction  → 50% partial profit
  2. Stop loss hit (1σ below/above entry) → close all
  3. State leaves TREND → close remaining

MEAN_REVERSION:
  1. BB 2σ (same side as entry) reached → close all (profit target)
  2. Stop loss hit (1σ beyond entry, i.e. 4σ level) → close all
  3. State leaves MEAN_REVERSION → close all

Position sizing  (PDF p.5 formula adapted for FX)
--------------------------------------------------
  stop_dist_price  = bb_std at entry  (= 1σ in price units)
  risk_amount      = capital × risk_pct / 100
  position_size    = risk_amount / stop_dist_price     [units of base ccy]
  position_notional= position_size × entry_price       [in capital ccy]
  position_ratio   = risk_pct / stop_dist_pct          [× capital]

  pnl_capital_pct  = position_ratio × price_return_pct
  Max loss per trade = risk_pct % of capital (when stop hits exactly)

Simplifications (research-grade)
---------------------------------
  - PnL expressed as % of capital (position_ratio applied)
  - No overnight swap / margin call
  - Executes at bar close (no intrabar detail)
  - Spread cost applied at entry and exit
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from .classifier import MarketClassifier, MarketState
from .config import BB_REVERSION_SIGMA, BB_TREND_SIGMA, BB_WINDOW, SPREAD_PCT
from .features import bollinger_bands


class Direction(str, Enum):
    LONG  = "LONG"
    SHORT = "SHORT"


@dataclass
class Trade:
    pair:          str
    strategy:      MarketState
    direction:     Direction
    entry_time:    pd.Timestamp
    entry_price:   float
    stop_price:    float          # 損切価格（1σ先）
    position_ratio: float         # ポジションサイズ = risk_pct / stop_dist_pct
    # ── 全決済 ──────────────────────────────────────────────────────────────
    exit_time:    Optional[pd.Timestamp] = None
    exit_price:   Optional[float]        = None
    exit_reason:  str                    = ""
    # ── 部分決済（TREND 3σ 50%利確） ────────────────────────────────────────
    partial_exit_done:  bool                    = False
    partial_exit_time:  Optional[pd.Timestamp] = None
    partial_exit_price: Optional[float]        = None

    @property
    def pnl_capital_pct(self) -> Optional[float]:
        """総資本に対するPnL（%）。部分決済がある場合は50/50で計算。"""
        if self.exit_price is None:
            return None
        mult = 1.0 if self.direction == Direction.LONG else -1.0
        if self.partial_exit_price is not None:
            r1 = 0.5 * self.position_ratio * mult * (self.partial_exit_price / self.entry_price - 1.0) * 100
            r2 = 0.5 * self.position_ratio * mult * (self.exit_price         / self.entry_price - 1.0) * 100
            return r1 + r2
        return self.position_ratio * mult * (self.exit_price / self.entry_price - 1.0) * 100

    # 後方互換用エイリアス
    @property
    def pnl_pct(self) -> Optional[float]:
        return self.pnl_capital_pct

    def record_partial_exit(self, ts: pd.Timestamp, price: float):
        self.partial_exit_done  = True
        self.partial_exit_time  = ts
        self.partial_exit_price = price

    def close(self, ts: pd.Timestamp, price: float, reason: str = ""):
        self.exit_time   = ts
        self.exit_price  = price
        self.exit_reason = reason


@dataclass
class BacktestConfig:
    bb_window:         int   = BB_WINDOW
    bb_trend_sigma:    float = BB_TREND_SIGMA        # 1.0: TREND エントリー
    bb_rev_sigma:      float = BB_REVERSION_SIGMA    # 3.0: MEAN_REV エントリー / TREND 部分利確
    bb_rev_exit_sigma: float = 2.0                   # MEAN_REV 出口（3σ→2σ）
    risk_pct:          float = 0.5                   # 1トレードの最大損失（資本の%）
    spread_pct:        float = SPREAD_PCT


class BacktestEngine:
    """
    Bar-by-bar backtest. Trades only the TOP-1 pair (largest |strength_diff|).
    One position open at a time across all pairs.
    """

    def __init__(self, clf: MarketClassifier, config: BacktestConfig | None = None):
        self.clf    = clf
        self.cfg    = config or BacktestConfig()
        self.trades: list[Trade] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        self.trades.clear()
        self._run_bar_by_bar()
        return self.summary_df()

    def summary_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "pair":               t.pair,
                "strategy":           t.strategy.value,
                "direction":          t.direction.value,
                "entry_time":         t.entry_time,
                "entry_price":        t.entry_price,
                "stop_price":         t.stop_price,
                "position_ratio":     t.position_ratio,
                "partial_exit_time":  t.partial_exit_time,
                "partial_exit_price": t.partial_exit_price,
                "exit_time":          t.exit_time,
                "exit_price":         t.exit_price,
                "exit_reason":        t.exit_reason,
                "pnl_pct":            t.pnl_capital_pct,
            })
        return pd.DataFrame(rows)

    def metrics(self) -> dict:
        df = self.summary_df()
        if df.empty:
            return {}
        completed = df.dropna(subset=["pnl_pct"])
        if completed.empty:
            return {}
        wins   = completed[completed["pnl_pct"] > 0]["pnl_pct"]
        losses = completed[completed["pnl_pct"] <= 0]["pnl_pct"]
        partial_hits = completed["partial_exit_price"].notna().sum()
        return {
            "total_trades":      len(completed),
            "win_rate":          len(wins) / len(completed),
            "avg_pnl_pct":       completed["pnl_pct"].mean(),
            "total_pnl_pct":     completed["pnl_pct"].sum(),
            "profit_factor":     wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf,
            "max_dd_pct":        _max_drawdown(completed["pnl_pct"]),
            "partial_exit_hits": int(partial_hits),
        }

    def metrics_by_strategy(self) -> pd.DataFrame:
        df = self.summary_df().dropna(subset=["pnl_pct"])
        if df.empty:
            return pd.DataFrame()
        return df.groupby("strategy")["pnl_pct"].agg(
            trades="count",
            win_rate=lambda x: (x > 0).mean(),
            avg_pnl=np.mean,
            total_pnl=np.sum,
        )

    # ── メインループ ──────────────────────────────────────────────────────────

    def _run_bar_by_bar(self):
        pairs  = [p for p in self.clf.states.columns if p in self.clf.price_data]
        cfg    = self.cfg

        # BB を全ペア分事前計算
        bb1 = {p: bollinger_bands(self.clf.price_data[p]["Close"], cfg.bb_window, cfg.bb_trend_sigma)    for p in pairs}
        bb2 = {p: bollinger_bands(self.clf.price_data[p]["Close"], cfg.bb_window, cfg.bb_rev_exit_sigma)  for p in pairs}
        bb3 = {p: bollinger_bands(self.clf.price_data[p]["Close"], cfg.bb_window, cfg.bb_rev_sigma)       for p in pairs}

        # 全ペアの共通タイムスタンプを作成（インデックスの和集合、ソート済み）
        all_ts = sorted(set().union(*(set(self.clf.price_data[p].index) for p in pairs)))

        # 強弱差 TOP-1 ペアを事前計算
        top_pair = self._compute_top_pair(pairs)

        open_trade: Optional[Trade] = None

        for i in range(1, len(all_ts)):
            ts      = all_ts[i]
            prev_ts = all_ts[i - 1]

            # ── Exit ─────────────────────────────────────────────────────────
            if open_trade is not None:
                p = open_trade.pair
                if ts not in self.clf.price_data[p].index:
                    continue

                close = float(self.clf.price_data[p]["Close"][ts])
                state = self.clf.states[p].get(ts, MarketState.NO_TRADE)

                if open_trade.strategy == MarketState.TREND:
                    open_trade = self._trend_exit(
                        open_trade, ts, close, state,
                        float(bb3[p]["upper"].get(ts, np.nan)),
                        float(bb3[p]["lower"].get(ts, np.nan)),
                    )
                else:
                    open_trade = self._rev_exit(
                        open_trade, ts, close, state,
                        float(bb2[p]["upper"].get(ts, np.nan)),
                        float(bb2[p]["lower"].get(ts, np.nan)),
                    )

            # ── Entry ─────────────────────────────────────────────────────────
            if open_trade is None:
                # TOP-1 ペアを取得
                entry_pair = top_pair.get(ts)
                if entry_pair is None or entry_pair not in pairs:
                    continue
                p = entry_pair

                if ts not in self.clf.price_data[p].index:
                    continue
                if prev_ts not in self.clf.price_data[p].index:
                    continue

                close      = float(self.clf.price_data[p]["Close"][ts])
                prev_close = float(self.clf.price_data[p]["Close"][prev_ts])
                state      = self.clf.states[p].get(ts, MarketState.NO_TRADE)
                sd         = self.clf.strength_diff(p).get(ts, float("nan"))

                if pd.isna(state) or state == MarketState.NO_TRADE:
                    continue

                bb1_row = {k: float(bb1[p][k].get(ts, np.nan)) for k in ["upper", "mid", "lower"]}
                bb3_row = {k: float(bb3[p][k].get(ts, np.nan)) for k in ["upper", "mid", "lower"]}
                bb_std  = float(bb1[p]["upper"].get(ts, np.nan)) - float(bb1[p]["mid"].get(ts, np.nan))

                if np.isnan(bb_std) or bb_std <= 0:
                    continue

                open_trade = self._check_entry(
                    p, state, ts, close, prev_close, sd,
                    bb1_row, bb3_row, bb_std,
                )

        # 末尾強制決済
        if open_trade is not None:
            p = open_trade.pair
            last_ts    = self.clf.price_data[p].index[-1]
            last_close = float(self.clf.price_data[p]["Close"].iloc[-1])
            adj = self._apply_spread(last_close, open_trade.direction, entry=False)
            sfx = "_after_partial" if open_trade.partial_exit_done else ""
            open_trade.close(last_ts, adj, f"end_of_data{sfx}")
            self.trades.append(open_trade)

    # ── TOP-1 ペア選択 ────────────────────────────────────────────────────────

    def _compute_top_pair(self, pairs: list[str]) -> dict:
        """各バーで |強弱差| 最大のペアを返す辞書 {timestamp: pair_name}"""
        abs_sd: dict[str, pd.Series] = {}
        for p in pairs:
            abs_sd[p] = self.clf.strength_diff(p).abs()
        df = pd.DataFrame(abs_sd).dropna(how="all")
        # idxmax: 各行で最大値を持つ列名
        return df.idxmax(axis=1).to_dict()

    # ── エントリー ────────────────────────────────────────────────────────────

    def _check_entry(
        self,
        pair:       str,
        state:      MarketState,
        ts:         pd.Timestamp,
        close:      float,
        prev_close: float,
        sd:         float,
        bb1:        dict,
        bb3:        dict,
        bb_std:     float,         # 1σ in price units → stop distance
    ) -> Optional[Trade]:
        if state == MarketState.TREND:
            return self._trend_entry(pair, ts, close, prev_close, sd, bb1, bb_std)
        if state == MarketState.MEAN_REVERSION:
            return self._rev_entry(pair, ts, close, prev_close, bb3, bb_std)
        return None

    def _trend_entry(self, pair, ts, close, prev_close, sd, bb1, bb_std) -> Optional[Trade]:
        if pd.isna(sd):
            return None
        direction = Direction.LONG if sd > 0 else Direction.SHORT
        upper1, lower1 = bb1["upper"], bb1["lower"]

        entered = False
        if direction == Direction.LONG  and close > upper1 and prev_close <= upper1:
            entered = True
        if direction == Direction.SHORT and close < lower1 and prev_close >= lower1:
            entered = True
        if not entered:
            return None

        entry_price = self._apply_spread(close, direction, entry=True)
        stop_price  = (entry_price - bb_std) if direction == Direction.LONG else (entry_price + bb_std)
        stop_dist_pct = bb_std / entry_price if entry_price > 0 else 1e-6
        position_ratio = (self.cfg.risk_pct / 100) / stop_dist_pct

        return Trade(pair, MarketState.TREND, direction, ts,
                     entry_price, stop_price, position_ratio)

    def _rev_entry(self, pair, ts, close, prev_close, bb3, bb_std) -> Optional[Trade]:
        upper3, lower3 = bb3["upper"], bb3["lower"]
        direction = None

        if close < lower3 and prev_close >= lower3:
            direction = Direction.LONG
        elif close > upper3 and prev_close <= upper3:
            direction = Direction.SHORT

        if direction is None:
            return None

        entry_price = self._apply_spread(close, direction, entry=True)
        # stop: さらに 1σ 外側（3σ + 1σ = 4σ 相当）
        stop_price = (entry_price - bb_std) if direction == Direction.LONG else (entry_price + bb_std)
        stop_dist_pct = bb_std / entry_price if entry_price > 0 else 1e-6
        position_ratio = (self.cfg.risk_pct / 100) / stop_dist_pct

        return Trade(pair, MarketState.MEAN_REVERSION, direction, ts,
                     entry_price, stop_price, position_ratio)

    # ── TREND 出口 ────────────────────────────────────────────────────────────

    def _trend_exit(
        self,
        trade:  Trade,
        ts:     pd.Timestamp,
        close:  float,
        state,
        upper3: float,
        lower3: float,
    ) -> Optional[Trade]:
        # 損切チェック（最優先）
        if self._stop_hit(trade, close):
            adj = self._apply_spread(trade.stop_price, trade.direction, entry=False)
            sfx = "_after_partial" if trade.partial_exit_done else ""
            trade.close(ts, adj, f"stop{sfx}")
            self.trades.append(trade)
            return None

        # 3σ 部分利確
        if not trade.partial_exit_done:
            if trade.direction == Direction.LONG  and close >= upper3:
                adj = self._apply_spread(close, trade.direction, entry=False)
                trade.record_partial_exit(ts, adj)
                return trade
            if trade.direction == Direction.SHORT and close <= lower3:
                adj = self._apply_spread(close, trade.direction, entry=False)
                trade.record_partial_exit(ts, adj)
                return trade

        # トレンド崩壊 → 全決済
        if state != MarketState.TREND:
            adj = self._apply_spread(close, trade.direction, entry=False)
            sfx = "_after_partial" if trade.partial_exit_done else ""
            trade.close(ts, adj, f"state_change{sfx}")
            self.trades.append(trade)
            return None

        return trade

    # ── MEAN_REV 出口 ─────────────────────────────────────────────────────────

    def _rev_exit(
        self,
        trade:  Trade,
        ts:     pd.Timestamp,
        close:  float,
        state,
        upper2: float,
        lower2: float,
    ) -> Optional[Trade]:
        # 損切チェック（最優先）
        if self._stop_hit(trade, close):
            adj = self._apply_spread(trade.stop_price, trade.direction, entry=False)
            trade.close(ts, adj, "stop")
            self.trades.append(trade)
            return None

        # 2σ 到達 → 利確（3σ→2σ への引き戻し）
        # LONG: lower_3σ でエントリー → lower_2σ まで戻れば利確
        # SHORT: upper_3σ でエントリー → upper_2σ まで下がれば利確
        if trade.direction == Direction.LONG  and close >= lower2:
            adj = self._apply_spread(close, trade.direction, entry=False)
            trade.close(ts, adj, "2sigma_target")
            self.trades.append(trade)
            return None
        if trade.direction == Direction.SHORT and close <= upper2:
            adj = self._apply_spread(close, trade.direction, entry=False)
            trade.close(ts, adj, "2sigma_target")
            self.trades.append(trade)
            return None

        # 状態変化 → 全決済
        if state != MarketState.MEAN_REVERSION:
            adj = self._apply_spread(close, trade.direction, entry=False)
            trade.close(ts, adj, "state_change")
            self.trades.append(trade)
            return None

        return trade

    # ── ユーティリティ ────────────────────────────────────────────────────────

    def _stop_hit(self, trade: Trade, close: float) -> bool:
        if trade.direction == Direction.LONG:
            return close <= trade.stop_price
        else:
            return close >= trade.stop_price

    def _apply_spread(self, price: float, direction: Direction, entry: bool) -> float:
        cost = self.cfg.spread_pct / 100.0
        if direction == Direction.LONG:
            return price * (1 + cost) if entry else price * (1 - cost)
        else:
            return price * (1 - cost) if entry else price * (1 + cost)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _max_drawdown(pnl_pct: pd.Series) -> float:
    cumulative  = pnl_pct.cumsum()
    running_max = cumulative.cummax()
    return float((cumulative - running_max).min())
