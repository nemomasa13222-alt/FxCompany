"""
Synthetic Pair Spread Strategy
================================
各通貨ペアの「疑似価格」を他の11ペアから算出し、
実際の価格との乖離が生じたときに乖離解消を狙うロジック。

【設計思想】
  実際のUSDJPY価格が「市場全体が示す適正レート（疑似USDJPY）」と乖離
  → 乖離は平均回帰する
  → 乖離の方向と反対ポジションを持ち、乖離が解消したら決済

【Leave-One-Out の理由】
  USDJPYの疑似価格算出時にUSDJPY自体を含めると循環参照になるため、
  対象ペアを除外した残り11ペアから強弱を算出する。

【ポジションサイジング（PDF p.5 公式準拠）】
  risk_amount    = capital × risk_pct / 100
  position_ratio = risk_amount / (entry_threshold × capital)
                 = risk_pct/100 / entry_threshold
  PnL(%of資本)   = position_ratio × 価格変動率

パラメータサーベイ対象変数は SyntheticConfig にすべて集約。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from .config import PAIRS, PAIR_CURRENCIES
from .features import currency_strength, log_returns


# ════════════════════════════════════════════════════════════════════════════
# ── パラメータ（サーベイ対象変数を一箇所に集約） ─────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class SyntheticConfig:
    """
    ★パラメータサーベイ時はここの値を変えるだけでよい★

    スプレッド計算パラメータ
    ------------------------
    spread_window   : ローリング累積バー数
                      5分足 × 6 = 30分  (デフォルト)
                      サーベイ推奨範囲: 3~48本（15分~4時間）

    entry_threshold : |cum_spread| > これでエントリー（対数リターン単位）
                      ≈ 0.001 で約0.1%（USDJPY なら約15pips）
                      サーベイ推奨範囲: 0.0005 ~ 0.005

    exit_threshold  : |cum_spread| < これでエグジット（乖離解消と判定）
                      0 に近いほど「完全解消」を待つ
                      サーベイ推奨範囲: 0.0 ~ 0.0005

    ポジションサイジングパラメータ
    --------------------------------
    capital         : 初期資金 (JPY)
    risk_pct        : 1トレードの最大損失 (% of capital) = 1.0%
                      → entry_threshold分だけ逆行した時に risk_pct% 損失

    コストパラメータ
    -----------------
    spread_cost_pct : 片道スプレッドコスト (%)
                      0.02% ≈ 3pips (USDJPY想定)
    """

    # ── スプレッド計算 ──────────────────────────────────────────────────
    spread_window:   int   = 6        # bars  (5min × 6 = 30分)
    entry_threshold: float = 0.0010   # log-return単位  (≈ 0.1% = 約15pips@150)
    exit_threshold:  float = 0.0001   # log-return単位  (≈ 0.01% ≈ 1.5pips@150)

    # ── ポジションサイジング ────────────────────────────────────────────
    capital:         float = 1_000_000.0  # JPY
    risk_pct:        float = 1.0          # % of capital

    # ── コスト ─────────────────────────────────────────────────────────
    spread_cost_pct: float = 0.02         # % 片道

    # ── 自動計算プロパティ ──────────────────────────────────────────────

    @property
    def position_ratio(self) -> float:
        """
        ポジションサイズ比率 = risk_pct% / entry_threshold%

        entry_threshold分だけ価格が逆行したとき、ちょうど risk_pct% の損失になる。
        例: risk=1%, threshold=0.1% → position_ratio=10x (レバレッジ10倍相当)
        """
        return (self.risk_pct / 100.0) / self.entry_threshold

    @property
    def risk_amount_jpy(self) -> float:
        """1トレードの最大損失額 (JPY)"""
        return self.capital * self.risk_pct / 100.0

    def summary(self) -> str:
        return (
            f"SyntheticConfig("
            f"window={self.spread_window}bars, "
            f"entry={self.entry_threshold:.4f}, "
            f"exit={self.exit_threshold:.4f}, "
            f"risk={self.risk_pct}%, "
            f"pos_ratio={self.position_ratio:.1f}x, "
            f"cost={self.spread_cost_pct}%)"
        )


# ════════════════════════════════════════════════════════════════════════════
# ── スプレッド計算 ────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def compute_synthetic_return(
    pair:         str,
    returns_dict: dict[str, pd.Series],
) -> pd.Series:
    """
    対象ペアを除外した残り11ペアから合成対数リターンを算出 (Leave-One-Out)。

    例: USDJPY の場合
        USD強弱 = {GBPUSD, AUDUSD, NZDUSD} の3ペアから算出
        JPY強弱 = {EURJPY, GBPJPY, AUDJPY, NZDJPY, CHFJPY} の5ペアから算出
        疑似リターン = USD強弱 - JPY強弱

    Returns:
        pd.Series: 疑似対数リターン（NaN = 算出不可）
    """
    base, quote = PAIR_CURRENCIES[pair]

    returns_ex = {p: r for p, r in returns_dict.items() if p != pair}
    pairs_ex   = {p: c for p, c in PAIR_CURRENCIES.items() if p != pair}

    strength_ex = currency_strength(returns_ex, pairs_ex)

    if base not in strength_ex.columns or quote not in strength_ex.columns:
        idx = next(iter(returns_dict.values())).index
        return pd.Series(np.nan, index=idx, name=f"syn_{pair}")

    return (strength_ex[base] - strength_ex[quote]).rename(f"syn_{pair}")


def compute_spread_df(
    pair:         str,
    returns_dict: dict[str, pd.Series],
    window:       int,
) -> pd.DataFrame:
    """
    1ペア分のスプレッド系列を生成。

    列構成:
        actual_ret       : 実際の対数リターン
        synthetic_ret    : 疑似対数リターン (leave-one-out)
        spread           : actual - synthetic  (1バーごとの乖離)
        cum_spread       : rolling sum over `window` bars (累積乖離)
        actual_price_rel : 実際価格の相対変化 (t=0 → 1.0)
        syn_price_rel    : 疑似価格の相対変化 (t=0 → 1.0)
    """
    actual_ret    = returns_dict[pair]
    synthetic_ret = compute_synthetic_return(pair, returns_dict).reindex(actual_ret.index)

    spread     = actual_ret - synthetic_ret
    cum_spread = spread.rolling(window, min_periods=1).sum()

    # 価格レベル（可視化用）: 両方を1.0スタートで正規化
    actual_price_rel = np.exp(actual_ret.fillna(0).cumsum())
    syn_price_rel    = np.exp(synthetic_ret.fillna(0).cumsum())

    return pd.DataFrame({
        "actual_ret":       actual_ret,
        "synthetic_ret":    synthetic_ret,
        "spread":           spread,
        "cum_spread":       cum_spread,
        "actual_price_rel": actual_price_rel,
        "syn_price_rel":    syn_price_rel,
    })


# ════════════════════════════════════════════════════════════════════════════
# ── トレードオブジェクト ──────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

class Direction(str, Enum):
    LONG  = "LONG"
    SHORT = "SHORT"


@dataclass
class SyntheticTrade:
    pair:           str
    direction:      Direction
    entry_time:     pd.Timestamp
    entry_price:    float
    entry_spread:   float      # エントリー時のcum_spread
    position_ratio: float      # ポジションサイズ比率（資本の何倍か）

    exit_time:    Optional[pd.Timestamp] = None
    exit_price:   Optional[float]        = None
    exit_reason:  str                    = ""

    def pnl_pct(self, price: float) -> float:
        """指定価格時点のPnL（% of 資本）"""
        mult = 1.0 if self.direction == Direction.LONG else -1.0
        return mult * (price / self.entry_price - 1.0) * self.position_ratio * 100.0

    @property
    def final_pnl_pct(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        return self.pnl_pct(self.exit_price)

    def close(self, ts: pd.Timestamp, price: float, reason: str):
        self.exit_time   = ts
        self.exit_price  = price
        self.exit_reason = reason


# ════════════════════════════════════════════════════════════════════════════
# ── バックテストエンジン ──────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

class SyntheticSpreadEngine:
    """
    全12ペアに対して疑似スプレッド戦略をバックテスト。
    各ペアは独立して1ポジションまで保有可能。

    使い方:
        engine = SyntheticSpreadEngine(price_data, SyntheticConfig())
        trades_df = engine.run()
        print(engine.metrics())
    """

    def __init__(
        self,
        price_data: dict[str, pd.DataFrame],
        config:     SyntheticConfig | None = None,
    ):
        self.price_data = price_data
        self.cfg        = config or SyntheticConfig()
        self.trades:    list[SyntheticTrade] = []

        # 全ペアの対数リターン
        self.returns: dict[str, pd.Series] = {
            pair: log_returns(df["Close"])
            for pair, df in price_data.items()
        }

        # 全ペアのスプレッドDF（事前計算）
        self.spread_data: dict[str, pd.DataFrame] = {
            pair: compute_spread_df(pair, self.returns, self.cfg.spread_window)
            for pair in self.returns
            if pair in PAIR_CURRENCIES
        }

    # ── Public API ────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        self.trades.clear()
        for pair in self.spread_data:
            self._run_pair(pair)
        return self.summary_df()

    def summary_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "pair":           t.pair,
                "direction":      t.direction.value,
                "entry_time":     t.entry_time,
                "entry_price":    t.entry_price,
                "entry_spread":   t.entry_spread,
                "position_ratio": t.position_ratio,
                "exit_time":      t.exit_time,
                "exit_price":     t.exit_price,
                "exit_reason":    t.exit_reason,
                "pnl_pct":        t.final_pnl_pct,
            })
        return pd.DataFrame(rows)

    def metrics(self) -> dict:
        df = self.summary_df()
        if df.empty:
            return {}
        c = df.dropna(subset=["pnl_pct"])
        if c.empty:
            return {}
        wins   = c[c["pnl_pct"] > 0]["pnl_pct"]
        losses = c[c["pnl_pct"] <= 0]["pnl_pct"]
        return {
            "config":        self.cfg.summary(),
            "total_trades":  len(c),
            "win_rate":      len(wins) / len(c),
            "avg_pnl_pct":   c["pnl_pct"].mean(),
            "total_pnl_pct": c["pnl_pct"].sum(),
            "profit_factor": wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf"),
            "max_dd_pct":    _max_drawdown(c["pnl_pct"]),
            "stop_count":    int((c["exit_reason"] == "stop").sum()),
            "closed_count":  int((c["exit_reason"] == "spread_closed").sum()),
        }

    def metrics_by_pair(self) -> pd.DataFrame:
        df = self.summary_df().dropna(subset=["pnl_pct"])
        if df.empty:
            return pd.DataFrame()
        return df.groupby("pair")["pnl_pct"].agg(
            trades="count",
            win_rate=lambda x: (x > 0).mean(),
            avg_pnl=np.mean,
            total_pnl=np.sum,
        ).sort_values("total_pnl", ascending=False)

    # ── Per-pair simulation ───────────────────────────────────────────────

    def _run_pair(self, pair: str):
        sd    = self.spread_data[pair]
        price = self.price_data[pair]["Close"]
        cfg   = self.cfg

        open_trade: Optional[SyntheticTrade] = None

        for i in range(cfg.spread_window, len(sd)):
            ts         = sd.index[i]
            cum_spread = float(sd["cum_spread"].iloc[i])

            if np.isnan(cum_spread) or ts not in price.index:
                continue

            close = float(price.loc[ts])

            # ── Exit ─────────────────────────────────────────────────────
            if open_trade is not None:
                pnl = open_trade.pnl_pct(close)

                # 損切（ハードストップ）
                if pnl <= -cfg.risk_pct:
                    adj = self._apply_cost(close, open_trade.direction, entry=False)
                    open_trade.close(ts, adj, "stop")
                    self.trades.append(open_trade)
                    open_trade = None

                # 乖離解消エグジット
                elif abs(cum_spread) <= cfg.exit_threshold:
                    adj = self._apply_cost(close, open_trade.direction, entry=False)
                    open_trade.close(ts, adj, "spread_closed")
                    self.trades.append(open_trade)
                    open_trade = None

            # ── Entry ─────────────────────────────────────────────────────
            if open_trade is None and abs(cum_spread) > cfg.entry_threshold:
                # cum_spread > 0: 実際が疑似より高い → Short（実際が下がって解消）
                # cum_spread < 0: 実際が疑似より低い → Long（実際が上がって解消）
                direction = Direction.SHORT if cum_spread > 0 else Direction.LONG
                adj       = self._apply_cost(close, direction, entry=True)
                open_trade = SyntheticTrade(
                    pair           = pair,
                    direction      = direction,
                    entry_time     = ts,
                    entry_price    = adj,
                    entry_spread   = cum_spread,
                    position_ratio = cfg.position_ratio,
                )

        # 末尾強制決済
        if open_trade is not None:
            last_ts    = sd.index[-1]
            last_close = float(price.iloc[-1])
            adj = self._apply_cost(last_close, open_trade.direction, entry=False)
            open_trade.close(last_ts, adj, "end_of_data")
            self.trades.append(open_trade)

    def _apply_cost(self, price: float, direction: Direction, entry: bool) -> float:
        cost = self.cfg.spread_cost_pct / 100.0
        if direction == Direction.LONG:
            return price * (1 + cost) if entry else price * (1 - cost)
        else:
            return price * (1 - cost) if entry else price * (1 + cost)


# ════════════════════════════════════════════════════════════════════════════
# ── 可視化 ────────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def plot_synthetic_spread(
    pair:       str,
    price_data: dict[str, pd.DataFrame],
    spread_df:  pd.DataFrame,
    config:     SyntheticConfig,
    trades:     list[SyntheticTrade] | None = None,
    last_n:     int = 500,
    figsize:    tuple = (18, 12),
) -> plt.Figure:
    """
    3パネルチャート:
      上段: 実際価格 vs 疑似価格（絶対値で比較）
      中段: 累積スプレッド (cum_spread) + エントリー閾値線
      下段: 単バースプレッド (spread)
    """
    sl      = slice(-last_n, None)
    sd      = spread_df.iloc[sl]
    price   = price_data[pair]["Close"].reindex(sd.index)
    xs      = range(len(sd))

    # 疑似価格を実際価格の最初の値に合わせてスケーリング
    first_actual = float(price.dropna().iloc[0])
    actual_price = price.values
    syn_price    = sd["syn_price_rel"].values / float(sd["syn_price_rel"].dropna().iloc[0]) * first_actual

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=figsize,
                                         gridspec_kw={"height_ratios": [4, 2, 1.5]})
    fig.suptitle(
        f"{pair}  Synthetic Spread Strategy  "
        f"(window={config.spread_window}bars, "
        f"entry={config.entry_threshold:.4f}, "
        f"exit={config.exit_threshold:.4f})",
        fontsize=10, fontweight="bold"
    )

    # ── 上段: 価格比較 ──────────────────────────────────────────────────
    ax1.plot(xs, actual_price, color="#1a1a2e", linewidth=0.8, label="Actual")
    ax1.plot(xs, syn_price,    color="#E91E63", linewidth=0.8,
             linestyle="--", alpha=0.85, label="Synthetic")

    # トレードのエントリー・エグジットをマーク
    if trades:
        pair_trades = [t for t in trades if t.pair == pair]
        for t in pair_trades:
            if t.entry_time in sd.index:
                xi = list(sd.index).index(t.entry_time)
                color = "#2196F3" if t.direction == Direction.LONG else "#FF5722"
                ax1.axvline(xi, color=color, alpha=0.4, linewidth=0.7)
            if t.exit_time and t.exit_time in sd.index:
                xi = list(sd.index).index(t.exit_time)
                ax1.axvline(xi, color="#4CAF50", alpha=0.4, linewidth=0.7)

    ax1.set_ylabel(f"{pair} Price")
    ax1.legend(fontsize=8, loc="upper left")
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))

    # ── 中段: 累積スプレッド ────────────────────────────────────────────
    cum = sd["cum_spread"].values
    ax2.plot(xs, cum, color="#673AB7", linewidth=0.8, label="cum_spread")
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.axhline( config.entry_threshold, color="#FF5722", linewidth=0.8,
                linestyle="--", alpha=0.9, label=f"+entry ({config.entry_threshold:.4f})")
    ax2.axhline(-config.entry_threshold, color="#2196F3", linewidth=0.8,
                linestyle="--", alpha=0.9, label=f"-entry ({-config.entry_threshold:.4f})")
    ax2.axhline( config.exit_threshold,  color="#888888", linewidth=0.5,
                linestyle=":",  alpha=0.7)
    ax2.axhline(-config.exit_threshold,  color="#888888", linewidth=0.5,
                linestyle=":",  alpha=0.7)

    ax2.fill_between(xs, cum, 0,
                     where=(cum >  config.entry_threshold), alpha=0.15, color="#FF5722")
    ax2.fill_between(xs, cum, 0,
                     where=(cum < -config.entry_threshold), alpha=0.15, color="#2196F3")

    ax2.set_ylabel(f"Cum Spread\n(rolling {config.spread_window}bars)")
    ax2.legend(fontsize=7, loc="upper right", ncol=3)

    # ── 下段: 単バースプレッド ──────────────────────────────────────────
    sp = sd["spread"].values
    ax3.bar(xs, sp, color=["#FF5722" if v > 0 else "#2196F3" for v in sp],
            width=1.0, alpha=0.6)
    ax3.axhline(0, color="black", linewidth=0.5)
    ax3.set_ylabel("Spread\n(per bar)")

    # 共通X軸ラベル
    step = max(1, last_n // 8)
    ticks = range(0, last_n, step)
    labels = [str(sd.index[i])[:16] for i in ticks]
    ax3.set_xticks(list(ticks))
    ax3.set_xticklabels(labels, rotation=30, ha="right", fontsize=6.5)
    for ax in [ax1, ax2]:
        plt.setp(ax.get_xticklabels(), visible=False)

    plt.tight_layout()
    return fig


# ════════════════════════════════════════════════════════════════════════════
# ── パラメータサーベイ ────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def param_survey(
    price_data:       dict[str, pd.DataFrame],
    window_grid:      list[int]   = None,
    threshold_grid:   list[float] = None,
    exit_ratio_grid:  list[float] = None,
) -> pd.DataFrame:
    """
    パラメータサーベイ（高速版）。

    最適化:
        per-barスプレッド（spread列）はパラメータに依存しないため1回だけ計算。
        window（ローリング幅）とthreshold/exitだけをグリッドで変化させる。
        計算量: O(12 × compute_synthetic) + O(N_combos × 12 × backtest)

    Args:
        window_grid     : spread_window の候補（デフォルト: [3,6,12,24]）
        threshold_grid  : entry_threshold の候補
        exit_ratio_grid : exit_threshold = entry_threshold × ratio
    """
    if window_grid is None:
        window_grid = [3, 6, 12, 24]

    if threshold_grid is None:
        threshold_grid = [0.0005, 0.0010, 0.0020, 0.0030]

    if exit_ratio_grid is None:
        exit_ratio_grid = [0.0, 0.1, 0.2]

    import itertools, math

    # ── Step 1: per-barスプレッドを1回だけ計算（最大windowで初期化） ──────────
    max_window = max(window_grid)
    print(f"スプレッド事前計算中（{len(price_data)}ペア）...")
    base_returns = {p: log_returns(df["Close"]) for p, df in price_data.items()}
    # per-barスプレッド（window=1で累積なし）
    raw_spread: dict[str, pd.Series] = {}
    raw_price:  dict[str, pd.Series] = {}
    for pair in list(price_data.keys()):
        if pair not in PAIR_CURRENCIES:
            continue
        actual_ret    = base_returns[pair]
        synthetic_ret = compute_synthetic_return(pair, base_returns).reindex(actual_ret.index)
        raw_spread[pair] = actual_ret - synthetic_ret
        raw_price[pair]  = price_data[pair]["Close"]

    print(f"完了。サーベイ開始: {len(window_grid)}×{len(threshold_grid)}×{len(exit_ratio_grid)}"
          f" = {len(window_grid)*len(threshold_grid)*len(exit_ratio_grid)}通り")

    # ── Step 2: 各パラメータ組み合わせでバックテスト ─────────────────────────
    combos = list(itertools.product(window_grid, threshold_grid, exit_ratio_grid))
    total  = len(combos)
    rows   = []

    for i, (w, thr, ex_ratio) in enumerate(combos, 1):
        cfg = SyntheticConfig(
            spread_window   = w,
            entry_threshold = thr,
            exit_threshold  = thr * ex_ratio,
        )

        # cum_spreadはwindowによって変わるので再計算（高速）
        trades: list[SyntheticTrade] = []

        for pair in raw_spread:
            sp   = raw_spread[pair]
            cum  = sp.rolling(w, min_periods=1).sum()
            price = raw_price[pair]

            open_trade = None
            for j in range(w, len(sp)):
                ts         = sp.index[j]
                cum_val    = float(cum.iloc[j])
                if np.isnan(cum_val) or ts not in price.index:
                    continue
                close = float(price.loc[ts])

                if open_trade is not None:
                    pnl = open_trade.pnl_pct(close)
                    if pnl <= -cfg.risk_pct:
                        adj = close * (1 - cfg.spread_cost_pct/100) if open_trade.direction == Direction.LONG else close * (1 + cfg.spread_cost_pct/100)
                        open_trade.close(ts, adj, "stop")
                        trades.append(open_trade)
                        open_trade = None
                    elif abs(cum_val) <= cfg.exit_threshold:
                        adj = close * (1 - cfg.spread_cost_pct/100) if open_trade.direction == Direction.LONG else close * (1 + cfg.spread_cost_pct/100)
                        open_trade.close(ts, adj, "spread_closed")
                        trades.append(open_trade)
                        open_trade = None

                if open_trade is None and abs(cum_val) > cfg.entry_threshold:
                    direction = Direction.SHORT if cum_val > 0 else Direction.LONG
                    cost = cfg.spread_cost_pct / 100.0
                    adj = close * (1 + cost) if direction == Direction.LONG else close * (1 - cost)
                    open_trade = SyntheticTrade(
                        pair=pair, direction=direction,
                        entry_time=ts, entry_price=adj,
                        entry_spread=cum_val, position_ratio=cfg.position_ratio,
                    )

            if open_trade is not None:
                last_close = float(price.iloc[-1])
                cost = cfg.spread_cost_pct / 100.0
                adj = last_close * (1 - cost) if open_trade.direction == Direction.LONG else last_close * (1 + cost)
                open_trade.close(sp.index[-1], adj, "end_of_data")
                trades.append(open_trade)

        # metrics
        pnls = [t.final_pnl_pct for t in trades if t.final_pnl_pct is not None]
        if not pnls:
            continue
        s = pd.Series(pnls)
        wins   = s[s > 0]
        losses = s[s <= 0]
        pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else 99.0
        pf = min(pf, 99.0)

        stop_cnt   = sum(1 for t in trades if t.exit_reason == "stop")
        closed_cnt = sum(1 for t in trades if t.exit_reason == "spread_closed")

        rows.append({
            "window":     w,
            "entry_thr":  thr,
            "exit_ratio": ex_ratio,
            "trades":     len(pnls),
            "win_rate":   (s > 0).mean(),
            "pf":         pf,
            "total_pnl":  s.sum(),
            "max_dd":     float((s.cumsum() - s.cumsum().cummax()).min()),
            "stop_cnt":   stop_cnt,
            "closed_cnt": closed_cnt,
        })

        if i % 10 == 0 or i == total:
            r = rows[-1]
            print(f"  {i}/{total}  w={w} thr={thr:.4f} ex={ex_ratio:.1f}  "
                  f"PF={r['pf']:.2f}  trades={r['trades']}")

    return pd.DataFrame(rows).sort_values("pf", ascending=False).reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════
# ── ユーティリティ ────────────────────────────────────────════════════════════
# ════════════════════════════════════════════════════════════════════════════

def _max_drawdown(pnl_pct: pd.Series) -> float:
    cumulative  = pnl_pct.cumsum()
    running_max = cumulative.cummax()
    return float((cumulative - running_max).min())
