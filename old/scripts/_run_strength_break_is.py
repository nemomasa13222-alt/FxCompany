# -*- coding: utf-8 -*-
"""
通貨強弱 × ブレイクダウン  ─  IS期間（2022-2023）セッション別検証
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats
from pathlib import Path

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "strength_break"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAIR_CURRENCIES = {
    "USDJPY": ("USD","JPY"), "EURJPY": ("EUR","JPY"),
    "GBPJPY": ("GBP","JPY"), "AUDJPY": ("AUD","JPY"),
    "NZDJPY": ("NZD","JPY"), "CHFJPY": ("CHF","JPY"),
    "GBPUSD": ("GBP","USD"), "AUDUSD": ("AUD","USD"),
    "NZDUSD": ("NZD","USD"), "EURGBP": ("EUR","GBP"),
    "EURAUD": ("EUR","AUD"), "AUDNZD": ("AUD","NZD"),
}
CURRENCIES      = sorted({c for v in PAIR_CURRENCIES.values() for c in v})
STRENGTH_WINDOW = 24
HORIZONS        = [1, 3, 6, 12, 24]
JST             = pd.Timedelta(hours=9)

IS_START = "2022-01-01"
IS_END   = "2023-12-31"
OOS_START= "2024-01-01"

SESSIONS = [
    ("東京 09-15JST",   9, 15, "#f39c12"),
    ("欧州 15-21JST",  15, 21, "#27ae60"),
    ("NY   21-03JST",  21,  3, "#2980b9"),
    ("深夜 03-09JST",   3,  9, "#8e44ad"),
]

# ── データ読込 ──────────────────────────────────────────────
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists():
        continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for pair in dfs:
    common_idx = common_idx.intersection(dfs[pair].index)
for pair in dfs:
    dfs[pair] = dfs[pair].reindex(common_idx)

usdjpy = dfs["USDJPY"]

# ── 通貨強弱スコア ──────────────────────────────────────────
pair_logret = {
    p: np.log(df["Close"] / df["Close"].shift(STRENGTH_WINDOW))
    for p, df in dfs.items()
}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt     = {c: 0 for c in CURRENCIES}
for pair, (b, q) in PAIR_CURRENCIES.items():
    if pair not in pair_logret: continue
    r = pair_logret[pair]
    raw_str[b] += r;  raw_str[q] -= r
    cnt[b] += 1;      cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]

strength_diff = pd.DataFrame(raw_str)["USD"] - pd.DataFrame(raw_str)["JPY"]

# ── ブレイク & フィルター ────────────────────────────────────
break_mask = (usdjpy["Low"] < usdjpy["Low"].shift(1)) & strength_diff.notna()
q10 = strength_diff.quantile(0.10)
q25 = strength_diff.quantile(0.25)

mask_all     = break_mask
mask_large   = break_mask & (strength_diff <= q25)
mask_extreme = break_mask & (strength_diff <= q10)

# ── IS / OOS 分割 ──────────────────────────────────────────
is_mask  = (common_idx >= IS_START)  & (common_idx <= IS_END)
oos_mask = (common_idx >= OOS_START)

# ── セッション割り当て ──────────────────────────────────────
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name, s, e, _ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return "その他"

sess_labels = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# ── 先行リターン（次の足Open始値ベース） ─────────────────────
# エントリー = 次足Open → Close(t+h) の対数リターン
# ショート目線なので r<0 が利益
entry_price = usdjpy["Open"].shift(-1)       # 次足Open
future_ret = {}
for h in HORIZONS:
    future_ret[h] = np.log(usdjpy["Close"].shift(-h) / entry_price)

# ── 集計関数 ────────────────────────────────────────────────
def calc_stats(ret_series):
    r = ret_series.dropna()
    if len(r) < 30:
        return None
    return {
        "n":      len(r),
        "mean":   r.mean() * 100,
        "median": np.median(r) * 100,
        "skew":   stats.skew(r),
        "kurt":   stats.kurtosis(r),
        "neg_rate": (r < 0).mean() * 100,   # 価格下落率（ショート勝率）
    }

GROUPS = {
    "全ブレイク":   mask_all,
    "強弱差大(Q25)": mask_large,
    "強弱差極大(Q10)": mask_extreme,
}

# ── IS期間 × セッション集計 ────────────────────────────────
print(f"\n== IS期間 {IS_START} 〜 {IS_END} ==")
rows = []
for sess_name, *_ in SESSIONS:
    sess_mask = sess_labels == sess_name
    for g_label, g_mask in GROUPS.items():
        combined = g_mask & is_mask & sess_mask
        for h in HORIZONS:
            s = calc_stats(future_ret[h][combined])
            if s:
                rows.append({"period":"IS","session":sess_name,
                             "group":g_label,"horizon":h,**s})

# OOS期間
for sess_name, *_ in SESSIONS:
    sess_mask = sess_labels == sess_name
    combined = mask_extreme & oos_mask & sess_mask
    for h in HORIZONS:
        s = calc_stats(future_ret[h][combined])
        if s:
            rows.append({"period":"OOS","session":sess_name,
                         "group":"強弱差極大(Q10)","horizon":h,**s})

df_stats = pd.DataFrame(rows)
df_stats.to_csv(OUT_DIR / "is_session_summary.csv",
                index=False, encoding="utf-8-sig")

# ── コンソール出力（IS・強弱差極大のみ） ──────────────────────
print(f"\n{'セッション':18s} {'H':>4s}  {'Mean%':>8s}  {'Skew':>6s}  "
      f"{'下落率%':>7s}  {'n':>5s}")
print("-" * 60)
df_ex = df_stats[(df_stats["period"]=="IS") & (df_stats["group"]=="強弱差極大(Q10)")]
for sess_name, *_ in SESSIONS:
    sub = df_ex[df_ex["session"]==sess_name].sort_values("horizon")
    for _, row in sub.iterrows():
        tag = "★" if row["mean"] < 0 and row["skew"] < -0.5 else "  "
        print(f"  {tag}{sess_name:16s} {row['horizon']:>3.0f}本  "
              f"{row['mean']:+8.4f}  {row['skew']:+6.3f}  "
              f"{row['neg_rate']:>7.1f}  {row['n']:5,}")
    print()

# ── 図1: IS×セッション×horizon ヒートマップ ─────────────────
print("図1: IS ヒートマップ描画中...")
df_is_ex = df_stats[(df_stats["period"]=="IS") & (df_stats["group"]=="強弱差極大(Q10)")]
sess_names = [s[0] for s in SESSIONS]

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"IS期間 ({IS_START}〜{IS_END})  強弱差極大(Q10)  ─  セッション × 先行バー",
             fontsize=12, fontweight="bold")

for ax, (metric, label, cmap) in zip(axes, [
    ("mean",     "期待値 (%)",  "RdYlGn_r"),
    ("skew",     "歪度 (Skew)", "RdYlGn_r"),
    ("neg_rate", "下落率 (%)",  "RdYlGn"),
]):
    pivot = df_is_ex.pivot(index="session", columns="horizon", values=metric).reindex(sess_names)
    n_piv = df_is_ex.pivot(index="session", columns="horizon", values="n").reindex(sess_names)
    vmax  = pivot.abs().max().max()
    center = 50 if metric=="neg_rate" else 0
    vmin_v = (50 - vmax) if metric=="neg_rate" else -vmax
    vmax_v = (50 + vmax) if metric=="neg_rate" else  vmax

    im = ax.imshow(pivot.values, cmap=cmap, aspect="auto", vmin=vmin_v, vmax=vmax_v)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    ax.set_xticks(range(len(HORIZONS)))
    ax.set_xticklabels([f"{h}本\n({h*5}分)" for h in HORIZONS], fontsize=8)
    ax.set_yticks(range(len(sess_names)))
    ax.set_yticklabels(sess_names, fontsize=8)
    ax.set_title(label, fontsize=10, fontweight="bold")

    for i in range(len(sess_names)):
        for j, h in enumerate(HORIZONS):
            val = pivot.iloc[i, j]
            n   = int(n_piv.iloc[i, j]) if not pd.isna(n_piv.iloc[i, j]) else 0
            if not np.isnan(val):
                fmt = "+.3f" if metric != "neg_rate" else ".1f"
                ax.text(j, i, f"{val:{fmt}}\n(n={n:,})",
                        ha="center", va="center", fontsize=7,
                        color="white" if abs(val-center) > vmax*0.5 else "black")

plt.tight_layout()
fig.savefig(OUT_DIR/"is_session_heatmap.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 図2: IS vs OOS (NYセッション・強弱差極大) ────────────────
print("図2: IS vs OOS 比較描画中...")
H_FOCUS = 6

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"IS vs OOS 比較  ─  強弱差極大(Q10) / {H_FOCUS}本後（{H_FOCUS*5}分後）",
             fontsize=12, fontweight="bold")

for ax, (period, mask_p, color_base) in zip(axes, [
    ("IS  2022-2023", is_mask,  ["#95a5a6","#3498db","#e74c3c"]),
    ("OOS 2024",      oos_mask, ["#bdc3c7","#85c1e9","#f1948a"]),
]):
    ax.set_facecolor("#f8f9fa")
    ax.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6)
    ax.set_title(period, fontsize=11, fontweight="bold")

    for (sess_name, _, _, s_color) in SESSIONS:
        sess_mask = sess_labels == sess_name
        combined  = mask_extreme & mask_p & sess_mask
        r = future_ret[H_FOCUS][combined].dropna() * 100
        if len(r) < 30: continue
        lo, hi = np.percentile(r, [1,99])
        try:
            kde = stats.gaussian_kde(r, bw_method=0.3)
            xs  = np.linspace(lo, hi, 400)
            ax.plot(xs, kde(xs), lw=2.0, color=s_color,
                    label=f"{sess_name}  μ={r.mean():+.4f}%  n={len(r):,}")
        except Exception:
            pass

    ax.set_xlabel("累積対数リターン (%)", fontsize=9)
    ax.set_ylabel("確率密度", fontsize=9)
    ax.legend(fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
fig.savefig(OUT_DIR/"is_vs_oos_kde.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 図3: 全セッション IS 期待値 × Skew バブルチャート ─────────
print("図3: バブルチャート描画中...")
fig, axes = plt.subplots(1, len(HORIZONS), figsize=(22, 5), sharey=True)
fig.patch.set_facecolor("#fafafa")
fig.suptitle("IS期間  強弱差極大(Q10)  ─  期待値 × 歪度  (バブル=サンプル数)",
             fontsize=11, fontweight="bold")

sess_colors = {s[0]: s[3] for s in SESSIONS}

for ax, h in zip(axes, HORIZONS):
    ax.set_facecolor("#f8f9fa")
    ax.axhline(0, color="#333", lw=0.7, ls="--", alpha=0.5)
    ax.axvline(0, color="#333", lw=0.7, ls="--", alpha=0.5)

    sub = df_is_ex[df_is_ex["horizon"]==h]
    for _, row in sub.iterrows():
        c = sess_colors.get(row["session"], "gray")
        ax.scatter(row["mean"], row["skew"],
                   s=row["n"]/3, color=c, alpha=0.75, edgecolors="white", lw=0.5,
                   zorder=5)
        ax.text(row["mean"], row["skew"]+0.08,
                row["session"].split()[0], fontsize=7.5, ha="center", color=c)

    ax.set_title(f"{h}本後\n({h*5}分)", fontsize=9)
    ax.set_xlabel("Mean (%)" if h==HORIZONS[2] else "", fontsize=8)
    if h == HORIZONS[0]:
        ax.set_ylabel("Skew", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.2)

# 凡例
for sess_name, _, _, color in SESSIONS:
    axes[-1].scatter([], [], color=color,
                     label=sess_name.split()[0], s=60, alpha=0.8)
axes[-1].legend(fontsize=8, loc="upper right", framealpha=0.9, title="セッション")

plt.tight_layout()
fig.savefig(OUT_DIR/"is_bubble.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終IS判定サマリー ──────────────────────────────────────
print("\n" + "="*65)
print("  IS判定サマリー  ─  強弱差極大(Q10)  全horizon平均")
print("="*65)
print(f"  {'セッション':18s}  {'MeanAvg%':>9s}  {'SkewAvg':>8s}  {'下落率Avg':>9s}  {'判定':>8s}")
print("-"*65)
for sess_name, *_ in SESSIONS:
    sub = df_is_ex[df_is_ex["session"]==sess_name]
    if len(sub)==0: continue
    m = sub["mean"].mean()
    sk = sub["skew"].mean()
    nr = sub["neg_rate"].mean()
    if m < 0 and sk < -0.3 and nr > 51:
        verdict = "★ 採用候補"
    elif m < 0 or (sk < -0.5 and nr > 50):
        verdict = "△ 要検討"
    else:
        verdict = "✗ 非推奨"
    print(f"  {sess_name:18s}  {m:+9.4f}  {sk:+8.3f}  {nr:>9.1f}  {verdict}")

print(f"\n保存先: {OUT_DIR}")
print("完了")
