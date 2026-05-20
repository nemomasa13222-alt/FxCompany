# -*- coding: utf-8 -*-
"""
Lead-Lag IS期間 ランキング型動的ペア選択
==========================================
- ウォームアップ : 2022-01-01 ~ 2022-01-31（計算初期化のみ）
- 取引期間      : 2022-02-01 ~ 2023-12-31
- ランキング更新 : 毎月1日（直近1ヶ月の実現PnLで上位3ペアを選択）
- コスト        : スプレッド片道のみ・エグジット無料

実行: python -m fx_market_classifier.run_is_ranking
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np
import pandas as pd

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "lead_lag_is"
OUT_DIR.mkdir(parents=True, exist_ok=True)

JPY_PAIRS  = ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY"]
WARMUP_END = "2022-01-31"
TRADE_START = "2022-02-01"
TRADE_END   = "2023-12-31"
TOP_N       = 3

# ── 設定（50日分最良パラメータ） ──────────────────────────────────────────────
from fx_market_classifier.lead_lag import LeadLagConfig, LeadLagTrade, CurrencyTracker, Direction, CaseType
from fx_market_classifier.config  import PAIR_CURRENCIES
from fx_market_classifier.features import log_returns, currency_strength


def load_data(pairs, full_start="2022-01-01", end="2023-12-31"):
    price_data = {}
    for pair in pairs:
        path = DATA_DIR / f"{pair}_5min.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df = df.loc[full_start:end]
        price_data[pair] = df
        print(f"  {pair}: {len(df):,}本  {df.index[0].date()} ~ {df.index[-1].date()}")
    return price_data


class LeadLagRankingEngine:
    """
    毎月ランキングを更新し上位N ペアのみエントリーする Lead-Lag エンジン。

    ランキング指標: 直近1ヶ月の実現PnL合計（トレードなし=0）
    更新タイミング: 毎月1日の最初のバー
    ウォームアップ: warmup_end 以前はエントリーしない（計算だけ行う）
    """

    def __init__(self, price_data: dict, cfg: LeadLagConfig,
                 top_n: int = 3,
                 warmup_end: str = "2022-01-31",
                 trade_start: str = "2022-02-01"):
        self.price_data  = price_data
        self.cfg         = cfg
        self.top_n       = top_n
        self.warmup_end  = pd.Timestamp(warmup_end)
        self.trade_start = pd.Timestamp(trade_start)
        self.trades: list[LeadLagTrade] = []

        self._precompute()

        # ランキング管理
        self.active_pairs: set = set(price_data.keys())  # 初期は全ペア
        self._monthly_trades: dict[str, list[float]] = {p: [] for p in price_data}
        self._current_month: int = -1
        self._ranking_log: list[dict] = []  # ランキング履歴

    # ── 事前計算（LeadLagEngine と同じロジック） ─────────────────────────────

    def _precompute(self):
        self.returns = {p: log_returns(df["Close"]) for p, df in self.price_data.items()}
        self.strength = currency_strength(self.returns, PAIR_CURRENCIES)

        self.synthetic_ret: dict[str, pd.Series] = {}
        for pair in self.returns:
            base, quote = PAIR_CURRENCIES.get(pair, (None, None))
            if base and quote and base in self.strength.columns and quote in self.strength.columns:
                self.synthetic_ret[pair] = (
                    self.strength[base] - self.strength[quote]
                ).reindex(self.returns[pair].index)
            else:
                self.synthetic_ret[pair] = pd.Series(np.nan, index=self.returns[pair].index)

        self.spread: dict[str, pd.Series] = {}
        self.cum_spread: dict[str, pd.Series] = {}
        for pair in self.returns:
            s = self.returns[pair] - self.synthetic_ret[pair]
            self.spread[pair]     = s
            self.cum_spread[pair] = s.rolling(self.cfg.spread_window, min_periods=1).sum()

        self._strength_ff = self.strength.ffill()

    # ── ランキング更新 ────────────────────────────────────────────────────────

    def _update_ranking(self, ts: pd.Timestamp):
        """前月の実現PnLで上位 top_n ペアを選択"""
        scores = {}
        for pair in self.price_data:
            pnls = self._monthly_trades.get(pair, [])
            scores[pair] = sum(pnls) if pnls else 0.0  # トレードなし=0

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        old_active = set(self.active_pairs)
        self.active_pairs = {p for p, _ in ranked[:self.top_n]}

        # 履歴保存
        self._ranking_log.append({
            "date": ts.strftime("%Y-%m-%d"),
            **{f"score_{p}": round(s, 4) for p, s in ranked},
            "selected": str(sorted(self.active_pairs)),
        })

        changed = old_active != self.active_pairs
        tag = " ★変更" if changed else ""
        top3 = ", ".join(f"{p}({scores[p]:+.2f}%)" for p, _ in ranked[:self.top_n])
        print(f"  [{ts.strftime('%Y-%m')}] ランキング更新{tag}: [{top3}]")

        # 月次リセット
        for p in self._monthly_trades:
            self._monthly_trades[p] = []

    # ── コスト計算 ────────────────────────────────────────────────────────────

    def _cost(self, price, direction, entry, pair=""):
        if self.cfg.spread_entry_only and pair:
            if not entry:
                c = 0.0
            else:
                from fx_market_classifier.pair_costs import PAIR_COSTS, PairCostSpec, _to_pct
                spec = PAIR_COSTS.get(pair, PairCostSpec(spread_pips=0.5))
                c = _to_pct(pair, spec.spread_pips)
        else:
            c = self.cfg.spread_cost_pct / 100.0

        if direction == Direction.LONG:
            return price * (1 + c) if entry else price * (1 - c)
        else:
            return price * (1 - c) if entry else price * (1 + c)

    def _val(self, series, ts, default=np.nan):
        if series is None: return default
        try:
            v = series.get(ts, default)
            return float(v) if not pd.isna(v) else default
        except Exception:
            return default

    # ── エグジット判定 ────────────────────────────────────────────────────────

    def _check_exit(self, trade, src_cum, close):
        pnl   = trade.pnl(close)
        entry = trade.entry_source_spread
        if pnl <= -self.cfg.risk_pct:
            return True, "stop"
        level = self.cfg.exit_level
        if entry > 0:
            if src_cum <= level:  return True, "spread_reduced"
        else:
            if src_cum >= -level: return True, "spread_reduced"
        return False, ""

    # ── Case B エントリー ─────────────────────────────────────────────────────

    def _case_b(self, sig_pair, direction, src_cum, ts, tracker, open_trades):
        if sig_pair in open_trades: return
        if sig_pair not in self.active_pairs: return   # ランク外はスキップ
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

    # ── メインループ ──────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        self.trades.clear()
        cfg = self.cfg

        all_ts  = sorted(set().union(*(set(df.index) for df in self.price_data.values())))
        tracker = CurrencyTracker()
        open_trades: dict[str, LeadLagTrade] = {}

        for i in range(max(cfg.spread_window, 1), len(all_ts)):
            ts = all_ts[i]

            # ── 月次ランキング更新（取引開始後、毎月1日） ─────────────────
            if ts >= self.trade_start and ts.month != self._current_month:
                if self._current_month != -1:  # 初回は更新しない（全ペア解放のまま）
                    self._update_ranking(ts)
                self._current_month = ts.month

            # ── エグジット ────────────────────────────────────────────────
            closed = []
            for pair, trade in list(open_trades.items()):
                src_cum = self._val(self.cum_spread.get(trade.source_pair), ts)
                close   = self._val(self.price_data[pair]["Close"], ts)
                if np.isnan(src_cum) or np.isnan(close): continue

                ok, reason = self._check_exit(trade, src_cum, close)
                if ok:
                    adj = self._cost(close, trade.direction, entry=False, pair=pair)
                    trade.close(ts, adj, reason)

                    # 伝播分類
                    ar = self._val(self.returns.get(pair), ts, 0.0)
                    sr = self._val(self.synthetic_ret.get(pair), ts, 0.0)
                    e  = trade.entry_source_spread
                    real_adj  = ar < 0 if e > 0 else ar > 0
                    pseudo_adj = sr > 0 if e > 0 else sr < 0
                    if real_adj and pseudo_adj: prop = "Both"
                    elif real_adj:   prop = "Real"
                    elif pseudo_adj: prop = "Pseudo"
                    else:            prop = "Neither"
                    trade.propagation = prop

                    self.trades.append(trade)
                    base, quote = PAIR_CURRENCIES[pair]
                    tracker.exit_pair(base, quote)
                    closed.append(pair)

                    # 月次スコア記録（取引期間のみ）
                    if ts >= self.trade_start and trade.final_pnl is not None:
                        self._monthly_trades[pair].append(trade.final_pnl)

            for p in closed:
                del open_trades[p]

            # ── エントリー（ウォームアップ中はスキップ） ──────────────────
            if ts < self.trade_start:
                continue
            if ts not in self._strength_ff.index:
                continue

            curr_s = self._strength_ff.loc[ts]
            for sig_pair in list(self.cum_spread.keys()):
                src_cum = self._val(self.cum_spread[sig_pair], ts)
                if np.isnan(src_cum) or abs(src_cum) <= cfg.entry_threshold: continue

                base, quote = PAIR_CURRENCIES.get(sig_pair, (None, None))
                if not base: continue

                net      = float(curr_s.get(base, 0)) - float(curr_s.get(quote, 0))
                sig_down = src_cum < -cfg.entry_threshold
                sig_up   = src_cum >  cfg.entry_threshold
                b_strong = net > 0
                q_strong = net < 0

                if sig_down and b_strong:
                    self._case_b(sig_pair, Direction.LONG,  src_cum, ts, tracker, open_trades)
                elif sig_up and q_strong:
                    self._case_b(sig_pair, Direction.SHORT, src_cum, ts, tracker, open_trades)

        # 末尾強制決済
        for pair, trade in list(open_trades.items()):
            last_close = float(self.price_data[pair]["Close"].iloc[-1])
            adj = self._cost(last_close, trade.direction, entry=False, pair=pair)
            trade.close(all_ts[-1], adj, "end_of_data")
            self.trades.append(trade)

        return self.summary_df()

    # ── 集計 ─────────────────────────────────────────────────────────────────

    def summary_df(self) -> pd.DataFrame:
        if not self.trades: return pd.DataFrame()
        return pd.DataFrame([{
            "pair":         t.pair,
            "case_type":    t.case_type.value,
            "direction":    t.direction.value,
            "entry_time":   t.entry_time,
            "exit_time":    t.exit_time,
            "exit_reason":  t.exit_reason,
            "propagation":  t.propagation,
            "pnl_pct":      t.final_pnl,
        } for t in self.trades])

    def metrics(self) -> dict:
        df = self.summary_df().dropna(subset=["pnl_pct"])
        if df.empty: return {}
        w  = df[df.pnl_pct > 0]["pnl_pct"]
        l  = df[df.pnl_pct <= 0]["pnl_pct"]
        pf = w.sum() / abs(l.sum()) if l.sum() != 0 else np.inf
        prop = df["propagation"].value_counts().to_dict()
        return {
            "trades":           len(df),
            "win_rate":         float(len(w) / len(df)),
            "avg_pnl":          float(df.pnl_pct.mean()),
            "total_pnl":        float(df.pnl_pct.sum()),
            "pf":               float(min(pf, 99.0)),
            "max_dd":           float((df.pnl_pct.cumsum() - df.pnl_pct.cumsum().cummax()).min()),
            "stop_cnt":         int((df.exit_reason == "stop").sum()),
            "reduced_cnt":      int((df.exit_reason == "spread_reduced").sum()),
            "propagation_rate": float((prop.get("Pseudo",0) + prop.get("Real",0)
                                       + prop.get("Both",0)) / max(len(df), 1)),
        }

    def metrics_by_pair(self) -> pd.DataFrame:
        df = self.summary_df().dropna(subset=["pnl_pct"])
        if df.empty: return pd.DataFrame()
        return df.groupby("pair")["pnl_pct"].agg(
            trades="count",
            win_rate=lambda x: (x > 0).mean(),
            avg_pnl="mean",
            total_pnl="sum",
        )


def make_charts(df_trades, m, pb, ranking_log):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    jp_fonts = ["Yu Gothic", "Meiryo", "MS Gothic"]
    avail = {f.name for f in fm.fontManager.ttflist}
    jp = next((f for f in jp_fonts if f in avail), None)
    if jp: plt.rcParams["font.family"] = jp

    df_c = df_trades.dropna(subset=["pnl_pct"])
    cum  = df_c["pnl_pct"].cumsum()
    dd   = cum - cum.cummax()

    # PnL曲線
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), facecolor="#0f172a")
    fig.suptitle(
        f"IS期間 ランキング型（上位{TOP_N}ペア）\n"
        f"PF={m.get('pf',0):.3f}  勝率={m.get('win_rate',0)*100:.1f}%  "
        f"T={m.get('trades',0)}  MaxDD={m.get('max_dd',0):.2f}%",
        color="white", fontsize=10,
    )
    for ax in axes:
        ax.set_facecolor("#1e293b"); ax.tick_params(colors="#94a3b8")
        ax.spines[:].set_color("#334155")

    axes[0].plot(range(len(cum)), cum, color="#22d3ee", lw=1.5)
    axes[0].axhline(0, color="#475569", lw=0.8, ls="--")
    axes[0].fill_between(range(len(cum)), cum, 0, where=(cum>=0), color="#22d3ee", alpha=0.15)
    axes[0].fill_between(range(len(cum)), cum, 0, where=(cum<0),  color="#f87171", alpha=0.15)
    axes[0].set_ylabel("累積PnL (%)", color="#94a3b8")
    axes[0].set_title("全採用ペア合算（取引期間 2022-02〜2023-12）", color="#e2e8f0", fontsize=9)

    axes[1].fill_between(range(len(dd)), dd, 0, color="#f87171", alpha=0.4)
    axes[1].plot(range(len(dd)), dd, color="#f87171", lw=0.8)
    axes[1].set_ylabel("ドローダウン (%)", color="#94a3b8")
    axes[1].set_xlabel("トレード番号", color="#94a3b8")

    plt.tight_layout()
    fig.savefig(OUT_DIR / "pnl_curve_ranking.png", dpi=120,
                bbox_inches="tight", facecolor="#0f172a")
    plt.close(fig)

    # ペア別棒グラフ
    if not pb.empty:
        pb_r = pb.reset_index().sort_values("total_pnl", ascending=True)
        fig2, ax = plt.subplots(figsize=(9, 5), facecolor="#0f172a")
        ax.set_facecolor("#1e293b"); ax.tick_params(colors="#94a3b8")
        ax.spines[:].set_color("#334155")
        colors = ["#22c55e" if v >= 0 else "#f87171" for v in pb_r["total_pnl"]]
        bars = ax.barh(pb_r["pair"], pb_r["total_pnl"], color=colors, height=0.6)
        ax.axvline(0, color="#475569", lw=1)
        ax.set_xlabel("累積PnL (%)", color="#94a3b8")
        ax.set_title("IS期間 ランキング型 ペア別累積損益", color="#e2e8f0", fontsize=11)
        for bar, (_, row) in zip(bars, pb_r.iterrows()):
            pnl = row["total_pnl"]; t = int(row.get("trades",0)); wr = row.get("win_rate",0)
            lbl = f"  {pnl:+.1f}%  T={t} wr={wr:.0%}"
            ax.text(bar.get_width() + (0.1 if pnl>=0 else -0.1),
                    bar.get_y() + bar.get_height()/2, lbl,
                    va="center", ha="left" if pnl>=0 else "right",
                    color="#e2e8f0", fontsize=8)
        plt.tight_layout()
        fig2.savefig(OUT_DIR / "pair_pnl_ranking.png", dpi=120,
                     bbox_inches="tight", facecolor="#0f172a")
        plt.close(fig2)

    # ランキング推移（選択ペアの時系列）
    if ranking_log:
        df_rank = pd.DataFrame(ranking_log)
        fig3, ax = plt.subplots(figsize=(12, 4), facecolor="#0f172a")
        ax.set_facecolor("#1e293b"); ax.tick_params(colors="#94a3b8")
        ax.spines[:].set_color("#334155")
        colors_p = {
            "USDJPY":"#22d3ee","EURJPY":"#22c55e","GBPJPY":"#f59e0b",
            "AUDJPY":"#f87171","NZDJPY":"#a78bfa","CHFJPY":"#fb923c",
        }
        dates = df_rank["date"].tolist()
        x     = range(len(dates))
        for pair in JPY_PAIRS:
            col = f"score_{pair}"
            if col in df_rank.columns:
                ax.plot(x, df_rank[col], color=colors_p.get(pair,"white"),
                        lw=1.5, marker="o", markersize=4, label=pair)
        ax.axhline(0, color="#475569", lw=0.8, ls="--")
        ax.set_xticks(x)
        ax.set_xticklabels([d[:7] for d in dates], rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("月次PnL (%)", color="#94a3b8")
        ax.set_title("月次ランキングスコア推移（採用ペア選択の根拠）",
                     color="#e2e8f0", fontsize=10)
        ax.legend(fontsize=7, loc="upper left",
                  facecolor="#1e293b", edgecolor="#475569", labelcolor="white")
        plt.tight_layout()
        fig3.savefig(OUT_DIR / "ranking_history.png", dpi=120,
                     bbox_inches="tight", facecolor="#0f172a")
        plt.close(fig3)

    print("  チャート保存完了")


def main():
    print("=" * 60)
    print(f"Lead-Lag ランキング型 IS期間検証")
    print(f"  ウォームアップ : 2022-01-01 ~ {WARMUP_END}")
    print(f"  取引期間      : {TRADE_START} ~ {TRADE_END}")
    print(f"  上位ペア数    : TOP {TOP_N}")
    print(f"  コスト        : スプレッド片道のみ")
    print("=" * 60)

    print("\n[1] データ読み込み...")
    price_data = load_data(JPY_PAIRS, full_start="2022-01-01", end=TRADE_END)
    if not price_data:
        print("ERROR: データなし"); return

    cfg = LeadLagConfig(
        spread_window      = 6,
        entry_threshold    = 0.0015,
        exit_ratio         = 1.0,
        risk_pct           = 0.5,
        use_case_a         = False,
        spread_entry_only  = True,
        use_realistic_cost = False,
    )

    print(f"\n[2] ランキング型バックテスト実行...")
    print(f"  初月（2022-02）は全ペア解放、以降毎月1日に上位{TOP_N}に絞る")
    t0     = time.time()
    engine = LeadLagRankingEngine(
        price_data, cfg,
        top_n       = TOP_N,
        warmup_end  = WARMUP_END,
        trade_start = TRADE_START,
    )
    df_tr   = engine.run()
    m       = engine.metrics()
    elapsed = time.time() - t0
    print(f"\n  完了: {elapsed:.1f}秒")

    print("\n=== 結果 ===")
    for k, v in m.items():
        if isinstance(v, float):
            print(f"  {k:<22}: {v:.4f}")
        else:
            print(f"  {k:<22}: {v}")

    pb = engine.metrics_by_pair()
    print("\n=== ペア別 ===")
    print(pb.to_string())

    # ランキング履歴
    print("\n=== ランキング履歴 ===")
    for r in engine._ranking_log:
        print(f"  {r['date']}  選択: {r['selected']}")

    # 保存
    df_tr.to_csv(OUT_DIR / "ranking_trades_is.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(engine._ranking_log).to_csv(
        OUT_DIR / "ranking_history.csv", index=False, encoding="utf-8-sig")
    pb.reset_index().to_csv(
        OUT_DIR / "ranking_pair_pnl.csv", index=False, encoding="utf-8-sig")

    # survey_is.csv も上書き（PDF生成に使う）
    row = {"window": 6, "entry_thr": 0.0015, "exit_ratio": 1.0, **m}
    pd.DataFrame([row]).to_csv(OUT_DIR / "survey_is.csv", index=False, encoding="utf-8-sig")
    pb.reset_index().to_csv(OUT_DIR / "pair_ranking_is.csv", index=False, encoding="utf-8-sig")

    print("\n[3] チャート生成...")
    make_charts(df_tr, m, pb, engine._ranking_log)

    print(f"\n保存先: {OUT_DIR}")
    print("次: python -m fx_market_classifier.make_is_report_pdf")


if __name__ == "__main__":
    main()
