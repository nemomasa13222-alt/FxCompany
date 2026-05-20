# -*- coding: utf-8 -*-
"""
Include-Self vs Leave-One-Out 比較解析
  同一パラメータ・同一期間・同一コストで両方式を比較する

実行: python _run_loo_comparison.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import itertools, time
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass
_prop = fm.FontProperties(fname=FONT_PATH, size=8)

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "loo_comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START = "2022-01-01"
IS_END   = "2023-12-31"

ALL_PAIRS = [
    "USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
    "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD",
]

# 比較するパラメータ（代表5設定）
CONFIGS = [
    {"label": "w3_e003_er01",  "window": 3,  "entry": 0.003,  "exit_r": 0.1},
    {"label": "w3_e003_er10",  "window": 3,  "entry": 0.003,  "exit_r": 1.0},
    {"label": "w24_e003_er10", "window": 24, "entry": 0.003,  "exit_r": 1.0},
    {"label": "w6_e0015_er10", "window": 6,  "entry": 0.0015, "exit_r": 1.0},
    {"label": "w12_e002_er05", "window": 12, "entry": 0.002,  "exit_r": 0.5},
]

sys.path.insert(0, str(ROOT))
from fx_market_classifier.lead_lag import LeadLagEngine, LeadLagConfig


# ══════════════════════════════════════════════════════════════════════
# データ読み込み
# ══════════════════════════════════════════════════════════════════════

def load_data():
    data = {}
    print(f"\nIS期間データ読み込み: {IS_START} 〜 {IS_END}")
    for pair in ALL_PAIRS:
        f = DATA_DIR / f"{pair}_5min.parquet"
        if not f.exists():
            print(f"  {pair}: スキップ")
            continue
        df = pd.read_parquet(f)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df = df.loc[IS_START:IS_END]
        if len(df) < 1000:
            continue
        data[pair] = df
        print(f"  {pair}: {len(df):,}本")
    return data


# ══════════════════════════════════════════════════════════════════════
# 1設定で両方式を実行 → 詳細メトリクスを返す
# ══════════════════════════════════════════════════════════════════════

def run_one(data, cfg_dict, exclude_self: bool) -> dict:
    cfg = LeadLagConfig(
        spread_window      = cfg_dict["window"],
        entry_threshold    = cfg_dict["entry"],
        exit_ratio         = cfg_dict["exit_r"],
        risk_pct           = 0.5,
        stop_dist_pct      = 1.0,
        use_case_a         = False,
        use_realistic_cost = True,
        exclude_self       = exclude_self,
    )
    engine = LeadLagEngine(data, cfg)
    df_tr  = engine.run()

    if df_tr.empty:
        return {}

    df_tr = df_tr.dropna(subset=["pnl_pct"])
    m     = engine.metrics()
    if not m:
        return {}

    # ── ペア別 ──
    pair_stats = (df_tr.groupby("pair")["pnl_pct"]
                  .agg(total_pnl="sum", trades="count",
                       win_rate=lambda x: (x > 0).mean())
                  .reset_index())

    # ── 月別 ──
    df_tr["ym"] = df_tr["exit_time"].dt.to_period("M")
    monthly = (df_tr.groupby("ym")["pnl_pct"]
               .agg(total_pnl="sum", trades="count",
                    win_rate=lambda x: (x > 0).mean())
               .reset_index())

    # ── スプレッド縮小分類 ──
    prop = df_tr["propagation"].value_counts().to_dict() if "propagation" in df_tr.columns else {}
    n    = len(df_tr)
    spread_reduced = int((df_tr["exit_reason"] == "spread_reduced").sum())
    stop_cnt       = int((df_tr["exit_reason"] == "stop").sum())

    return {
        "method":          "LOO" if exclude_self else "Include-Self",
        "trades":          m["trades"],
        "win_rate":        m["win_rate"],
        "pf":              m["pf"],
        "total_pnl":       m["total_pnl"],
        "max_dd":          m["max_dd"],
        "spread_reduced":  spread_reduced,
        "stop_cnt":        stop_cnt,
        "prop_Pseudo":     prop.get("Pseudo", 0),
        "prop_Real":       prop.get("Real",   0),
        "prop_Both":       prop.get("Both",   0),
        "prop_Neither":    prop.get("Neither",0),
        "propagation_rate": m.get("propagation_rate", 0),
        "pair_stats":      pair_stats,
        "monthly":         monthly,
        "df_trades":       df_tr,
    }


# ══════════════════════════════════════════════════════════════════════
# 全コストなし版も実行（純粋アルファ確認）
# ══════════════════════════════════════════════════════════════════════

def run_nocost(data, cfg_dict, exclude_self: bool) -> dict:
    cfg = LeadLagConfig(
        spread_window      = cfg_dict["window"],
        entry_threshold    = cfg_dict["entry"],
        exit_ratio         = cfg_dict["exit_r"],
        risk_pct           = 0.5,
        stop_dist_pct      = 1.0,
        use_case_a         = False,
        use_realistic_cost = False,
        spread_cost_pct    = 0.0,
        exclude_self       = exclude_self,
    )
    engine = LeadLagEngine(data, cfg)
    df_tr  = engine.run()
    if df_tr.empty:
        return {}
    df_tr = df_tr.dropna(subset=["pnl_pct"])
    m = engine.metrics()
    return {"pf": m.get("pf", 0), "total_pnl": m.get("total_pnl", 0)} if m else {}


# ══════════════════════════════════════════════════════════════════════
# チャート生成
# ══════════════════════════════════════════════════════════════════════

def make_pnl_chart(res_inc, res_loo, label):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle(f"IS 累積損益曲線 — {label}", fontproperties=_prop, fontsize=11)

    for ax, res, color, title in zip(
        axes,
        [res_inc, res_loo],
        ["#2266AA", "#CC3333"],
        ["Include-Self", "Leave-One-Out"],
    ):
        ax.set_facecolor("#F5F8FF")
        ax.grid(color="#D8E0F0", lw=0.4)
        if not res or res_inc.get("trades", 0) == 0:
            ax.text(0.5, 0.5, "トレードなし", ha="center", va="center",
                    transform=ax.transAxes, fontproperties=_prop)
        else:
            df = res["df_trades"]
            cum = df["pnl_pct"].cumsum()
            ax.plot(range(len(cum)), cum, color=color, lw=1.5)
            ax.fill_between(range(len(cum)), cum, 0,
                            where=(cum >= 0), color=color, alpha=0.1)
            ax.fill_between(range(len(cum)), cum, 0,
                            where=(cum < 0), color="#CC3333", alpha=0.1)
            ax.axhline(0, color="#888", lw=0.8, ls="--")
        pf  = res.get("pf", 0) if res else 0
        pnl = res.get("total_pnl", 0) if res else 0
        ax.set_title(f"{title}  PF={pf:.3f}  PnL={pnl:+.1f}%",
                     fontproperties=_prop, fontsize=9)
        ax.set_xlabel("トレード番号", fontproperties=_prop)
        ax.set_ylabel("累積PnL (%)", fontproperties=_prop)

    plt.tight_layout()
    out = OUT_DIR / f"pnl_{label}.png"
    plt.savefig(str(out), dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def make_propagation_chart(results_inc, results_loo):
    """Include-Self vs LOO の伝播分類比較（全設定合算）"""
    def agg_prop(results):
        keys = ["prop_Pseudo","prop_Real","prop_Both","prop_Neither"]
        tot = {k: sum(r.get(k, 0) for r in results if r) for k in keys}
        n   = sum(tot.values())
        return {k: v/n*100 if n > 0 else 0 for k, v in tot.items()}, n

    inc_pct, inc_n = agg_prop(results_inc)
    loo_pct, loo_n = agg_prop(results_loo)

    labels = ["Pseudo追随", "Real逆行", "両方", "どちらでも"]
    keys   = ["prop_Pseudo","prop_Real","prop_Both","prop_Neither"]
    colors = ["#2266AA","#CC3333","#FF8800","#888888"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle("スプレッド縮小要因の分類（全設定合算）", fontproperties=_prop, fontsize=11)

    for ax, pct, n, title in zip(
        axes, [inc_pct, loo_pct], [inc_n, loo_n],
        ["Include-Self", "Leave-One-Out"]
    ):
        ax.set_facecolor("#F5F8FF")
        vals = [pct[k] for k in keys]
        bars = ax.bar(labels, vals, color=colors, alpha=0.8, width=0.6)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, v + 0.5,
                    f"{v:.1f}%", ha="center", fontproperties=_prop, fontsize=8)
        ax.set_ylabel("割合 (%)", fontproperties=_prop)
        ax.set_title(f"{title}  (N={n:,})", fontproperties=_prop, fontsize=9)
        ax.set_ylim(0, 100)
        ax.grid(axis="y", color="#D8E0F0", lw=0.4)
        for t in ax.get_xticklabels():
            t.set_fontproperties(_prop)

    plt.tight_layout()
    out = OUT_DIR / "propagation_comparison.png"
    plt.savefig(str(out), dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def make_pf_bar_chart(configs, results_inc, results_loo):
    """設定別PF比較棒グラフ"""
    labels = [c["label"] for c in configs]
    pf_inc = [r.get("pf", 0) if r else 0 for r in results_inc]
    pf_loo = [r.get("pf", 0) if r else 0 for r in results_loo]

    x = np.arange(len(labels))
    w = 0.35

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#F5F8FF"); ax.set_facecolor("#F5F8FF")

    b1 = ax.bar(x - w/2, pf_inc, w, color="#2266AA", alpha=0.8, label="Include-Self")
    b2 = ax.bar(x + w/2, pf_loo, w, color="#CC3333", alpha=0.8, label="Leave-One-Out")

    ax.axhline(1.0, color="#000", lw=1.5, ls="--", label="PF=1.0")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontproperties=_prop, rotation=15, ha="right")
    ax.set_ylabel("PF", fontproperties=_prop)
    ax.set_title("設定別 PF比較: Include-Self vs Leave-One-Out", fontproperties=_prop, fontsize=11)
    ax.legend(prop=_prop)
    ax.grid(axis="y", color="#D8E0F0", lw=0.4)

    for bar, v in zip(list(b1)+list(b2), pf_inc+pf_loo):
        ax.text(bar.get_x()+bar.get_width()/2, v+0.01,
                f"{v:.3f}", ha="center", fontproperties=_prop, fontsize=7)

    plt.tight_layout()
    out = OUT_DIR / "pf_comparison.png"
    plt.savefig(str(out), dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def make_pair_chart(res_inc, res_loo, label):
    """ペア別PnL比較"""
    if not res_inc or not res_loo:
        return None
    ps_inc = res_inc["pair_stats"].set_index("pair")["total_pnl"]
    ps_loo = res_loo["pair_stats"].set_index("pair")["total_pnl"]
    pairs  = sorted(set(ps_inc.index) | set(ps_loo.index))

    x = np.arange(len(pairs)); w = 0.35
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#F5F8FF"); ax.set_facecolor("#F5F8FF")

    ax.bar(x-w/2, [ps_inc.get(p, 0) for p in pairs], w, color="#2266AA", alpha=0.8, label="Include-Self")
    ax.bar(x+w/2, [ps_loo.get(p, 0) for p in pairs], w, color="#CC3333", alpha=0.8, label="Leave-One-Out")
    ax.axhline(0, color="#000", lw=0.8, ls="--")
    ax.set_xticks(x); ax.set_xticklabels(pairs, fontproperties=_prop, rotation=45, ha="right")
    ax.set_ylabel("累積PnL (%)", fontproperties=_prop)
    ax.set_title(f"ペア別成績比較 — {label}", fontproperties=_prop, fontsize=10)
    ax.legend(prop=_prop)
    ax.grid(axis="y", color="#D8E0F0", lw=0.4)

    plt.tight_layout()
    out = OUT_DIR / f"pair_{label}.png"
    plt.savefig(str(out), dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 65)
    print("Include-Self vs Leave-One-Out 比較解析")
    print(f"  IS期間: {IS_START} 〜 {IS_END}")
    print(f"  ペア: {len(ALL_PAIRS)}  設定数: {len(CONFIGS)}")
    print("=" * 65)

    data = load_data()

    results_inc, results_loo = [], []
    nocost_inc, nocost_loo   = [], []
    pnl_charts, pair_charts  = [], []

    for i, cfg in enumerate(CONFIGS, 1):
        print(f"\n[{i}/{len(CONFIGS)}] {cfg['label']}")

        print("  Include-Self ...", end=" ", flush=True)
        r_inc = run_one(data, cfg, exclude_self=False)
        print(f"T={r_inc.get('trades',0)}  PF={r_inc.get('pf',0):.3f}")

        print("  Leave-One-Out ...", end=" ", flush=True)
        r_loo = run_one(data, cfg, exclude_self=True)
        print(f"T={r_loo.get('trades',0)}  PF={r_loo.get('pf',0):.3f}")

        print("  コストなし(Inc) ...", end=" ", flush=True)
        nc_inc = run_nocost(data, cfg, exclude_self=False)
        print(f"PF={nc_inc.get('pf',0):.3f}")

        print("  コストなし(LOO) ...", end=" ", flush=True)
        nc_loo = run_nocost(data, cfg, exclude_self=True)
        print(f"PF={nc_loo.get('pf',0):.3f}")

        results_inc.append(r_inc)
        results_loo.append(r_loo)
        nocost_inc.append(nc_inc)
        nocost_loo.append(nc_loo)

        # チャート
        pc  = make_pnl_chart(r_inc, r_loo, cfg["label"])
        prc = make_pair_chart(r_inc, r_loo, cfg["label"])
        pnl_charts.append(pc)
        pair_charts.append(prc)

    # 全体チャート
    prop_chart = make_propagation_chart(results_inc, results_loo)
    pf_chart   = make_pf_bar_chart(CONFIGS, results_inc, results_loo)

    # 結果をCSV保存
    rows = []
    for cfg, r_inc, r_loo, nc_inc, nc_loo in zip(
            CONFIGS, results_inc, results_loo, nocost_inc, nocost_loo):
        for method, r, nc in [("Include-Self", r_inc, nc_inc), ("LOO", r_loo, nc_loo)]:
            if not r: continue
            rows.append({
                "config":         cfg["label"],
                "method":         method,
                "trades":         r.get("trades",0),
                "win_rate":       r.get("win_rate",0),
                "pf":             r.get("pf",0),
                "total_pnl":      r.get("total_pnl",0),
                "max_dd":         r.get("max_dd",0),
                "spread_reduced": r.get("spread_reduced",0),
                "stop_cnt":       r.get("stop_cnt",0),
                "prop_Pseudo":    r.get("prop_Pseudo",0),
                "prop_Real":      r.get("prop_Real",0),
                "prop_Both":      r.get("prop_Both",0),
                "prop_Neither":   r.get("prop_Neither",0),
                "pf_nocost":      nc.get("pf",0),
                "pnl_nocost":     nc.get("total_pnl",0),
            })
    df_summary = pd.DataFrame(rows)
    df_summary.to_csv(OUT_DIR / "comparison_summary.csv", index=False, encoding="utf-8-sig")

    elapsed = time.time() - t0
    print(f"\n完了: {elapsed:.0f}秒")
    print(f"出力先: {OUT_DIR}")
    print("\n次: python _make_loo_report_pdf.py")

    # サマリー表示
    print("\n=== サマリー ===")
    print(df_summary[["config","method","trades","win_rate","pf",
                       "total_pnl","max_dd","pf_nocost"]].to_string(index=False))


if __name__ == "__main__":
    main()
