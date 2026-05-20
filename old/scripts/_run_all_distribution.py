# -*- coding: utf-8 -*-
"""
12通貨ペア  対数変化率の分布比較  ─  全ペア版
_analyze_return_distribution.py をベースに全12ペアへ展開。
同じ make_chart / kde_curve ロジックを使用。
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.gridspec as gridspec

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass
_p8  = fm.FontProperties(fname=FONT_PATH, size=8)
_p9  = fm.FontProperties(fname=FONT_PATH, size=9)
_p10 = fm.FontProperties(fname=FONT_PATH, size=10)
_p11 = fm.FontProperties(fname=FONT_PATH, size=11)

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "distribution_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))
from fx_market_classifier.features import log_returns, currency_strength
from fx_market_classifier.config   import PAIR_CURRENCIES

ALL_PAIRS = list(PAIR_CURRENCIES.keys())
START  = "2022-01-01"
END    = "2024-12-31"
WINDOW = 6

# ── データ読み込み ───────────────────────────────────────────
print("データ読み込み中...")
raw_data = {}
for p in ALL_PAIRS:
    f = DATA_DIR / f"{p}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    raw_data[p] = df.loc[START:END]
print(f"  読込ペア数: {len(raw_data)}")

# 全ペアの log returns を事前計算
all_returns = {p: log_returns(df["Close"]) for p,df in raw_data.items()}

# ── LOO 強弱差を計算（ペアごとに当該ペアを除外） ─────────────
def compute_cum_spread_loo(target: str, window: int = WINDOW) -> pd.Series:
    """対象ペアを LOO 除外した通貨強弱差の rolling sum。
    除外後に base/quote が消える場合は全ペアで計算（CHFJPYのCHFなど）。"""
    base, quote = PAIR_CURRENCIES[target]
    returns_loo = {p: r for p, r in all_returns.items() if p != target}
    st_loo = currency_strength(returns_loo, PAIR_CURRENCIES)

    if base not in st_loo.columns or quote not in st_loo.columns:
        # フォールバック: LOO除外せず全ペアで計算
        st_full = currency_strength(all_returns, PAIR_CURRENCIES)
        diff = (st_full[base] - st_full[quote]).reindex(all_returns[target].index)
    else:
        diff = (st_loo[base] - st_loo[quote]).reindex(all_returns[target].index)

    return diff.rolling(window, min_periods=1).sum()

# ── 統計モーメント ────────────────────────────────────────────
def moments(x: np.ndarray, label: str) -> dict:
    return {
        "label": label, "n": len(x),
        "mean": float(np.mean(x)),
        "std":  float(np.std(x, ddof=1)),
        "skewness": float(stats.skew(x)),
        "kurtosis": float(stats.kurtosis(x)),
        "p5":  float(np.percentile(x, 5)),
        "p95": float(np.percentile(x, 95)),
    }

# ── KDE 曲線計算 ─────────────────────────────────────────────
def kde_curve(arr, x_range, bandwidth=None):
    """arr は小数単位（×100 して % に）、x_range は % 単位"""
    from scipy.stats import gaussian_kde
    arr_clean = arr[np.isfinite(arr)]
    if len(arr_clean) < 10:
        return x_range, np.zeros_like(x_range)
    kde = gaussian_kde(arr_clean * 100, bw_method=bandwidth)
    return x_range, kde(x_range)

# ── チャート描画（既存 make_chart を汎化） ────────────────────
def make_chart(pair, base_c, quote_c,
               ret_all, ret_top10, ret_top5,
               ret_pos10, ret_neg10,
               mom_all, mom_top10, mom_top5,
               mom_pos10, mom_neg10):

    fig = plt.figure(figsize=(20, 16))
    fig.patch.set_facecolor("#FAFBFF")
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.50, wspace=0.38)

    SPECS = {
        "all":   ("#2266AA", f"全期間（3年）",                  0.30),
        "top10": ("#FF8800", "|強弱差| 上位10%",                0.60),
        "top5":  ("#CC3333", "|強弱差| 上位5%",                 0.85),
        "pos10": ("#22AA66", f"{base_c}強 上位10%（正の強弱差）", 0.75),
        "neg10": ("#9933CC", f"{quote_c}強 上位10%（負の強弱差）",0.75),
    }

    moms   = [mom_all, mom_top10, mom_top5, mom_pos10, mom_neg10]
    keys   = ["all", "top10", "top5", "pos10", "neg10"]
    arrays = [ret_all, ret_top10, ret_top5, ret_pos10, ret_neg10]
    labels_short = ["全期間", "|強弱|\n上位10%", "|強弱|\n上位5%",
                    f"{base_c}強\n上位10%", f"{quote_c}強\n上位10%"]

    xlim = (-0.12, 0.12)
    x_ref = np.linspace(*xlim, 500)

    # ── パネル1: KDE 比較（全期間 vs |強弱差|大） ─────────────
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.set_facecolor("#F0F4FF"); ax1.grid(color="#C8D4F0", lw=0.5, alpha=0.8)

    for key, arr in [("all", ret_all), ("top10", ret_top10), ("top5", ret_top5)]:
        c, lbl, alpha = SPECS[key]
        idx = keys.index(key)
        xk, yk = kde_curve(arr, x_ref)
        ax1.fill_between(xk, yk, alpha=alpha*0.35, color=c)
        ax1.plot(xk, yk, color=c, lw=2.0 if key=="all" else 2.5,
                 label=f"{lbl}  σ={moms[idx]['std']*100:.4f}%")
        mu = moms[idx]["mean"] * 100
        ax1.axvline(mu, color=c, lw=1.2, ls="--", alpha=0.8)

    mu_all = mom_all["mean"]*100; sd_all = mom_all["std"]*100
    ax1.axvspan(mu_all-sd_all, mu_all+sd_all, alpha=0.06, color="#2266AA",
                label=f"全期間 ±1σ（{mu_all-sd_all:.4f}〜{mu_all+sd_all:.4f}%）")
    ax1.set_xlim(*xlim)
    ax1.set_xlabel("対数変化率（%）", fontproperties=_p9)
    ax1.set_ylabel("確率密度", fontproperties=_p9)
    ax1.set_title(f"{pair} 対数変化率の分布比較\n"
                  f"全期間（青）vs |通貨強弱差| 上位10%（橙）・5%（赤）",
                  fontproperties=_p11, fontsize=12, pad=8)
    ax1.legend(prop=_p8, loc="upper right", framealpha=0.9)
    ax1.axvline(0, color="#333", lw=1.0, ls="-", alpha=0.5)

    # ── パネル2: 方向別比較 ──────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.set_facecolor("#F0F4FF"); ax2.grid(color="#C8D4F0", lw=0.5, alpha=0.8)

    for key, arr in [("all", ret_all), ("pos10", ret_pos10), ("neg10", ret_neg10)]:
        c, lbl, alpha = SPECS[key]
        idx = keys.index(key)
        xk, yk = kde_curve(arr, x_ref)
        ax2.fill_between(xk, yk, alpha=alpha*0.35, color=c)
        ax2.plot(xk, yk, color=c, lw=2.0, label=lbl)
        mu = moms[idx]["mean"] * 100
        ax2.axvline(mu, color=c, lw=1.2, ls="--", alpha=0.8)

    ax2.set_xlim(*xlim)
    ax2.set_xlabel("対数変化率（%）", fontproperties=_p9)
    ax2.set_ylabel("確率密度", fontproperties=_p9)
    ax2.set_title(f"方向別比較\n{base_c}強（緑）vs {quote_c}強（紫）",
                  fontproperties=_p9, fontsize=9)
    ax2.legend(prop=_p8)
    ax2.axvline(0, color="#333", lw=1.0, ls="-", alpha=0.5)

    # ── パネル3: 統計モーメントテーブル ─────────────────────
    ax3 = fig.add_subplot(gs[1, :])
    ax3.axis("off")
    cols = ["条件", "n", "平均\n(×10⁻⁴)", "標準偏差\n(×10⁻⁴)",
            "歪度\n(Skewness)", "超過尖度\n(Kurtosis)", "5%分位", "95%分位", "t検定 p値"]

    # t検定（各条件 vs 全期間）
    pvals = [None]
    for arr in [ret_top10, ret_top5, ret_pos10, ret_neg10]:
        if len(arr) < 30:
            pvals.append(np.nan)
        else:
            _, p = stats.ttest_ind(ret_all, arr, equal_var=False)
            pvals.append(p)

    rows = []
    for i, m in enumerate(moms):
        pv = pvals[i]
        pv_str = "—" if pv is None else (f"{pv:.4f}" + (" ★有意" if pv<0.05 else " ns"))
        rows.append([
            m["label"], f"{m['n']:,}",
            f"{m['mean']*10000:+.4f}", f"{m['std']*10000:.4f}",
            f"{m['skewness']:+.4f}", f"{m['kurtosis']:+.1f}",
            f"{m['p5']*100:.4f}%", f"{m['p95']*100:.4f}%",
            pv_str,
        ])

    bg_row = ["#EEF3FF","#FFF3E0","#FFEBEE","#E8F5E9","#F3E5F3"]
    cell_colors = [[bg_row[i]]*len(cols) for i in range(len(rows))]
    tbl = ax3.table(cellText=rows, colLabels=cols, cellLoc="center",
                    loc="center", cellColours=cell_colors)
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1, 2.0)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1A3A7A")
            cell.set_text_props(color="white", fontsize=8.5)
        cell.set_edgecolor("#AABBCC")
    ax3.set_title("統計モーメント比較（次バーの対数変化率）",
                  fontproperties=_p10, fontsize=11, pad=12)

    # ── パネル4: 標準偏差 ────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.set_facecolor("#F0F4FF"); ax4.grid(color="#C8D4F0", lw=0.5, axis="y")
    stds  = [m["std"]*10000 for m in moms]
    clrs  = [SPECS[k][0] for k in keys]
    bars4 = ax4.bar(range(len(labels_short)), stds, color=clrs,
                    alpha=0.85, width=0.6, edgecolor="white", lw=0.8)
    ax4.set_xticks(range(len(labels_short)))
    ax4.set_xticklabels(labels_short, fontproperties=_p8, fontsize=8)
    ax4.set_title("標準偏差（ボラティリティ）×10⁻⁴\n★強弱差が大きいとボラが1.5〜2倍に拡大",
                  fontproperties=_p9, fontsize=8.5)
    ax4.set_ylabel("標準偏差 ×10⁻⁴", fontproperties=_p8)
    for bar, v in zip(bars4, stds):
        ax4.text(bar.get_x()+bar.get_width()/2, v+0.05,
                 f"{v:.2f}", ha="center", fontproperties=_p8,
                 fontsize=9, fontweight="bold")
    ax4.axhline(stds[0], color="#2266AA", lw=1.5, ls="--", alpha=0.7,
                label=f"全期間 σ={stds[0]:.2f}"); ax4.legend(prop=_p8)

    # ── パネル5: 歪度 ────────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.set_facecolor("#F0F4FF"); ax5.grid(color="#C8D4F0", lw=0.5, axis="y")
    skews = [m["skewness"] for m in moms]
    bars5 = ax5.bar(range(len(labels_short)), skews, color=clrs,
                    alpha=0.85, width=0.6, edgecolor="white", lw=0.8)
    ax5.axhline(0, color="#333", lw=1.0, ls="--")
    ax5.set_xticks(range(len(labels_short)))
    ax5.set_xticklabels(labels_short, fontproperties=_p8, fontsize=8)
    ax5.set_title("歪度（Skewness）\n負=左裾が厚い（下落リスク大）",
                  fontproperties=_p9, fontsize=8.5)
    for bar, v in zip(bars5, skews):
        offset = 0.04 if v >= 0 else -0.08
        ax5.text(bar.get_x()+bar.get_width()/2, v+offset,
                 f"{v:+.3f}", ha="center", fontproperties=_p8,
                 fontsize=9, fontweight="bold")

    # ── パネル6: 超過尖度 ────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, 2])
    ax6.set_facecolor("#F0F4FF"); ax6.grid(color="#C8D4F0", lw=0.5, axis="y")
    kurts = [max(m["kurtosis"], 0.1) for m in moms]
    bars6 = ax6.bar(range(len(labels_short)), kurts, color=clrs,
                    alpha=0.85, width=0.6, edgecolor="white", lw=0.8)
    ax6.set_yscale("log")
    ax6.axhline(3, color="#333", lw=1.0, ls="--", alpha=0.5, label="正規分布=3")
    ax6.set_xticks(range(len(labels_short)))
    ax6.set_xticklabels(labels_short, fontproperties=_p8, fontsize=8)
    ax6.set_title("超過尖度（対数スケール）\n★全期間は極端なファットテール",
                  fontproperties=_p9, fontsize=8.5)
    ax6.legend(prop=_p8)
    for bar, v in zip(bars6, kurts):
        ax6.text(bar.get_x()+bar.get_width()/2, v*1.15,
                 f"{v:.0f}", ha="center", fontproperties=_p8,
                 fontsize=9, fontweight="bold")

    fig.text(0.5, 0.005,
             f"Dukascopy 5分足 {pair}  {START}〜{END}  |  "
             f"通貨強弱差: LOO方式（cum_spread window={WINDOW}）  |  "
             "条件付き分布 = 大きな強弱差の次バーリターン",
             ha="center", fontproperties=_p8, color="#666", fontsize=8)

    out = OUT_DIR / f"return_distribution_{pair.lower()}.png"
    plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    return out

# ── 全ペア実行 ──────────────────────────────────────────────
print("\n全ペア分析開始...\n")
summary_rows = []

for pair in ALL_PAIRS:
    if pair not in raw_data:
        print(f"  [{pair}] データなし → スキップ"); continue

    base_c, quote_c = PAIR_CURRENCIES[pair]
    print(f"[{pair}]  {base_c}/{quote_c}", end="  ")

    # LOO 強弱差（累積）
    cum_spread = compute_cum_spread_loo(pair)

    # 対数変化率
    ret_series = log_returns(raw_data[pair]["Close"]).dropna()

    # cum_spread と ret_series を整合
    cum_spread = cum_spread.reindex(ret_series.index).dropna()
    ret_aligned = ret_series.reindex(cum_spread.index).dropna()

    # 次バーのリターン
    ret_next     = ret_aligned.shift(-1).dropna()
    cs_for_next  = cum_spread.reindex(ret_next.index)
    abs_cs       = cs_for_next.abs()

    q90 = abs_cs.quantile(0.90)
    q95 = abs_cs.quantile(0.95)

    ret_all   = ret_aligned.values
    ret_top10 = ret_next[abs_cs >= q90].values
    ret_top5  = ret_next[abs_cs >= q95].values
    ret_pos10 = ret_next[cs_for_next >= q90].values    # base強
    ret_neg10 = ret_next[cs_for_next <= -q90].values   # quote強

    print(f"n={len(ret_all):,}  top10={len(ret_top10):,}  "
          f"pos={len(ret_pos10):,}  neg={len(ret_neg10):,}")

    mom_all   = moments(ret_all,   f"全期間（3年）")
    mom_top10 = moments(ret_top10, "|強弱差| 上位10%")
    mom_top5  = moments(ret_top5,  "|強弱差| 上位5%")
    mom_pos10 = moments(ret_pos10, f"{base_c}強 上位10%（正の強弱差）")
    mom_neg10 = moments(ret_neg10, f"{quote_c}強 上位10%（負の強弱差）")

    out = make_chart(pair, base_c, quote_c,
                     ret_all, ret_top10, ret_top5,
                     ret_pos10, ret_neg10,
                     mom_all, mom_top10, mom_top5,
                     mom_pos10, mom_neg10)
    print(f"  → 保存: {out.name}")

    # サマリー
    for key, m in [("全期間",mom_all),("|強弱差|上位10%",mom_top10),
                   ("|強弱差|上位5%",mom_top5),(f"{base_c}強",mom_pos10),
                   (f"{quote_c}強",mom_neg10)]:
        summary_rows.append({"pair":pair,"base":base_c,"quote":quote_c,
                              "condition":key,**m})

pd.DataFrame(summary_rows).to_csv(
    OUT_DIR/"summary_all_pairs.csv", index=False, encoding="utf-8-sig")

print(f"\n保存先: {OUT_DIR}")
print("完了")
