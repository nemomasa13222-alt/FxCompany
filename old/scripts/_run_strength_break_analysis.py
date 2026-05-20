# -*- coding: utf-8 -*-
"""
通貨強弱 × ブレイクダウン分析
────────────────────────────────────────
条件 ①: 12ペア（7通貨）の強弱スコアを算出 → USD-JPY 差が極端
条件 ②: 現在足 Low が前足 Low を下抜け → ショートシグナル
分析  : 1/3/6/12/24 本後の累積対数リターン分布を 3群比較
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

# ── フォント設定 ────────────────────────────────────────────
FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    prop = fm.FontProperties(fname=FONT_PATH)
    plt.rcParams["font.family"] = prop.get_name()
except Exception:
    pass

# ── パス設定 ────────────────────────────────────────────────
BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "strength_break"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 12ペア × 7通貨の定義 ────────────────────────────────────
PAIR_CURRENCIES = {
    "USDJPY": ("USD", "JPY"),
    "EURJPY": ("EUR", "JPY"),
    "GBPJPY": ("GBP", "JPY"),
    "AUDJPY": ("AUD", "JPY"),
    "NZDJPY": ("NZD", "JPY"),
    "CHFJPY": ("CHF", "JPY"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"),
    "EURGBP": ("EUR", "GBP"),
    "EURAUD": ("EUR", "AUD"),
    "AUDNZD": ("AUD", "NZD"),
}
CURRENCIES = sorted({c for pair in PAIR_CURRENCIES.values() for c in pair})

STRENGTH_WINDOW = 24    # 24本 = 2時間
HORIZONS        = [1, 3, 6, 12, 24]
Q_LARGE         = 0.25  # 下位25% = 強弱差大
Q_EXTREME       = 0.10  # 下位10% = 強弱差極大

# ── データ読み込み ──────────────────────────────────────────
print("=" * 60)
print("  データ読み込み")
print("=" * 60)

dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists():
        print(f"  [SKIP] {pair}: parquetなし")
        continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open", "High", "Low", "Close"]]
    print(f"  {pair}: {len(df):>8,}本  {df.index[0].date()} 〜 {df.index[-1].date()}")

if "USDJPY" not in dfs:
    print("[ERROR] USDJPYデータなし。終了。")
    sys.exit(1)

# ── 共通インデックスで整合 ──────────────────────────────────
common_idx = dfs["USDJPY"].index
for pair in dfs:
    common_idx = common_idx.intersection(dfs[pair].index)
print(f"\n共通バー数: {len(common_idx):,}  "
      f"({common_idx[0].date()} 〜 {common_idx[-1].date()})\n")

for pair in dfs:
    dfs[pair] = dfs[pair].reindex(common_idx)

usdjpy = dfs["USDJPY"]

# ── 通貨強弱スコア算出 ──────────────────────────────────────
print("通貨強弱スコアを算出中...")

# 各ペアの対数リターン（STRENGTH_WINDOW 本前比）
pair_logret = {}
for pair, df in dfs.items():
    pair_logret[pair] = np.log(df["Close"] / df["Close"].shift(STRENGTH_WINDOW))

# 各通貨の強弱 = 関与ペアのリターンの平均（base:+, quote:-）
raw_strength = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
pair_count   = {c: 0 for c in CURRENCIES}

for pair, (base, quote) in PAIR_CURRENCIES.items():
    if pair not in pair_logret:
        continue
    r = pair_logret[pair]
    raw_strength[base] = raw_strength[base] + r
    raw_strength[quote] = raw_strength[quote] - r
    pair_count[base] += 1
    pair_count[quote] += 1

for c in CURRENCIES:
    if pair_count[c] > 0:
        raw_strength[c] /= pair_count[c]

strength_df   = pd.DataFrame(raw_strength)
strength_diff = strength_df["USD"] - strength_df["JPY"]   # 負 = USD弱・JPY強

# ── ブレイク条件 ────────────────────────────────────────────
# 現在足 Low < 前足 Low
break_mask = (usdjpy["Low"] < usdjpy["Low"].shift(1)) & strength_diff.notna()

print(f"全ブレイク数: {break_mask.sum():,}")

# 強弱差閾値（全バーの分布から決定）
valid_diff = strength_diff.dropna()
q_th_large   = valid_diff.quantile(Q_LARGE)
q_th_extreme = valid_diff.quantile(Q_EXTREME)
print(f"強弱差閾値 ─ 大({int(Q_LARGE*100)}%): {q_th_large:.5f}  "
      f"極大({int(Q_EXTREME*100)}%): {q_th_extreme:.5f}")

mask_all     = break_mask
mask_large   = break_mask & (strength_diff <= q_th_large)
mask_extreme = break_mask & (strength_diff <= q_th_extreme)

print(f"  全ブレイク:      {mask_all.sum():>6,}")
print(f"  強弱差大 (≤Q{int(Q_LARGE*100)}):  {mask_large.sum():>6,}")
print(f"  強弱差極大(≤Q{int(Q_EXTREME*100)}):  {mask_extreme.sum():>6,}")

# ── 先行対数リターン算出 ────────────────────────────────────
# r(h) = log(Close_t+h / Close_t)   負 = 価格下落 = ショート利益
close = usdjpy["Close"]
future_ret = {h: np.log(close.shift(-h) / close) for h in HORIZONS}

# ── 統計サマリー ────────────────────────────────────────────
GROUPS = {
    "全ブレイク":       mask_all,
    f"強弱差大 (≤Q{int(Q_LARGE*100)})":   mask_large,
    f"強弱差極大(≤Q{int(Q_EXTREME*100)})": mask_extreme,
}

print("\n" + "=" * 70)
print(f"  {'':32s}{'Mean%':>8} {'Median%':>9} {'Skew':>7} {'Kurt':>7} {'n':>6}")
print("-" * 70)

summary_rows = []
for h in HORIZONS:
    for label, mask in GROUPS.items():
        r = future_ret[h][mask].dropna()
        if len(r) < 30:
            continue
        mean_pct   = r.mean()  * 100
        median_pct = np.median(r) * 100
        skewness   = stats.skew(r)
        kurtosis   = stats.kurtosis(r)
        print(f"  {h}本後 {label:28s} {mean_pct:+8.4f} {median_pct:+9.4f} "
              f"{skewness:+7.3f} {kurtosis:+7.2f} {len(r):6,}")
        summary_rows.append({
            "horizon": h, "group": label, "n": len(r),
            "mean_pct": mean_pct, "median_pct": median_pct,
            "skew": skewness, "kurt": kurtosis,
        })
    print()

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv(OUT_DIR / "summary.csv", index=False, encoding="utf-8-sig")
print(f"\nサマリー保存: {OUT_DIR / 'summary.csv'}")

# ── ヒストグラム描画 ────────────────────────────────────────
print("\nヒストグラム描画中...")

GROUP_STYLE = {
    "全ブレイク":       ("#95a5a6", 0.45, 1.2),
    f"強弱差大 (≤Q{int(Q_LARGE*100)})":   ("#3498db", 0.65, 1.8),
    f"強弱差極大(≤Q{int(Q_EXTREME*100)})": ("#e74c3c", 0.85, 2.2),
}

fig, axes = plt.subplots(len(HORIZONS), 1, figsize=(16, 5.5 * len(HORIZONS)))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("USD/JPY ブレイクダウン後リターン分布  ─  通貨強弱差フィルター比較\n"
             f"（強弱算出窓: {STRENGTH_WINDOW}本/{STRENGTH_WINDOW*5}分  "
             f"│ 分析対象: 12ペア 7通貨）",
             fontsize=13, y=1.01, fontweight="bold")

for ax, h in zip(axes, HORIZONS):
    ax.set_facecolor("#f8f9fa")
    ax.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6, zorder=5)
    ax.set_title(f"▶  {h} 本後 ({h*5} 分後)", fontsize=11, fontweight="bold", pad=8)

    stat_lines = []
    for label, mask in GROUPS.items():
        r = future_ret[h][mask].dropna() * 100
        if len(r) < 30:
            continue
        color, alpha, _ = GROUP_STYLE[label]

        # ヒストグラム（パーセンタイルでビン範囲制限）
        lo, hi = np.percentile(r, [1, 99])
        bins = np.linspace(lo, hi, 90)
        ax.hist(r, bins=bins, density=True, alpha=alpha,
                color=color, edgecolor="none", label=f"{label}  n={len(r):,}")

        # KDE
        try:
            kde = stats.gaussian_kde(r, bw_method=0.25)
            xs  = np.linspace(lo, hi, 400)
            ax.plot(xs, kde(xs), color=color, lw=2.0, zorder=10)
        except Exception:
            pass

        mean_v  = r.mean()
        skew_v  = stats.skew(r / 100)
        stat_lines.append(f"{label}:  μ={mean_v:+.4f}%   skew={skew_v:+.3f}")

    ax.set_xlabel("累積対数リターン (%)", fontsize=9)
    ax.set_ylabel("確率密度", fontsize=9)
    ax.legend(fontsize=8.5, loc="upper right", framealpha=0.9)

    info = "\n".join(stat_lines)
    ax.text(0.015, 0.97, info, transform=ax.transAxes,
            fontsize=8, va="top", ha="left",
            bbox=dict(fc="white", alpha=0.85, boxstyle="round,pad=0.4",
                      ec="#cccccc"))

plt.tight_layout(rect=[0, 0, 1, 0.98])
out_png = OUT_DIR / "strength_break_histograms.png"
fig.savefig(str(out_png), dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"保存: {out_png}")

# ── 期待値・歪度トレンド図 ──────────────────────────────────
fig2, (ax_mean, ax_skew) = plt.subplots(2, 1, figsize=(12, 8))
fig2.patch.set_facecolor("#fafafa")
fig2.suptitle("期待値・歪度の時間変化  ─  フィルター別比較", fontsize=12, y=1.01)

for label, mask in GROUPS.items():
    color, _, lw = GROUP_STYLE[label]
    means, skews = [], []
    for h in HORIZONS:
        r = future_ret[h][mask].dropna()
        means.append(r.mean() * 100 if len(r) >= 30 else np.nan)
        skews.append(stats.skew(r) if len(r) >= 30 else np.nan)
    ax_mean.plot(HORIZONS, means, marker="o", color=color, lw=lw,
                 label=label, markersize=7)
    ax_skew.plot(HORIZONS, skews, marker="s", color=color, lw=lw,
                 label=label, markersize=7)

for ax, ylabel, title in [
    (ax_mean, "期待値 (%)", "期待値（負 = ショート有利）"),
    (ax_skew, "歪度 (skewness)", "歪度（負 = 左裾厚い）"),
]:
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
    ax.set_xlabel("先行バー数 (×5分)", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.set_xticks(HORIZONS)
    ax.legend(fontsize=9, framealpha=0.9)
    ax.set_facecolor("#f8f9fa")
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
out_trend = OUT_DIR / "strength_break_trend.png"
fig2.savefig(str(out_trend), dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig2)
print(f"保存: {out_trend}")

print("\n" + "=" * 60)
print("  完了")
print("=" * 60)
