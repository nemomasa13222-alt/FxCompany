# -*- coding: utf-8 -*-
"""
Daily-Open Normalization Lead-Lag Engine
=========================================
日足始値を100として、イントラデイの%変化率でReal vs Synthetic を比較する。

Core idea:
  各UTCカレンダー日の最初のバーの始値を「100」として正規化。
  通貨強弱インデックスも同じ%変化率ベースで計算。
  Real%変化率 と Synthetic%変化率 の差（spread）が閾値を超えたらエントリー。

Cases:
  Case B: spread < -threshold (Synthetic先行UP) → 対象ペア自身をLONG
  Case B-DOWN: spread > +threshold (Real先行UP) かつ quote強 → 対象ペア自身をSHORT
  Case A: spread > +threshold (Real先行UP) かつ base強 → 遅行ペアを探してLONG/SHORT
  Case A-DOWN: spread < -threshold (Synthetic先行UP) かつ quote強 → 遅行ペアを探してLONG/SHORT

Sort mode:
  'strength': 通貨強弱差 |Str(base) - Str(quote)| 降順でエントリー優先順位付け
  'spread'  : |spread| 降順でエントリー優先順位付け

Exit:
  1. |spread_now| <= exit_threshold → take profit (spread_reduced)
  2. price_pnl <= -stop_loss_pct    → stop loss (stop)
  3. bars_held >= time_limit_bars   → time limit (time_limit)
  4. 日付変わり時の強制決済         → day_end
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from .config import PAIR_CURRENCIES, CURRENCIES


# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DailyOpenConfig:
    entry_threshold: float = 3.0    # % — spread が この値を超えたらエントリー
    exit_threshold:  float = 1.0    # % — spread がこの値に縮小したら利確
    stop_loss_pct:   float = 1.5    # % — 価格ベースの損切り幅
    time_limit_bars: int   = 60     # バー数 — 5分足 × 60 = 5時間
    sort_mode:       str   = 'spread'   # 'spread' or 'strength'
    risk_pct:        float = 0.5    # % — 1トレードあたりのリスク
    capital:         float = 1_000_000.0
    use_case_a:      bool  = True
    use_case_b:      bool  = True
    spread_cost_pct: float = 0.02   # % — 片道コスト

    @property
    def position_ratio(self) -> float:
        """position_ratio = risk_pct / entry_threshold"""
        return (self.risk_pct / 100.0) / (self.entry_threshold / 100.0)

    def summary(self) -> str:
        return (f"entry={self.entry_threshold}% exit={self.exit_threshold}% "
                f"sort={self.sort_mode}")


# ═══════════════════════════════════════════════════════════════════════
# Trade
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DailyOpenTrade:
    pair:            str
    source_pair:     str
    case_type:       str          # 'A' or 'B'
    direction:       str          # 'LONG' or 'SHORT'
    entry_time:      pd.Timestamp
    entry_bar:       int
    entry_price:     float
    entry_spread:    float        # signal pair の spread@entry
    sort_score:      float        # ranking score
    position_ratio:  float
    exit_time:       Optional[pd.Timestamp] = None
    exit_price:      Optional[float]        = None
    exit_reason:     str = ''

    def price_pnl(self, price: float) -> float:
        """価格ベースPnL (%)"""
        if self.direction == 'LONG':
            return (price / self.entry_price - 1.0) * 100.0
        else:
            return (self.entry_price / price - 1.0) * 100.0

    def capital_pnl(self, price: float) -> float:
        """資本ベースPnL (% of capital)"""
        return self.price_pnl(price) * self.position_ratio

    @property
    def final_price_pnl(self) -> Optional[float]:
        return self.price_pnl(self.exit_price) if self.exit_price is not None else None

    @property
    def final_capital_pnl(self) -> Optional[float]:
        return self.capital_pnl(self.exit_price) if self.exit_price is not None else None

    def close(self, ts: pd.Timestamp, price: float, reason: str):
        self.exit_time   = ts
        self.exit_price  = price
        self.exit_reason = reason


# ═══════════════════════════════════════════════════════════════════════
# Currency Tracker (C3)
# ═══════════════════════════════════════════════════════════════════════

class CurrencyTracker:
    def __init__(self):
        self._dir: dict[str, str] = {}   # {currency: 'LONG'/'SHORT'}

    def can_enter(self, base: str, quote: str, direction: str) -> bool:
        bd = direction
        qd = 'SHORT' if direction == 'LONG' else 'LONG'
        if base  in self._dir and self._dir[base]  != bd: return False
        if quote in self._dir and self._dir[quote] != qd: return False
        return True

    def enter(self, base: str, quote: str, direction: str):
        self._dir[base]  = direction
        self._dir[quote] = 'SHORT' if direction == 'LONG' else 'LONG'

    def exit_pair(self, base: str, quote: str):
        self._dir.pop(base,  None)
        self._dir.pop(quote, None)


# ═══════════════════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════════════════

class DailyOpenEngine:
    """
    使い方:
        engine = DailyOpenEngine(price_data, DailyOpenConfig())
        df     = engine.run()
        print(engine.metrics())
    """

    def __init__(self, price_data: dict[str, pd.DataFrame],
                 config: DailyOpenConfig = None):
        self.price_data = {p: df for p, df in price_data.items()
                           if p in PAIR_CURRENCIES}
        self.cfg    = config or DailyOpenConfig()
        self.trades: list[DailyOpenTrade] = []
        self._precompute()

    # ── 事前計算 ──────────────────────────────────────────────────────

    def _precompute(self):
        cfg   = self.cfg
        pairs = list(self.price_data.keys())

        # Step 1: real_pct (日足始値=100 からの%変化率)
        rp_dict: dict[str, pd.Series] = {}
        for pair in pairs:
            df    = self.price_data[pair]
            close = df['Close']
            opens = df['Open']
            # UTCカレンダー日ごとに最初のバーのOpenを取得
            utc_date  = close.index.normalize()   # midnight UTC
            daily_open = opens.groupby(utc_date).transform('first')
            rp_dict[pair] = (close - daily_open) / daily_open * 100.0

        # Step 2: 共通インデックスで整列
        all_idx = sorted(set().union(*[set(s.index) for s in rp_dict.values()]))
        self.rp = pd.DataFrame(rp_dict, index=all_idx).ffill()

        # Step 3: 通貨強弱 (real_pctベース)
        strength_cols: dict[str, pd.Series] = {}
        for ccy in CURRENCIES:
            contribs = []
            for pair in pairs:
                base, quote = PAIR_CURRENCIES[pair]
                if base == ccy:
                    contribs.append(self.rp[pair])
                elif quote == ccy:
                    contribs.append(-self.rp[pair])
            if contribs:
                strength_cols[ccy] = pd.concat(contribs, axis=1).mean(axis=1)
        self.strength = pd.DataFrame(strength_cols)

        # Step 4: synthetic_pct = Strength(base) - Strength(quote)
        synth_dict: dict[str, pd.Series] = {}
        for pair in pairs:
            base, quote = PAIR_CURRENCIES[pair]
            if base in self.strength.columns and quote in self.strength.columns:
                synth_dict[pair] = self.strength[base] - self.strength[quote]
        self.sp = pd.DataFrame(synth_dict)

        # Step 5: spread = real_pct - synthetic_pct
        self.spread = self.rp.reindex(columns=list(synth_dict)) - self.sp

        # 日付カラム（UTC date）
        self.utc_dates = pd.Series(
            [ts.normalize() for ts in self.spread.index],
            index=self.spread.index
        )

        self.pairs = [p for p in pairs if p in self.spread.columns]

    # ── ユーティリティ ────────────────────────────────────────────────

    def _val(self, df: pd.DataFrame, col: str, ts, default=np.nan):
        try:
            v = df.at[ts, col]
            return float(v) if pd.notna(v) else default
        except (KeyError, TypeError):
            return default

    def _price(self, pair: str, ts) -> Optional[float]:
        try:
            v = self.price_data[pair]['Close'].get(ts)
            return float(v) if v is not None and pd.notna(v) else None
        except Exception:
            return None

    def _adj_price(self, price: float, direction: str, entry: bool) -> float:
        c = self.cfg.spread_cost_pct / 100.0
        if direction == 'LONG':
            return price * (1 + c) if entry else price * (1 - c)
        else:
            return price * (1 - c) if entry else price * (1 + c)

    # ── メインループ ──────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        self.trades.clear()
        cfg     = self.cfg
        tracker = CurrencyTracker()
        open_trades: dict[str, DailyOpenTrade] = {}

        all_ts   = list(self.spread.index)
        prev_date = None

        for i, ts in enumerate(all_ts):
            cur_date = self.utc_dates.iloc[i]

            # ── 日付変わり → 全ポジション強制決済 ─────────────────────
            if prev_date is not None and cur_date != prev_date:
                for pair, trade in list(open_trades.items()):
                    price = self._price(pair, ts)
                    if price is None:
                        price = trade.entry_price
                    trade.close(ts, self._adj_price(price, trade.direction, False), 'day_end')
                    self.trades.append(trade)
                    base, quote = PAIR_CURRENCIES[pair]
                    tracker.exit_pair(base, quote)
                open_trades.clear()

            prev_date = cur_date

            # ── Exit ──────────────────────────────────────────────────
            to_close = []
            for pair, trade in list(open_trades.items()):
                price = self._price(pair, ts)
                if price is None:
                    continue

                spread_now  = self._val(self.spread, trade.source_pair, ts)
                bars_held   = i - trade.entry_bar
                price_pnl   = trade.price_pnl(price)

                if price_pnl <= -cfg.stop_loss_pct:
                    trade.close(ts, self._adj_price(price, trade.direction, False), 'stop')
                    to_close.append(pair)
                elif bars_held >= cfg.time_limit_bars:
                    trade.close(ts, self._adj_price(price, trade.direction, False), 'time_limit')
                    to_close.append(pair)
                elif pd.notna(spread_now) and abs(spread_now) <= cfg.exit_threshold:
                    trade.close(ts, self._adj_price(price, trade.direction, False), 'spread_reduced')
                    to_close.append(pair)

            for pair in to_close:
                t = open_trades.pop(pair)
                base, quote = PAIR_CURRENCIES[pair]
                tracker.exit_pair(base, quote)
                self.trades.append(t)

            # ── Entry ─────────────────────────────────────────────────
            # シグナル収集
            signals: list[tuple[float, str, str, str, float, float, float]] = []
            # (sort_score, sig_pair, case_type, direction_hint, spread_val, str_diff, ...)

            for sig_pair in self.pairs:
                spread_val = self._val(self.spread, sig_pair, ts)
                if pd.isna(spread_val) or abs(spread_val) <= cfg.entry_threshold:
                    continue

                base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
                if not base:
                    continue

                str_base  = self._val(self.strength, base,  ts, 0.0)
                str_quote = self._val(self.strength, quote, ts, 0.0)
                str_diff  = str_base - str_quote  # > 0 → base strong

                # ソートスコア
                if cfg.sort_mode == 'strength':
                    score = abs(str_diff)
                else:  # 'spread'
                    score = abs(spread_val)

                if spread_val < -cfg.entry_threshold:
                    # Synthetic先行UP
                    if str_diff > 0:   # base強 → Case B LONG
                        signals.append((score, sig_pair, 'B', 'LONG',
                                        spread_val, str_diff, str_base))
                    elif str_diff < 0 and cfg.use_case_a:  # quote強 → Case A DOWN
                        signals.append((score, sig_pair, 'A_DOWN', 'A_DOWN',
                                        spread_val, str_diff, str_quote))

                elif spread_val > cfg.entry_threshold:
                    # Real先行UP
                    if str_diff > 0 and cfg.use_case_a:   # base強 → Case A UP
                        signals.append((score, sig_pair, 'A_UP', 'A_UP',
                                        spread_val, str_diff, str_base))
                    elif str_diff < 0:  # quote強 → Case B SHORT
                        signals.append((score, sig_pair, 'B', 'SHORT',
                                        spread_val, str_diff, str_quote))

            # スコア降順でソート
            signals.sort(key=lambda x: -x[0])

            for (score, sig_pair, case_type, dir_hint,
                 spread_val, str_diff, leading_str) in signals:

                if case_type == 'B':
                    self._enter_case_b(sig_pair, dir_hint, spread_val, score,
                                       ts, i, tracker, open_trades)

                elif case_type == 'A_UP':
                    base, quote = PAIR_CURRENCIES[sig_pair]
                    self._enter_case_a(sig_pair, base, spread_val, score,
                                       ts, i, tracker, open_trades)

                elif case_type == 'A_DOWN':
                    base, quote = PAIR_CURRENCIES[sig_pair]
                    self._enter_case_a_down(sig_pair, quote, spread_val, score,
                                            ts, i, tracker, open_trades)

        # 末尾強制決済
        last_ts = all_ts[-1]
        for pair, trade in list(open_trades.items()):
            price = self._price(pair, last_ts) or trade.entry_price
            trade.close(last_ts, self._adj_price(price, trade.direction, False), 'end_of_data')
            self.trades.append(trade)

        return self.summary_df()

    # ── Case B エントリー ─────────────────────────────────────────────

    def _enter_case_b(self, sig_pair, direction, spread_val, score,
                      ts, bar_i, tracker, open_trades):
        if sig_pair in open_trades:
            return
        base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
        if not base:
            return
        if not tracker.can_enter(base, quote, direction):
            return

        price = self._price(sig_pair, ts)
        if price is None:
            return

        adj = self._adj_price(price, direction, True)
        trade = DailyOpenTrade(
            pair=sig_pair, source_pair=sig_pair,
            case_type='B', direction=direction,
            entry_time=ts, entry_bar=bar_i,
            entry_price=adj, entry_spread=spread_val,
            sort_score=score,
            position_ratio=self.cfg.position_ratio,
        )
        open_trades[sig_pair] = trade
        tracker.enter(base, quote, direction)

    # ── Case A UP エントリー（Real先行、base強 → 遅行ペア探索） ───────

    def _enter_case_a(self, sig_pair, leading_ccy, spread_val, score,
                      ts, bar_i, tracker, open_trades):
        cfg = self.cfg
        for lag_pair in self.pairs:
            if lag_pair == sig_pair or lag_pair in open_trades:
                continue
            lag_base, lag_quote = PAIR_CURRENCIES.get(lag_pair, (None, None))
            if not lag_base:
                continue
            if leading_ccy not in (lag_base, lag_quote):
                continue

            # 遅行判定: |lag_spread| <= entry_threshold
            lag_spread = self._val(self.spread, lag_pair, ts)
            if pd.isna(lag_spread) or abs(lag_spread) > cfg.entry_threshold:
                continue

            # 方向
            direction = 'LONG' if lag_base == leading_ccy else 'SHORT'

            # 通貨強弱方向チェック
            lag_str_base  = self._val(self.strength, lag_base,  ts, 0.0)
            lag_str_quote = self._val(self.strength, lag_quote, ts, 0.0)
            lag_diff = lag_str_base - lag_str_quote
            if direction == 'LONG'  and lag_diff < 0: continue
            if direction == 'SHORT' and lag_diff > 0: continue

            if not tracker.can_enter(lag_base, lag_quote, direction):
                continue

            price = self._price(lag_pair, ts)
            if price is None:
                continue

            adj = self._adj_price(price, direction, True)
            lag_score = (abs(lag_diff) if cfg.sort_mode == 'strength'
                         else abs(lag_spread))
            trade = DailyOpenTrade(
                pair=lag_pair, source_pair=sig_pair,
                case_type='A', direction=direction,
                entry_time=ts, entry_bar=bar_i,
                entry_price=adj, entry_spread=spread_val,
                sort_score=lag_score,
                position_ratio=cfg.position_ratio,
            )
            open_trades[lag_pair] = trade
            tracker.enter(lag_base, lag_quote, direction)

    # ── Case A DOWN エントリー（Synthetic先行、quote強 → 遅行ペア探索）

    def _enter_case_a_down(self, sig_pair, leading_ccy, spread_val, score,
                           ts, bar_i, tracker, open_trades):
        """quote通貨が強い → leading_ccyを含む遅行ペアをSHORT/LONG"""
        cfg = self.cfg
        for lag_pair in self.pairs:
            if lag_pair == sig_pair or lag_pair in open_trades:
                continue
            lag_base, lag_quote = PAIR_CURRENCIES.get(lag_pair, (None, None))
            if not lag_base:
                continue
            if leading_ccy not in (lag_base, lag_quote):
                continue

            lag_spread = self._val(self.spread, lag_pair, ts)
            if pd.isna(lag_spread) or abs(lag_spread) > cfg.entry_threshold:
                continue

            # leading_ccy が quote として強い → lag_pair内でquoteとして動かす
            # leading_ccy が lag_base → SHORT（base が quote-side 側 → 売り）
            # leading_ccy が lag_quote → LONG（quote として強い → 分母が強 → base弱）
            direction = 'SHORT' if lag_base == leading_ccy else 'LONG'

            lag_str_base  = self._val(self.strength, lag_base,  ts, 0.0)
            lag_str_quote = self._val(self.strength, lag_quote, ts, 0.0)
            lag_diff = lag_str_base - lag_str_quote
            if direction == 'LONG'  and lag_diff < 0: continue
            if direction == 'SHORT' and lag_diff > 0: continue

            if not tracker.can_enter(lag_base, lag_quote, direction):
                continue

            price = self._price(lag_pair, ts)
            if price is None:
                continue

            adj = self._adj_price(price, direction, True)
            lag_score = (abs(lag_diff) if cfg.sort_mode == 'strength'
                         else abs(lag_spread))
            trade = DailyOpenTrade(
                pair=lag_pair, source_pair=sig_pair,
                case_type='A', direction=direction,
                entry_time=ts, entry_bar=bar_i,
                entry_price=adj, entry_spread=spread_val,
                sort_score=lag_score,
                position_ratio=cfg.position_ratio,
            )
            open_trades[lag_pair] = trade
            tracker.enter(lag_base, lag_quote, direction)

    # ── 集計 ─────────────────────────────────────────────────────────

    def summary_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                'pair':          t.pair,
                'source_pair':   t.source_pair,
                'case_type':     t.case_type,
                'direction':     t.direction,
                'entry_time':    t.entry_time,
                'exit_time':     t.exit_time,
                'exit_reason':   t.exit_reason,
                'entry_spread':  t.entry_spread,
                'sort_score':    t.sort_score,
                'price_pnl':     t.final_price_pnl,
                'capital_pnl':   t.final_capital_pnl,
            })
        return pd.DataFrame(rows)

    def metrics(self) -> dict:
        df = self.summary_df()
        if df.empty:
            return {}
        c = df.dropna(subset=['capital_pnl'])
        if c.empty:
            return {}
        w = c[c.capital_pnl > 0]['capital_pnl']
        l = c[c.capital_pnl <= 0]['capital_pnl']
        pf = w.sum() / abs(l.sum()) if l.sum() != 0 else np.inf
        cum = c['capital_pnl'].cumsum()
        dd  = (cum - cum.cummax()).min()
        reasons = c['exit_reason'].value_counts().to_dict()
        return {
            'config':        self.cfg.summary(),
            'trades':        len(c),
            'win_rate':      float((c.capital_pnl > 0).mean()),
            'avg_pnl':       float(c.capital_pnl.mean()),
            'total_pnl':     float(c.capital_pnl.sum()),
            'pf':            float(min(pf, 99.0)),
            'max_dd':        float(dd),
            'case_a':        int((c.case_type == 'A').sum()),
            'case_b':        int((c.case_type == 'B').sum()),
            'stop_cnt':      reasons.get('stop', 0),
            'reduced_cnt':   reasons.get('spread_reduced', 0),
            'time_cnt':      reasons.get('time_limit', 0),
            'day_end_cnt':   reasons.get('day_end', 0),
        }

    def metrics_by_pair(self) -> pd.DataFrame:
        df = self.summary_df().dropna(subset=['capital_pnl'])
        if df.empty:
            return pd.DataFrame()
        g = df.groupby('pair')['capital_pnl'].agg(
            trades='count',
            win_rate=lambda x: (x > 0).mean(),
            avg_pnl='mean',
            total_pnl='sum',
        )
        return g.sort_values('total_pnl', ascending=False)


# ═══════════════════════════════════════════════════════════════════════
# パラメータサーベイ
# ═══════════════════════════════════════════════════════════════════════

def param_survey(
    price_data: dict,
    entry_grid:    list[float] = None,
    exit_grid:     list[float] = None,
    sort_modes:    list[str]   = None,
    stop_loss_pct: float       = 1.5,
    time_limit_bars: int       = 60,
    risk_pct:      float       = 0.5,
) -> pd.DataFrame:
    """
    18通り（3×3×2）のパラメータサーベイ。
    """
    import itertools

    if entry_grid  is None: entry_grid  = [2.0, 3.0, 5.0]
    if exit_grid   is None: exit_grid   = [0.5, 1.0, 1.5]
    if sort_modes  is None: sort_modes  = ['spread', 'strength']

    combos = list(itertools.product(entry_grid, exit_grid, sort_modes))
    print(f"パラメータサーベイ: {len(combos)}通り")

    rows = []
    for k, (entry, exit_thr, sort) in enumerate(combos, 1):
        cfg = DailyOpenConfig(
            entry_threshold=entry,
            exit_threshold=exit_thr,
            stop_loss_pct=stop_loss_pct,
            time_limit_bars=time_limit_bars,
            sort_mode=sort,
            risk_pct=risk_pct,
        )
        engine = DailyOpenEngine(price_data, cfg)
        engine.run()
        m = engine.metrics()
        if not m:
            continue

        rows.append({
            'entry_threshold': entry,
            'exit_threshold':  exit_thr,
            'sort_mode':       sort,
            **{k2: m[k2] for k2 in [
                'trades', 'win_rate', 'avg_pnl', 'total_pnl',
                'pf', 'max_dd', 'case_a', 'case_b',
                'stop_cnt', 'reduced_cnt', 'time_cnt', 'day_end_cnt',
            ]},
        })

        pf_s = f"{m['pf']:.2f}" if m['pf'] < 99 else "inf"
        print(f"  [{k:2d}/{len(combos)}] "
              f"entry={entry}% exit={exit_thr}% sort={sort:<8}  "
              f"T={m['trades']:4d} win={m['win_rate']*100:.1f}% "
              f"PF={pf_s}  total={m['total_pnl']:+.2f}%")

    return pd.DataFrame(rows).sort_values('pf', ascending=False).reset_index(drop=True)
