"""
Lead-Lag Information Propagation Strategy
==========================================
通貨強弱インデックスと擬似価格を使ったlead-lag型情報伝播戦略。

Core idea:
  実際の価格(Real)と擬似価格(Pseudo)の乖離(spread)が生じたとき、
  どちらが先行しているかを判定し、遅行側が追随するポジションをとる。

Case A: Real leads (cum_spread > threshold, 方向一致)
  → 他の関連通貨ペアで遅行側にエントリー（他ペアのPseudoが追随する）

Case B: Pseudo leads (cum_spread < -threshold, 方向一致)
  → 対象ペア自身にエントリー（RealがPseudoに追随する）

Currency position management (C3):
  通貨単位でLONG/SHORTの方向を管理。同一通貨に複数の相反ポジションは不可。

Position sizing (株戦略 logic_verification P6 準拠):
  risk_amount    = capital × risk_pct / 100
  stop_dist      = entry_price × stop_dist_pct / 100
  position_ratio = risk_pct / stop_dist_pct  ← entry_thresholdとは独立
  PnL(%of資本)   = position_ratio × 価格変動率
  最大損失       = position_ratio × stop_dist_pct = risk_pct ✓

Spread exit logic:
  entry_threshold × exit_ratio = spread縮小量の目標
  exit_level = entry_threshold × (1 - exit_ratio)
  Exit when source_cum_spread crosses exit_level toward zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from .config import PAIR_CURRENCIES, CURRENCIES
from .features import log_returns, currency_strength


# ════════════════════════════════════════════════════════════════════════
# ── パラメータ（サーベイ変数を一箇所集約） ──────────────────────────────────
# ════════════════════════════════════════════════════════════════════════

@dataclass
class LeadLagConfig:
    """
    ★パラメータサーベイ時はここを変える★

    spread_window   : 累積ウィンドウ (bars)  → 4候補
    entry_threshold : エントリー閾値（シグナル発火点のみ。ポジションサイズに無関係）
    exit_ratio      : spread縮小率での利確    → 5候補
      exit_ratio=1.0 → 完全ゼロ回帰まで保有
      exit_ratio=0.5 → 50%縮小で利確
      exit_ratio=0.1 → 10%縮小で早期利確
    risk_pct        : 1トレード最大損失 (%)  → 0.5固定
    stop_dist_pct   : ストップ幅（エントリー価格比 %）→ ポジションサイズの基準
    capital         : 初期資金 (JPY)
    spread_cost_pct : 片道コスト (%)

    ポジションサイジング（株戦略logic_verification P6と同じ設計）:
      リスク金額     = capital × risk_pct / 100
      ストップ幅     = entry_price × stop_dist_pct / 100
      position_ratio = risk_pct / stop_dist_pct  （entry_thresholdとは独立）
    """
    spread_window:    int   = 6
    entry_threshold:  float = 0.0010
    exit_ratio:       float = 0.5
    risk_pct:         float = 0.5
    stop_dist_pct:    float = 1.0    # ストップ幅（%）。position_ratioの基準
    capital:          float = 1_000_000.0
    spread_cost_pct:  float = 0.02    # 固定コスト（use_realistic=Falseの時のみ使用）
    use_case_a:       bool  = True    # False → Case B のみ
    use_realistic_cost: bool = False  # True → pair_costs.py のペア別コストを使用
    spread_entry_only:  bool = False  # True → スプレッド片道のみ・スリッページなし・エグジット無料
    exclude_self:       bool = False  # True → LOO強弱（自ペアを除外してsynthetic_retを計算）

    @property
    def exit_level(self) -> float:
        """source cum_spreadがこの水準に戻ったら利確"""
        return self.entry_threshold * (1.0 - self.exit_ratio)

    @property
    def position_ratio(self) -> float:
        """
        ポジションサイズ比率 = risk_pct / stop_dist_pct
        （株戦略 P6: 株数 = リスク金額 ÷ ストップ幅 と同じ設計）
        例: risk_pct=0.5%, stop_dist_pct=1.0% → position_ratio=0.5（資本の50%投入）
        """
        return (self.risk_pct / 100.0) / (self.stop_dist_pct / 100.0)

    @property
    def risk_amount(self) -> float:
        return self.capital * self.risk_pct / 100.0

    def summary(self) -> str:
        return (f"w={self.spread_window} entry={self.entry_threshold:.4f} "
                f"exit_r={self.exit_ratio:.1f} risk={self.risk_pct}% "
                f"stop={self.stop_dist_pct}%")


# ════════════════════════════════════════════════════════════════════════
# ── 補助クラス ────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════

class CaseType(str, Enum):
    A = "A"   # Real leads → enter other lagging pairs
    B = "B"   # Pseudo leads → enter the pair itself


class Direction(str, Enum):
    LONG  = "LONG"
    SHORT = "SHORT"


class CurrencyTracker:
    """
    C3: 通貨単位ポジション管理。
    同一通貨にLONG/SHORT両方のポジションは不可。
    """
    def __init__(self):
        self._dir: dict[str, Direction] = {}

    def can_enter(self, base: str, quote: str, direction: Direction) -> bool:
        base_d  = direction
        quote_d = Direction.SHORT if direction == Direction.LONG else Direction.LONG
        if base  in self._dir and self._dir[base]  != base_d:  return False
        if quote in self._dir and self._dir[quote] != quote_d: return False
        return True

    def enter(self, base: str, quote: str, direction: Direction):
        base_d  = direction
        quote_d = Direction.SHORT if direction == Direction.LONG else Direction.LONG
        self._dir[base]  = base_d
        self._dir[quote] = quote_d

    def exit_pair(self, base: str, quote: str):
        self._dir.pop(base,  None)
        self._dir.pop(quote, None)


@dataclass
class LeadLagTrade:
    pair:                str
    source_pair:         str        # シグナル発生元ペア
    case_type:           CaseType
    direction:           Direction
    entry_time:          pd.Timestamp
    entry_price:         float
    entry_source_spread: float      # 発生元のcum_spread@entry
    position_ratio:      float
    exit_time:           Optional[pd.Timestamp] = None
    exit_price:          Optional[float]        = None
    exit_reason:         str                    = ""
    propagation:         str                    = ""  # Real/Pseudo/Both/Neither

    def pnl(self, price: float) -> float:
        mult = 1.0 if self.direction == Direction.LONG else -1.0
        return mult * (price / self.entry_price - 1.0) * self.position_ratio * 100.0

    @property
    def final_pnl(self) -> Optional[float]:
        return self.pnl(self.exit_price) if self.exit_price is not None else None

    def close(self, ts, price, reason):
        self.exit_time   = ts
        self.exit_price  = price
        self.exit_reason = reason


# ════════════════════════════════════════════════════════════════════════
# ── メインエンジン ────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════

class LeadLagEngine:
    """
    Lead-Lag戦略バックテストエンジン。

    使い方:
        engine = LeadLagEngine(price_data, LeadLagConfig())
        df     = engine.run()
        print(engine.metrics())
    """

    def __init__(self, price_data: dict, config: LeadLagConfig = None):
        self.price_data = price_data
        self.cfg        = config or LeadLagConfig()
        self.trades:    list[LeadLagTrade] = []
        self._precompute()

    # ── 事前計算 ─────────────────────────────────────────────────────────

    def _precompute(self):
        self.returns = {p: log_returns(df["Close"]) for p, df in self.price_data.items()}

        # 通貨強弱（エントリー方向判定用・常にInclude-Self）
        self.strength = currency_strength(self.returns, PAIR_CURRENCIES)

        # 疑似リターン
        self.synthetic_ret: dict[str, pd.Series] = {}
        for pair in self.returns:
            base, quote = PAIR_CURRENCIES.get(pair, (None, None))
            if not base or not quote:
                self.synthetic_ret[pair] = pd.Series(np.nan, index=self.returns[pair].index)
                continue

            if self.cfg.exclude_self:
                # LOO（Leave-One-Out）: 自ペアを除外して強弱を計算 → 自己参照を排除
                returns_loo = {p: r for p, r in self.returns.items() if p != pair}
                strength_loo = currency_strength(returns_loo, PAIR_CURRENCIES)
                if base in strength_loo.columns and quote in strength_loo.columns:
                    self.synthetic_ret[pair] = (
                        strength_loo[base] - strength_loo[quote]
                    ).reindex(self.returns[pair].index)
                else:
                    self.synthetic_ret[pair] = pd.Series(np.nan, index=self.returns[pair].index)
            else:
                # Include-Self（既存動作）
                if base in self.strength.columns and quote in self.strength.columns:
                    self.synthetic_ret[pair] = (
                        self.strength[base] - self.strength[quote]
                    ).reindex(self.returns[pair].index)
                else:
                    self.synthetic_ret[pair] = pd.Series(np.nan, index=self.returns[pair].index)

        # per-bar spread と cumulative spread
        self.spread:     dict[str, pd.Series] = {}
        self.cum_spread: dict[str, pd.Series] = {}
        for pair in self.returns:
            s = self.returns[pair] - self.synthetic_ret[pair]
            self.spread[pair]     = s
            self.cum_spread[pair] = s.rolling(self.cfg.spread_window,
                                              min_periods=1).sum()

        # 通貨強弱をffillしてインデックスを統一
        self._strength_ff = self.strength.ffill()

    # ── メインループ ─────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        self.trades.clear()
        cfg = self.cfg

        all_ts  = sorted(set().union(*(set(df.index) for df in self.price_data.values())))
        tracker = CurrencyTracker()
        open_trades: dict[str, LeadLagTrade] = {}

        for i in range(max(cfg.spread_window, 1), len(all_ts)):
            ts      = all_ts[i]
            prev_ts = all_ts[i - 1]

            # ── Exit ──────────────────────────────────────────────────
            closed = []
            for pair, trade in list(open_trades.items()):
                src  = trade.source_pair
                src_cum = self._val(self.cum_spread.get(src), ts)
                close   = self._val(self.price_data[pair]["Close"], ts)
                if np.isnan(src_cum) or np.isnan(close):
                    continue

                ok, reason = self._check_exit(trade, src_cum, close)
                if ok:
                    prop = self._classify_propagation(
                        trade,
                        self._val(self.returns.get(src), ts, 0.0),
                        self._val(self.synthetic_ret.get(src), ts, 0.0),
                    )
                    adj = self._cost(close, trade.direction, entry=False, pair=pair)
                    trade.close(ts, adj, reason)
                    trade.propagation = prop
                    self.trades.append(trade)
                    base, quote = PAIR_CURRENCIES[pair]
                    tracker.exit_pair(base, quote)
                    closed.append(pair)

            for p in closed:
                del open_trades[p]

            # ── Entry ─────────────────────────────────────────────────
            if ts not in self._strength_ff.index:
                continue
            curr_s = self._strength_ff.loc[ts]

            for sig_pair in list(self.cum_spread.keys()):
                src_cum = self._val(self.cum_spread[sig_pair], ts)
                if np.isnan(src_cum) or abs(src_cum) <= cfg.entry_threshold:
                    continue

                base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
                if not base:
                    continue

                net = float(curr_s.get(base, 0)) - float(curr_s.get(quote, 0))
                sig_up   = src_cum >  cfg.entry_threshold
                sig_down = src_cum < -cfg.entry_threshold
                b_strong = net > 0
                q_strong = net < 0

                if cfg.use_case_a and sig_up and b_strong:
                    # Case A UP: Real led up, base strong → other lagging base-long pairs
                    self._case_a(sig_pair, base, src_cum, Direction.LONG,
                                 ts, curr_s, tracker, open_trades)

                elif cfg.use_case_a and sig_down and q_strong:
                    # Case A DOWN: Real led down, quote strong → other lagging quote-strong pairs
                    self._case_a(sig_pair, quote, src_cum, Direction.SHORT,
                                 ts, curr_s, tracker, open_trades)

                elif sig_down and b_strong:
                    # Case B UP: Pseudo led up, base strong → LONG the pair itself
                    self._case_b(sig_pair, Direction.LONG, src_cum,
                                 ts, tracker, open_trades)

                elif sig_up and q_strong:
                    # Case B DOWN: Pseudo led down, quote strong → SHORT the pair itself
                    self._case_b(sig_pair, Direction.SHORT, src_cum,
                                 ts, tracker, open_trades)

        # 末尾強制決済
        for pair, trade in list(open_trades.items()):
            last_close = float(self.price_data[pair]["Close"].iloc[-1])
            adj = self._cost(last_close, trade.direction, entry=False, pair=pair)
            trade.close(all_ts[-1], adj, "end_of_data")
            self.trades.append(trade)

        return self.summary_df()

    # ── Case A ──────────────────────────────────────────────────────────

    def _case_a(self, sig_pair, leading_ccy, src_cum, trade_dir,
                ts, curr_s, tracker, open_trades):
        """Real leads: 遅行ペアを探してエントリー"""
        cfg = self.cfg
        for lag_pair in self.cum_spread:
            if lag_pair == sig_pair or lag_pair in open_trades:
                continue
            lag_base, lag_quote = PAIR_CURRENCIES.get(lag_pair, (None, None))
            if not lag_base:
                continue

            # 先行通貨が含まれているか
            if leading_ccy not in (lag_base, lag_quote):
                continue

            # A2: まだシグナル未発生（遅行判定）
            lag_cum = self._val(self.cum_spread[lag_pair], ts)
            if np.isnan(lag_cum) or abs(lag_cum) > cfg.entry_threshold:
                continue

            # 方向
            direction = (Direction.LONG if lag_base == leading_ccy
                         else Direction.SHORT)

            # 通貨強弱方向チェック（制約）
            lag_net = float(curr_s.get(lag_base, 0)) - float(curr_s.get(lag_quote, 0))
            if direction == Direction.LONG  and lag_net < 0: continue
            if direction == Direction.SHORT and lag_net > 0: continue

            # C3チェック
            if not tracker.can_enter(lag_base, lag_quote, direction): continue

            close = self._val(self.price_data[lag_pair]["Close"], ts)
            if np.isnan(close): continue

            adj   = self._cost(close, direction, entry=True, pair=lag_pair)
            trade = LeadLagTrade(
                pair=lag_pair, source_pair=sig_pair,
                case_type=CaseType.A, direction=direction,
                entry_time=ts, entry_price=adj,
                entry_source_spread=src_cum,
                position_ratio=cfg.position_ratio,
            )
            open_trades[lag_pair] = trade
            tracker.enter(lag_base, lag_quote, direction)

    # ── Case B ──────────────────────────────────────────────────────────

    def _case_b(self, sig_pair, direction, src_cum, ts, tracker, open_trades):
        """Pseudo leads: ペア自身にエントリー"""
        if sig_pair in open_trades: return
        base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
        if not base: return
        if not tracker.can_enter(base, quote, direction): return

        close = self._val(self.price_data[sig_pair]["Close"], ts)
        if np.isnan(close): return

        adj   = self._cost(close, direction, entry=True, pair=sig_pair)
        trade = LeadLagTrade(
            pair=sig_pair, source_pair=sig_pair,
            case_type=CaseType.B, direction=direction,
            entry_time=ts, entry_price=adj,
            entry_source_spread=src_cum,
            position_ratio=self.cfg.position_ratio,
        )
        open_trades[sig_pair] = trade
        tracker.enter(base, quote, direction)

    # ── エグジット判定 ────────────────────────────────────────────────────

    def _check_exit(self, trade, src_cum, close):
        cfg   = self.cfg
        pnl   = trade.pnl(close)
        entry = trade.entry_source_spread

        # ストップロス
        if pnl <= -cfg.risk_pct:
            return True, "stop"

        # スプレッド縮小による利確
        level = cfg.exit_level   # entry_threshold × (1 - exit_ratio)
        if entry > 0:
            if src_cum <= level:
                return True, "spread_reduced"
        else:
            if src_cum >= -level:
                return True, "spread_reduced"

        return False, ""

    # ── Propagation分類 ──────────────────────────────────────────────────

    def _classify_propagation(self, trade, actual_ret, synth_ret):
        """
        直近バーのactual_ret, synthetic_retを見て
        スプレッドが縮小した要因を分類する。

        entry_source_spread > 0 → Real was ABOVE Pseudo → spread closes when:
          - actual_ret < 0 (Real pulls back) → "Real"
          - synth_ret  > 0 (Pseudo catches up) → "Pseudo"
        """
        entry = trade.entry_source_spread
        if entry > 0:
            real_adj  = actual_ret < 0
            pseudo_adj = synth_ret > 0
        else:
            real_adj  = actual_ret > 0
            pseudo_adj = synth_ret < 0

        if real_adj and pseudo_adj: return "Both"
        if real_adj:   return "Real"
        if pseudo_adj: return "Pseudo"
        return "Neither"

    # ── ユーティリティ ────────────────────────────────────────────────────

    def _val(self, series, ts, default=np.nan):
        if series is None: return default
        try:
            v = series.get(ts, default)
            return float(v) if not pd.isna(v) else default
        except Exception:
            return default

    def _cost(self, price, direction, entry, pair: str = ""):
        """
        コスト適用。
        spread_entry_only=True : スプレッド片道・エントリーのみ。スリッページなし。エグジット無料。
        use_realistic_cost=True: ペア別スプレッド（片道）+ スリッページ
        use_realistic_cost=False: 固定 spread_cost_pct（往復）
        """
        if self.cfg.spread_entry_only and pair:
            from .pair_costs import PAIR_COSTS, PairCostSpec
            if not entry:
                c = 0.0  # エグジット無料
            else:
                spec = PAIR_COSTS.get(pair, PairCostSpec(spread_pips=0.5))
                # スプレッドのみ（スリッページ除去）
                from .pair_costs import _to_pct
                c = _to_pct(pair, spec.spread_pips)
        elif self.cfg.use_realistic_cost and pair:
            from .pair_costs import PAIR_COSTS, PairCostSpec
            spec = PAIR_COSTS.get(pair, PairCostSpec(spread_pips=0.5))
            c = spec.entry_cost_pct(pair) if entry else spec.exit_cost_pct(pair)
        else:
            c = self.cfg.spread_cost_pct / 100.0

        if direction == Direction.LONG:
            return price * (1 + c) if entry else price * (1 - c)
        else:
            return price * (1 - c) if entry else price * (1 + c)

    # ── 集計 ─────────────────────────────────────────────────────────────

    def summary_df(self) -> pd.DataFrame:
        if not self.trades: return pd.DataFrame()
        return pd.DataFrame([{
            "pair":          t.pair,
            "source_pair":   t.source_pair,
            "case_type":     t.case_type.value,
            "direction":     t.direction.value,
            "entry_time":    t.entry_time,
            "exit_time":     t.exit_time,
            "exit_reason":   t.exit_reason,
            "propagation":   t.propagation,
            "pnl_pct":       t.final_pnl,
            "entry_spread":  t.entry_source_spread,
        } for t in self.trades])

    def metrics(self) -> dict:
        df = self.summary_df()
        if df.empty: return {}
        c  = df.dropna(subset=["pnl_pct"])
        if c.empty: return {}
        w  = c[c.pnl_pct > 0]["pnl_pct"]
        l  = c[c.pnl_pct <= 0]["pnl_pct"]
        pf = w.sum() / abs(l.sum()) if l.sum() != 0 else np.inf
        prop = c["propagation"].value_counts().to_dict()
        return {
            "config":            self.cfg.summary(),
            "trades":            len(c),
            "win_rate":          float(len(w) / len(c)),
            "avg_pnl":           float(c.pnl_pct.mean()),
            "total_pnl":         float(c.pnl_pct.sum()),
            "pf":                float(min(pf, 99.0)),
            "max_dd":            float((c.pnl_pct.cumsum() - c.pnl_pct.cumsum().cummax()).min()),
            "stop_cnt":          int((c.exit_reason == "stop").sum()),
            "reduced_cnt":       int((c.exit_reason == "spread_reduced").sum()),
            "case_a":            int((c.case_type == "A").sum()),
            "case_b":            int((c.case_type == "B").sum()),
            "prop_Real":         prop.get("Real",    0),
            "prop_Pseudo":       prop.get("Pseudo",  0),
            "prop_Both":         prop.get("Both",    0),
            "prop_Neither":      prop.get("Neither", 0),
            "propagation_rate":  float((prop.get("Pseudo",0) + prop.get("Real",0) + prop.get("Both",0))
                                       / max(len(c), 1)),
        }

    def metrics_by_pair(self) -> pd.DataFrame:
        df = self.summary_df().dropna(subset=["pnl_pct"])
        if df.empty: return pd.DataFrame()
        g  = df.groupby("pair")["pnl_pct"].agg(
            trades="count",
            win_rate=lambda x: (x > 0).mean(),
            avg_pnl=np.mean,
            total_pnl=np.sum,
        )
        return g.sort_values("total_pnl", ascending=False)


# ════════════════════════════════════════════════════════════════════════
# ── パラメータサーベイ ────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════

def param_survey(
    price_data:       dict,
    window_grid:      list[int]   = None,
    threshold_grid:   list[float] = None,
    exit_ratio_grid:  list[float] = None,
    risk_pct:         float       = 0.5,
) -> pd.DataFrame:
    """
    100通り（4×5×5）のパラメータサーベイ。
    事前計算は一部共有して高速化。
    """
    import itertools, math

    if window_grid     is None: window_grid     = [3, 6, 12, 24]
    if threshold_grid  is None: threshold_grid  = [0.0005, 0.001, 0.0015, 0.002, 0.003]
    if exit_ratio_grid is None: exit_ratio_grid = [0.1, 0.2, 0.5, 0.8, 1.0]

    combos = list(itertools.product(window_grid, threshold_grid, exit_ratio_grid))
    print(f"パラメータサーベイ: {len(combos)}通り")

    rows = []
    for i, (w, thr, er) in enumerate(combos, 1):
        cfg = LeadLagConfig(
            spread_window=w, entry_threshold=thr,
            exit_ratio=er, risk_pct=risk_pct,
        )
        engine = LeadLagEngine(price_data, cfg)
        engine.run()
        m = engine.metrics()
        if not m: continue

        pf = m["pf"]
        rows.append({
            "window": w, "entry_thr": thr, "exit_ratio": er,
            **{k: m[k] for k in ["trades","win_rate","avg_pnl","total_pnl",
                                  "pf","max_dd","stop_cnt","reduced_cnt",
                                  "case_a","case_b","prop_Real","prop_Pseudo",
                                  "prop_Both","prop_Neither","propagation_rate"]},
        })

        if i % 20 == 0 or i == len(combos):
            r = rows[-1]
            pf_s = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
            print(f"  {i}/{len(combos)}  w={w} thr={thr:.4f} er={er:.1f}  "
                  f"PF={pf_s}  trades={r['trades']}  prop={r['propagation_rate']:.0%}")

    return pd.DataFrame(rows).sort_values("pf", ascending=False).reset_index(drop=True)
