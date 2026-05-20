# -*- coding: utf-8 -*-
"""
Lead-Lag IS期間パラメータサーベイ
=====================================
データ : Dukascopy 5分足  data/dukascopy/*.parquet
IS期間 : 2022-01-01 ~ 2023-12-31
対象   : 全12ペア（JPYクロス6 + USDクロス/その他6）
コスト : Realistic（pair_costs.py の国内証券基準）

実行: python -m fx_market_classifier.run_is_survey
"""
import sys, itertools, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
import numpy as np
import pandas as pd

# ── パス設定 ──────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data" / "dukascopy"
OUT_DIR    = ROOT / "docs" / "lead_lag_is"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── パラメータグリッド ─────────────────────────────────────────────────────────
JPY_PAIRS  = [
    "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY",
    "GBPUSD", "AUDUSD", "NZDUSD", "EURGBP", "EURAUD", "AUDNZD",
]
IS_START   = "2022-01-01"
IS_END     = "2023-12-31"

WINDOWS     = [3, 6, 12, 24]
THRESHOLDS  = [0.0005, 0.001, 0.0015, 0.002, 0.003]
EXIT_RATIOS = [0.1, 0.2, 0.5, 0.8, 1.0]

TOTAL_PARAMS = len(WINDOWS) * len(THRESHOLDS) * len(EXIT_RATIOS)  # 100通り


def load_dukascopy(pairs: list[str], start: str, end: str) -> dict:
    """Dukascopy parquet を読み込んでIS期間に絞る"""
    price_data = {}
    for pair in pairs:
        path = DATA_DIR / f"{pair}_5min.parquet"
        if not path.exists():
            print(f"  [WARN] {pair}: ファイルなし → スキップ")
            continue
        df = pd.read_parquet(path)
        # タイムゾーンを UTC-naive に統一
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        # IS期間に絞る
        df = df.loc[start:end]
        if len(df) < 1000:
            print(f"  [WARN] {pair}: データ不足({len(df)}本) → スキップ")
            continue
        price_data[pair] = df
        print(f"  {pair}: {len(df):>7,}本  {df.index[0].date()} ~ {df.index[-1].date()}")
    return price_data


def run_survey(price_data: dict) -> pd.DataFrame:
    """パラメータグリッドサーベイを実行して結果 DataFrame を返す"""
    from .lead_lag import LeadLagEngine, LeadLagConfig

    results = []
    total   = TOTAL_PARAMS
    done    = 0
    t0      = time.time()

    for window, thr, er in itertools.product(WINDOWS, THRESHOLDS, EXIT_RATIOS):
        cfg = LeadLagConfig(
            spread_window    = window,
            entry_threshold  = thr,
            exit_ratio       = er,
            risk_pct         = 0.5,
            stop_dist_pct    = 1.0,     # ポジションサイズ基準（entry_thresholdと独立）
            exclude_self     = True,    # LOO: 自己参照を排除
            use_case_a       = False,   # Case B のみ
            use_realistic_cost = True,
        )
        try:
            engine  = LeadLagEngine(price_data, cfg)
            engine.run()
            m       = engine.metrics()
        except Exception as e:
            print(f"  [ERR] w={window} thr={thr} er={er}: {e}")
            done += 1
            continue

        if m:
            results.append({
                "window":           window,
                "entry_thr":        thr,
                "exit_ratio":       er,
                "trades":           m["trades"],
                "win_rate":         m["win_rate"],
                "avg_pnl":          m["avg_pnl"],
                "total_pnl":        m["total_pnl"],
                "pf":               m["pf"],
                "max_dd":           m["max_dd"],
                "stop_cnt":         m["stop_cnt"],
                "reduced_cnt":      m["reduced_cnt"],
                "prop_Real":        m["prop_Real"],
                "prop_Pseudo":      m["prop_Pseudo"],
                "prop_Both":        m["prop_Both"],
                "prop_Neither":     m["prop_Neither"],
                "propagation_rate": m["propagation_rate"],
            })

        done += 1
        elapsed = time.time() - t0
        eta     = elapsed / done * (total - done)
        print(f"  [{done:>3}/{total}]  w={window:>2} thr={thr:.4f} er={er:.1f}"
              f"  T={m.get('trades',0):>4}  PF={m.get('pf',0):.2f}"
              f"  ETA {eta:.0f}s", end="\r")

    print()
    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("pf", ascending=False).reset_index(drop=True)


