# -*- coding: utf-8 -*-
"""
12通貨ペア × セッション × 自己相関フィルター付き解析
─────────────────────────────────────────────────────────────
docs/strength_break/ のロジックを全ペアに拡張し、ac フィルターを追加。

リターン計算: close.shift(-h) / close  ← strength_break と同じ
グループ（5つ）:
  全ブレイク            (gray)
  強弱差大 ≤Q25         (blue)
  強弱差極大 ≤Q10       (red)
  ≤Q10 + ac > 0         (navy)   モメンタム継続
  ≤Q10 + ac < 0         (orange) 逆張り
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
OUT_DIR  = ROOT / "docs" / "pair_session_charts_ac"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START           = "2022-01-01"; END = "2024-12-31"
STRENGTH_WINDOW = 24
AC_WINDOW       = 12
Q_LARGE         = 0.25
Q_EXTREME       = 0.10
HORIZONS        = [1, 3, 6, 12, 24]
JST             = pd.Timedelta(hours=9)

SESSIONS = [
    ("東京\n09-15JST",  9, 15, "#f39c12"),
    ("欧州\n15-21JST", 15, 21, "#27ae60"),
    ("NY\n21-03JST",   21,  3, "#2980b9"),
    ("深夜\n03-09JST",  3,  9, "#8e44ad"),
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

# ── 通貨強弱（全ペア共通） ──────────────────────────────────
print("通貨強弱算出中...")
pair_logret = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
               for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt     = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_logret: continue
    r = pair_logret[pair]
    raw_str[b] += r; raw_str[q] -= r
    cnt[b] += 1;     cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)

# セッション
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e,_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# ── 自己相関（ペア別） ──────────────────────────────────────
print("自己相関算出中...")
def rolling_ac(series, w):
    arr = series.values; res = np.full(len(arr), np.nan)
    for i in range(w-1, len(arr)):
        x = arr[i-w+1:i+1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-1], x[1:])
        res[i] = c[0,1]
    return pd.Series(res, index=series.index)

ac_dict = {}
for pair, df in dfs.items():
    ret = np.log(df["Close"]/df["Close"].shift(1))
    ac_dict[pair] = rolling_ac(ret, AC_WINDOW)

# グループカラー
GRP_STYLE = {
    "全ブレイク":          ("#95a5a6", 0.75),
    "強弱差大(≤Q25)":     ("#3498db", 0.80),
    "強弱差極大(≤Q10)":   ("#e74c3c", 0.85),
    "≤Q10+ac>0\n(モメンタム)": ("#1a3a7a", 0.90),
    "≤Q10+ac<0\n(逆張り)":     ("#e07b00", 0.90),
}

# ════════════════════════════════════════════════════════════
# Image#5: セッション別ヒストグラム
# ════════════════════════════════════════════════════════════
def make_hist(pair, base_c, quote_c):
    df_p = dfs[pair]; ac = ac_dict[pair]
    close= df_p["Close"]
    diff = str_df[base_c] - str_df[quote_c]
    q10  = diff.quantile(Q_EXTREME)

    # ── strength_break と同じ: close/close リターン ────────
    future_ret = {h: np.log(close.shift(-h)/close) for h in HORIZONS}
    h = 6

    breakdown   = (df_p["Low"] < df_p["Low"].shift(1)) & diff.notna()
    mask_all    = breakdown
    mask_ext    = breakdown & (diff <= q10)
    mask_acp    = mask_ext & (ac > 0.0)
    mask_acn    = mask_ext & (ac < 0.0)

    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.patch.set_facecolor("#F8F9FA")
    fig.suptitle(
        f"強弱差 × 自己相関フィルター  ─  セッション別リターン分布（6本後 / 30分後）\n"
        f"{pair}（{base_c}/{quote_c}）  "
        f"灰=全Break  赤=Q10  紺=Q10+ac>0  橙=Q10+ac<0",
        fontsize=12, fontweight="bold"
    )

    for ax, (sname,s,e,color) in zip(axes.flat, SESSIONS):
        ax.set_facecolor("#FFFFFF")
        sm = sess_s == sname

        r_all = future_ret[h][mask_all & sm].dropna()
        r_ext = future_ret[h][mask_ext & sm].dropna()
        r_acp = future_ret[h][mask_acp & sm].dropna()
        r_acn = future_ret[h][mask_acn & sm].dropna()

        if len(r_all) < 10: ax.set_title(sname); continue
        lo = np.percentile(r_all, 1); hi = np.percentile(r_all, 99)
        bins  = np.linspace(lo, hi, 60)
        xplot = np.linspace(lo, hi, 400)

        def plot_dist(r, clr, alpha, label, zo):
            if len(r) < 30: return
            ax.hist(r, bins=bins, density=True, color=clr,
                    alpha=alpha, edgecolor="none", zorder=zo,
                    label=f"{label}  n={len(r):,}")
            kde = gaussian_kde(r, bw_method=0.3)
            ax.plot(xplot, kde(xplot), color=clr, lw=2.0, zorder=zo+10)
            ax.axvline(r.mean(), color=clr, lw=1.2, ls="--", alpha=0.8)

        plot_dist(r_all, "#CCCCCC", 1.0, "全BreakDown", 2)
        plot_dist(r_ext, "#e74c3c", 0.65,"Q10",         3)
        plot_dist(r_acp, "#1a3a7a", 0.78,"Q10+ac>0",    4)
        plot_dist(r_acn, "#e07b00", 0.78,"Q10+ac<0",    4)

        ax.axvline(0, color="#333333", lw=1.2, ls="--", alpha=0.5, zorder=10)
        ax.set_xlim(lo, hi)
        ax.set_xlabel("累積対数リターン（%）", fontsize=9)
        ax.set_ylabel("確率密度", fontsize=9)
        ax.set_title(sname, fontsize=12, fontweight="bold", color=color)
        ax.legend(fontsize=8, framealpha=0.9, loc="upper right")
        ax.grid(axis="y", alpha=0.2)

        lines=[]
        for r,lbl,c in [(r_ext,"Q10","#e74c3c"),(r_acp,"Q10+ac>0","#1a3a7a"),
                         (r_acn,"Q10+ac<0","#e07b00")]:
            if len(r)>=30:
                lines.append(f"{lbl}: μ={r.mean()*100:+.4f}% sk={stats.skew(r):+.2f} n={len(r):,}")
        if lines:
            ax.text(0.97,0.96,"\n".join(lines),
                    transform=ax.transAxes,fontsize=7.5,
                    ha="right",va="top",
                    bbox=dict(fc="white",alpha=0.88,boxstyle="round,pad=0.3",
                              ec=color,lw=1.0))

    plt.tight_layout(rect=[0,0,1,0.94])
    fig.savefig(str(OUT_DIR/f"{pair}_hist_ac.png"), dpi=140,
                bbox_inches="tight", facecolor="#F8F9FA")
    plt.close(fig)

# ════════════════════════════════════════════════════════════
# Image#6: セッション別期待値 グループ比較（strength_break と同じ軸）
# ════════════════════════════════════════════════════════════
def make_mean(pair, base_c, quote_c):
    df_p = dfs[pair]; ac = ac_dict[pair]
    close= df_p["Close"]
    diff = str_df[base_c] - str_df[quote_c]
    q10  = diff.quantile(Q_EXTREME)
    q25  = diff.quantile(Q_LARGE)

    # ── strength_break と同じ: close/close リターン ────────
    future_ret = {h: np.log(close.shift(-h)/close) for h in HORIZONS}

    breakdown   = (df_p["Low"] < df_p["Low"].shift(1)) & diff.notna()
    masks = {
        "全ブレイク":                breakdown,
        f"強弱差大(≤Q{int(Q_LARGE*100)})":   breakdown & (diff <= q25),
        f"強弱差極大(≤Q{int(Q_EXTREME*100)})":breakdown & (diff <= q10),
        "≤Q10+ac>0\n(モメンタム)":   breakdown & (diff <= q10) & (ac > 0.0) & ac.notna(),
        "≤Q10+ac<0\n(逆張り)":       breakdown & (diff <= q10) & (ac < 0.0) & ac.notna(),
    }

    groups = list(GRP_STYLE.items())   # [(label, (color, alpha)), ...]
    sess_names = [s[0] for s in SESSIONS]
    x  = np.arange(len(sess_names))
    bw = 0.16
    offsets = np.arange(len(groups)) - (len(groups)-1)/2

    fig, axes = plt.subplots(1, len(HORIZONS), figsize=(26, 6))
    fig.patch.set_facecolor("#F8F9FA")
    fig.suptitle(
        f"セッション別 期待値（%）  ─  自己相関フィルター効果\n"
        f"{pair}（{base_c}/{quote_c}）  /  "
        f"（負 = ショート有利）",
        fontsize=11, fontweight="bold"
    )

    for ax, h in zip(axes, HORIZONS):
        ax.set_facecolor("#F8F9FA")
        ax.axhline(0, color="#333333", lw=0.8, ls="--", alpha=0.6)

        for gi, (glabel, (gcolor, galpha)) in enumerate(groups):
            means = []
            for sname,*_ in SESSIONS:
                sm = sess_s == sname
                r  = future_ret[h][masks[glabel] & sm].dropna()
                means.append(r.mean() * 100 if len(r)>=10 else 0.0)
            ax.bar(x + offsets[gi]*bw, means, bw,
                   color=gcolor, alpha=galpha, edgecolor="none",
                   label=glabel.replace("\n"," ") if h==HORIZONS[0] else "")

        ax.set_title(f"{h}本後\n({h*5}分後)", fontsize=9, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([s.replace("\n"," ") for s in sess_names],
                           fontsize=7.5, rotation=15, ha="right")
        ax.set_ylabel("Mean (%)" if h==HORIZONS[0] else "", fontsize=8)
        ax.grid(axis="y", alpha=0.2)

    handles=[plt.Rectangle((0,0),1,1,fc=v[0],alpha=v[1])
             for _,v in groups]
    axes[0].legend(handles,[k.replace("\n"," ") for k,_ in groups],
                   fontsize=7.5, loc="lower left", framealpha=0.9)

    plt.tight_layout(rect=[0,0,1,0.90])
    fig.savefig(str(OUT_DIR/f"{pair}_mean_ac.png"), dpi=140,
                bbox_inches="tight", facecolor="#F8F9FA")
    plt.close(fig)

# ── 全ペア実行 ──────────────────────────────────────────────
print("\n全ペア生成中...")
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    print(f"  {pair}...", end=" ")
    make_hist(pair, base_c, quote_c)
    make_mean(pair, base_c, quote_c)
    print("完了")

# ── サマリーグリッド（全12ペア × 6本後） ──────────────────
print("\nサマリーグリッド生成中...")
pairs_list = list(PAIR_CURRENCIES.keys())
fig, axes = plt.subplots(4, 3, figsize=(26, 22))
fig.patch.set_facecolor("#F8F9FA")
fig.suptitle("全12ペア  自己相関フィルター効果  ─  セッション別期待値（6本後 / 30分後）",
             fontsize=14, fontweight="bold")

for pi, pair in enumerate(pairs_list):
    if pair not in dfs: continue
    ax = axes[pi//3][pi%3]; ax.set_facecolor("#F8F9FA")
    ax.axhline(0, color="#333333", lw=0.8, ls="--", alpha=0.6)
    base_c,quote_c = PAIR_CURRENCIES[pair]

    df_p = dfs[pair]; ac = ac_dict[pair]
    close= df_p["Close"]
    diff = str_df[base_c] - str_df[quote_c]
    q10  = diff.quantile(Q_EXTREME); q25 = diff.quantile(Q_LARGE)
    future_ret6 = np.log(close.shift(-6)/close)
    breakdown   = (df_p["Low"] < df_p["Low"].shift(1)) & diff.notna()

    masks_sum = {
        "全BreakDown":    breakdown,
        f"≤Q{int(Q_LARGE*100)}":        breakdown & (diff <= q25),
        f"≤Q{int(Q_EXTREME*100)}":      breakdown & (diff <= q10),
        "≤Q10+ac>0": breakdown & (diff <= q10) & (ac > 0.0) & ac.notna(),
        "≤Q10+ac<0": breakdown & (diff <= q10) & (ac < 0.0) & ac.notna(),
    }
    colors_sum = ["#95a5a6","#3498db","#e74c3c","#1a3a7a","#e07b00"]
    sess_names_s = [s[0].replace("\n"," ") for s in SESSIONS]
    x = np.arange(len(sess_names_s)); bw=0.16
    offsets = np.arange(5)-(5-1)/2

    for gi,(gk,gc) in enumerate(zip(masks_sum.keys(),colors_sum)):
        means=[]
        for sname,*_ in SESSIONS:
            r = future_ret6[masks_sum[gk] & (sess_s==sname)].dropna()
            means.append(r.mean()*100 if len(r)>=10 else 0.0)
        ax.bar(x+offsets[gi]*bw, means, bw, color=gc, alpha=0.85, edgecolor="none")

    ax.set_title(f"{pair}  ({base_c}/{quote_c})", fontsize=9, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([s.split()[0] for s in sess_names_s], fontsize=8)
    ax.set_ylabel("Mean (%)", fontsize=7.5)
    ax.grid(axis="y", alpha=0.2)

# 凡例パネル
ax_leg = axes[3][2]; ax_leg.axis("off")
handles=[plt.Rectangle((0,0),1,1,fc=c,alpha=0.85)
         for c in ["#95a5a6","#3498db","#e74c3c","#1a3a7a","#e07b00"]]
ax_leg.legend(handles,
              ["全BreakDown",f"≤Q{int(Q_LARGE*100)}",f"≤Q{int(Q_EXTREME*100)}",
               "≤Q10+ac>0（モメンタム）","≤Q10+ac<0（逆張り）"],
              fontsize=10, loc="center", framealpha=0.9, ncol=1)

plt.tight_layout()
fig.savefig(str(OUT_DIR/"all_pairs_ac_summary.png"), dpi=120,
            bbox_inches="tight", facecolor="#F8F9FA")
plt.close(fig)

print(f"\n保存先: {OUT_DIR}")
print("完了")
