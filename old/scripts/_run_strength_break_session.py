# -*- coding: utf-8 -*-
"""
通貨強弱 × ブレイクダウン分析  ─  時間帯別整理
セッション定義（JST）:
  東京     09:00-15:00  (Tokyo)
  欧州     15:00-21:00  (London/Pre-NY)
  NY       21:00-03:00  (NY / London-NY overlap)
  深夜     03:00-09:00  (Quiet / Sydney)
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

# ── フォント ────────────────────────────────────────────────
FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    prop = fm.FontProperties(fname=FONT_PATH)
    plt.rcParams["font.family"] = prop.get_name()
except Exception:
    pass

# ── パス ────────────────────────────────────────────────────
BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "strength_break"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 定数 ────────────────────────────────────────────────────
PAIR_CURRENCIES = {
    "USDJPY": ("USD", "JPY"), "EURJPY": ("EUR", "JPY"),
    "GBPJPY": ("GBP", "JPY"), "AUDJPY": ("AUD", "JPY"),
    "NZDJPY": ("NZD", "JPY"), "CHFJPY": ("CHF", "JPY"),
    "GBPUSD": ("GBP", "USD"), "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"), "EURGBP": ("EUR", "GBP"),
    "EURAUD": ("EUR", "AUD"), "AUDNZD": ("AUD", "NZD"),
}
CURRENCIES      = sorted({c for v in PAIR_CURRENCIES.values() for c in v})
STRENGTH_WINDOW = 24
HORIZONS        = [1, 3, 6, 12, 24]
Q_LARGE         = 0.25
Q_EXTREME       = 0.10
JST             = pd.Timedelta(hours=9)

# セッション定義: (表示名, 開始時JST, 終了時JST, 色)
SESSIONS = [
    ("東京\n09-15JST",  9,  15, "#f39c12"),
    ("欧州\n15-21JST", 15,  21, "#27ae60"),
    ("NY\n21-03JST",   21,   3, "#2980b9"),
    ("深夜\n03-09JST",  3,   9, "#8e44ad"),
]

# ── データ読み込み ──────────────────────────────────────────
print("データ読み込み中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists():
        continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open", "High", "Low", "Close"]]

common_idx = dfs["USDJPY"].index
for pair in dfs:
    common_idx = common_idx.intersection(dfs[pair].index)
for pair in dfs:
    dfs[pair] = dfs[pair].reindex(common_idx)

usdjpy = dfs["USDJPY"]
print(f"共通バー数: {len(common_idx):,}  ({common_idx[0].date()} 〜 {common_idx[-1].date()})")

# ── 通貨強弱スコア ──────────────────────────────────────────
pair_logret = {
    pair: np.log(df["Close"] / df["Close"].shift(STRENGTH_WINDOW))
    for pair, df in dfs.items()
}
raw_strength = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
pair_count   = {c: 0 for c in CURRENCIES}
for pair, (base, quote) in PAIR_CURRENCIES.items():
    if pair not in pair_logret:
        continue
    r = pair_logret[pair]
    raw_strength[base] += r
    raw_strength[quote] -= r
    pair_count[base] += 1
    pair_count[quote] += 1
for c in CURRENCIES:
    if pair_count[c] > 0:
        raw_strength[c] /= pair_count[c]

strength_diff = pd.DataFrame(raw_strength)["USD"] - pd.DataFrame(raw_strength)["JPY"]

# ── ブレイク条件 & フィルター ───────────────────────────────
break_mask = (usdjpy["Low"] < usdjpy["Low"].shift(1)) & strength_diff.notna()
q25 = strength_diff.quantile(Q_LARGE)
q10 = strength_diff.quantile(Q_EXTREME)

mask_all     = break_mask
mask_large   = break_mask & (strength_diff <= q25)
mask_extreme = break_mask & (strength_diff <= q10)

GROUPS = {
    "全ブレイク":           mask_all,
    f"強弱差大(≤Q{int(Q_LARGE*100)})":    mask_large,
    f"強弱差極大(≤Q{int(Q_EXTREME*100)})": mask_extreme,
}

# ── JST 時間帯割り当て ──────────────────────────────────────
jst_hour = (common_idx + JST).hour   # UTC → JST 変換

def get_session(hour):
    for name, start, end, _ in SESSIONS:
        if start < end:
            if start <= hour < end:
                return name
        else:   # 跨日 (例: 21〜3時)
            if hour >= start or hour < end:
                return name
    return "その他"

session_labels = pd.Series([get_session(h) for h in jst_hour], index=common_idx)

# ── 先行リターン ────────────────────────────────────────────
close     = usdjpy["Close"]
future_ret = {h: np.log(close.shift(-h) / close) for h in HORIZONS}

# ── 統計集計 ────────────────────────────────────────────────
print("\n集計中...")
rows = []
for sess_name, s_start, s_end, s_color in SESSIONS:
    sess_mask_all = session_labels == sess_name
    for g_label, g_mask in GROUPS.items():
        combined = g_mask & sess_mask_all
        for h in HORIZONS:
            r = future_ret[h][combined].dropna()
            if len(r) < 30:
                continue
            rows.append({
                "session": sess_name, "group": g_label, "horizon": h,
                "n": len(r),
                "mean_pct": r.mean() * 100,
                "median_pct": np.median(r) * 100,
                "skew": stats.skew(r),
                "kurt": stats.kurtosis(r),
            })

df_stats = pd.DataFrame(rows)
df_stats.to_csv(OUT_DIR / "session_summary.csv", index=False, encoding="utf-8-sig")

# コンソール出力
print(f"\n{'セッション':12s} {'グループ':22s} {'horizon':>7s} "
      f"{'Mean%':>9s} {'Skew':>7s} {'n':>6s}")
print("-" * 70)
for _, row in df_stats.iterrows():
    print(f"{row['session'][:10]:12s} {row['group']:22s} {row['horizon']:>7.0f}本後  "
          f"{row['mean_pct']:+9.4f} {row['skew']:+7.3f} {row['n']:6,}")

# ── 図1: ヒートマップ ─ Mean% と Skew ──────────────────────
print("\nヒートマップ描画中...")

group_target = f"強弱差極大(≤Q{int(Q_EXTREME*100)})"
sess_names   = [s[0] for s in SESSIONS]
df_target    = df_stats[df_stats["group"] == group_target].copy()

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"時間帯 × 先行バー数  ─  {group_target}\n"
             "(USD弱・JPY強フィルター  /  USD-JPY ブレイクダウン後リターン)",
             fontsize=12, fontweight="bold")

for ax, metric, label, cmap, fmt in [
    (axes[0], "mean_pct", "期待値 (%)", "RdYlGn_r", "+.4f"),
    (axes[1], "skew",     "歪度 (Skew)", "RdYlGn_r", "+.3f"),
]:
    pivot = (df_target.pivot(index="session", columns="horizon", values=metric)
             .reindex(sess_names))
    n_pivot = (df_target.pivot(index="session", columns="horizon", values="n")
               .reindex(sess_names))

    vmax = pivot.abs().max().max()
    im = ax.imshow(pivot.values, cmap=cmap, aspect="auto",
                   vmin=-vmax, vmax=vmax)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)

    ax.set_xticks(range(len(HORIZONS)))
    ax.set_xticklabels([f"{h}本\n({h*5}分)" for h in HORIZONS], fontsize=8)
    ax.set_yticks(range(len(sess_names)))
    ax.set_yticklabels(sess_names, fontsize=9)
    ax.set_title(label, fontsize=10, fontweight="bold")

    for i, sess in enumerate(sess_names):
        for j, h in enumerate(HORIZONS):
            val = pivot.iloc[i, j] if not pd.isna(pivot.iloc[i, j]) else np.nan
            n   = n_pivot.iloc[i, j] if not pd.isna(n_pivot.iloc[i, j]) else 0
            if not np.isnan(val):
                ax.text(j, i, f"{val:{fmt}}\n(n={int(n):,})",
                        ha="center", va="center", fontsize=7.5,
                        color="white" if abs(val) > vmax * 0.5 else "black")

plt.tight_layout()
fig.savefig(OUT_DIR / "session_heatmap.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: session_heatmap.png")

# ── 図2: セッション別 Mean% 棒グラフ (全グループ) ──────────
fig, axes = plt.subplots(1, len(HORIZONS), figsize=(20, 6), sharey=False)
fig.patch.set_facecolor("#fafafa")
fig.suptitle("セッション別 期待値 (%)  ─  グループ比較\n"
             "（負 = ショート有利）", fontsize=12, fontweight="bold")

g_colors = {
    "全ブレイク":           "#95a5a6",
    f"強弱差大(≤Q{int(Q_LARGE*100)})":    "#3498db",
    f"強弱差極大(≤Q{int(Q_EXTREME*100)})": "#e74c3c",
}
g_labels = list(GROUPS.keys())
x = np.arange(len(sess_names))
bar_w = 0.25

for ax, h in zip(axes, HORIZONS):
    ax.set_facecolor("#f8f9fa")
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.6)
    for i, (g_label, g_mask) in enumerate(GROUPS.items()):
        means = []
        for sess_name, *_ in SESSIONS:
            sub = df_stats[(df_stats["group"] == g_label) &
                           (df_stats["session"] == sess_name) &
                           (df_stats["horizon"] == h)]
            means.append(sub["mean_pct"].values[0] if len(sub) > 0 else 0)
        bars = ax.bar(x + i * bar_w, means, bar_w,
                      color=g_colors[g_label], alpha=0.8, label=g_label if h == HORIZONS[0] else "")
    ax.set_title(f"{h}本後\n({h*5}分後)", fontsize=9, fontweight="bold")
    ax.set_xticks(x + bar_w)
    ax.set_xticklabels([s[0].replace("\n", "\n") for s in SESSIONS], fontsize=7.5)
    ax.set_ylabel("Mean (%)" if h == HORIZONS[0] else "", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(labelsize=7)

axes[0].legend(fontsize=7.5, loc="lower left", framealpha=0.9)
plt.tight_layout()
fig.savefig(OUT_DIR / "session_mean_bar.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: session_mean_bar.png")

# ── 図3: 強弱差極大 × セッション別ヒストグラム (6本後) ──────
H_FOCUS = 6   # 30分後に注目
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"強弱差極大フィルター  ─  セッション別リターン分布  ({H_FOCUS}本後 / {H_FOCUS*5}分後)\n"
             "（全ブレイクとの比較）", fontsize=12, fontweight="bold")

for ax, (sess_name, s_start, s_end, s_color) in zip(axes.flat, SESSIONS):
    ax.set_facecolor("#f8f9fa")
    ax.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6, zorder=5)
    ax.set_title(sess_name.replace("\n", " "), fontsize=10, fontweight="bold",
                 color=s_color)

    sess_mask = session_labels == sess_name
    for g_label, g_mask, color, alpha in [
        ("全ブレイク",           mask_all,     "#95a5a6", 0.5),
        (f"強弱差極大(≤Q{int(Q_EXTREME*100)})", mask_extreme, s_color,    0.75),
    ]:
        r = future_ret[H_FOCUS][g_mask & sess_mask].dropna() * 100
        if len(r) < 20:
            continue
        lo, hi = np.percentile(r, [1, 99])
        bins = np.linspace(lo, hi, 70)
        ax.hist(r, bins=bins, density=True, alpha=alpha, color=color,
                edgecolor="none", label=f"{g_label}  n={len(r):,}")
        try:
            kde = stats.gaussian_kde(r, bw_method=0.25)
            xs  = np.linspace(lo, hi, 300)
            ax.plot(xs, kde(xs), color=color, lw=2.0, zorder=10)
        except Exception:
            pass
        mean_v = r.mean()
        skew_v = stats.skew(r / 100)
        ax.axvline(mean_v, color=color, lw=1.2, ls=":", alpha=0.9)

    sub = df_stats[(df_stats["group"] == group_target) &
                   (df_stats["session"] == sess_name) &
                   (df_stats["horizon"] == H_FOCUS)]
    if len(sub) > 0:
        info = (f"μ={sub['mean_pct'].values[0]:+.4f}%  "
                f"skew={sub['skew'].values[0]:+.3f}\n"
                f"n={int(sub['n'].values[0]):,}")
        ax.text(0.97, 0.97, info, transform=ax.transAxes,
                fontsize=9, va="top", ha="right",
                bbox=dict(fc="white", alpha=0.85, boxstyle="round,pad=0.4",
                          ec="#cccccc"))
    ax.set_xlabel("累積対数リターン (%)", fontsize=8)
    ax.set_ylabel("確率密度", fontsize=8)
    ax.legend(fontsize=8, loc="upper left", framealpha=0.9)
    ax.tick_params(labelsize=8)

plt.tight_layout()
fig.savefig(OUT_DIR / "session_histograms.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: session_histograms.png")

# ── 図4: 時間帯別 Skew 推移 ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("セッション × 先行バー数  ─  期待値・歪度推移\n"
             f"（フィルター: {group_target}）",
             fontsize=12, fontweight="bold")

for ax, metric, ylabel, title in [
    (axes[0], "mean_pct", "Mean (%)", "期待値（負=ショート有利）"),
    (axes[1], "skew",     "Skew",    "歪度（負=左裾厚い）"),
]:
    ax.set_facecolor("#f8f9fa")
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
    for sess_name, _, _, s_color in SESSIONS:
        sub = df_target[df_target["session"] == sess_name].sort_values("horizon")
        if len(sub) == 0:
            continue
        ax.plot(sub["horizon"], sub[metric], marker="o", lw=2,
                color=s_color, label=sess_name.replace("\n", " "), markersize=7)
    ax.set_xlabel("先行バー数 (×5分)", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_xticks(HORIZONS)
    ax.legend(fontsize=9, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(labelsize=8)

plt.tight_layout()
fig.savefig(OUT_DIR / "session_trend.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"  保存: session_trend.png")

# ── 最終サマリー出力 ────────────────────────────────────────
print("\n" + "=" * 75)
print(f"  強弱差極大 ({group_target}) ─ セッション別サマリー")
print("=" * 75)
print(f"  {'セッション':12s}  {'horizon':>6s}  {'Mean%':>9s}  {'Skew':>7s}  {'n':>6s}")
print("-" * 75)
for sess_name, *_ in SESSIONS:
    sub = df_target[df_target["session"] == sess_name].sort_values("horizon")
    for _, row in sub.iterrows():
        tag = "★" if row["mean_pct"] < 0 and row["skew"] < -0.5 else "  "
        print(f"  {tag}{sess_name.replace(chr(10),' '):14s}  "
              f"{row['horizon']:>4.0f}本後  "
              f"{row['mean_pct']:+9.4f}  {row['skew']:+7.3f}  {row['n']:6,}")
    print()

print("★ = Mean負 かつ Skew < -0.5  (最も条件が揃った時間帯)")
print(f"\n保存先: {OUT_DIR}")
