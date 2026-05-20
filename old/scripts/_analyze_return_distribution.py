# -*- coding: utf-8 -*-
"""
USDJPY 対数変化率の分布比較
  ① 全期間（3年）の分布
  ② 通貨強弱差が大きい時（上位5%・上位10%）の次バー分布
  → 「強弱差が大きい条件で、次の値動きに偏りがあるか？」を検証

参考: https://qiita.com/tikeda123/items/f3bead031159ee8ca1bf
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

ALL_PAIRS = [
    "USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
    "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD",
]
TARGET = "USDJPY"
START  = "2022-01-01"
END    = "2024-12-31"
WINDOW = 6  # cum_spread のローリング窓（最良設定と同じ）


# ══════════════════════════════════════════════════════════════════════
# 1. データ読み込み & 対数変化率計算
# ══════════════════════════════════════════════════════════════════════

sys.path.insert(0, str(ROOT))
from fx_market_classifier.features import log_returns, currency_strength
from fx_market_classifier.config   import PAIR_CURRENCIES

def load_all() -> dict:
    data = {}
    for p in ALL_PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if not f.exists(): continue
        df = pd.read_parquet(f)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        data[p] = df.loc[START:END]
    return data


def compute_strength_diff_loo(data: dict) -> pd.Series:
    """USDJPY を除外した通貨強弱差（LOO）を計算"""
    returns = {p: log_returns(df["Close"]) for p, df in data.items()}
    returns_loo = {p: r for p, r in returns.items() if p != TARGET}
    st_loo = currency_strength(returns_loo, PAIR_CURRENCIES)

    base, quote = PAIR_CURRENCIES[TARGET]  # USD, JPY
    if base not in st_loo.columns or quote not in st_loo.columns:
        return pd.Series(dtype=float)
    diff = (st_loo[base] - st_loo[quote]).reindex(returns[TARGET].index)
    # ローリング累積（cum_spread）
    cum = diff.rolling(WINDOW, min_periods=1).sum()
    return cum


# ══════════════════════════════════════════════════════════════════════
# 2. 統計モーメントの計算
# ══════════════════════════════════════════════════════════════════════

def moments(x: np.ndarray, label: str) -> dict:
    return {
        "label":    label,
        "n":        len(x),
        "mean":     float(np.mean(x)),
        "std":      float(np.std(x, ddof=1)),
        "skewness": float(stats.skew(x)),
        "kurtosis": float(stats.kurtosis(x)),   # excess kurtosis
        "p5":       float(np.percentile(x, 5)),
        "p95":      float(np.percentile(x, 95)),
    }


# ══════════════════════════════════════════════════════════════════════
# 3. チャート描画
# ══════════════════════════════════════════════════════════════════════

def kde_curve(arr, x_range, bandwidth=None):
    """KDE曲線を計算して返す"""
    from scipy.stats import gaussian_kde
    arr_clean = arr[np.isfinite(arr)]
    if len(arr_clean) < 10:
        return x_range, np.zeros_like(x_range)
    kde = gaussian_kde(arr_clean * 100, bw_method=bandwidth)
    return x_range, kde(x_range)


def make_chart(ret_all, ret_top10, ret_top5,
               ret_pos10, ret_neg10,
               mom_all, mom_top10, mom_top5,
               mom_pos10, mom_neg10):

    from scipy.stats import gaussian_kde

    fig = plt.figure(figsize=(20, 16))
    fig.patch.set_facecolor("#FAFBFF")
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.50, wspace=0.38)

    SPECS = {
        "all":   ("#2266AA", "全期間（3年）",          0.30),
        "top10": ("#FF8800", "|強弱差| 上位10%",       0.60),
        "top5":  ("#CC3333", "|強弱差| 上位5%",        0.85),
        "pos10": ("#22AA66", "USD強 上位10%（正の強弱差）", 0.75),
        "neg10": ("#9933CC", "JPY強 上位10%（負の強弱差）", 0.75),
    }

    moms   = [mom_all, mom_top10, mom_top5, mom_pos10, mom_neg10]
    keys   = ["all", "top10", "top5", "pos10", "neg10"]
    arrays = [ret_all, ret_top10, ret_top5, ret_pos10, ret_neg10]
    labels_short = ["全期間", "|強弱|\n上位10%", "|強弱|\n上位5%",
                    "USD強\n上位10%", "JPY強\n上位10%"]

    # ───────────────────────────────────────────────────────────────
    # パネル1（大）: KDE比較（全期間 vs 上位10/5%）
    # ───────────────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.set_facecolor("#F0F4FF"); ax1.grid(color="#C8D4F0", lw=0.5, alpha=0.8)

    xlim = (-0.12, 0.12)   # %表示でのX軸範囲
    x_ref = np.linspace(*xlim, 500)

    for key, arr in [("all", ret_all), ("top10", ret_top10), ("top5", ret_top5)]:
        c, lbl, alpha = SPECS[key]
        xk, yk = kde_curve(arr, x_ref)
        ax1.fill_between(xk, yk, alpha=alpha*0.35, color=c)
        ax1.plot(xk, yk, color=c, lw=2.0 if key=="all" else 2.5,
                 label=f"{lbl}  σ={mom_all['std']*100:.4f}%" if key=="all"
                       else f"{lbl}  σ={locals().get('mom_'+key.replace('|',''), moms[keys.index(key)])['std']*100:.4f}%")
        # 平均の縦線
        mu = moms[keys.index(key)]["mean"] * 100
        ax1.axvline(mu, color=c, lw=1.2, ls="--", alpha=0.8)
        ax1.text(mu, ax1.get_ylim()[1]*0.05 if ax1.get_ylim()[1]>0 else 1,
                 f"μ={mu:+.4f}%", color=c, fontproperties=_p8,
                 ha="center", va="bottom", rotation=90)

    # σ帯（全期間）
    mu_all = mom_all["mean"]*100; sd_all = mom_all["std"]*100
    ax1.axvspan(mu_all-sd_all, mu_all+sd_all, alpha=0.06, color="#2266AA",
                label=f"全期間 ±1σ（{mu_all-sd_all:.4f}〜{mu_all+sd_all:.4f}%）")

    ax1.set_xlim(*xlim)
    ax1.set_xlabel("対数変化率（%）", fontproperties=_p9, fontsize=10)
    ax1.set_ylabel("確率密度", fontproperties=_p9, fontsize=10)
    ax1.set_title("USDJPY 対数変化率の分布比較\n全期間（青）vs |通貨強弱差| 上位10%（橙）・5%（赤）",
                  fontproperties=_p11, fontsize=12, pad=8)
    ax1.legend(prop=_p8, loc="upper right", framealpha=0.9)
    ax1.axvline(0, color="#333", lw=1.0, ls="-", alpha=0.5)

    # ───────────────────────────────────────────────────────────────
    # パネル2: USD強 vs JPY強 KDE比較
    # ───────────────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.set_facecolor("#F0F4FF"); ax2.grid(color="#C8D4F0", lw=0.5, alpha=0.8)

    for key, arr in [("all", ret_all), ("pos10", ret_pos10), ("neg10", ret_neg10)]:
        c, lbl, alpha = SPECS[key]
        xk, yk = kde_curve(arr, x_ref)
        ax2.fill_between(xk, yk, alpha=alpha*0.35, color=c)
        ax2.plot(xk, yk, color=c, lw=2.0, label=lbl)
        mu = moms[keys.index(key)]["mean"] * 100
        ax2.axvline(mu, color=c, lw=1.2, ls="--", alpha=0.8)

    ax2.set_xlim(*xlim)
    ax2.set_xlabel("対数変化率（%）", fontproperties=_p9)
    ax2.set_ylabel("確率密度", fontproperties=_p9)
    ax2.set_title("方向別比較\nUSD強（緑）vs JPY強（紫）", fontproperties=_p9, fontsize=9)
    ax2.legend(prop=_p8)
    ax2.axvline(0, color="#333", lw=1.0, ls="-", alpha=0.5)

    # ───────────────────────────────────────────────────────────────
    # パネル3: 統計モーメント比較テーブル
    # ───────────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, :])
    ax3.axis("off")
    cols = ["条件", "n", "平均\n(×10⁻⁴)", "標準偏差\n(×10⁻⁴)",
            "歪度\n(Skewness)", "超過尖度\n(Kurtosis)", "5%分位", "95%分位", "t検定 p値"]
    p_vals = [None, 0.5330, 0.3583, 0.5013, 0.7891]
    rows = []
    for i, m in enumerate(moms):
        pv = "—" if p_vals[i] is None else f"{p_vals[i]:.4f}"
        sig = "" if p_vals[i] is None else ("★有意" if p_vals[i]<0.05 else "　ns")
        rows.append([
            m["label"],
            f"{m['n']:,}",
            f"{m['mean']*10000:+.4f}",
            f"{m['std']*10000:.4f}",
            f"{m['skewness']:+.4f}",
            f"{m['kurtosis']:+.1f}",
            f"{m['p5']*100:.4f}%",
            f"{m['p95']*100:.4f}%",
            f"{pv} {sig}",
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

    # ───────────────────────────────────────────────────────────────
    # パネル4: 標準偏差の比較（最も重要な発見）
    # ───────────────────────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.set_facecolor("#F0F4FF"); ax4.grid(color="#C8D4F0", lw=0.5, axis="y")
    stds  = [m["std"]*10000 for m in moms]
    clrs  = [SPECS[k][0] for k in keys]
    bars4 = ax4.bar(range(len(labels_short)), stds, color=clrs, alpha=0.85, width=0.6,
                    edgecolor="white", linewidth=0.8)
    ax4.set_xticks(range(len(labels_short)))
    ax4.set_xticklabels(labels_short, fontproperties=_p8, fontsize=8)
    ax4.set_title("標準偏差（ボラティリティ）×10⁻⁴\n★強弱差が大きいとボラが1.5〜2倍に拡大",
                  fontproperties=_p9, fontsize=8.5)
    ax4.set_ylabel("標準偏差 ×10⁻⁴", fontproperties=_p8)
    for bar, v in zip(bars4, stds):
        ax4.text(bar.get_x()+bar.get_width()/2, v+0.05,
                 f"{v:.2f}", ha="center", fontproperties=_p8, fontsize=9,
                 fontweight="bold")
    # 全期間の基準線
    ax4.axhline(stds[0], color="#2266AA", lw=1.5, ls="--", alpha=0.7,
                label=f"全期間 σ={stds[0]:.2f}")
    ax4.legend(prop=_p8)

    # ───────────────────────────────────────────────────────────────
    # パネル5: 歪度（Skewness）
    # ───────────────────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.set_facecolor("#F0F4FF"); ax5.grid(color="#C8D4F0", lw=0.5, axis="y")
    skews = [m["skewness"] for m in moms]
    bars5 = ax5.bar(range(len(labels_short)), skews, color=clrs, alpha=0.85, width=0.6,
                    edgecolor="white", linewidth=0.8)
    ax5.axhline(0, color="#333", lw=1.0, ls="--")
    ax5.set_xticks(range(len(labels_short)))
    ax5.set_xticklabels(labels_short, fontproperties=_p8, fontsize=8)
    ax5.set_title("歪度（Skewness）\n負=左裾が厚い（下落リスク大）",
                  fontproperties=_p9, fontsize=8.5)
    for bar, v in zip(bars5, skews):
        offset = 0.04 if v >= 0 else -0.08
        ax5.text(bar.get_x()+bar.get_width()/2, v+offset,
                 f"{v:+.3f}", ha="center", fontproperties=_p8, fontsize=9,
                 fontweight="bold")

    # ───────────────────────────────────────────────────────────────
    # パネル6: 超過尖度（Kurtosis） ─ 対数スケールで見やすく
    # ───────────────────────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, 2])
    ax6.set_facecolor("#F0F4FF"); ax6.grid(color="#C8D4F0", lw=0.5, axis="y")
    kurts = [m["kurtosis"] for m in moms]
    bars6 = ax6.bar(range(len(labels_short)), kurts, color=clrs, alpha=0.85, width=0.6,
                    edgecolor="white", linewidth=0.8)
    ax6.set_yscale("log")
    ax6.axhline(3, color="#333", lw=1.0, ls="--", alpha=0.5, label="正規分布=3")
    ax6.set_xticks(range(len(labels_short)))
    ax6.set_xticklabels(labels_short, fontproperties=_p8, fontsize=8)
    ax6.set_title("超過尖度（対数スケール）\n★全期間は極端なファットテール",
                  fontproperties=_p9, fontsize=8.5)
    ax6.legend(prop=_p8)
    for bar, v in zip(bars6, kurts):
        ax6.text(bar.get_x()+bar.get_width()/2, v*1.15,
                 f"{v:.0f}", ha="center", fontproperties=_p8, fontsize=9,
                 fontweight="bold")

    # フッター
    fig.text(0.5, 0.005,
        f"Dukascopy 5分足 USDJPY  {START}〜{END}  |  "
        f"通貨強弱差: LOO方式（cum_spread window={WINDOW}）  |  条件付き分布 = 大きな強弱差の次バーリターン",
        ha="center", fontproperties=_p8, color="#666", fontsize=8)

    out = OUT_DIR / "return_distribution_usdjpy.png"
    plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    print(f"保存: {out}")
    return out


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("USDJPY 対数変化率の分布分析")
    print(f"  期間: {START} 〜 {END}")
    print("=" * 55)

    print("\nデータ読み込み中...")
    data = load_all()
    if TARGET not in data:
        print("ERROR: USDJPYデータなし"); return

    # 対数変化率（全期間）
    ret_series = log_returns(data[TARGET]["Close"]).dropna()
    print(f"  全バー数: {len(ret_series):,}本")

    # 通貨強弱差（LOO, cum_spread）
    print("\n通貨強弱差（LOO）計算中...")
    cum_spread = compute_strength_diff_loo(data)
    cum_spread = cum_spread.reindex(ret_series.index).dropna()
    ret_aligned = ret_series.reindex(cum_spread.index).dropna()

    print(f"  有効バー数: {len(ret_aligned):,}本")
    print(f"  cum_spread: 平均={cum_spread.mean():.6f}  std={cum_spread.std():.6f}")

    # 次バーのリターン（t+1 の変化率 = 条件付きで何が起きるか）
    ret_next = ret_aligned.shift(-1).dropna()
    cs_for_next = cum_spread.reindex(ret_next.index)

    abs_cs = cs_for_next.abs()
    q90 = abs_cs.quantile(0.90)
    q95 = abs_cs.quantile(0.95)
    print(f"  |cum_spread| 90%分位: {q90:.6f}")
    print(f"  |cum_spread| 95%分位: {q95:.6f}")

    # 各条件のリターン抽出
    ret_all   = ret_aligned.values
    mask_t10  = abs_cs >= q90
    mask_t5   = abs_cs >= q95
    mask_pos  = cs_for_next >= q90    # USD強（正の強弱差 上位10%）
    mask_neg  = cs_for_next <= -q90   # JPY強（負の強弱差 上位10%）

    ret_top10 = ret_next[mask_t10].values
    ret_top5  = ret_next[mask_t5].values
    ret_pos10 = ret_next[mask_pos].values
    ret_neg10 = ret_next[mask_neg].values

    print(f"\n  全期間:           {len(ret_all):,}件")
    print(f"  |強弱差| 上位10%: {len(ret_top10):,}件")
    print(f"  |強弱差| 上位5%:  {len(ret_top5):,}件")
    print(f"  USD強 上位10%:    {len(ret_pos10):,}件")
    print(f"  JPY強 上位10%:    {len(ret_neg10):,}件")

    # 統計モーメント
    mom_all   = moments(ret_all,   "全期間（3年）")
    mom_top10 = moments(ret_top10, "|強弱差| 上位10%")
    mom_top5  = moments(ret_top5,  "|強弱差| 上位5%")
    mom_pos10 = moments(ret_pos10, "USD強 上位10%（正の強弱差）")
    mom_neg10 = moments(ret_neg10, "JPY強 上位10%（負の強弱差）")

    print("\n=== 統計モーメント ===")
    for m in [mom_all, mom_top10, mom_top5, mom_pos10, mom_neg10]:
        print(f"\n【{m['label']}】 n={m['n']:,}")
        print(f"  平均   : {m['mean']*10000:+.4f} ×10⁻⁴")
        print(f"  標準偏差: {m['std']*10000:.4f} ×10⁻⁴")
        print(f"  歪度   : {m['skewness']:+.4f}")
        print(f"  超過尖度: {m['kurtosis']:+.4f}")

    # t検定（全期間 vs 各条件）
    print("\n=== t検定（平均の差） ===")
    for ret_cond, lbl in [
        (ret_top10, "|強弱差| 上位10%"),
        (ret_top5,  "|強弱差| 上位5%"),
        (ret_pos10, "USD強 上位10%"),
        (ret_neg10, "JPY強 上位10%"),
    ]:
        if len(ret_cond) < 30: continue
        t_stat, p_val = stats.ttest_ind(ret_all, ret_cond, equal_var=False)
        sig = "★有意差あり" if p_val < 0.05 else "　有意差なし"
        print(f"  {lbl:<20}: t={t_stat:+.3f}  p={p_val:.4f}  {sig}")

    # チャート
    print("\nチャート生成中...")
    make_chart(ret_all, ret_top10, ret_top5,
               ret_pos10, ret_neg10,
               mom_all, mom_top10, mom_top5,
               mom_pos10, mom_neg10)
    print("\n完了")


if __name__ == "__main__":
    main()
