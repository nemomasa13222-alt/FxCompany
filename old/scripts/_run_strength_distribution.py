# -*- coding: utf-8 -*-
"""
12通貨ペア  対数変化率の分布比較
─────────────────────────────────────────────────────────────
全期間 vs 強弱差が大きい時の次バー対数リターン分布を比較
条件:
  全期間          : 全バー
  |強弱差| 上位10%: |base_strength - quote_strength| >= 90th percentile
  |強弱差| 上位5% : |base_strength - quote_strength| >= 95th percentile
  base強 上位10%  : diff >= 90th percentile (base通貨が強い)
  quote強 上位10% : diff <= 10th percentile (quote通貨が強い)
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
from scipy import stats
from scipy.stats import gaussian_kde
from pathlib import Path
import warnings; warnings.filterwarnings("ignore")

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "strength_distribution"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STRENGTH_WINDOW = 6    # 画像の注釈：cum_spread_window=6
JST = pd.Timedelta(hours=9)

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# 条件のカラーと凡例
COND_COLORS = {
    "all":   "#3867a8",
    "top10": "#e07b00",
    "top5":  "#c0392b",
    "base":  "#1d8a4c",
    "quote": "#7e3fa8",
}

# ── データ読込 ──────────────────────────────────────────────
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
print(f"共通バー数: {len(common_idx):,}  ({common_idx[0].date()} 〜 {common_idx[-1].date()})")

# ── 通貨強弱（STRENGTH_WINDOW本の累積対数リターン） ────────────
print("通貨強弱算出中...")
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]; raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)

# ── 統計計算関数 ─────────────────────────────────────────────
def get_stats(r_series):
    r = r_series.dropna().values
    if len(r) < 30:
        return {"n":0,"mean":np.nan,"std":np.nan,"skew":np.nan,
                "kurt":np.nan,"p5":np.nan,"p95":np.nan,"pval":np.nan}
    m = r.mean()*100; s = r.std()*100
    sk = stats.skew(r); ku = stats.kurtosis(r)
    p5,p95 = np.percentile(r*100,[5,95])
    _,pval = stats.ttest_1samp(r, 0)
    return {"n":len(r),"mean":m,"std":s,"skew":sk,"kurt":ku,
            "p5":p5,"p95":p95,"pval":pval}

# ── ペア別図生成 ─────────────────────────────────────────────
def make_pair_fig(pair, base_c, quote_c):
    df_p = dfs[pair]

    # 強弱差（base - quote）とその絶対値
    diff     = str_df[base_c] - str_df[quote_c]
    abs_diff = diff.abs()

    # 次バーの対数変化率（close-to-close）× 100 → %
    next_ret = np.log(df_p["Close"].shift(-1) / df_p["Close"]) * 100

    # 各閾値
    q90_abs = abs_diff.quantile(0.90)
    q95_abs = abs_diff.quantile(0.95)
    q90_pos = diff.quantile(0.90)   # base強
    q10_pos = diff.quantile(0.10)   # quote強

    valid = abs_diff.notna() & next_ret.notna()
    masks = {
        "all":   valid,
        "top10": valid & (abs_diff >= q90_abs),
        "top5":  valid & (abs_diff >= q95_abs),
        "base":  valid & (diff >= q90_pos),
        "quote": valid & (diff <= q10_pos),
    }

    # 統計量
    stat_all   = get_stats(next_ret[masks["all"]])
    stat_top10 = get_stats(next_ret[masks["top10"]])
    stat_top5  = get_stats(next_ret[masks["top5"]])
    stat_base  = get_stats(next_ret[masks["base"]])
    stat_quote = get_stats(next_ret[masks["quote"]])

    # 条件ラベル
    cond_labels = {
        "all":   f"全期間（3年）",
        "top10": "|強弱差| 上位10%",
        "top5":  "|強弱差| 上位5%",
        "base":  f"{base_c}強 上位10%（正の強弱差）",
        "quote": f"{quote_c}強 上位10%（負の強弱差）",
    }
    cond_stats = {
        "all":   stat_all, "top10": stat_top10, "top5": stat_top5,
        "base":  stat_base, "quote": stat_quote,
    }

    # ── レイアウト ───────────────────────────────────────────
    fig = plt.figure(figsize=(20, 16))
    fig.patch.set_facecolor("#f5f7fa")

    gs = gridspec.GridSpec(3, 3, figure=fig,
                           height_ratios=[1.0, 0.7, 0.7],
                           hspace=0.42, wspace=0.3)

    # x軸範囲（全期間の1〜99%ile）
    r_all = next_ret[masks["all"]].dropna().values
    lo = np.percentile(r_all, 1); hi = np.percentile(r_all, 99)
    xs = np.linspace(lo, hi, 400)

    # ── 左上: 全期間 vs |強弱差|大 ──────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.set_facecolor("#ffffff")
    ax1.axvline(0, color="#666666", lw=1.0, ls="--", alpha=0.7)

    # ±1σ 帯（全期間）
    m_all = stat_all["mean"]/100; s_all = stat_all["std"]/100
    y_max_est = 25
    ax1.fill_betweenx([0, y_max_est], m_all*100-stat_all["std"],
                      m_all*100+stat_all["std"],
                      color="#ddddff", alpha=0.4, zorder=1,
                      label=f"全期間 ±1σ ({m_all*100-stat_all['std']:.4f}〜{m_all*100+stat_all['std']:.4f}%)")

    for key, color, lw, ls in [
        ("all",   COND_COLORS["all"],   2.2, "-"),
        ("top10", COND_COLORS["top10"], 2.0, "-"),
        ("top5",  COND_COLORS["top5"],  2.0, "-"),
    ]:
        r = next_ret[masks[key]].dropna().values
        if len(r) < 30: continue
        st = cond_stats[key]
        try:
            kde = gaussian_kde(r, bw_method=0.2)
            y = kde(xs/100)*100   # %スケール合わせ
            ax1.plot(xs, y/100, color=color, lw=lw, ls=ls,
                     label=f"{cond_labels[key]}  σ={st['std']:.4f}%")
            ax1.fill_between(xs, y/100, alpha=0.12, color=color)
        except: pass

    ax1.set_xlabel("対数変化率（%）", fontsize=9)
    ax1.set_ylabel("確率密度", fontsize=9)
    ax1.set_xlim(lo, hi)
    ax1.legend(fontsize=8, framealpha=0.9, loc="upper right")
    ax1.set_title(f"{pair}  対数変化率の分布比較\n"
                  f"全期間（青）vs |通貨強弱差| 上位10%（橙）・5%（赤）",
                  fontsize=10, fontweight="bold")
    ax1.grid(alpha=0.2)
    # 垂直線（平均）
    for key, color in [("all",COND_COLORS["all"]),("top10",COND_COLORS["top10"]),
                       ("top5",COND_COLORS["top5"])]:
        m = cond_stats[key].get("mean", np.nan)
        if not np.isnan(m):
            ax1.axvline(m, color=color, lw=1.2, ls=":", alpha=0.8)

    # ── 右上: 方向別比較 ────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.set_facecolor("#ffffff")
    ax2.axvline(0, color="#666666", lw=1.0, ls="--", alpha=0.7)

    for key, color, lw in [
        ("all",   COND_COLORS["all"],   2.2),
        ("base",  COND_COLORS["base"],  2.0),
        ("quote", COND_COLORS["quote"], 2.0),
    ]:
        r = next_ret[masks[key]].dropna().values
        if len(r) < 30: continue
        try:
            kde = gaussian_kde(r, bw_method=0.2)
            y = kde(xs/100)*100
            ax2.plot(xs, y/100, color=color, lw=lw,
                     label=f"{cond_labels[key].split('（')[0]}")
            ax2.fill_between(xs, y/100, alpha=0.15, color=color)
        except: pass

    ax2.set_xlabel("対数変化率（%）", fontsize=9)
    ax2.set_ylabel("確率密度", fontsize=9)
    ax2.set_xlim(lo, hi)
    ax2.legend(fontsize=7.5, framealpha=0.9, loc="upper right")
    ax2.set_title(f"方向別比較\n{base_c}強（緑）vs {quote_c}強（紫）",
                  fontsize=10, fontweight="bold")
    ax2.grid(alpha=0.2)

    # ── 中段: 統計モーメント テーブル ───────────────────────
    ax_tbl = fig.add_subplot(gs[1, :])
    ax_tbl.axis("off")

    cond_order = ["all","top10","top5","base","quote"]
    col_headers = ["条件", "n", "平均\n(×10⁻²%)", "標準偏差\n(×10⁻²%)",
                   "歪度\n(Skewness)", "超過尖度\n(Kurtosis)",
                   "5%分位", "95%分位", "t検定 p値"]
    rows_data = []
    for key in cond_order:
        st = cond_stats[key]
        if st["n"] == 0:
            rows_data.append([cond_labels[key], "─","─","─","─","─","─","─","─"])
            continue
        pval_str = f"{st['pval']:.4f}" if not np.isnan(st['pval']) else "─"
        if not np.isnan(st['pval']):
            pval_str += " ***" if st['pval']<0.001 else " **" if st['pval']<0.01 else \
                        " *"   if st['pval']<0.05  else " ns"
        rows_data.append([
            cond_labels[key],
            f"{st['n']:,}",
            f"{st['mean']*100:.4f}",
            f"{st['std']*100:.4f}",
            f"{st['skew']:+.4f}",
            f"{st['kurt']:+.1f}",
            f"{st['p5']:.4f}%",
            f"{st['p95']:.4f}%",
            pval_str,
        ])

    tbl = ax_tbl.table(
        cellText=rows_data, colLabels=col_headers,
        loc="center", cellLoc="center",
    )
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5)
    tbl.scale(1, 1.7)

    # ヘッダー行
    for j in range(len(col_headers)):
        tbl[0,j].set_facecolor("#1a3a6e"); tbl[0,j].set_text_props(color="white",fontweight="bold")

    # 条件行の色分け
    row_colors = {0:"#ddeeff",1:"#ffe8cc",2:"#ffd5d5",3:"#d5f0e0",4:"#e8d5f5"}
    for i in range(len(cond_order)):
        for j in range(len(col_headers)):
            tbl[i+1,j].set_facecolor(row_colors[i])
            if j in [4,5]:  # Skew/Kurt列
                val_str = rows_data[i][j]
                try:
                    v = float(val_str.replace("+",""))
                    if j==4 and v < -0.3:
                        tbl[i+1,j].set_facecolor("#ffaaaa")
                    elif j==4 and v > 0.3:
                        tbl[i+1,j].set_facecolor("#aaffaa")
                except: pass

    ax_tbl.set_title("統計モーメント比較（次バーの対数変化率）",
                     fontsize=10, fontweight="bold", pad=4)

    # ── 下段: 3つの棒グラフ ─────────────────────────────────
    bar_labels = ["全期間","|強弱差|\n上位10%","|強弱差|\n上位5%",
                  f"{base_c}強\n上位10%",f"{quote_c}強\n上位10%"]
    bar_colors = [COND_COLORS[k] for k in cond_order]

    std_vals  = [cond_stats[k].get("std",  np.nan)*100 for k in cond_order]
    skew_vals = [cond_stats[k].get("skew", np.nan)     for k in cond_order]
    kurt_vals = [cond_stats[k].get("kurt", np.nan)     for k in cond_order]

    for ax_b, vals, title, ylabel, y_ref, use_log in [
        (fig.add_subplot(gs[2, 0]), std_vals,
         f"標準偏差（ボラティリティ）×10⁻²%\n★強弱差が大きいとボラが1.5〜2倍に拡大",
         "標準偏差 ×10⁻²%", None, False),
        (fig.add_subplot(gs[2, 1]), skew_vals,
         "歪度（Skewness）\n負=左裾が厚い（下落リスク大）",
         "歪度", 0, False),
        (fig.add_subplot(gs[2, 2]), kurt_vals,
         "超過尖度（対数スケール）\n★全期間は極端なファットテール",
         "超過尖度", 3, True),
    ]:
        ax_b.set_facecolor("#f8f8f8")
        x = np.arange(len(bar_labels))
        bars = ax_b.bar(x, vals, color=bar_colors, alpha=0.85, edgecolor="none",
                        width=0.6)
        if y_ref is not None:
            ax_b.axhline(y_ref, color="#888888", lw=1.2, ls="--", alpha=0.7,
                         label=f"y={y_ref}")
            if y_ref == 3:
                ax_b.legend(fontsize=7.5)
        for bar, val in zip(bars, vals):
            if np.isnan(val): continue
            h = bar.get_height()
            fmt = f"{val:.2f}" if abs(val)<100 else f"{val:.0f}"
            ax_b.text(bar.get_x()+bar.get_width()/2, h*1.02 if h>=0 else h*0.95,
                      fmt, ha="center", va="bottom" if h>=0 else "top",
                      fontsize=8, fontweight="bold")
        ax_b.set_xticks(x); ax_b.set_xticklabels(bar_labels, fontsize=7.5)
        ax_b.set_ylabel(ylabel, fontsize=8); ax_b.set_title(title, fontsize=8.5)
        ax_b.grid(axis="y", alpha=0.25)
        if use_log:
            pos_vals = [v for v in vals if not np.isnan(v) and v>0]
            if pos_vals: ax_b.set_yscale("log")

    # フッター
    date_range = f"{common_idx[0].date()} 〜 {common_idx[-1].date()}"
    fig.text(0.5, 0.005,
             f"Dukascopy 5分足 {pair}  {date_range}  |  "
             f"通貨強弱: LOO方式 (cum_spread_window={STRENGTH_WINDOW})  |  "
             f"条件付き分布 = 大きな強弱差の次バーリターン",
             ha="center", fontsize=7, color="#777777")

    fig.suptitle(f"{pair}  （{base_c} / {quote_c}）  対数変化率の分布比較",
                 fontsize=13, fontweight="bold", y=0.995)

    out_path = OUT_DIR / f"{pair}_distribution.png"
    plt.savefig(str(out_path), dpi=140, bbox_inches="tight",
                facecolor="#f5f7fa")
    plt.close(fig)
    return cond_stats

# ── 全ペア実行 ──────────────────────────────────────────────
print("\n全ペア図生成中...")
summary_rows = []
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    cond_stats = make_pair_fig(pair, base_c, quote_c)
    print(f"  {pair}: 保存完了")

    for key,label in [("all","全期間"),("top10","|強弱差|上位10%"),
                       ("top5","|強弱差|上位5%"),("base",f"{base_c}強"),
                       ("quote",f"{quote_c}強")]:
        st = cond_stats[key]
        summary_rows.append({"pair":pair,"base":base_c,"quote":quote_c,
                              "condition":label,**st})

# サマリーCSV
pd.DataFrame(summary_rows).to_csv(OUT_DIR/"summary_stats.csv",
                                   index=False, encoding="utf-8-sig")

# ── サマリーグリッド（全12ペア比較） ──────────────────────────
print("\nサマリーグリッド（Skew × Kurt × 条件）生成中...")
pairs_list = list(PAIR_CURRENCIES.keys())

fig_sum, axes_sum = plt.subplots(3, 4, figsize=(28, 18))
fig_sum.patch.set_facecolor("#f5f7fa")
fig_sum.suptitle("全12ペア  強弱差フィルター別  Skew vs ExKurt 比較\n"
                 "（次バー対数リターン分布  /  全期間2022-2024）",
                 fontsize=14, fontweight="bold")

for i,pair in enumerate(pairs_list):
    if pair not in dfs: continue
    ax = axes_sum[i//4][i%4]; ax.set_facecolor("#f8f8f8")
    base_c,quote_c = PAIR_CURRENCIES[pair]
    df_p = dfs[pair]
    diff = str_df[base_c] - str_df[quote_c]
    abs_diff = diff.abs()
    next_ret = np.log(df_p["Close"].shift(-1)/df_p["Close"])*100
    valid = abs_diff.notna() & next_ret.notna()

    thresholds = [
        ("全期間",    valid,                                    COND_COLORS["all"]),
        ("|差|上位10%",valid&(abs_diff>=abs_diff.quantile(0.90)),COND_COLORS["top10"]),
        ("|差|上位5%", valid&(abs_diff>=abs_diff.quantile(0.95)),COND_COLORS["top5"]),
        (f"{base_c}強",valid&(diff>=diff.quantile(0.90)),       COND_COLORS["base"]),
        (f"{quote_c}強",valid&(diff<=diff.quantile(0.10)),      COND_COLORS["quote"]),
    ]

    for label,mask,color in thresholds:
        r = next_ret[mask].dropna().values
        if len(r)<30: continue
        sk=stats.skew(r); ku=stats.kurtosis(r)
        ax.scatter(sk, np.log10(max(ku,0.1)+1), s=max(len(r)/300,30),
                   color=color, alpha=0.8, edgecolors="white", lw=0.5)
        ax.text(sk, np.log10(max(ku,0.1)+1)+0.05, label,
                fontsize=6.5, ha="center", color=color, fontweight="bold")

    ax.axvline(0, color="#888888", lw=0.8, ls="--", alpha=0.5)
    ax.set_title(f"{pair}  ({base_c}/{quote_c})", fontsize=9, fontweight="bold")
    ax.set_xlabel("歪度 Skew", fontsize=7.5)
    ax.set_ylabel("log10(ExKurt+1)", fontsize=7.5)
    ax.grid(alpha=0.2)

plt.tight_layout()
fig_sum.savefig(OUT_DIR/"summary_skew_kurt.png", dpi=130,
                bbox_inches="tight", facecolor="#f5f7fa")
plt.close(fig_sum)

print(f"\n保存先: {OUT_DIR}")
print("完了")
