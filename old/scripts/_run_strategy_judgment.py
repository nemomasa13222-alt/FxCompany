# -*- coding: utf-8 -*-
"""
12通貨ペア × 4セッション  最終戦略判定
──────────────────────────────────────────────────────────────
自己相関フィルター込みで順張り/逆張りを判定。
リターン: close.shift(-h) / close（strength_break と統一）

判定ルール（H=6本後, H=12本後 を確認）:
  SHORT（順張り）: Q10+ac>0 の Mean<0 AND Skew<-0.2
  LONG （逆張り）: Q10+ac<0 の Mean>0 AND Skew> 0.2
  WEAK_S / WEAK_L: Mean のみ満たす
  UNCLEAR        : どちらも不明確
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

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "strategy_judgment"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START = "2022-01-01"; END = "2024-12-31"
STRENGTH_WINDOW = 24; AC_WINDOW = 12
Q_LARGE = 0.25; Q_EXTREME = 0.10
HORIZONS = [1, 3, 6, 12, 24]
H_MAIN   = 6
JST = pd.Timedelta(hours=9)

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

# ── 読込 ────────────────────────────────────────────────────
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

# ── 強弱 ────────────────────────────────────────────────────
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    r = pair_lr[pair]
    raw_str[b] += r; raw_str[q] -= r
    cnt[b] += 1;     cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)

jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e,_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

def rolling_ac(series, w):
    arr=series.values; res=np.full(len(arr),np.nan)
    for i in range(w-1,len(arr)):
        x=arr[i-w+1:i+1]
        if np.any(np.isnan(x)): continue
        c=np.corrcoef(x[:-1],x[1:]); res[i]=c[0,1]
    return pd.Series(res, index=series.index)

# ── 全ペア解析 ───────────────────────────────────────────────
print("全ペア解析中...")
all_rows = []

for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    df_p = dfs[pair]
    close = df_p["Close"]
    diff  = str_df[base_c] - str_df[quote_c]
    q10   = diff.quantile(Q_EXTREME)
    q25   = diff.quantile(Q_LARGE)

    ac = rolling_ac(np.log(close/close.shift(1)), AC_WINDOW)

    breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & diff.notna()
    future_ret= {h: np.log(close.shift(-h)/close) for h in HORIZONS}

    masks = {
        "全BreakDown": breakdown,
        "Q25":         breakdown & (diff <= q25),
        "Q10":         breakdown & (diff <= q10),
        "Q10+ac>0":    breakdown & (diff <= q10) & (ac > 0.0) & ac.notna(),
        "Q10+ac<0":    breakdown & (diff <= q10) & (ac < 0.0) & ac.notna(),
    }

    for sname,s,e,_ in SESSIONS:
        sm = sess_s == sname
        row = {"pair":pair,"base":base_c,"quote":quote_c,"session":sname}
        for mk, mask in masks.items():
            r = future_ret[H_MAIN][mask & sm].dropna()
            if len(r) < 20:
                row[f"{mk}_n"]    = len(r)
                row[f"{mk}_mean"] = np.nan
                row[f"{mk}_skew"] = np.nan
            else:
                row[f"{mk}_n"]    = len(r)
                row[f"{mk}_mean"] = r.mean()*100
                row[f"{mk}_skew"] = stats.skew(r)
        all_rows.append(row)

df_all = pd.DataFrame(all_rows)
df_all.to_csv(OUT_DIR/"stats_ac.csv", index=False, encoding="utf-8-sig")

# ── 判定ロジック ─────────────────────────────────────────────
def judge(row):
    m_acp = row.get("Q10+ac>0_mean", np.nan)
    sk_acp= row.get("Q10+ac>0_skew", np.nan)
    n_acp = row.get("Q10+ac>0_n",    0)
    m_acn = row.get("Q10+ac<0_mean", np.nan)
    sk_acn= row.get("Q10+ac<0_skew", np.nan)
    n_acn = row.get("Q10+ac<0_n",    0)
    m_q10 = row.get("Q10_mean",      np.nan)

    # 強判定
    if (not np.isnan(m_acp)) and n_acp>=50 and m_acp<0 and sk_acp<-0.2:
        return "▼SHORT", "Q10+ac>0", m_acp, sk_acp, n_acp
    if (not np.isnan(m_acn)) and n_acn>=50 and m_acn>0 and sk_acn> 0.2:
        return "▲LONG",  "Q10+ac<0", m_acn, sk_acn, n_acn
    # 弱判定（Meanのみ）
    if (not np.isnan(m_acp)) and n_acp>=30 and m_acp<0:
        return "▽short", "Q10+ac>0", m_acp, sk_acp, n_acp
    if (not np.isnan(m_acn)) and n_acn>=30 and m_acn>0:
        return "△long",  "Q10+ac<0", m_acn, sk_acn, n_acn
    # Q10のみで判断（ac効果なし）
    if (not np.isnan(m_q10)) and m_q10<0:
        return "▽short", "Q10のみ",   m_q10, np.nan, row.get("Q10_n",0)
    if (not np.isnan(m_q10)) and m_q10>0:
        return "△long",  "Q10のみ",   m_q10, np.nan, row.get("Q10_n",0)
    return "─", "─", np.nan, np.nan, 0

# 判定を追加
judgments = [judge(row) for _,row in df_all.iterrows()]
df_all["judge"]  = [j[0] for j in judgments]
df_all["filter"] = [j[1] for j in judgments]
df_all["j_mean"] = [j[2] for j in judgments]
df_all["j_skew"] = [j[3] for j in judgments]
df_all["j_n"]    = [j[4] for j in judgments]

# ── コンソール出力 ───────────────────────────────────────────
pairs_list = list(PAIR_CURRENCIES.keys())
sess_names = [s[0] for s in SESSIONS]

print("\n" + "="*95)
print("  最終戦略判定マトリックス（自己相関フィルター込み）")
print("  ▼SHORT=順張り  ▲LONG=逆張り  ▽▲=弱シグナル  ─=不明")
print("="*95)
print(f"  {'ペア':8s}", end="")
for s in sess_names: print(f"  {s.replace(chr(10),' '):>15s}", end="")
print()
print("-"*95)

for pair in pairs_list:
    sub = df_all[df_all["pair"]==pair]
    print(f"  {pair:8s}", end="")
    for sname in sess_names:
        row = sub[sub["session"]==sname]
        if len(row)==0: print(f"  {'─':>15s}", end=""); continue
        j = row["judge"].values[0]
        m = row["j_mean"].values[0]
        f = row["filter"].values[0]
        if np.isnan(m): val = f"{'─':>15s}"
        else:           val = f"{j} {m:+.3f}%"
        print(f"  {val:>15s}", end="")
    print()

# ── 図1: 判定マトリックス（カラーグリッド） ─────────────────
def judge_color(j):
    if   "▼SHORT" in j: return "#1a3a7a", "white",  "▼SHORT\n（順張り・強）"
    elif "▽short" in j: return "#7fb3e8", "black",  "▽short\n（順張り・弱）"
    elif "▲LONG"  in j: return "#b03030", "white",  "▲LONG\n（逆張り・強）"
    elif "△long"  in j: return "#e8a0a0", "black",  "△long\n（逆張り・弱）"
    return "#dddddd", "#888888", "─"

fig, ax = plt.subplots(figsize=(18, 10))
fig.patch.set_facecolor("#f8f9fa"); ax.set_facecolor("#f0f0f0")

sess_labels = [s[0].replace("\n"," ") for s in SESSIONS]

for i,pair in enumerate(pairs_list):
    sub = df_all[df_all["pair"]==pair]
    base_c,quote_c = PAIR_CURRENCIES[pair]
    for j,sname in enumerate(sess_names):
        row = sub[sub["session"]==sname]
        judge_str = row["judge"].values[0] if len(row) else "─"
        flt       = row["filter"].values[0] if len(row) else "─"
        m_val     = row["j_mean"].values[0] if len(row) else np.nan
        sk_val    = row["j_skew"].values[0] if len(row) else np.nan
        n_val     = row["j_n"].values[0] if len(row) else 0

        bg, tc, label = judge_color(judge_str)
        ax.add_patch(plt.Rectangle((j, len(pairs_list)-1-i), 1, 1,
                     facecolor=bg, edgecolor="white", lw=1.5))

        # メインラベル
        ax.text(j+0.5, len(pairs_list)-1-i+0.65, label,
                ha="center", va="center", fontsize=8, color=tc,
                fontweight="bold")
        # フィルター
        ax.text(j+0.5, len(pairs_list)-1-i+0.35,
                flt.replace("\n"," "), ha="center", va="center",
                fontsize=6.5, color=tc, alpha=0.9)
        # Mean と n
        if not np.isnan(m_val):
            ax.text(j+0.5, len(pairs_list)-1-i+0.15,
                    f"μ={m_val:+.3f}%  n={int(n_val)}",
                    ha="center", va="center", fontsize=6, color=tc, alpha=0.85)

ax.set_xlim(0, len(sess_names)); ax.set_ylim(0, len(pairs_list))
ax.set_xticks([x+0.5 for x in range(len(sess_labels))])
ax.set_xticklabels(sess_labels, fontsize=11, fontweight="bold")
ax.set_yticks([y+0.5 for y in range(len(pairs_list))])
ax.set_yticklabels(reversed(pairs_list), fontsize=11, fontweight="bold")
ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")

from matplotlib.patches import Patch
legend_els=[
    Patch(fc="#1a3a7a",label="▼SHORT（強）: Q10+ac>0, Mean<0, Skew<-0.2"),
    Patch(fc="#7fb3e8",label="▽short（弱）: Mean<0 のみ"),
    Patch(fc="#b03030",label="▲LONG（強）:  Q10+ac<0, Mean>0, Skew>0.2"),
    Patch(fc="#e8a0a0",label="△long（弱）:  Mean>0 のみ"),
    Patch(fc="#dddddd",label="─  エッジなし"),
]
ax.legend(handles=legend_els, loc="lower center",
          bbox_to_anchor=(0.5, -0.08), ncol=5, fontsize=8.5, framealpha=0.95)
ax.set_title("12通貨ペア × 4セッション  最終戦略判定\n"
             "（強弱差Q10 + 自己相関フィルター / 6本後=30分後リターン）",
             fontsize=13, fontweight="bold", pad=14)

plt.tight_layout()
fig.savefig(OUT_DIR/"judgment_matrix.png", dpi=150,
            bbox_inches="tight", facecolor="#f8f9fa")
plt.close(fig)

# ── 図2: Mean × Skew バブルチャート（セッション別） ────────
fig, axes = plt.subplots(1, 4, figsize=(24, 7))
fig.patch.set_facecolor("#f8f9fa")
fig.suptitle("強弱差Q10 + 自己相関フィルター別  Mean vs Skew\n"
             "（青丸=ac>0群, 橙丸=ac<0群 / バブルサイズ=サンプル数 / 6本後）",
             fontsize=12, fontweight="bold")

for ax,(sname,s,e,scolor) in zip(axes, SESSIONS):
    ax.set_facecolor("#f8f8f8")
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
    ax.axvline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
    sub = df_all[df_all["session"]==sname]

    for pair in pairs_list:
        r = sub[sub["pair"]==pair]
        if len(r)==0: continue
        base_c,quote_c = PAIR_CURRENCIES[pair]
        for mk,clr,marker in [("Q10+ac>0","#1a3a7a","o"),
                               ("Q10+ac<0","#e07b00","s")]:
            m  = r[f"{mk}_mean"].values[0]
            sk = r[f"{mk}_skew"].values[0]
            n  = r[f"{mk}_n"].values[0]
            if np.isnan(m) or n<20: continue
            ax.scatter(m, sk, s=max(n/20,20), c=clr, alpha=0.75,
                       marker=marker, edgecolors="white", lw=0.5)
            ax.text(m, sk+max(abs(sk)*0.06,0.1), pair,
                    fontsize=7, ha="center", color=clr, fontweight="bold")

    ax.set_title(sname.replace("\n"," "), fontsize=10,
                 fontweight="bold", color=scolor)
    ax.set_xlabel("Mean（%）\n← SHORT有利 │ LONG有利 →", fontsize=8)
    ax.set_ylabel("Skew\n← SHORT有利 │ LONG有利 →", fontsize=8)
    ax.grid(alpha=0.2)
    ax.text(0.02,0.98,"● ac>0群 ■ ac<0群",
            transform=ax.transAxes, fontsize=7.5, va="top",
            bbox=dict(fc="white",alpha=0.8,boxstyle="round"))

plt.tight_layout()
fig.savefig(OUT_DIR/"mean_skew_bubble.png", dpi=140,
            bbox_inches="tight", facecolor="#f8f9fa")
plt.close(fig)

# ── 図3: 全ペア × 全horizon のheatmap（最良フィルター） ───────
fig, axes = plt.subplots(1, len(HORIZONS), figsize=(22, 9))
fig.patch.set_facecolor("#f8f9fa")
fig.suptitle("全ペア × 全Horizon  最良フィルター（Q10+ac）の期待値\n"
             "（赤=LONG有利 / 青=SHORT有利 / 各セルは4セッションの平均）",
             fontsize=12, fontweight="bold")

for ax, h in zip(axes, HORIZONS):
    mat = np.full((len(pairs_list), len(sess_names)), np.nan)
    for pi, pair in enumerate(pairs_list):
        df_p = dfs[pair]
        close = df_p["Close"]
        diff  = str_df[PAIR_CURRENCIES[pair][0]] - str_df[PAIR_CURRENCIES[pair][1]]
        q10   = diff.quantile(Q_EXTREME)
        ac    = rolling_ac(np.log(close/close.shift(1)), AC_WINDOW)
        breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & diff.notna()
        fr = np.log(close.shift(-h)/close)

        for si, (sname,*_) in enumerate(SESSIONS):
            sm = sess_s == sname
            # 最良フィルターを自動選択
            r_acp = fr[breakdown & (diff<=q10) & (ac>0) & ac.notna() & sm].dropna()
            r_acn = fr[breakdown & (diff<=q10) & (ac<0) & ac.notna() & sm].dropna()
            if len(r_acp)>=20 and len(r_acn)>=20:
                m_acp = r_acp.mean()*100; m_acn = r_acn.mean()*100
                mat[pi,si] = m_acp if abs(m_acp)>abs(m_acn) else m_acn
            elif len(r_acp)>=20: mat[pi,si] = r_acp.mean()*100
            elif len(r_acn)>=20: mat[pi,si] = r_acn.mean()*100

    from matplotlib.colors import TwoSlopeNorm
    vmax = np.nanpercentile(np.abs(mat),95) if not np.all(np.isnan(mat)) else 0.01
    vmax = max(vmax, 0.001)
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    im = ax.imshow(mat, cmap="RdBu", aspect="auto", norm=norm)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    ax.set_xticks(range(len(sess_names)))
    ax.set_xticklabels([s.split()[0] for s in sess_labels],fontsize=8)
    ax.set_yticks(range(len(pairs_list)))
    ax.set_yticklabels(pairs_list, fontsize=8)
    ax.set_title(f"{h}本後\n({h*5}分後)", fontsize=9, fontweight="bold")
    for pi in range(len(pairs_list)):
        for si in range(len(sess_names)):
            val = mat[pi,si]
            if not np.isnan(val):
                c="white" if abs(val)>vmax*0.55 else "black"
                ax.text(si,pi,f"{val:+.3f}",ha="center",va="center",
                        fontsize=6.5,color=c)

plt.tight_layout()
fig.savefig(OUT_DIR/"horizon_heatmap.png", dpi=140,
            bbox_inches="tight", facecolor="#f8f9fa")
plt.close(fig)

# ── 最終サマリー表 ────────────────────────────────────────────
print("\n" + "="*100)
print("  最終戦略判定サマリー（自己相関フィルター付き）")
print("="*100)
print(f"  {'ペア':8s}  {'セッション':16s}  {'判定':14s}  {'最良フィルター':16s}  {'Mean%':>8s}  {'Skew':>7s}  {'n':>5s}")
print("-"*100)

playbook = []
for pair in pairs_list:
    sub = df_all[df_all["pair"]==pair]
    base_c,quote_c = PAIR_CURRENCIES[pair]
    for sname in sess_names:
        row = sub[sub["session"]==sname]
        if len(row)==0: continue
        j = row["judge"].values[0]
        flt = row["filter"].values[0]
        m = row["j_mean"].values[0]
        sk = row["j_skew"].values[0]
        n = row["j_n"].values[0]
        mark = "★" if j in ["▼SHORT","▲LONG"] else "  "
        if not np.isnan(m):
            print(f"  {mark}{pair:8s}  {sname.replace(chr(10),' '):16s}  "
                  f"{j:14s}  {flt:16s}  {m:+8.4f}  {sk:+7.3f}  {n:5.0f}")
            playbook.append({"pair":pair,"base":base_c,"quote":quote_c,
                             "session":sname,"judge":j,"filter":flt,
                             "mean":m,"skew":sk,"n":int(n)})
        else:
            print(f"    {pair:8s}  {sname.replace(chr(10),' '):16s}  {'─':14s}")

pd.DataFrame(playbook).to_csv(OUT_DIR/"playbook.csv",
                               index=False, encoding="utf-8-sig")
print(f"\n保存先: {OUT_DIR}")
print("完了")
