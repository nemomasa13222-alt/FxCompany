# -*- coding: utf-8 -*-
"""
USD/JPY デュアルシステム ロバストネス検証（IS期間）
────────────────────────────────────────────────────────────
パラメータ感度を2×2マトリックスで確認：
  マトリックス① ATR期間 × Q閾値        → PF・DD ヒートマップ
  マトリックス② 自己相関閾値A × B      → PF・DD ヒートマップ
  時間安定性  : 2022年 / 2023年 それぞれ黒字か確認
合格基準（4項目）:
  R1: 全組み合わせ中 PF>1.0 の割合 ≥ 80%
  R2: 採用パラメータが PF上位50% に入る
  R3: 2022年 PF>1.0 かつ 2023年 PF>1.0
  R4: MaxDD < 25%（全組み合わせ）
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
OUT_DIR  = BASE / "docs" / "usdjpy_dual"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START = "2022-01-01"; IS_END = "2023-12-31"
STRENGTH_WINDOW = 24
JST       = pd.Timedelta(hours=9)
CAPITAL   = 1_000_000; RISK_PCT = 0.005
PIP_VALUE = 100; PIP_SIZE = 0.01
MAX_HOLD  = 48

# ── ベースパラメータ（採用値） ────────────────────────────────
BASE_ATR   = 14
BASE_Q     = 0.10
BASE_AC_A  = 0.15   # 戦略A(ショート): ac > X
BASE_AC_B  = 0.00   # 戦略B(ロング):  ac < X

# ── スキャン範囲 ─────────────────────────────────────────────
ATR_VALS  = [7, 10, 14, 20, 28]
Q_VALS    = [0.05, 0.10, 0.15, 0.20, 0.25]
AC_A_VALS = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25]
AC_B_VALS = [-0.10, -0.05, 0.00, 0.05, 0.10]

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
usdjpy = dfs["USDJPY"].copy()
is_idx   = (common_idx >= IS_START) & (common_idx <= IS_END)
is22_idx = (common_idx >= "2022-01-01") & (common_idx <= "2022-12-31")
is23_idx = (common_idx >= "2023-01-01") & (common_idx <= "2023-12-31")

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
str_df       = pd.DataFrame(raw_str)
strength_raw = str_df["USD"] - str_df["JPY"]

# セッション
jst_hour = (common_idx + JST).hour
def in_sess(h_series, s, e):
    if s < e: return (h_series >= s) & (h_series < e)
    return (h_series >= s) | (h_series < e)

sess_NY    = in_sess(pd.Series(jst_hour, index=common_idx), 21, 3)
sess_Tokyo = in_sess(pd.Series(jst_hour, index=common_idx),  9, 15)

# ブレイクダウン（Q依存なので後で適用）
breakdown_base = (usdjpy["Low"] < usdjpy["Low"].shift(1)) & strength_raw.notna()

# 自己相関（AC_WINDOW=12固定）
ret = np.log(usdjpy["Close"]/usdjpy["Close"].shift(1))
def rolling_ac(series, window):
    arr=series.values; res=np.full(len(arr),np.nan)
    for i in range(window-1,len(arr)):
        x=arr[i-window+1:i+1]
        if np.any(np.isnan(x)): continue
        c=np.corrcoef(x[:-1],x[1:]); res[i]=c[0,1]
    return pd.Series(res, index=series.index)

ac = rolling_ac(ret, 12)   # AC_WINDOWは12固定

# ── バックテスト関数（高速版） ────────────────────────────────
def fast_bt(signal_mask, direction, atr_arr):
    """シグナルマスクと方向を受け取り、P&Lシリーズを返す"""
    positions = np.where(signal_mask)[0]
    pnl_list  = []
    for sp in positions:
        ep = sp + 1
        if ep >= len(usdjpy): continue
        entry_p = usdjpy["Open"].iloc[ep]
        atr_val = atr_arr[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_dist = atr_val
        sl_pips = sl_dist / PIP_SIZE
        if sl_pips <= 0: continue
        lot = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

        if direction == "short":
            best = entry_p; trail = entry_p + sl_dist
            exit_p = None; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep+h
                if bp >= len(usdjpy): break
                bh = usdjpy["High"].iloc[bp]; bl = usdjpy["Low"].iloc[bp]; held=h
                if bh >= trail: exit_p=trail; break
                if bl < best: best=bl; trail=min(trail, best+sl_dist)
            if exit_p is None:
                fp=ep+held
                if fp < len(usdjpy): exit_p=usdjpy["Close"].iloc[fp]
                else: continue
            pnl = (entry_p - exit_p)/PIP_SIZE*PIP_VALUE*lot
        else:
            best = entry_p; trail = entry_p - sl_dist
            exit_p = None; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep+h
                if bp >= len(usdjpy): break
                bh = usdjpy["High"].iloc[bp]; bl = usdjpy["Low"].iloc[bp]; held=h
                if bl <= trail: exit_p=trail; break
                if bh > best: best=bh; trail=max(trail, best-sl_dist)
            if exit_p is None:
                fp=ep+held
                if fp < len(usdjpy): exit_p=usdjpy["Close"].iloc[fp]
                else: continue
            pnl = (exit_p - entry_p)/PIP_SIZE*PIP_VALUE*lot

        pnl_list.append((usdjpy.index[sp], pnl))
    return pnl_list

def calc_stats(pnl_pairs, period_mask=None):
    if not pnl_pairs: return {"pf":0,"dd":999,"pnl":0,"n":0}
    df = pd.DataFrame(pnl_pairs, columns=["bar","pnl"])
    if period_mask is not None:
        df = df[df["bar"].isin(common_idx[period_mask])]
    if len(df)==0: return {"pf":0,"dd":999,"pnl":0,"n":0}
    wins = df[df["pnl"]>0]["pnl"].sum()
    loss = df[df["pnl"]<=0]["pnl"].abs().sum()
    pf   = wins/loss if loss>0 else float("inf")
    cum  = df["pnl"].cumsum()
    dd   = (cum.cummax()-cum).max()/CAPITAL*100
    return {"pf":pf,"dd":dd,"pnl":df["pnl"].sum(),"n":len(df)}

# ════════════════════════════════════════════════════════════
# マトリックス① ATR × Q閾値
# ════════════════════════════════════════════════════════════
print("\nマトリックス①: ATR × Q閾値 スキャン中...")
mat1_pf = np.full((len(ATR_VALS), len(Q_VALS)), np.nan)
mat1_dd = np.full((len(ATR_VALS), len(Q_VALS)), np.nan)
mat1_pnl= np.full((len(ATR_VALS), len(Q_VALS)), np.nan)

for i, atr_p in enumerate(ATR_VALS):
    # ATRを計算
    hi,lo,cl=usdjpy["High"],usdjpy["Low"],usdjpy["Close"].shift(1)
    tr=pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr_arr = tr.rolling(atr_p).mean().values

    for j, q_val in enumerate(Q_VALS):
        q_thresh = strength_raw.quantile(q_val)
        bd = breakdown_base & (strength_raw <= q_thresh)

        # 戦略A
        sig_A = bd & is_idx & sess_NY    & (ac > BASE_AC_A) & ac.notna()
        pnl_A = fast_bt(sig_A, "short", atr_arr)

        # 戦略B
        sig_B = bd & is_idx & sess_Tokyo & (ac < BASE_AC_B) & ac.notna()
        pnl_B = fast_bt(sig_B, "long",  atr_arr)

        combined = pnl_A + pnl_B
        sv = calc_stats(combined)
        mat1_pf[i,j]  = sv["pf"]
        mat1_dd[i,j]  = sv["dd"]
        mat1_pnl[i,j] = sv["pnl"]

    print(f"  ATR={atr_p:2d}: PF範囲 {mat1_pf[i,:].min():.2f}〜{mat1_pf[i,:].max():.2f}")

# ════════════════════════════════════════════════════════════
# マトリックス② 自己相関閾値A × B
# ════════════════════════════════════════════════════════════
print("\nマトリックス②: AC閾値A × B スキャン中...")
# ベースATRを使用
hi,lo,cl=usdjpy["High"],usdjpy["Low"],usdjpy["Close"].shift(1)
tr=pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
atr_base = tr.rolling(BASE_ATR).mean().values
q_base   = strength_raw.quantile(BASE_Q)
bd_base  = breakdown_base & (strength_raw <= q_base)

mat2_pf = np.full((len(AC_A_VALS), len(AC_B_VALS)), np.nan)
mat2_dd = np.full((len(AC_A_VALS), len(AC_B_VALS)), np.nan)
mat2_n  = np.full((len(AC_A_VALS), len(AC_B_VALS)), np.nan)

for i, ac_a in enumerate(AC_A_VALS):
    for j, ac_b in enumerate(AC_B_VALS):
        sig_A = bd_base & is_idx & sess_NY    & (ac > ac_a) & ac.notna()
        sig_B = bd_base & is_idx & sess_Tokyo & (ac < ac_b) & ac.notna()
        pnl_A = fast_bt(sig_A, "short", atr_base)
        pnl_B = fast_bt(sig_B, "long",  atr_base)
        sv    = calc_stats(pnl_A + pnl_B)
        mat2_pf[i,j] = sv["pf"]
        mat2_dd[i,j] = sv["dd"]
        mat2_n[i,j]  = sv["n"]

print(f"  完了: PF範囲 {np.nanmin(mat2_pf):.2f}〜{np.nanmax(mat2_pf):.2f}")

# ════════════════════════════════════════════════════════════
# 時間安定性: 2022 vs 2023
# ════════════════════════════════════════════════════════════
print("\n時間安定性確認...")
sig_A_base = bd_base & is_idx & sess_NY    & (ac > BASE_AC_A) & ac.notna()
sig_B_base = bd_base & is_idx & sess_Tokyo & (ac < BASE_AC_B) & ac.notna()
pnl_A_all  = fast_bt(sig_A_base, "short", atr_base)
pnl_B_all  = fast_bt(sig_B_base, "long",  atr_base)
combined_all = pnl_A_all + pnl_B_all

sv22 = calc_stats(combined_all, is22_idx)
sv23 = calc_stats(combined_all, is23_idx)
sv22A= calc_stats(pnl_A_all, is22_idx); sv23A = calc_stats(pnl_A_all, is23_idx)
sv22B= calc_stats(pnl_B_all, is22_idx); sv23B = calc_stats(pnl_B_all, is23_idx)

print(f"\n  {'':20s} {'2022':>12s} {'2023':>12s}")
print(f"  {'戦略A（ショート）':20s} PF={sv22A['pf']:.2f} n={sv22A['n']}   PF={sv23A['pf']:.2f} n={sv23A['n']}")
print(f"  {'戦略B（ロング）':20s}  PF={sv22B['pf']:.2f} n={sv22B['n']}   PF={sv23B['pf']:.2f} n={sv23B['n']}")
print(f"  {'統合システム':20s}      PF={sv22['pf']:.2f} n={sv22['n']}   PF={sv23['pf']:.2f} n={sv23['n']}")

# ════════════════════════════════════════════════════════════
# ロバストネス判定
# ════════════════════════════════════════════════════════════
all_pf = np.concatenate([mat1_pf.flatten(), mat2_pf.flatten()])
all_dd = np.concatenate([mat1_dd.flatten(), mat2_dd.flatten()])
all_pf = all_pf[~np.isnan(all_pf)]
all_dd = all_dd[~np.isnan(all_dd)]

base_pf_mat1 = mat1_pf[ATR_VALS.index(BASE_ATR), Q_VALS.index(BASE_Q)]
base_pf_mat2 = mat2_pf[AC_A_VALS.index(BASE_AC_A), AC_B_VALS.index(BASE_AC_B)]

r1_ratio = (all_pf > 1.0).mean() * 100
r2_mat1  = (base_pf_mat1 > np.nanmedian(mat1_pf))
r2_mat2  = (base_pf_mat2 > np.nanmedian(mat2_pf))
r3_ok    = (sv22["pf"] > 1.0) and (sv23["pf"] > 1.0)
r4_ok    = (all_dd < 25).all()

print("\n" + "="*65)
print("  ロバストネス判定")
print("="*65)
print(f"\n  R1: PF>1.0 の割合  {r1_ratio:.1f}%  {'✅ 合格(≥80%)' if r1_ratio>=80 else '❌ 不合格'}")
print(f"  R2: 採用PFが中央値超  Mat①:{r2_mat1}  Mat②:{r2_mat2}  "
      f"{'✅ 合格' if r2_mat1 and r2_mat2 else '❌ 不合格'}")
print(f"  R3: 年別安定  2022 PF={sv22['pf']:.2f}  2023 PF={sv23['pf']:.2f}  "
      f"{'✅ 合格' if r3_ok else '❌ 不合格'}")
print(f"  R4: 全DD<25%  最大DD={all_dd.max():.1f}%  "
      f"{'✅ 合格' if r4_ok else '❌ 不合格'}")

passed = sum([r1_ratio>=80, r2_mat1 and r2_mat2, r3_ok, r4_ok])
print(f"\n  総合: {passed}/4 項目合格  {'★ ロバストネス合格' if passed==4 else '△ 要改善' if passed>=3 else '✗ 不合格'}")

# 結果をCSV保存
rows_mat1 = [{"type":"ATR×Q","row":a,"col":q,"pf":mat1_pf[i,j],"dd":mat1_dd[i,j],"pnl":mat1_pnl[i,j]}
             for i,a in enumerate(ATR_VALS) for j,q in enumerate(Q_VALS)]
rows_mat2 = [{"type":"ACA×ACB","row":a,"col":b,"pf":mat2_pf[i,j],"dd":mat2_dd[i,j],"n":mat2_n[i,j]}
             for i,a in enumerate(AC_A_VALS) for j,b in enumerate(AC_B_VALS)]
pd.DataFrame(rows_mat1+rows_mat2).to_csv(OUT_DIR/"robust_scan.csv",
                                          index=False, encoding="utf-8-sig")

# ── ヘルパー ─────────────────────────────────────────────────
def _plot_heatmap(ax, mat, rows, cols, xlabel, ylabel, title, cmap, center,
                  hi_row, hi_col, fmt=".2f"):
    ax.set_facecolor("#f8f9fa")
    vmax = np.nanmax(np.abs(mat - (center or 0)))
    vmin = (center or 0) - vmax; vmax2 = (center or 0) + vmax
    im = ax.imshow(mat, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax2)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([str(c) for c in cols], fontsize=8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([str(r) for r in rows], fontsize=8)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=10, fontweight="bold")
    for i in range(len(rows)):
        for j in range(len(cols)):
            val = mat[i, j]
            if np.isnan(val): continue
            is_adopted = (i == hi_row and j == hi_col)
            txt = f"{val:{fmt}}"
            if is_adopted: txt = f"★{txt}"
            c = "white" if abs(val-(center or 0)) > vmax*0.55 else "black"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5,
                    color=c, fontweight="bold" if is_adopted else "normal")

# ── 可視化 ──────────────────────────────────────────────────
fig = plt.figure(figsize=(22, 18))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("USD/JPY デュアルシステム ロバストネス検証  ─  IS期間（2022-2023）\n"
             "採用パラメータ: ATR=14, Q=10%, ac_A>0.15, ac_B<0.00",
             fontsize=13, fontweight="bold", y=0.98)
gs = fig.add_gridspec(2, 3, hspace=0.45, wspace=0.35)

# ① ATR×Q PF ヒートマップ
ax = fig.add_subplot(gs[0, 0])
_plot_heatmap(ax, mat1_pf, ATR_VALS, Q_VALS, "ATR期間", "Q閾値",
              "① ATR × Q閾値  PF", "RdYlGn", 1.0,
              hi_row=ATR_VALS.index(BASE_ATR), hi_col=Q_VALS.index(BASE_Q), fmt=".2f")

# ② ATR×Q DD ヒートマップ
ax = fig.add_subplot(gs[0, 1])
_plot_heatmap(ax, mat1_dd, ATR_VALS, Q_VALS, "ATR期間", "Q閾値",
              "① ATR × Q閾値  MaxDD(%)", "RdYlGn_r", None,
              hi_row=ATR_VALS.index(BASE_ATR), hi_col=Q_VALS.index(BASE_Q), fmt=".1f")

# ③ ATR×Q 損益
ax = fig.add_subplot(gs[0, 2])
_plot_heatmap(ax, mat1_pnl/10000, ATR_VALS, Q_VALS, "ATR期間", "Q閾値",
              "① ATR × Q閾値  総損益(万円)", "RdYlGn", 0,
              hi_row=ATR_VALS.index(BASE_ATR), hi_col=Q_VALS.index(BASE_Q), fmt="+.0f")

# ④ AC_A×AC_B PF
ax = fig.add_subplot(gs[1, 0])
_plot_heatmap(ax, mat2_pf, AC_A_VALS, AC_B_VALS, "ac_A閾値(>X)", "ac_B閾値(<X)",
              "② ac閾値A × B  PF", "RdYlGn", 1.0,
              hi_row=AC_A_VALS.index(BASE_AC_A), hi_col=AC_B_VALS.index(BASE_AC_B), fmt=".2f")

# ⑤ AC_A×AC_B DD
ax = fig.add_subplot(gs[1, 1])
_plot_heatmap(ax, mat2_dd, AC_A_VALS, AC_B_VALS, "ac_A閾値(>X)", "ac_B閾値(<X)",
              "② ac閾値A × B  MaxDD(%)", "RdYlGn_r", None,
              hi_row=AC_A_VALS.index(BASE_AC_A), hi_col=AC_B_VALS.index(BASE_AC_B), fmt=".1f")

# ⑥ 年別安定性
ax = fig.add_subplot(gs[1, 2])
ax.set_facecolor("#f8f9fa")
years  = ["2022", "2023"]
labels = ["戦略A\nショート", "戦略B\nロング", "統合"]
pfs_22 = [sv22A["pf"], sv22B["pf"], sv22["pf"]]
pfs_23 = [sv23A["pf"], sv23B["pf"], sv23["pf"]]
x = np.arange(len(labels)); w=0.35
b1 = ax.bar(x-w/2, pfs_22, w, color="#3498db", alpha=0.8, label="2022年")
b2 = ax.bar(x+w/2, pfs_23, w, color="#e74c3c", alpha=0.8, label="2023年")
ax.axhline(1.0, color="black", lw=1.2, ls="--", alpha=0.6)
ax.set_title("③ 年別安定性  PF比較", fontsize=10, fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("Profit Factor", fontsize=9)
ax.legend(fontsize=9)
for bar in list(b1)+list(b2):
    h=bar.get_height()
    ax.text(bar.get_x()+bar.get_width()/2, h+0.02, f"{h:.2f}",
            ha="center", va="bottom", fontsize=8)
ax.set_ylim(0, max(pfs_22+pfs_23)*1.25)
ax.grid(axis="y", alpha=0.3)

plt.savefig(OUT_DIR/"robust_heatmap.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# 数値サマリーをCSVに追記
robust_summary = {
    "r1_pf_pass_ratio": r1_ratio,
    "r2_base_above_median": r2_mat1 and r2_mat2,
    "r3_2022_pf": sv22["pf"], "r3_2023_pf": sv23["pf"],
    "r4_max_dd_pct": all_dd.max(),
    "passed_criteria": passed,
    "verdict": "合格" if passed==4 else "要改善" if passed>=3 else "不合格",
}
pd.Series(robust_summary).to_csv(OUT_DIR/"robust_summary.csv", encoding="utf-8-sig")

print(f"\n保存先: {OUT_DIR}")
print("完了")
