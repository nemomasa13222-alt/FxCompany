# -*- coding: utf-8 -*-
"""
Log-Return × Daily Cumulative Spread Engine
============================================
元のlead_lag.pyとの差分は1点のみ:

  [元]  cum_spread = rolling_sum(spread, window=N_bars)   ← 固定ローリング窓
  [新]  cum_spread = cumsum(spread, since_daily_open_UTC) ← 当日累積（毎日リセット）

ログリターン計算・通貨強弱・エントリー/エグジットロジックは全て同一。
この変更で「ローリング窓の機械的平均回帰」の影響を除去し、
純粋な累積乖離として解析する。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

from .config import PAIR_CURRENCIES, CURRENCIES


# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LogDailyConfig:
    entry_threshold: float = 0.0015  # log-return 累積閾値
    exit_threshold:  float = 0.0005  # spread縮小利確閾値
    stop_loss_pct:   float = 1.5     # 価格ベース損切り (%)
    time_limit_bars: int   = 60      # 時間切れ（5時間）
    sort_mode:       str   = 'spread'  # 'spread' or 'strength'
    risk_pct:        float = 0.5     # 1トレードリスク (%)
    capital:         float = 1_000_000.0
    use_case_a:      bool  = True
    use_case_b:      bool  = True
    spread_cost_pct: float = 0.02    # 片道コスト (%)

    @property
    def position_ratio(self) -> float:
        return (self.risk_pct / 100.0) / self.entry_threshold

    def summary(self) -> str:
        return (f"entry={self.entry_threshold:.4f} exit={self.exit_threshold:.4f} "
                f"sort={self.sort_mode}")


# ═══════════════════════════════════════════════════════════════════════
# Trade / Tracker
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LogDailyTrade:
    pair:           str
    source_pair:    str
    case_type:      str
    direction:      str
    entry_time:     pd.Timestamp
    entry_bar:      int
    entry_price:    float
    entry_spread:   float
    sort_score:     float
    position_ratio: float
    exit_time:      Optional[pd.Timestamp] = None
    exit_price:     Optional[float]        = None
    exit_reason:    str = ''

    def price_pnl(self, price: float) -> float:
        if self.direction == 'LONG':
            return (price / self.entry_price - 1.0) * 100.0
        else:
            return (self.entry_price / price - 1.0) * 100.0

    def capital_pnl(self, price: float) -> float:
        return self.price_pnl(price) * self.position_ratio

    @property
    def final_price_pnl(self) -> Optional[float]:
        return self.price_pnl(self.exit_price) if self.exit_price is not None else None

    @property
    def final_capital_pnl(self) -> Optional[float]:
        return self.capital_pnl(self.exit_price) if self.exit_price is not None else None

    def close(self, ts, price, reason):
        self.exit_time  = ts
        self.exit_price = price
        self.exit_reason = reason


class CurrencyTracker:
    def __init__(self):
        self._dir: dict[str, str] = {}

    def can_enter(self, base, quote, direction) -> bool:
        bd = direction
        qd = 'SHORT' if direction == 'LONG' else 'LONG'
        if base  in self._dir and self._dir[base]  != bd: return False
        if quote in self._dir and self._dir[quote] != qd: return False
        return True

    def enter(self, base, quote, direction):
        self._dir[base]  = direction
        self._dir[quote] = 'SHORT' if direction == 'LONG' else 'LONG'

    def exit_pair(self, base, quote):
        self._dir.pop(base,  None)
        self._dir.pop(quote, None)


# ═══════════════════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════════════════

class LogDailyEngine:
    """
    ログリターン + 当日累積スプレッド Lead-Lag エンジン。

    元のlead_lag.pyとの唯一の違い:
      cum_spread = cumsum(spread) per UTC calendar day  (ローリング窓なし)
    """

    def __init__(self, price_data: dict[str, pd.DataFrame],
                 config: LogDailyConfig = None):
        self.price_data = {p: df for p, df in price_data.items()
                           if p in PAIR_CURRENCIES}
        self.cfg    = config or LogDailyConfig()
        self.trades: list[LogDailyTrade] = []
        self._precompute()

    # ── 事前計算 ──────────────────────────────────────────────────────

    def _precompute(self):
        pairs = list(self.price_data.keys())

        # Step 1: ログリターン（元のlead_lag.pyと同じ）
        log_ret: dict[str, pd.Series] = {}
        for pair in pairs:
            c = self.price_data[pair]['Close']
            log_ret[pair] = np.log(c / c.shift(1))

        # Step 2: 通貨強弱（ログリターンベース・Include-Self）
        all_idx = sorted(set().union(*[set(s.index) for s in log_ret.values()]))
        lr_df = pd.DataFrame(log_ret, index=all_idx).fillna(0.0)

        strength_cols: dict[str, pd.Series] = {}
        for ccy in CURRENCIES:
            contribs = []
            for pair in pairs:
                base, quote = PAIR_CURRENCIES[pair]
                if base == ccy:
                    contribs.append(lr_df[pair])
                elif quote == ccy:
                    contribs.append(-lr_df[pair])
            if contribs:
                strength_cols[ccy] = pd.concat(contribs, axis=1).mean(axis=1)
        self.strength = pd.DataFrame(strength_cols)

        # Step 3: synthetic log return
        synth: dict[str, pd.Series] = {}
        for pair in pairs:
            base, quote = PAIR_CURRENCIES[pair]
            if base in self.strength.columns and quote in self.strength.columns:
                synth[pair] = self.strength[base] - self.strength[quote]
        sp_df = pd.DataFrame(synth)

        # Step 4: per-bar spread = log_return - synthetic_log_return
        spread_bar = lr_df[list(sp_df.columns)] - sp_df

        # Step 5: ★変更点★ 当日UTC累積（ローリング窓→日次cumsum）
        utc_dates = spread_bar.index.normalize()  # UTC date for each bar
        self.cum_spread = spread_bar.groupby(utc_dates).transform('cumsum')

        # ユーティリティ用
        self.strength_ff = self.strength.ffill()
        self.pairs       = [p for p in pairs if p in self.cum_spread.columns]
        self.all_idx     = list(self.cum_spread.index)

    # ── ユーティリティ ────────────────────────────────────────────────

    def _val(self, df, col, ts, default=np.nan):
        try:
            v = df.at[ts, col]
            return float(v) if pd.notna(v) else default
        except Exception:
            return default

    def _price(self, pair, ts) -> Optional[float]:
        try:
            v = self.price_data[pair]['Close'].get(ts)
            return float(v) if v is not None and pd.notna(v) else None
        except Exception:
            return None

    def _adj(self, price, direction, entry) -> float:
        c = self.cfg.spread_cost_pct / 100.0
        if direction == 'LONG':
            return price * (1 + c) if entry else price * (1 - c)
        else:
            return price * (1 - c) if entry else price * (1 + c)

    # ── メインループ ──────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        self.trades.clear()
        cfg      = self.cfg
        tracker  = CurrencyTracker()
        open_trades: dict[str, LogDailyTrade] = {}
        all_ts   = self.all_idx
        prev_date = None

        for i, ts in enumerate(all_ts):
            cur_date = ts.normalize()

            # ── 日付変わり → 強制決済（日次cumsum のリセットと同期）
            if prev_date is not None and cur_date != prev_date:
                for pair, trade in list(open_trades.items()):
                    price = self._price(pair, ts) or trade.entry_price
                    trade.close(ts, self._adj(price, trade.direction, False), 'day_end')
                    self.trades.append(trade)
                    tracker.exit_pair(*PAIR_CURRENCIES[pair])
                open_trades.clear()
            prev_date = cur_date

            # ── Exit ──────────────────────────────────────────────────
            to_close = []
            for pair, trade in list(open_trades.items()):
                price = self._price(pair, ts)
                if price is None:
                    continue
                src_cum   = self._val(self.cum_spread, trade.source_pair, ts)
                bars_held = i - trade.entry_bar
                price_pnl = trade.price_pnl(price)

                if price_pnl <= -cfg.stop_loss_pct:
                    trade.close(ts, self._adj(price, trade.direction, False), 'stop')
                    to_close.append(pair)
                elif bars_held >= cfg.time_limit_bars:
                    trade.close(ts, self._adj(price, trade.direction, False), 'time_limit')
                    to_close.append(pair)
                elif pd.notna(src_cum) and abs(src_cum) <= cfg.exit_threshold:
                    trade.close(ts, self._adj(price, trade.direction, False), 'spread_reduced')
                    to_close.append(pair)

            for pair in to_close:
                t = open_trades.pop(pair)
                tracker.exit_pair(*PAIR_CURRENCIES[pair])
                self.trades.append(t)

            # ── Entry ─────────────────────────────────────────────────
            if ts not in self.strength_ff.index:
                continue
            curr_s = self.strength_ff.loc[ts]

            # シグナル収集 & ソート
            signals = []
            for sig_pair in self.pairs:
                src_cum = self._val(self.cum_spread, sig_pair, ts)
                if pd.isna(src_cum) or abs(src_cum) <= cfg.entry_threshold:
                    continue

                base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
                if not base:
                    continue

                str_base  = float(curr_s.get(base,  0))
                str_quote = float(curr_s.get(quote, 0))
                net       = str_base - str_quote

                score = (abs(net) if cfg.sort_mode == 'strength' else abs(src_cum))

                sig_up   = src_cum >  cfg.entry_threshold
                sig_down = src_cum < -cfg.entry_threshold
                b_strong = net > 0
                q_strong = net < 0

                if cfg.use_case_a and sig_up and b_strong:
                    signals.append((score, sig_pair, 'A_UP',   src_cum, base,  net))
                elif cfg.use_case_a and sig_down and q_strong:
                    signals.append((score, sig_pair, 'A_DOWN', src_cum, quote, net))
                elif sig_down and b_strong:
                    signals.append((score, sig_pair, 'B_LONG',  src_cum, None, net))
                elif sig_up and q_strong:
                    signals.append((score, sig_pair, 'B_SHORT', src_cum, None, net))

            signals.sort(key=lambda x: -x[0])

            for score, sig_pair, case, src_cum, lead_ccy, net in signals:
                if case == 'B_LONG':
                    self._enter_b(sig_pair, 'LONG', src_cum, score, ts, i,
                                  tracker, open_trades)
                elif case == 'B_SHORT':
                    self._enter_b(sig_pair, 'SHORT', src_cum, score, ts, i,
                                  tracker, open_trades)
                elif case == 'A_UP':
                    self._enter_a(sig_pair, lead_ccy, 'LONG', src_cum, score,
                                  ts, i, curr_s, tracker, open_trades)
                elif case == 'A_DOWN':
                    self._enter_a(sig_pair, lead_ccy, 'SHORT', src_cum, score,
                                  ts, i, curr_s, tracker, open_trades)

        # 末尾強制決済
        for pair, trade in list(open_trades.items()):
            price = self._price(pair, all_ts[-1]) or trade.entry_price
            trade.close(all_ts[-1],
                        self._adj(price, trade.direction, False), 'end_of_data')
            self.trades.append(trade)

        return self.summary_df()

    # ── Case B ───────────────────────────────────────────────────────

    def _enter_b(self, sig_pair, direction, src_cum, score,
                 ts, bar_i, tracker, open_trades):
        if sig_pair in open_trades:
            return
        base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
        if not base or not tracker.can_enter(base, quote, direction):
            return
        price = self._price(sig_pair, ts)
        if price is None:
            return
        adj = self._adj(price, direction, True)
        open_trades[sig_pair] = LogDailyTrade(
            pair=sig_pair, source_pair=sig_pair,
            case_type='B', direction=direction,
            entry_time=ts, entry_bar=bar_i,
            entry_price=adj, entry_spread=src_cum,
            sort_score=score, position_ratio=self.cfg.position_ratio,
        )
        tracker.enter(base, quote, direction)

    # ── Case A ───────────────────────────────────────────────────────

    def _enter_a(self, sig_pair, lead_ccy, lead_dir, src_cum, score,
                 ts, bar_i, curr_s, tracker, open_trades):
        cfg = self.cfg
        for lag_pair in self.pairs:
            if lag_pair == sig_pair or lag_pair in open_trades:
                continue
            lb, lq = PAIR_CURRENCIES.get(lag_pair, (None, None))
            if not lb or lead_ccy not in (lb, lq):
                continue
            lag_cum = self._val(self.cum_spread, lag_pair, ts)
            if pd.isna(lag_cum) or abs(lag_cum) > cfg.entry_threshold:
                continue

            direction = 'LONG' if lb == lead_ccy else 'SHORT'
            lag_net = float(curr_s.get(lb, 0)) - float(curr_s.get(lq, 0))
            if direction == 'LONG'  and lag_net < 0: continue
            if direction == 'SHORT' and lag_net > 0: continue
            if not tracker.can_enter(lb, lq, direction): continue

            price = self._price(lag_pair, ts)
            if price is None:
                continue
            adj       = self._adj(price, direction, True)
            lag_score = (abs(lag_net) if cfg.sort_mode == 'strength'
                         else abs(lag_cum))
            open_trades[lag_pair] = LogDailyTrade(
                pair=lag_pair, source_pair=sig_pair,
                case_type='A', direction=direction,
                entry_time=ts, entry_bar=bar_i,
                entry_price=adj, entry_spread=src_cum,
                sort_score=lag_score, position_ratio=cfg.position_ratio,
            )
            tracker.enter(lb, lq, direction)

    # ── 集計 ─────────────────────────────────────────────────────────

    def summary_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([{
            'pair':         t.pair,
            'source_pair':  t.source_pair,
            'case_type':    t.case_type,
            'direction':    t.direction,
            'entry_time':   t.entry_time,
            'exit_time':    t.exit_time,
            'exit_reason':  t.exit_reason,
            'entry_spread': t.entry_spread,
            'price_pnl':    t.final_price_pnl,
            'capital_pnl':  t.final_capital_pnl,
        } for t in self.trades])

    def metrics(self) -> dict:
        df = self.summary_df()
        if df.empty:
            return {}
        c = df.dropna(subset=['capital_pnl'])
        if c.empty:
            return {}
        w  = c[c.capital_pnl > 0]['capital_pnl']
        l  = c[c.capital_pnl <= 0]['capital_pnl']
        pf = w.sum() / abs(l.sum()) if l.sum() != 0 else np.inf
        cum = c['capital_pnl'].cumsum()
        dd  = (cum - cum.cummax()).min()
        reasons = c['exit_reason'].value_counts().to_dict()
        return {
            'config':       self.cfg.summary(),
            'trades':       len(c),
            'win_rate':     float((c.capital_pnl > 0).mean()),
            'avg_pnl':      float(c.capital_pnl.mean()),
            'total_pnl':    float(c.capital_pnl.sum()),
            'pf':           float(min(pf, 99.0)),
            'max_dd':       float(dd),
            'case_a':       int((c.case_type == 'A').sum()),
            'case_b':       int((c.case_type == 'B').sum()),
            'stop_cnt':     reasons.get('stop', 0),
            'reduced_cnt':  reasons.get('spread_reduced', 0),
            'time_cnt':     reasons.get('time_limit', 0),
            'day_end_cnt':  reasons.get('day_end', 0),
        }


# ═══════════════════════════════════════════════════════════════════════
# パラメータサーベイ
# ═══════════════════════════════════════════════════════════════════════

def param_survey(
    price_data:     dict,
    entry_grid:     list[float] = None,
    exit_grid:      list[float] = None,
    sort_modes:     list[str]   = None,
    stop_loss_pct:  float       = 1.5,
    time_limit_bars: int        = 60,
    risk_pct:       float       = 0.5,
) -> pd.DataFrame:
    import itertools

    if entry_grid  is None: entry_grid  = [0.0005, 0.001, 0.0015, 0.002, 0.003]
    if exit_grid   is None: exit_grid   = [0.0002, 0.0005, 0.001]
    if sort_modes  is None: sort_modes  = ['spread', 'strength']

    combos = list(itertools.product(entry_grid, exit_grid, sort_modes))
    print(f"パラメータサーベイ: {len(combos)}通り")

    rows = []
    for k, (entry, exit_t, sort) in enumerate(combos, 1):
        cfg = LogDailyConfig(
            entry_threshold=entry, exit_threshold=exit_t,
            sort_mode=sort, stop_loss_pct=stop_loss_pct,
            time_limit_bars=time_limit_bars, risk_pct=risk_pct,
        )
        engine = LogDailyEngine(price_data, cfg)
        engine.run()
        m = engine.metrics()
        if not m:
            continue

        pf_s = f"{m['pf']:.2f}" if m['pf'] < 99 else "inf"
        rows.append({
            'entry_threshold': entry,
            'exit_threshold':  exit_t,
            'sort_mode':       sort,
            **{k2: m[k2] for k2 in [
                'trades', 'win_rate', 'avg_pnl', 'total_pnl',
                'pf', 'max_dd', 'case_a', 'case_b',
                'stop_cnt', 'reduced_cnt', 'time_cnt', 'day_end_cnt',
            ]},
        })
        print(f"  [{k:2d}/{len(combos)}] "
              f"entry={entry:.4f} exit={exit_t:.4f} sort={sort:<8}  "
              f"T={m['trades']:4d} win={m['win_rate']*100:.1f}% "
              f"PF={pf_s}  total={m['total_pnl']:+.2f}%")

    return pd.DataFrame(rows).sort_values('pf', ascending=False).reset_index(drop=True)
