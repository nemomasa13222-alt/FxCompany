# -*- coding: utf-8 -*-
"""
12ペア × 4セッション  統計解析
─────────────────────────────────────────────────────────────
ブレイクダウン発生後のリターン分布を時間帯別に分析し、
各ペア × セッション に「順張り / 逆張り / 不明」を判定する。

指標:
  Mean      : 期待値（負=下落傾向=SHORT有利）
  Skew      : 歪度（負=左裾厚い=SHORT有利, 正=右裾厚い=LONG有利）
  ExKurt    : 超過尖度（高い=ファットテール=大きな動きが起きやすい）
  LeftTail  : 左裾の厚さ（5%ileの絶対値 / 95%ileの絶対値）
              >1 なら左（下落）裾が厚い
  DownRate  : 価格下落率（SHORTの勝率の理論値）
  tStat     : t統計量（絶対値が大きいほど有意）
  pValue    : 有意確率（<0.05 = 有意）

判定ルール:
  SHORT（順張り）: Mean<0 AND Skew<-0.2 AND DownRate>51%
  LONG （逆張り）: Mean>0 AND Skew> 0.2 AND DownRate<49%
  WEAK_S        : Mean<0 のみ（弱い順張りシグナル）
  WEAK_L        : Mean>0 のみ（弱い逆張りシグナル）
  UNCLEAR       : それ以外
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
import warnings; warnings.filterwarnings("ignore")

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "pair_session_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STRENGTH_WINDOW = 24
ATR_PERIOD      = 14
HORIZONS        = [6, 12, 24]   # 複数で確認
H_MAIN          = 12            # 主分析ホライゾン
JST             = pd.Timedelta(hours=9)

SESSIONS = [
    ("東京 09-15",  9, 15, "#f39c12"),
    ("欧州 15-21", 15, 21, "#27ae60"),
    ("NY   21-03", 21,  3, "#2980b9"),
    ("深夜 03-09",  3,  9, "#8e44ad"),
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
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
print(f"共通バー数: {len(common_idx):,}  ({common_idx[0].date()} 〜 {common_idx[-1].date()})")

# ── 通貨強弱 ────────────────────────────────────────────────
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

# ── 統計算出関数 ─────────────────────────────────────────────
def calc_stats(r: np.ndarray, h: int) -> dict:
    """リターン配列から統計量を算出"""
    if len(r) < 30:
        return {"n":len(r),"mean":np.nan,"skew":np.nan,"exkurt":np.nan,
                "lefttail":np.nan,"downrate":np.nan,"tstat":np.nan,"pval":np.nan}
    mean_v  = r.mean() * 100       # %換算
    skew_v  = stats.skew(r)
    kurt_v  = stats.kurtosis(r)    # excess kurtosis
    p5, p95 = np.percentile(r,[5,95])
    lefttail= abs(p5)/abs(p95) if abs(p95)>1e-10 else np.nan
    downrate= (r<0).mean()*100
    tstat, pval = stats.ttest_1samp(r, 0)
    return {
        "n":len(r), "mean":mean_v, "skew":skew_v,
        "exkurt":kurt_v, "lefttail":lefttail,
        "downrate":downrate, "tstat":tstat, "pval":pval
    }

def judge(s: dict) -> str:
    """統計量から手法を判定"""
    if s["n"] < 30 or np.isnan(s["mean"]): return "─"
    m, sk, dr, p = s["mean"], s["skew"], s["downrate"], s["pval"]
    # 有意水準（緩め: 0.15 で判断）
    sig = p < 0.15
    if m < 0 and sk < -0.2 and dr > 51:
        return "▼SHORT" if sig else "▽short"
    if m > 0 and sk >  0.2 and dr < 49:
        return "▲LONG"  if sig else "△long"
    if m < 0 and dr > 51:
        return "▽short（弱）"
    if m > 0 and dr < 49:
        return "△long（弱）"
    return "─"

# ── 全ペア × セッション解析 ────────────────────────────────
print("\n解析中...")
all_rows = []
pair_data = {}   # {pair: {sess: {h: stats}}}

for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    df_p = dfs[pair]

    # ATR
    hi,lo,cl = df_p["High"],df_p["Low"],df_p["Close"].shift(1)
    tr = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()

    # ブレイクダウン（フィルターなし、全て）
    breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & atr.notna()

    # 先行リターン（次足Open基準）
    entry_p = df_p["Open"].shift(-1)
    fut = {h: (np.log(df_p["Close"].shift(-h)/entry_p)).values
           for h in HORIZONS}

    pair_data[pair] = {}
    for sname,s,e,color in SESSIONS:
        sess_mask = (sess_s == sname)
        mask = breakdown & sess_mask
        bd_idx = np.where(mask.values)[0]

        pair_data[pair][sname] = {}
        for h in HORIZONS:
            r_raw = fut[h][bd_idx]
            valid = ~np.isnan(r_raw)
            r = r_raw[valid]
            st = calc_stats(r, h)
            pair_data[pair][sname][h] = st

            row = {"pair":pair,"base":base_c,"quote":quote_c,
                   "session":sname,"horizon":h, **st,
                   "judge":judge(st)}
            all_rows.append(row)

df_stats = pd.DataFrame(all_rows)
df_stats.to_csv(OUT_DIR/"stats_all.csv", index=False, encoding="utf-8-sig")

# ── コンソール出力（主要ホライゾン） ────────────────────────
print("\n" + "="*90)
print(f"  手法判定サマリー  ─  {H_MAIN}本後（{H_MAIN*5}分後）")
print("="*90)
print(f"  {'ペア':8s}", end="")
for s,*_ in SESSIONS: print(f"  {s[:7]:>12s}", end="")
print()
print(f"  {'':8s}", end="")
for _,*_ in SESSIONS: print(f"  {'Mean%/Skew':>12s}", end="")
print()
print("-"*90)

for pair in PAIR_CURRENCIES:
    if pair not in pair_data: continue
    print(f"  {pair:8s}", end="")
    for sname,*_ in SESSIONS:
        st = pair_data[pair][sname].get(H_MAIN,{})
        j  = judge(st)
        m  = st.get("mean",np.nan); sk = st.get("skew",np.nan)
        label = f"{m:+.3f}/{sk:+.2f}" if not np.isnan(m) else "─"
        print(f"  {label:>12s}", end="")
    print()

# 判定サマリー
print(f"\n  {'ペア':8s}", end="")
for s,*_ in SESSIONS: print(f"  {s[:7]:>12s}", end="")
print("\n" + "-"*90)
for pair in PAIR_CURRENCIES:
    if pair not in pair_data: continue
    print(f"  {pair:8s}", end="")
    for sname,*_ in SESSIONS:
        st = pair_data[pair][sname].get(H_MAIN,{})
        j  = judge(st)
        print(f"  {j:>12s}", end="")
    print()

# ════════════════════════════════════════════════════════════
# 図1: 判定ヒートマップ（12ペア × 4セッション）
# ════════════════════════════════════════════════════════════
print("\n図描画中...")
pairs_list = list(PAIR_CURRENCIES.keys())
sess_names = [s[0] for s in SESSIONS]

# Mean と Skew を2段で表示
fig, axes = plt.subplots(2, 2, figsize=(22, 14))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"12ペア × 4セッション  統計解析  ─  {H_MAIN}本後（{H_MAIN*5}分後）リターン\n"
             "ブレイクダウン（現在足Low < 前足Low）発生後の分布特性",
             fontsize=13, fontweight="bold")

df_main = df_stats[df_stats["horizon"]==H_MAIN]

for (r_ax, c_ax), (metric, label, cmap, center) in zip(
    [(0,0),(0,1),(1,0),(1,1)],
    [("mean",     "期待値 Mean(%)",      "RdYlGn_r", 0),
     ("skew",     "歪度 Skew",           "RdYlGn_r", 0),
     ("exkurt",   "超過尖度 ExKurt",      "YlOrRd",   0),
     ("lefttail", "左裾比 LeftTail\n(>1=左裾厚=SHORT有利)", "RdYlGn_r", 1)],
):
    ax = axes[r_ax][c_ax]
    ax.set_facecolor("#f0f0f0")
    mat = np.full((len(pairs_list), len(sess_names)), np.nan)
    for i,pair in enumerate(pairs_list):
        for j,sname in enumerate(sess_names):
            sub = df_main[(df_main["pair"]==pair) & (df_main["session"]==sname)]
            if len(sub): mat[i,j] = sub[metric].values[0]

    # カラースケール（中心固定）
    finite = mat[~np.isnan(mat)]
    if len(finite)==0: continue
    vmax = np.nanpercentile(np.abs(finite - center), 95)
    vmax = max(vmax, 0.001)

    from matplotlib.colors import TwoSlopeNorm
    norm = TwoSlopeNorm(vmin=center-vmax, vcenter=center, vmax=center+vmax)
    im = ax.imshow(mat, cmap=cmap, aspect="auto", norm=norm)
    plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)

    ax.set_xticks(range(len(sess_names)))
    ax.set_xticklabels([s.split()[0] for s in sess_names], fontsize=9)
    ax.set_yticks(range(len(pairs_list)))
    ax.set_yticklabels(pairs_list, fontsize=9)
    ax.set_title(label, fontsize=11, fontweight="bold")

    for i in range(len(pairs_list)):
        for j in range(len(sess_names)):
            val = mat[i,j]
            if np.isnan(val): continue
            fmt = f"{val:+.3f}" if metric in ["mean","skew"] else f"{val:.2f}"
            # 判定マーク付加
            st = pair_data.get(pairs_list[i],{}).get(sess_names[j],{}).get(H_MAIN,{})
            jd = judge(st)
            mark = "▼" if "SHORT" in jd else "▲" if "LONG" in jd else ""
            txt = f"{mark}{fmt}"
            c = "white" if abs(val-center) > vmax*0.55 else "black"
            ax.text(j, i, txt, ha="center", va="center",
                    fontsize=7.5, color=c, fontweight="bold" if mark else "normal")

plt.tight_layout(rect=[0,0,1,0.95])
fig.savefig(OUT_DIR/"heatmap_stats.png", dpi=140,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ════════════════════════════════════════════════════════════
# 図2: 手法判定マップ（最終まとめ）
# ════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(16, 9))
fig.patch.set_facecolor("#fafafa"); ax.set_facecolor("#f0f0f0")

# カラーマッピング
def judge_color(j):
    if "▼SHORT" in j:   return "#1a6fa8", "▼ SHORT\n（強）"
    if "▽short" in j:   return "#7fb3d3", "▽ short\n（弱）"
    if "▲LONG"  in j:   return "#c0392b", "▲ LONG\n（強）"
    if "△long"  in j:   return "#e8a0a0", "△ long\n（弱）"
    return "#cccccc", "─"

judge_mat  = np.zeros((len(pairs_list), len(sess_names)))
color_grid = [[None]*len(sess_names) for _ in range(len(pairs_list))]
label_grid = [[""]*len(sess_names) for _ in range(len(pairs_list))]

for i,pair in enumerate(pairs_list):
    for j,sname in enumerate(sess_names):
        st = pair_data.get(pair,{}).get(sname,{}).get(H_MAIN,{})
        jd = judge(st)
        c,l = judge_color(jd)
        color_grid[i][j] = c
        m  = st.get("mean", np.nan)
        sk = st.get("skew", np.nan)
        n  = st.get("n", 0)
        p  = st.get("pval", np.nan)
        sig = "✓" if (not np.isnan(p) and p<0.10) else ""
        label_grid[i][j] = f"{l}\n{m:+.3f}%\nsk={sk:+.2f}{sig}" \
                           if not np.isnan(m) else "─"

# 描画
for i in range(len(pairs_list)):
    for j in range(len(sess_names)):
        ax.add_patch(plt.Rectangle((j,i),1,1,
                     facecolor=color_grid[i][j], edgecolor="white", lw=1.5))
        ax.text(j+0.5, i+0.5, label_grid[i][j],
                ha="center", va="center", fontsize=7.5,
                color="white" if color_grid[i][j] in ["#1a6fa8","#c0392b"] else "#333333",
                fontweight="bold")

ax.set_xlim(0, len(sess_names)); ax.set_ylim(0, len(pairs_list))
ax.set_xticks([x+0.5 for x in range(len(sess_names))])
ax.set_xticklabels(sess_names, fontsize=11, fontweight="bold")
ax.set_yticks([y+0.5 for y in range(len(pairs_list))])
ax.set_yticklabels(pairs_list, fontsize=11, fontweight="bold")
ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")

# 凡例
from matplotlib.patches import Patch
legend_els = [
    Patch(facecolor="#1a6fa8", label="▼ SHORT（強） p<0.10, Mean<0, Skew<-0.2, Down>51%"),
    Patch(facecolor="#7fb3d3", label="▽ short（弱） Mean<0 または Down>51%"),
    Patch(facecolor="#c0392b", label="▲ LONG（強）  p<0.10, Mean>0, Skew>0.2, Down<49%"),
    Patch(facecolor="#e8a0a0", label="△ long（弱）  Mean>0 または Down<49%"),
    Patch(facecolor="#cccccc", label="─  判定不明（エッジなし）"),
]
ax.legend(handles=legend_els, loc="lower right", fontsize=8,
          framealpha=0.95, ncol=1, bbox_to_anchor=(1.0,-0.01))

ax.set_title(f"手法判定マップ  ─  12ペア × 4セッション\n"
             f"({H_MAIN}本後={H_MAIN*5}分後リターン / ✓=p<0.10有意)",
             fontsize=12, fontweight="bold", pad=14)

plt.tight_layout()
fig.savefig(OUT_DIR/"judgment_map.png", dpi=140,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ════════════════════════════════════════════════════════════
# 図3: 各ペアのリターン分布（セッション別 KDE 重ね）
# ════════════════════════════════════════════════════════════
pairs_list = list(PAIR_CURRENCIES.keys())
n_cols = 4; n_rows = 3
fig, axes = plt.subplots(n_rows, n_cols, figsize=(24, n_rows*5))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"ペア別 セッション別 リターン分布  ({H_MAIN}本後={H_MAIN*5}分後)\n"
             "ブレイクダウン発生後の確率密度  ─  縦破線=0（中立）/ 色=時間帯",
             fontsize=13, fontweight="bold")

from scipy.stats import gaussian_kde
for i,pair in enumerate(pairs_list):
    ax = axes[i//n_cols][i%n_cols]
    ax.set_facecolor("#f8f8f8")
    ax.axvline(0, color="#333333", lw=1.0, ls="--", alpha=0.6)

    df_p = dfs[pair]
    entry_p = df_p["Open"].shift(-1)
    fut_12  = np.log(df_p["Close"].shift(-H_MAIN)/entry_p)*100
    breakdown = (df_p["Low"] < df_p["Low"].shift(1))

    stat_lines = []
    for sname,s,e,color in SESSIONS:
        sess_mask = (sess_s == sname)
        mask = breakdown & sess_mask
        r = fut_12[mask].dropna().values
        if len(r) < 30: continue
        lo,hi = np.percentile(r,[1,99])
        r_clip = r[(r>=lo)&(r<=hi)]
        if len(r_clip)<10: continue
        try:
            kde = gaussian_kde(r_clip, bw_method=0.3)
            xs  = np.linspace(lo,hi,300)
            ax.fill_between(xs, kde(xs), alpha=0.25, color=color)
            ax.plot(xs, kde(xs), color=color, lw=2.0,
                    label=f"{sname.split()[0]}")
            ax.axvline(r.mean()*1, color=color, lw=1.0, ls=":",alpha=0.8)
        except: pass

        st = calc_stats(r, H_MAIN)
        jd = judge(st)
        stat_lines.append(f"{sname.split()[0]}: μ={st['mean']:+.3f}% "
                          f"sk={st['skew']:+.2f} ku={st['exkurt']:.1f} {jd}")

    base_c,quote_c = PAIR_CURRENCIES[pair]
    ax.set_title(f"{pair}  ({base_c}/{quote_c})", fontsize=10, fontweight="bold")
    ax.set_xlabel("対数リターン (%)", fontsize=7.5)
    ax.set_ylabel("確率密度", fontsize=7.5)
    ax.legend(fontsize=7, loc="upper right", framealpha=0.8)

    info = "\n".join(stat_lines)
    ax.text(0.02,0.98,info,transform=ax.transAxes,fontsize=6.2,
            va="top",ha="left",
            bbox=dict(fc="white",alpha=0.85,boxstyle="round,pad=0.3",ec="#dddddd"))

plt.tight_layout()
fig.savefig(OUT_DIR/"distribution_all_pairs.png", dpi=130,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ════════════════════════════════════════════════════════════
# 図4: Skew vs ExKurt バブルチャート（ペア × セッション）
# ════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 4, figsize=(24, 7), sharey=False)
fig.patch.set_facecolor("#fafafa")
fig.suptitle("歪度（Skew） vs 超過尖度（ExKurt）  ─  セッション別\n"
             "バブルサイズ=サンプル数  /  左下=ファットテール（大きな動き多い）  "
             "Skew負=SHORT有利 / Skew正=LONG有利",
             fontsize=12, fontweight="bold")

sess_colors = {s[0]:s[3] for s in SESSIONS}
for ax, (sname,s,e,color) in zip(axes, SESSIONS):
    ax.set_facecolor("#f8f8f8")
    ax.axvline(0, color="#333333", lw=0.8, ls="--", alpha=0.5)
    ax.axhline(0, color="#333333", lw=0.8, ls="--", alpha=0.5)

    for pair in pairs_list:
        st = pair_data.get(pair,{}).get(sname,{}).get(H_MAIN,{})
        if st.get("n",0)<30: continue
        sk = st.get("skew",np.nan); ku = st.get("exkurt",np.nan)
        n  = st.get("n",100)
        if np.isnan(sk) or np.isnan(ku): continue
        jd = judge(st)
        c = "#1a6fa8" if "SHORT" in jd else "#c0392b" if "LONG" in jd else "#888888"
        ax.scatter(sk, ku, s=n/80, color=c, alpha=0.75, edgecolors="white", lw=0.5)
        ax.text(sk, ku+max(ku*0.05,0.3), pair, fontsize=7.5, ha="center",
                fontweight="bold", color=c)

    ax.set_title(sname.replace("\n"," "), fontsize=10, fontweight="bold", color=color)
    ax.set_xlabel("歪度 Skew\n← SHORT有利 │ LONG有利 →", fontsize=8)
    ax.set_ylabel("超過尖度 ExKurt（ファットテール度）", fontsize=8)
    ax.grid(alpha=0.2)

plt.tight_layout()
fig.savefig(OUT_DIR/"skew_kurt_scatter.png", dpi=140,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終サマリーCSV ─────────────────────────────────────────
# 各ペア×セッションの判定結果をワイドフォームで出力
pivot_judge = df_stats[df_stats["horizon"]==H_MAIN].pivot_table(
    index="pair", columns="session",
    values=["mean","skew","exkurt","lefttail","downrate","pval"],
    aggfunc="first")
pivot_judge.to_csv(OUT_DIR/"stats_pivot.csv", encoding="utf-8-sig")

# 判定テーブル
rows_jd = []
for pair in pairs_list:
    row = {"pair":pair}
    for sname,*_ in SESSIONS:
        st = pair_data.get(pair,{}).get(sname,{}).get(H_MAIN,{})
        jd = judge(st)
        m  = st.get("mean",np.nan)
        sk = st.get("skew",np.nan)
        n  = st.get("n",0)
        row[f"{sname}_judge"] = jd
        row[f"{sname}_mean"]  = round(m,4) if not np.isnan(m) else None
        row[f"{sname}_skew"]  = round(sk,3) if not np.isnan(sk) else None
        row[f"{sname}_n"]     = n
    rows_jd.append(row)
pd.DataFrame(rows_jd).to_csv(OUT_DIR/"judgment_table.csv",
                              index=False, encoding="utf-8-sig")

print(f"\n保存先: {OUT_DIR}")
print("  - heatmap_stats.png    : 統計量ヒートマップ（Mean/Skew/ExKurt/LeftTail）")
print("  - judgment_map.png     : 手法判定マップ（12×4 カラーグリッド）")
print("  - distribution_all_pairs.png : 全ペア分布KDE（セッション別重ね）")
print("  - skew_kurt_scatter.png: 歪度×尖度バブルチャート")
print("  - judgment_table.csv   : 手法判定テーブル")
print("完了")
