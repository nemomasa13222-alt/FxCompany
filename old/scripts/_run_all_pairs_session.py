# -*- coding: utf-8 -*-
"""
12通貨ペア  セッション別リターン分布  ─  Image#5 / Image#6 生成
  Image#5: 強弱差極大フィルター × セッション別ヒストグラム（4パネル）
  Image#6: セッション別期待値 × グループ比較 棒グラフ（5horizon）
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import gaussian_kde

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

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "pair_session_charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 定数 ────────────────────────────────────────────────────
START = "2022-01-01"; END = "2024-12-31"
STRENGTH_WINDOW = 24
HORIZONS = [1, 3, 6, 12, 24]
JST = pd.Timedelta(hours=9)

SESSIONS = [
    ("東京 09-15JST",  9, 15, "#E07B00"),
    ("欧州 15-21JST", 15, 21, "#22AA66"),
    ("NY   21-03JST", 21,  3, "#3866A8"),
    ("深夜 03-09JST",  3,  9, "#9933CC"),
]

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# ── データ読込 ──────────────────────────────────────────────
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]].loc[START:END]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
print(f"共通バー数: {len(common_idx):,}")

# ── 通貨強弱スコア ──────────────────────────────────────────
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

# セッション割り当て
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e,_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# ── ペア別生成関数 ───────────────────────────────────────────
def process_pair(pair, base_c, quote_c):
    df_p = dfs[pair]

    # ペア固有の強弱差
    strength_diff = str_df[base_c] - str_df[quote_c]
    q10 = strength_diff.quantile(0.10)
    q25 = strength_diff.quantile(0.25)

    # ブレイクダウン（current Low < prev Low）
    breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & strength_diff.notna()

    # 先行リターン（次足Open基準）
    entry_price = df_p["Open"].shift(-1)
    fut = {h: np.log(df_p["Close"].shift(-h) / entry_price) * 100
           for h in HORIZONS}

    # マスク
    mask_all     = breakdown
    mask_large   = breakdown & (strength_diff <= q25)
    mask_extreme = breakdown & (strength_diff <= q10)

    return {
        "strength_diff": strength_diff,
        "q10": q10, "q25": q25,
        "masks": {"all": mask_all, "large": mask_large, "extreme": mask_extreme},
        "fut": fut,
    }

# ════════════════════════════════════════════════════════════
# Image#5: セッション別ヒストグラム
# ════════════════════════════════════════════════════════════
def make_hist_fig(pair, base_c, quote_c, data):
    masks = data["masks"]; fut = data["fut"]; h = 6  # 6本後=30分後

    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.patch.set_facecolor("#F8F9FA")
    fig.suptitle(
        f"強弱差極大フィルター  ─  セッション別リターン分布  （6本後 / 30分後）\n"
        f"{pair}  ({base_c}/{quote_c})  /  全ブレイクとの比較",
        fontsize=13, fontweight="bold"
    )

    for ax, (sname, s, e, color) in zip(axes.flat, SESSIONS):
        ax.set_facecolor("#FFFFFF")
        sess_mask = sess_s == sname

        r_all = fut[h][masks["all"] & sess_mask].dropna() * 1  # already %
        r_ext = fut[h][masks["extreme"] & sess_mask].dropna()

        # x軸範囲（全ブレイクの1〜99%ile）
        if len(r_all) < 10: ax.set_title(sname); continue
        lo = np.percentile(r_all, 1); hi = np.percentile(r_all, 99)
        bins = np.linspace(lo, hi, 60)
        xplot = np.linspace(lo, hi, 400)

        # ── 全ブレイク（グレー、背面） ─────────────────────────
        ax.hist(r_all, bins=bins, density=True,
                color="#CCCCCC", alpha=1.0, zorder=2,
                edgecolor="none",
                label=f"全ブレイク n={len(r_all):,}")
        if len(r_all) >= 30:
            kde_all = gaussian_kde(r_all, bw_method=0.3)
            ax.plot(xplot, kde_all(xplot), color="#888888", lw=2.5, zorder=4)

        # ── 強弱差極大（セッション色、前面・均一） ──────────
        if len(r_ext) >= 30:
            ax.hist(r_ext, bins=bins, density=True,
                    color=color, alpha=0.80, zorder=3,
                    edgecolor="none",
                    label=f"強弱差極大(≤Q10) n={len(r_ext):,}")
            kde_ext = gaussian_kde(r_ext, bw_method=0.3)
            ax.plot(xplot, kde_ext(xplot), color=color, lw=2.5, zorder=5)
            mu   = r_ext.mean()
            skew = stats.skew(r_ext)
            # 平均の縦線
            ax.axvline(mu, color=color, lw=1.5, ls="--", alpha=0.9)
            ax.axvline(r_all.mean(), color="#888888", lw=1.2, ls=":", alpha=0.7)
            # 統計テキスト
            ax.text(0.97, 0.96,
                    f"μ={mu:+.4f}% skew={skew:+.3f}\nn={len(r_ext):,}",
                    transform=ax.transAxes, fontsize=9,
                    ha="right", va="top",
                    bbox=dict(fc="white", alpha=0.85, boxstyle="round,pad=0.3",
                              ec=color, lw=1.2))

        ax.axvline(0, color="#333333", lw=1.2, ls="--", alpha=0.6)
        ax.set_xlim(lo, hi)
        ax.set_xlabel("累積対数リターン（%）", fontsize=9)
        ax.set_ylabel("確率密度", fontsize=9)
        ax.set_title(sname, fontsize=12, fontweight="bold", color=color)
        ax.legend(fontsize=8.5, framealpha=0.9)
        ax.grid(axis="y", alpha=0.2)

    plt.tight_layout(rect=[0,0,1,0.95])
    out = OUT_DIR / f"{pair}_session_hist.png"
    fig.savefig(str(out), dpi=140, bbox_inches="tight", facecolor="#F8F9FA")
    plt.close(fig)

# ════════════════════════════════════════════════════════════
# Image#6: セッション別期待値 グループ比較棒グラフ
# ════════════════════════════════════════════════════════════
def make_mean_bar_fig(pair, base_c, quote_c, data):
    masks = data["masks"]; fut = data["fut"]
    sess_names = [s[0] for s in SESSIONS]
    sess_colors= [s[3] for s in SESSIONS]

    # グループ定義
    groups = [
        ("全ブレイク",        masks["all"],     "#AAAAAA", 0.7),
        ("強弱差大(≤Q25)",    masks["large"],   "#4477BB", 0.85),
        ("強弱差極大(≤Q10)",  masks["extreme"], "#CC3333", 0.9),
    ]

    fig, axes = plt.subplots(1, len(HORIZONS), figsize=(24, 6), sharey=False)
    fig.patch.set_facecolor("#F8F9FA")
    fig.suptitle(
        f"セッション別 期待値（%）  ─  グループ比較\n"
        f"{pair}  ({base_c}/{quote_c})  /  （負 = ショート有利）",
        fontsize=12, fontweight="bold"
    )

    x  = np.arange(len(sess_names))
    bw = 0.25  # バー幅

    for ax, h in zip(axes, HORIZONS):
        ax.set_facecolor("#F8F9FA")
        ax.axhline(0, color="#333333", lw=0.8, ls="--", alpha=0.6)

        for gi, (glabel, gmask, gcolor, galpha) in enumerate(groups):
            means = []
            for sname,*_ in SESSIONS:
                sess_mask = sess_s == sname
                r = fut[h][gmask & sess_mask].dropna()
                means.append(r.mean() if len(r)>=10 else 0.0)

            offset = (gi - 1) * bw
            bars = ax.bar(x + offset, means, bw,
                          color=gcolor, alpha=galpha,
                          label=glabel if h==HORIZONS[0] else "",
                          edgecolor="none")

        ax.set_title(f"{h}本後\n({h*5}分後)", fontsize=9, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([s.replace(" ","\n") for s in sess_names], fontsize=7.5)
        ax.set_ylabel("Mean (%)" if h==HORIZONS[0] else "", fontsize=8)
        ax.grid(axis="y", alpha=0.2)
        ax.tick_params(labelsize=7.5)

    # 凡例（一番左のaxに）
    handles = [plt.Rectangle((0,0),1,1,fc=g[2],alpha=g[3]) for g in groups]
    axes[0].legend(handles, [g[0] for g in groups],
                   fontsize=8, loc="lower left", framealpha=0.9)

    plt.tight_layout(rect=[0,0,1,0.92])
    out = OUT_DIR / f"{pair}_session_mean.png"
    fig.savefig(str(out), dpi=140, bbox_inches="tight", facecolor="#F8F9FA")
    plt.close(fig)

# ── 全ペア実行 ──────────────────────────────────────────────
print("\n全ペア生成中...")
for pair, (base_c, quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    print(f"  {pair}...", end=" ")
    data = process_pair(pair, base_c, quote_c)
    make_hist_fig(pair, base_c, quote_c, data)
    make_mean_bar_fig(pair, base_c, quote_c, data)
    print("完了")

# ── サマリーグリッド（全12ペアの比較） ──────────────────────
print("\nサマリーグリッド生成中...")

# 全ペアのQ10・セッション別μ・skewをまとめる
rows_summary = []
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    data = process_pair(pair, base_c, quote_c)
    for sname,*_ in SESSIONS:
        sess_mask = sess_s == sname
        for h in HORIZONS:
            r = data["fut"][h][data["masks"]["extreme"] & sess_mask].dropna()
            r_all = data["fut"][h][data["masks"]["all"] & sess_mask].dropna()
            rows_summary.append({
                "pair":pair,"base":base_c,"quote":quote_c,
                "session":sname,"horizon":h,
                "n_all":len(r_all),"n_extreme":len(r),
                "mean_all": r_all.mean() if len(r_all)>=10 else np.nan,
                "mean_extreme": r.mean() if len(r)>=10 else np.nan,
                "skew_extreme": stats.skew(r) if len(r)>=30 else np.nan,
                "kurt_extreme": stats.kurtosis(r) if len(r)>=30 else np.nan,
            })

pd.DataFrame(rows_summary).to_csv(
    OUT_DIR/"summary_session_stats.csv", index=False, encoding="utf-8-sig")

# サマリーグリッド（6本後のmeanヒートマップ）
pairs_list = list(PAIR_CURRENCIES.keys())
df_sum = pd.DataFrame(rows_summary)
df_sum6 = df_sum[df_sum["horizon"]==6]

fig_g, axes_g = plt.subplots(1, 4, figsize=(24, 8), sharey=True)
fig_g.patch.set_facecolor("#F8F9FA")
fig_g.suptitle("全12ペア  強弱差極大(Q10)  セッション別期待値（6本後/30分後）\n"
               "負=ショート有利（青） / 正=ロング有利（赤）",
               fontsize=13, fontweight="bold")

for ax, (sname,s,e,color) in zip(axes_g, SESSIONS):
    ax.set_facecolor("#F8F9FA")
    ax.axvline(0, color="#333333", lw=0.8, ls="--", alpha=0.6)

    sub = df_sum6[df_sum6["session"]==sname].set_index("pair")["mean_extreme"]
    sub = sub.reindex(pairs_list)
    bar_colors = ["#4477BB" if v<=0 else "#CC3333" for v in sub.values]

    bars = ax.barh(range(len(pairs_list)), sub.values,
                   color=bar_colors, alpha=0.8, edgecolor="none")
    ax.set_yticks(range(len(pairs_list)))
    ax.set_yticklabels(pairs_list, fontsize=9)
    ax.set_title(sname, fontsize=11, fontweight="bold", color=color)
    ax.set_xlabel("Mean（%）", fontsize=8)
    ax.grid(axis="x", alpha=0.2)

    for i,(bar,val) in enumerate(zip(bars, sub.values)):
        if not np.isnan(val):
            ax.text(val + (0.00002 if val>=0 else -0.00002),
                    i, f"{val:+.4f}%", va="center",
                    ha="left" if val>=0 else "right", fontsize=7)

plt.tight_layout()
fig_g.savefig(OUT_DIR/"summary_all_pairs_mean.png", dpi=130,
              bbox_inches="tight", facecolor="#F8F9FA")
plt.close(fig_g)

print(f"\n保存先: {OUT_DIR}")
print("完了")