def make_charts(price_data: dict, survey_df: pd.DataFrame):
    """PnL曲線とペア別成績チャートを生成"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .lead_lag import LeadLagEngine, LeadLagConfig

    if survey_df.empty:
        return

    # 最良設定で詳細実行
    best = survey_df.iloc[0]
    cfg  = LeadLagConfig(
        spread_window     = int(best["window"]),
        entry_threshold   = float(best["entry_thr"]),
        exit_ratio        = float(best["exit_ratio"]),
        risk_pct          = 0.5,
        use_case_a        = False,
        use_realistic_cost = True,
    )
    engine = LeadLagEngine(price_data, cfg)
    df_trades = engine.run()

    if df_trades.empty:
        return

    df_trades = df_trades.dropna(subset=["pnl_pct"])

    # ── PnL曲線 ────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), facecolor="#0f172a")
    fig.suptitle(
        f"IS期間 累積損益曲線（Realistic Cost）\n"
        f"w={int(best['window'])} entry={best['entry_thr']:.4f} exit={best['exit_ratio']:.1f}",
        color="white", fontsize=11,
    )

    ax1, ax2 = axes
    for ax in axes:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="#94a3b8")
        ax.spines[:].set_color("#334155")

    cum = df_trades["pnl_pct"].cumsum()
    ax1.plot(range(len(cum)), cum, color="#22d3ee", linewidth=1.5)
    ax1.axhline(0, color="#475569", linewidth=0.8, linestyle="--")
    ax1.fill_between(range(len(cum)), cum, 0,
                     where=(cum >= 0), color="#22d3ee", alpha=0.15)
    ax1.fill_between(range(len(cum)), cum, 0,
                     where=(cum < 0),  color="#f87171", alpha=0.15)
    ax1.set_ylabel("累積PnL (%)", color="#94a3b8")
    ax1.set_title("全ペア合算", color="#e2e8f0", fontsize=9)

    # ドローダウン
    roll_max = cum.cummax()
    dd       = cum - roll_max
    ax2.fill_between(range(len(dd)), dd, 0, color="#f87171", alpha=0.4)
    ax2.plot(range(len(dd)), dd, color="#f87171", linewidth=0.8)
    ax2.set_ylabel("ドローダウン (%)", color="#94a3b8")
    ax2.set_xlabel("トレード番号", color="#94a3b8")
    ax2.set_title("ドローダウン推移", color="#e2e8f0", fontsize=9)

    plt.tight_layout()
    fig.savefig(OUT_DIR / "pnl_curve_is.png", dpi=120, bbox_inches="tight",
                facecolor="#0f172a")
    plt.close(fig)
    print(f"  チャート保存: {OUT_DIR}/pnl_curve_is.png")

    # ── ペア別棒グラフ ──────────────────────────────────────────────────────
    pair_stats = (df_trades.groupby("pair")["pnl_pct"]
                  .agg(total_pnl="sum", trades="count",
                       win_rate=lambda x: (x > 0).mean())
                  .reset_index()
                  .sort_values("total_pnl", ascending=True))

    fig2, ax = plt.subplots(figsize=(9, 5), facecolor="#0f172a")
    ax.set_facecolor("#1e293b")
    ax.tick_params(colors="#94a3b8")
    ax.spines[:].set_color("#334155")

    colors = ["#22c55e" if v >= 0 else "#f87171" for v in pair_stats["total_pnl"]]
    bars   = ax.barh(pair_stats["pair"], pair_stats["total_pnl"],
                     color=colors, height=0.6)
    ax.axvline(0, color="#475569", linewidth=1)
    ax.set_xlabel("累積PnL (%)", color="#94a3b8")
    ax.set_title("IS期間 ペア別 累積損益（最良設定）", color="#e2e8f0", fontsize=11)
    for bar, (_, row) in zip(bars, pair_stats.iterrows()):
        label = f"  {row['total_pnl']:+.1f}%  (T={int(row['trades'])}, wr={row['win_rate']:.0%})"
        ax.text(bar.get_width() + (0.1 if bar.get_width() >= 0 else -0.1),
                bar.get_y() + bar.get_height() / 2,
                label, va="center", ha="left" if bar.get_width() >= 0 else "right",
                color="#e2e8f0", fontsize=8)

    plt.tight_layout()
    fig2.savefig(OUT_DIR / "pair_pnl_is.png", dpi=120, bbox_inches="tight",
                 facecolor="#0f172a")
    plt.close(fig2)
    print(f"  チャート保存: {OUT_DIR}/pair_pnl_is.png")

    # ペア別成績 CSV
    pair_stats.to_csv(OUT_DIR / "pair_ranking_is.csv", index=False, encoding="utf-8-sig")

    # 全トレード CSV
    df_trades.to_csv(OUT_DIR / "best_trades_is.csv", index=False, encoding="utf-8-sig")


def main():
    print("=" * 60)
    print("Lead-Lag IS期間サーベイ開始")
    print(f"  データ : {DATA_DIR}")
    print(f"  期間   : {IS_START} ~ {IS_END}")
    print(f"  ペア   : {JPY_PAIRS}")
    print(f"  パラメータ: {TOTAL_PARAMS}通り")
    print("=" * 60)

    print("\n[1] データ読み込み...")
    price_data = load_dukascopy(JPY_PAIRS, IS_START, IS_END)
    if not price_data:
        print("ERROR: データが読み込めませんでした")
        return

    print(f"\n[2] パラメータサーベイ実行中（{TOTAL_PARAMS}通り）...")
    t0  = time.time()
    df  = run_survey(price_data)
    elapsed = time.time() - t0
    print(f"\n  完了: {elapsed:.0f}秒  有効結果: {len(df)}件")

    if df.empty:
        print("ERROR: 結果が空です")
        return

    # 保存
    df.to_csv(OUT_DIR / "survey_is.csv", index=False, encoding="utf-8-sig")
    print(f"  サーベイ結果: {OUT_DIR}/survey_is.csv")

    # 上位10件を表示
    print("\n=== 上位10件（PF順） ===")
    cols = ["window","entry_thr","exit_ratio","trades","win_rate","pf","total_pnl","max_dd"]
    print(df[cols].head(10).to_string(index=False))

    print("\n[3] チャート生成...")
    make_charts(price_data, df)

    print("\n完了。次のステップ: python -m fx_market_classifier.make_is_report_pdf")


if __name__ == "__main__":
    main()
