# -*- coding: utf-8 -*-
"""
Phase 1: 5分足ファットテール分析
IS期間（2022-2023）の対数リターン確率密度 → ファットテール定義 → 反発率計測

対象: GBPUSD / EURUSD
実行: python _run_fat_tail_analysis.py
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "fat_tail_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
IS_START  = "2022-01-01"; IS_END = "2023-12-31"
TARGETS   = ["GBPUSD", "AUDUSD"]   # EURUSDデータなしのためAUDUSDで代替
PIP       = {"GBPUSD": 0.0001, "EURUSD": 0.0001}

# フィボナッチ水準
FIB_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786]
# ファットテール閾値候補（|対数リターン|の上位X%）
THRESHOLDS = [0.01, 0.02, 0.03, 0.05]   # 1%,2%,3%,5%
# 翌足何本以内に到達したか
MAX_BARS   = [1, 2, 3, 5]

try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except: pass

# ════════════════════════════════════════════════════
# ユーティリティ
# ════════════════════════════════════════════════════
def pip_val(pair): return PIP.get(pair, 0.0001)

def load_5min(pair: str) -> pd.DataFrame:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists():
        raise FileNotFoundError(f"{f}")
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    df = df[(df.index >= IS_START) & (df.index <= IS_END)]
    return df[["Open","High","Low","Close"]].dropna()

# ════════════════════════════════════════════════════
# メイン解析
# ════════════════════════════════════════════════════
all_results = []

for pair in TARGETS:
    print(f"\n{'='*60}")
    print(f"  {pair} — IS期間 5分足ファットテール分析")
    print(f"{'='*60}")

    df = load_5min(pair)
    pip = pip_val(pair)

    # 対数リターン（bar内: Close / Open - 1 の対数）
    log_ret = np.log(df["Close"] / df["Open"])  # 1バー内の動き
    abs_ret = log_ret.abs()

    print(f"バー数: {len(df):,}  期間: {df.index[0]} -> {df.index[-1]}")
    print(f"対数リターン 基本統計:")
    print(f"  平均={log_ret.mean():.6f}  標準偏差={log_ret.std():.6f}")
    print(f"  尖度(excess kurtosis)={log_ret.kurtosis():.2f}  "
          f"（正規分布=0、値が大きいほどファットテール）")

    # ── 確率密度のプロット
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"{pair} IS期間 5分足 対数リターン分布", fontsize=12, fontweight="bold")

    ax = axes[0]
    ax.hist(log_ret, bins=200, density=True, color="#2980b9", alpha=0.6, label="実データ")
    x = np.linspace(log_ret.quantile(0.001), log_ret.quantile(0.999), 500)
    ax.plot(x, stats.norm.pdf(x, log_ret.mean(), log_ret.std()),
            "r--", lw=1.5, label="正規分布")
    for thr in [0.01, 0.02]:
        cut = abs_ret.quantile(1 - thr)
        ax.axvline( cut, color="orange", lw=1, ls="--", alpha=0.8)
        ax.axvline(-cut, color="orange", lw=1, ls="--", alpha=0.8,
                   label=f"上位{thr*100:.0f}%閾値")
    ax.set_title("対数リターン分布（全体）"); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    ax = axes[1]
    ax.hist(log_ret, bins=200, density=True, color="#2980b9", alpha=0.6)
    ax.plot(x, stats.norm.pdf(x, log_ret.mean(), log_ret.std()), "r--", lw=1.5)
    ax.set_xlim(log_ret.quantile(0.001), log_ret.quantile(0.999))
    ax.set_yscale("log"); ax.set_title("対数スケール（ファットテール確認）")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / f"{pair}_return_dist.png", dpi=130, bbox_inches="tight")
    plt.close()

    # ── 各閾値でのファットテール事象を抽出
    print(f"\n  閾値別ファットテール事象数:")
    thr_info = {}
    for thr in THRESHOLDS:
        cut = abs_ret.quantile(1 - thr)
        n_events = (abs_ret > cut).sum()
        n_down   = ((log_ret < -cut)).sum()
        n_up     = ((log_ret >  cut)).sum()
        thr_info[thr] = {"cut": cut, "cut_pips": cut/pip,
                         "n": n_events, "n_down": n_down, "n_up": n_up}
        print(f"    上位{thr*100:.0f}%: |return|>{cut:.5f} "
              f"({cut/pip:.1f}pips)  事象={n_events}件 "
              f"(下落={n_down} 上昇={n_up})")

    # ── フィボナッチ到達率分析
    print(f"\n  フィボナッチ到達率分析:")
    print(f"  {'閾値':>6} {'方向':>6} {'件数':>5} "
          + "".join(f"{'Fib'+str(int(f*1000)):>9}" for f in FIB_LEVELS)
          + "   (最大N本以内)")

    for thr in THRESHOLDS:
        cut    = thr_info[thr]["cut"]
        for direction in ["down", "up"]:
            if direction == "down":
                events = df[log_ret < -cut].index
                label  = "下落"
            else:
                events = df[log_ret > cut].index
                label  = "上昇"

            if len(events) == 0: continue

            # 各フィボ水準 × 最大バー数 の到達率
            fib_reach = {f: {mb: 0 for mb in MAX_BARS} for f in FIB_LEVELS}
            sl_hit    = {mb: 0 for mb in MAX_BARS}
            n_valid   = 0

            for ts in events:
                pos = df.index.get_loc(ts)
                if pos + max(MAX_BARS) + 1 >= len(df): continue
                n_valid += 1

                bar      = df.iloc[pos]
                # エントリー: 極端バー翌足のOpen
                entry_i  = pos + 1
                entry_p  = df.iloc[entry_i]["Open"]

                if direction == "down":
                    # 下落後の買い
                    move     = bar["Open"] - bar["Close"]   # 下落幅
                    targets  = {f: entry_p + f * move for f in FIB_LEVELS}
                    # ストップ: エントリーから move * 0.5 下
                    sl_price = entry_p - move * 0.5
                else:
                    # 上昇後の売り
                    move     = bar["Close"] - bar["Open"]   # 上昇幅
                    targets  = {f: entry_p - f * move for f in FIB_LEVELS}
                    sl_price = entry_p + move * 0.5

                if move <= 0: continue

                for mb in MAX_BARS:
                    end_i = min(entry_i + mb, len(df) - 1)
                    future = df.iloc[entry_i+1 : end_i+1]
                    if len(future) == 0: continue

                    if direction == "down":
                        highs = future["High"].values
                        lows  = future["Low"].values
                        sl_hit[mb] += 1 if np.any(lows <= sl_price) else 0
                        for f, tp in targets.items():
                            if not fib_reach[f][mb]:  # 初回到達のみ
                                pass
                            if np.any(highs >= tp):
                                fib_reach[f][mb] += 1
                    else:
                        lows  = future["Low"].values
                        highs = future["High"].values
                        sl_hit[mb] += 1 if np.any(highs >= sl_price) else 0
                        for f, tp in targets.items():
                            if np.any(lows <= tp):
                                fib_reach[f][mb] += 1

            if n_valid == 0: continue

            # 結果出力（MAX_BARS=3 基準）
            mb_ref = 3
            fib_rates = [fib_reach[f][mb_ref]/n_valid*100 for f in FIB_LEVELS]
            sl_rate   = sl_hit[mb_ref]/n_valid*100
            print(f"  {thr*100:5.0f}%  {label:>6}  {n_valid:5d}  "
                  + "".join(f"{r:8.1f}%" for r in fib_rates)
                  + f"  SL率={sl_rate:.1f}%  (N={mb_ref}本)")

            for mb in MAX_BARS:
                for f in FIB_LEVELS:
                    rate = fib_reach[f][mb] / n_valid * 100 if n_valid > 0 else 0
                    sl_r = sl_hit[mb] / n_valid * 100 if n_valid > 0 else 0
                    all_results.append({
                        "pair":pair,"threshold":thr,"direction":direction,
                        "n":n_valid,"max_bars":mb,"fib":f,
                        "reach_rate":round(rate,2),"sl_rate":round(sl_r,2),
                        "cut_pips":round(thr_info[thr]["cut_pips"],1),
                    })

    # ── 最大バー数別の比較グラフ
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{pair} IS期間 — フィボナッチ到達率 vs 閾値・保有バー数",
                 fontsize=11, fontweight="bold")
    colors = ["#2980b9","#27ae60","#e74c3c","#8e44ad"]
    for ax_i, mb in enumerate(MAX_BARS):
        ax = axes[ax_i//2][ax_i%2]
        for d_i, direction in enumerate(["down", "up"]):
            label_d = "下落後買い" if direction=="down" else "上昇後売り"
            for t_i, thr in enumerate(THRESHOLDS):
                sub = [r for r in all_results
                       if r["pair"]==pair and r["direction"]==direction
                       and r["max_bars"]==mb and r["threshold"]==thr]
                if not sub: continue
                rates = [next((s["reach_rate"] for s in sub if s["fib"]==f), 0)
                         for f in FIB_LEVELS]
                ls = "-" if direction=="down" else "--"
                ax.plot([f*100 for f in FIB_LEVELS], rates,
                        marker="o", markersize=5, linewidth=1.5,
                        color=colors[t_i], ls=ls,
                        label=f"{label_d} {thr*100:.0f}%閾")
        ax.set_title(f"最大{mb}本以内到達率"); ax.set_xlabel("Fibonacci水準(%)")
        ax.set_ylabel("到達率(%)"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
        ax.set_xticks([f*100 for f in FIB_LEVELS])
    plt.tight_layout()
    plt.savefig(OUT_DIR / f"{pair}_fib_reach_rate.png", dpi=130, bbox_inches="tight")
    plt.close()
    print(f"\n  グラフ保存: {pair}_fib_reach_rate.png")

# ── CSV保存
df_results = pd.DataFrame(all_results)
df_results.to_csv(OUT_DIR / "fat_tail_results.csv", index=False, encoding="utf-8-sig")

# ── 総括サマリー
print(f"\n{'='*70}")
print("総括: 下落後買い / 翌3本以内 / フィボ到達率 上位ランキング")
print(f"{'='*70}")
summary = df_results[
    (df_results["direction"]=="down") & (df_results["max_bars"]==3)
].sort_values("reach_rate", ascending=False)
print(f"{'ペア':>8} {'閾値':>6} {'Fib':>6} {'到達率':>8} {'SL率':>7} {'件数':>6}")
print("-"*50)
for _,r in summary.head(20).iterrows():
    print(f"{r['pair']:>8} {r['threshold']*100:5.0f}%  "
          f"{r['fib']*100:5.1f}%  {r['reach_rate']:7.1f}%  "
          f"{r['sl_rate']:6.1f}%  {r['n']:6d}")

print(f"\n結果CSV: {OUT_DIR/'fat_tail_results.csv'}")
print("完了")
