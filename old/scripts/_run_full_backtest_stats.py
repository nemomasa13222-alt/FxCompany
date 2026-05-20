# -*- coding: utf-8 -*-
"""
全ペア × セッション  統計解析 + ISバックテスト
──────────────────────────────────────────────────────────────
指標: μ, Skew, Kurtosis, VaR95, CVaR95, P(r>σ), P(r<-σ)
      Tail Ratio, Omega Ratio
分類: 順張り優位 / 逆張り優位
ランキング: Tail Ratio × Omega Ratio で総合評価
バックテスト: IS期間 (2022-2023)
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
from matplotlib.colors import TwoSlopeNorm

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "full_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START = "2022-01-01"; IS_END = "2023-12-31"
STRENGTH_WINDOW = 24; AC_WINDOW = 12
Q_LARGE = 0.25; Q_EXTREME = 0.10
HORIZONS = [1, 3, 6, 12, 24]; H_MAIN = 6
CAPITAL = 1_000_000; RISK_PCT = 0.005
PIP_SIZE_JPY = 0.01; PIP_VAL_JPY = 100
PIP_SIZE_USD = 0.0001; PIP_VAL_USD = 1000
MAX_HOLD = 48
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
JPY_PAIRS = {p for p,(b,q) in PAIR_CURRENCIES.items() if b=="JPY" or q=="JPY"}
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
is_idx  = (common_idx >= IS_START) & (common_idx <= IS_END)
print(f"共通バー数: {len(common_idx):,}  IS: {is_idx.sum():,}")

# ── 通貨強弱 ────────────────────────────────────────────────
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

print("自己相関算出中...")
ac_dict = {}
for pair, df in dfs.items():
    ret = np.log(df["Close"]/df["Close"].shift(1))
    ac_dict[pair] = rolling_ac(ret, AC_WINDOW)

# ────────────────────────────────────────────────────────────
# 統計指標計算関数
# ────────────────────────────────────────────────────────────
def compute_metrics(r: np.ndarray, label: str) -> dict:
    """全統計指標を算出"""
    r = r[np.isfinite(r)]
    if len(r) < 20:
        return {"label":label,"n":len(r)}
    n = len(r)
    mu    = r.mean() * 100            # % 換算
    sigma = r.std(ddof=1) * 100
    skew  = stats.skew(r)
    kurt  = stats.kurtosis(r)         # excess kurtosis
    var95 = np.percentile(r, 5) * 100 # 5th percentile (negative = loss)
    # CVaR95 = Expected Shortfall
    cvar95= r[r <= np.percentile(r,5)].mean() * 100

    # Tail Ratio: 95th percentile / |5th percentile|
    p95   = np.percentile(r, 95) * 100
    p5    = np.percentile(r,  5) * 100
    tail_ratio = p95 / abs(p5) if abs(p5) > 1e-10 else np.nan
    # >1: 右裾が厚い (LONG有利), <1: 左裾が厚い (SHORT有利)

    # Omega Ratio (threshold=0)
    gains  = r[r > 0]; losses = r[r < 0]
    omega  = gains.sum() / abs(losses.sum()) if len(losses)>0 and losses.sum()!=0 else np.nan
    # >1: 上昇が大きい (LONG有利), <1: 下落が大きい (SHORT有利)

    # P(r > σ) と P(r < -σ)
    thr = sigma / 100  # %→小数に戻す
    p_up   = (r >  thr).mean() * 100
    p_down = (r < -thr).mean() * 100

    # 総合スコア（SHORT = Tail<1 AND Omega<1 AND mu<0）
    score_short = (1 if mu<0 else 0) + (1 if skew<-0.2 else 0) + \
                  (1 if (not np.isnan(tail_ratio) and tail_ratio<1) else 0) + \
                  (1 if (not np.isnan(omega) and omega<1) else 0)
    score_long  = (1 if mu>0 else 0) + (1 if skew> 0.2 else 0) + \
                  (1 if (not np.isnan(tail_ratio) and tail_ratio>1) else 0) + \
                  (1 if (not np.isnan(omega) and omega>1) else 0)

    if score_short >= 3:   strategy = "▼SHORT（強）"
    elif score_short == 2: strategy = "▽short（中）"
    elif score_long  >= 3: strategy = "▲LONG（強）"
    elif score_long  == 2: strategy = "△long（中）"
    else:                  strategy = "─"

    return {
        "label":label, "n":n,
        "μ(%)":    round(mu,5),
        "Skew":    round(skew,4),
        "Kurt":    round(kurt,3),
        "VaR95(%)":round(var95,5),
        "CVaR95(%)":round(cvar95,5),
        "P(r>σ)%": round(p_up,2),
        "P(r<-σ)%":round(p_down,2),
        "TailRatio":round(tail_ratio,4) if not np.isnan(tail_ratio) else np.nan,
        "OmegaRatio":round(omega,4) if not np.isnan(omega) else np.nan,
        "Strategy": strategy,
        "score_short": score_short,
        "score_long":  score_long,
    }

# ════════════════════════════════════════════════════════════
# PART 1: 統計解析（全期間、IS+OOS）
# ════════════════════════════════════════════════════════════
print("\n統計解析中（全期間）...")
stat_rows = []
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    close = dfs[pair]["Close"]
    diff  = str_df[base_c] - str_df[quote_c]
    q10   = diff.quantile(Q_EXTREME)
    q25   = diff.quantile(Q_LARGE)
    ac    = ac_dict[pair]
    bd    = (dfs[pair]["Low"] < dfs[pair]["Low"].shift(1)) & diff.notna()
    fut6  = np.log(close.shift(-H_MAIN) / close)

    groups = {
        "全BreakDown": bd,
        "Q25":         bd & (diff <= q25),
        "Q10":         bd & (diff <= q10),
        "Q10+ac>0":    bd & (diff <= q10) & (ac > 0) & ac.notna(),
        "Q10+ac<0":    bd & (diff <= q10) & (ac < 0) & ac.notna(),
    }

    for sname,s,e,_ in SESSIONS:
        sm = sess_s == sname
        for glabel, gmask in groups.items():
            r = fut6[gmask & sm].dropna().values
            m = compute_metrics(r, glabel)
            m.update({"pair":pair,"base":base_c,"quote":quote_c,
                      "session":sname,"group":glabel})
            stat_rows.append(m)

df_stats = pd.DataFrame(stat_rows)
df_stats.to_csv(OUT_DIR/"stats_full.csv", index=False, encoding="utf-8-sig")

# ════════════════════════════════════════════════════════════
# PART 2: ISバックテスト
# ════════════════════════════════════════════════════════════
print("\nISバックテスト実行中...")

def get_pip(pair):
    if pair in JPY_PAIRS: return PIP_SIZE_JPY, PIP_VAL_JPY
    return PIP_SIZE_USD, PIP_VAL_USD

def run_bt(pair, direction, mask):
    df_p = dfs[pair]
    hi,lo,cl = df_p["High"],df_p["Low"],df_p["Close"].shift(1)
    tr = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    pip_sz, pip_val = get_pip(pair)
    positions = np.where(mask.values)[0]
    records = []
    for sp in positions:
        ep = sp+1
        if ep >= len(df_p): continue
        entry_bar = df_p.index[ep]
        entry_p   = df_p["Open"].iloc[ep]
        atr_val   = atr.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_pips   = atr_val / pip_sz
        if sl_pips <= 0: continue
        lot = (CAPITAL * RISK_PCT) / (sl_pips * pip_val)

        if direction == "short":
            best=entry_p; trail=entry_p+atr_val
            exit_p=None; held=0
            for h in range(1, MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_p): break
                bh=df_p["High"].iloc[bp]; bl=df_p["Low"].iloc[bp]; held=h
                if bh>=trail: exit_p=trail; break
                if bl<best: best=bl; trail=min(trail,best+atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_p): exit_p=df_p["Close"].iloc[fp]
                else: continue
            pnl=(entry_p-exit_p)/pip_sz*pip_val*lot
        else:
            best=entry_p; trail=entry_p-atr_val
            exit_p=None; held=0
            for h in range(1, MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_p): break
                bh=df_p["High"].iloc[bp]; bl=df_p["Low"].iloc[bp]; held=h
                if bl<=trail: exit_p=trail; break
                if bh>best: best=bh; trail=max(trail,best-atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_p): exit_p=df_p["Close"].iloc[fp]
                else: continue
            pnl=(exit_p-entry_p)/pip_sz*pip_val*lot

        r_mult = pnl/(CAPITAL*RISK_PCT)
        sig_bar= df_p.index[sp]
        records.append({
            "pair":pair,"direction":direction,
            "signal_bar":sig_bar,"entry_bar":entry_bar,
            "pnl_yen":pnl,"r_mult":r_mult,"held":held,
            "session":sess_s.get(sig_bar,"─"),
        })
    return pd.DataFrame(records)

def bt_summary(df):
    if len(df)==0: return {}
    w=df[df["pnl_yen"]>0]; l=df[df["pnl_yen"]<=0]
    gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=df["pnl_yen"].cumsum()
    r=df["r_mult"]
    return {"n":len(df),"win_rate":len(w)/len(df)*100,
            "pf":pf,"total_pnl":df["pnl_yen"].sum(),
            "avg_r":r.mean(),"skew_r":stats.skew(r),
            "max_dd":(cum.cummax()-cum).max(),
            "dd_pct":(cum.cummax()-cum).max()/CAPITAL*100,
            "tail_ratio": np.percentile(r,95)/abs(np.percentile(r,5))
                          if abs(np.percentile(r,5))>1e-10 else np.nan,
            "omega": r[r>0].sum()/abs(r[r<0].sum())
                     if len(r[r<0])>0 else np.nan}

# プレイブック読込
pb_path = ROOT/"docs"/"strategy_judgment"/"playbook.csv"
if pb_path.exists():
    df_pb = pd.read_csv(pb_path, encoding="utf-8-sig")
else:
    # フォールバック: 強シグナルのみ使用
    df_pb = pd.DataFrame()

bt_all_records = []
bt_results = []

for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    close = dfs[pair]["Close"]
    diff  = str_df[base_c] - str_df[quote_c]
    q10   = diff.quantile(Q_EXTREME)
    ac    = ac_dict[pair]
    bd    = (dfs[pair]["Low"] < dfs[pair]["Low"].shift(1)) & diff.notna()

    for sname,s,e,scolor in SESSIONS:
        sm     = sess_s == sname
        # プレイブックから方向・フィルターを取得
        if len(df_pb):
            # セッション名の改行を除いて照合
            df_pb_tmp = df_pb.copy()
            df_pb_tmp["session_clean"] = df_pb_tmp["session"].str.replace("\n"," ").str.strip()
            sname_clean = sname.replace("\n"," ").strip()
            pb_row = df_pb_tmp[(df_pb_tmp["pair"]==pair) &
                               (df_pb_tmp["session_clean"]==sname_clean)]
        else:
            pb_row = pd.DataFrame()

        if len(pb_row):
            jdg = pb_row["judge"].values[0]
            flt = pb_row["filter"].values[0]
        else:
            jdg = "─"; flt = "─"

        if "SHORT" in jdg:
            direction = "short"
            if "ac>0" in flt:
                mask = bd & (diff<=q10) & (ac>0) & ac.notna() & sm & is_idx
            else:
                mask = bd & (diff<=q10) & sm & is_idx
        elif "LONG" in jdg:
            direction = "long"
            if "ac<0" in flt:
                mask = bd & (diff<=q10) & (ac<0) & ac.notna() & sm & is_idx
            else:
                mask = bd & (diff<=q10) & sm & is_idx
        else:
            continue  # 不明はスキップ

        df_bt = run_bt(pair, direction, mask)
        if len(df_bt) == 0: continue
        bt_all_records.append(df_bt)
        sv = bt_summary(df_bt)
        sv.update({"pair":pair,"session":sname,"direction":direction,
                   "judge":jdg,"filter":flt,"base":base_c,"quote":quote_c})
        bt_results.append(sv)
        print(f"  {pair} {sname.replace(chr(10),' ')}: "
              f"{direction} n={sv['n']} PF={sv['pf']:.2f} "
              f"TailR={sv.get('tail_ratio',0):.3f} "
              f"Omega={sv.get('omega',0):.3f}")

df_bt_all = pd.concat(bt_all_records, ignore_index=True) if bt_all_records else pd.DataFrame()
df_bt_res = pd.DataFrame(bt_results)
df_bt_all.to_csv(OUT_DIR/"bt_trades.csv", index=False, encoding="utf-8-sig")
df_bt_res.to_csv(OUT_DIR/"bt_results.csv", index=False, encoding="utf-8-sig")

# ════════════════════════════════════════════════════════════
# PART 3: ランキング
# ════════════════════════════════════════════════════════════
print("\nランキング生成中...")
# Q10+ac フィルター使用時の指標でランキング
df_ac = df_stats[df_stats["group"].isin(["Q10+ac>0","Q10+ac<0"])].copy()
df_ac = df_ac[df_ac["n"]>=30].dropna(subset=["TailRatio","OmegaRatio"])

# SHORT候補: TailRatio<1 AND Omega<1 AND μ<0 でスコア計算
df_short = df_ac[(df_ac["μ(%)"]<0) & (df_ac["group"]=="Q10+ac>0")].copy()
df_short["rank_score"] = (1/df_short["TailRatio"].clip(0.01)) * (1/df_short["OmegaRatio"].clip(0.01))
df_short_top = df_short.sort_values("rank_score",ascending=False).head(20)

# LONG候補: TailRatio>1 AND Omega>1 AND μ>0
df_long = df_ac[(df_ac["μ(%)"]>0) & (df_ac["group"]=="Q10+ac<0")].copy()
df_long["rank_score"] = df_long["TailRatio"] * df_long["OmegaRatio"]
df_long_top = df_long.sort_values("rank_score",ascending=False).head(20)

print("\n" + "="*90)
print("  SHORT優位ランキング（Q10+ac>0）  Tail×Omega スコア順")
print("="*90)
print(f"  {'#':>3}  {'ペア':8s}  {'セッション':16s}  "
      f"{'μ(%)':>9s}  {'Skew':>6s}  {'VaR95':>8s}  "
      f"{'TailR':>7s}  {'Omega':>7s}  {'Score':>8s}")
print("-"*90)
for rank, (_,row) in enumerate(df_short_top.iterrows(),1):
    print(f"  {rank:>3}. {row['pair']:8s}  "
          f"{row['session'].replace(chr(10),' '):16s}  "
          f"{row['μ(%)']:+9.5f}  {row['Skew']:+6.3f}  "
          f"{row['VaR95(%)']:+8.5f}  "
          f"{row['TailRatio']:7.4f}  {row['OmegaRatio']:7.4f}  "
          f"{row['rank_score']:8.4f}")

print("\n" + "="*90)
print("  LONG優位ランキング（Q10+ac<0）  Tail×Omega スコア順")
print("="*90)
print(f"  {'#':>3}  {'ペア':8s}  {'セッション':16s}  "
      f"{'μ(%)':>9s}  {'Skew':>6s}  {'VaR95':>8s}  "
      f"{'TailR':>7s}  {'Omega':>7s}  {'Score':>8s}")
print("-"*90)
for rank, (_,row) in enumerate(df_long_top.iterrows(),1):
    print(f"  {rank:>3}. {row['pair']:8s}  "
          f"{row['session'].replace(chr(10),' '):16s}  "
          f"{row['μ(%)']:+9.5f}  {row['Skew']:+6.3f}  "
          f"{row['VaR95(%)']:+8.5f}  "
          f"{row['TailRatio']:7.4f}  {row['OmegaRatio']:7.4f}  "
          f"{row['rank_score']:8.4f}")

# ════════════════════════════════════════════════════════════
# 図1: Tail Ratio × Omega Ratio 散布図（全ペア×セッション）
# ════════════════════════════════════════════════════════════
print("\n図生成中...")
fig, axes = plt.subplots(1, 4, figsize=(24, 7))
fig.patch.set_facecolor("#f8f9fa")
fig.suptitle("Tail Ratio × Omega Ratio  ─  全ペア × セッション別\n"
             "（Q10+ac>0=●青  Q10+ac<0=■橙 / 右上=LONG有利 / 左下=SHORT有利）",
             fontsize=12, fontweight="bold")

pairs_list = list(PAIR_CURRENCIES.keys())
colors_m = {"Q10+ac>0":"#1a3a7a","Q10+ac<0":"#e07b00"}
markers_m = {"Q10+ac>0":"o","Q10+ac<0":"s"}

for ax,(sname,s,e,scolor) in zip(axes,SESSIONS):
    ax.set_facecolor("#f8f8f8")
    ax.axhline(1,color="#333",lw=0.8,ls="--",alpha=0.5)
    ax.axvline(1,color="#333",lw=0.8,ls="--",alpha=0.5)
    ax.fill_between([0,1],[0,0],[1,1],alpha=0.05,color="#1a3a7a")  # SHORT領域
    ax.fill_between([1,4],[1,1],[4,4],alpha=0.05,color="#b03030")  # LONG領域

    sub = df_stats[(df_stats["session"]==sname) &
                   (df_stats["group"].isin(["Q10+ac>0","Q10+ac<0"])) &
                   (df_stats["n"]>=30)].dropna(subset=["TailRatio","OmegaRatio"])
    for _,row in sub.iterrows():
        gk = row["group"]
        x  = row["TailRatio"]; y = row["OmegaRatio"]
        n  = row["n"]
        ax.scatter(x,y,s=max(n/20,30),c=colors_m[gk],
                   marker=markers_m[gk],alpha=0.75,edgecolors="white",lw=0.5)
        ax.text(x,y+0.03,row["pair"],fontsize=6.5,
                ha="center",color=colors_m[gk],fontweight="bold")

    ax.set_title(sname.replace("\n"," "), fontsize=10,
                 fontweight="bold",color=scolor)
    ax.set_xlabel("Tail Ratio\n(>1:右裾厚 / <1:左裾厚)", fontsize=8)
    ax.set_ylabel("Omega Ratio\n(>1:利益>損失)", fontsize=8)
    ax.set_xlim(0.3,2.5); ax.set_ylim(0.4,2.5)
    ax.grid(alpha=0.2)
    ax.text(0.35,0.35,"SHORT\n有利",fontsize=8,color="#1a3a7a",
            alpha=0.6,transform=ax.transAxes,fontweight="bold")
    ax.text(0.65,0.65,"LONG\n有利",fontsize=8,color="#b03030",
            alpha=0.6,transform=ax.transAxes,fontweight="bold")

plt.tight_layout()
fig.savefig(OUT_DIR/"tail_omega_scatter.png", dpi=140,
            bbox_inches="tight",facecolor="#f8f9fa")
plt.close(fig)

# 図2: ヒートマップ（TailRatio と OmegaRatio）
fig, axes = plt.subplots(2, 4, figsize=(24, 12))
fig.patch.set_facecolor("#f8f9fa")
fig.suptitle("Tail Ratio / Omega Ratio ヒートマップ\n"
             "（Q10+ac>0群 / 6本後 / 赤=LONG有利 / 青=SHORT有利）",
             fontsize=12, fontweight="bold")

for col,(sname,s,e,scolor) in enumerate(SESSIONS):
    for row_idx,(metric,title) in enumerate([
        ("TailRatio","Tail Ratio (>1=右裾厚=LONG)"),
        ("OmegaRatio","Omega Ratio (>1=利益>損失=LONG)"),
    ]):
        ax = axes[row_idx][col]
        ax.set_facecolor("#eeeeee")
        sub = df_stats[(df_stats["session"]==sname) &
                       (df_stats["group"]=="Q10+ac>0") &
                       (df_stats["n"]>=20)]
        vals = sub.set_index("pair")[metric].reindex(pairs_list)
        mat  = vals.values.reshape(-1,1)
        vmax = max(abs(np.nanmax(mat)-1), abs(np.nanmin(mat)-1), 0.1)
        norm = TwoSlopeNorm(vmin=1-vmax,vcenter=1,vmax=1+vmax)
        im = ax.imshow(mat, cmap="RdBu", aspect="auto", norm=norm)
        plt.colorbar(im,ax=ax,fraction=0.06,pad=0.02)
        ax.set_yticks(range(len(pairs_list)))
        ax.set_yticklabels(pairs_list,fontsize=8)
        ax.set_xticks([]); ax.set_xlabel("")
        if row_idx==0:
            ax.set_title(f"{sname.replace(chr(10),' ')}\n{title}",
                         fontsize=8.5,fontweight="bold",color=scolor)
        else:
            ax.set_title(title,fontsize=8.5,fontweight="bold")
        for pi,pair in enumerate(pairs_list):
            val=vals.get(pair,np.nan)
            if not np.isnan(val):
                c="white" if abs(val-1)>vmax*0.55 else "black"
                ax.text(0,pi,f"{val:.3f}",ha="center",va="center",
                        fontsize=7.5,color=c)

plt.tight_layout()
fig.savefig(OUT_DIR/"tail_omega_heatmap.png", dpi=140,
            bbox_inches="tight",facecolor="#f8f9fa")
plt.close(fig)

# 図3: バックテスト P&L 曲線
if len(df_bt_all):
    fig, axes = plt.subplots(3, 4, figsize=(24, 18))
    fig.patch.set_facecolor("#f8f9fa")
    fig.suptitle("ISバックテスト  累積損益曲線  ─  プレイブック適用（2022-2023）\n"
                 "SL: 資金0.5%  /  TP: トレーリング(ATR×1.0)  /  最大48本保有",
                 fontsize=12, fontweight="bold")

    pairs_list_bt = df_bt_res["pair"].unique().tolist()
    for pi, pair in enumerate(pairs_list):
        ax = axes[pi//4][pi%4]; ax.set_facecolor("#f8f8f8")
        ax.axhline(0,color="#333",lw=0.8,ls="--",alpha=0.5)
        sub_bt = df_bt_all[df_bt_all["pair"]==pair]
        if len(sub_bt)==0:
            ax.set_title(f"{pair}（シグナルなし）",fontsize=9)
            continue
        sv = bt_summary(sub_bt)
        cum = sub_bt["pnl_yen"].cumsum()
        ax.plot(range(len(cum)),cum.values,color="#2c3e50",lw=2.0)
        ax.fill_between(range(len(cum)),cum.values,
                        color="#2c3e50",alpha=0.08)

        for sname,_,_,scolor in SESSIONS:
            sub_s = sub_bt[sub_bt["session"]==sname]
            if len(sub_s)<3: continue
            c2 = sub_s["pnl_yen"].cumsum()
            ax.plot(range(len(c2)),c2.values,color=scolor,lw=1.2,
                    ls="--",alpha=0.7,label=sname.split()[0])

        ax.set_title(f"{pair}  PF={sv['pf']:.2f}  {sv['total_pnl']:+,.0f}円\n"
                     f"n={sv['n']}  DD={sv['dd_pct']:.1f}%  "
                     f"TailR={sv.get('tail_ratio',0):.3f}  "
                     f"Ω={sv.get('omega',0):.3f}",
                     fontsize=8,fontweight="bold")
        ax.legend(fontsize=6.5,framealpha=0.9)
        ax.grid(axis="y",alpha=0.2)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

    plt.tight_layout()
    fig.savefig(OUT_DIR/"bt_pnl_curves.png", dpi=130,
                bbox_inches="tight",facecolor="#f8f9fa")
    plt.close(fig)

# 図4: 総合ランキング表（視覚化）
fig, (ax_s, ax_l) = plt.subplots(1, 2, figsize=(22, 14))
fig.patch.set_facecolor("#f8f9fa")
fig.suptitle("戦略ランキング  ─  Tail Ratio × Omega Ratio スコア順\n"
             "（Q10+自己相関フィルター / 6本後=30分後 / 全期間 2022-2024）",
             fontsize=13, fontweight="bold")

def draw_ranking_table(ax, df_top, title, clr, is_short):
    ax.set_facecolor("#f8f9fa"); ax.axis("off")
    cols = ["#","ペア","セッション","μ(%)","Skew","Kurt",
            "VaR95","CVaR95","TailR","Omega","判定"]
    ax.set_xlim(0,1); ax.set_ylim(0,1)
    # ヘッダー
    ax.add_patch(plt.Rectangle((0,0.95),1,0.05,fc=clr,transform=ax.transAxes,clip_on=False))
    ax.text(0.5,0.97,title,ha="center",va="center",color="white",
            fontsize=11,fontweight="bold",transform=ax.transAxes)
    col_xs=[0.02,0.08,0.18,0.37,0.47,0.55,0.63,0.72,0.81,0.89,0.97]
    for cx,col in zip(col_xs,cols):
        ax.text(cx,0.93,col,ha="left",va="center",fontsize=7.5,
                fontweight="bold",color="#333",transform=ax.transAxes)
    ax.plot([0,1],[0.915,0.915],color="#cccccc",lw=0.8,
            transform=ax.transAxes,clip_on=False)

    for ri,(_,row) in enumerate(df_top.iterrows()):
        y = 0.895 - ri*0.044
        bg = "#f0f0f0" if ri%2==0 else "white"
        ax.add_patch(plt.Rectangle((0,y-0.015),1,0.04,fc=bg,
                                    transform=ax.transAxes,clip_on=False))
        vals = [
            str(ri+1),
            row.get("pair","─"),
            row.get("session","─").replace("\n"," ")[:12],
            f"{row.get('μ(%)',0):+.5f}",
            f"{row.get('Skew',0):+.3f}",
            f"{row.get('Kurt',0):+.1f}",
            f"{row.get('VaR95(%)',0):+.5f}",
            f"{row.get('CVaR95(%)',0):+.5f}",
            f"{row.get('TailRatio',0):.4f}",
            f"{row.get('OmegaRatio',0):.4f}",
            row.get("Strategy","─"),
        ]
        for cx,v in zip(col_xs,vals):
            c = "#1a3a7a" if is_short and v.startswith(("-","▼")) else \
                "#b03030" if not is_short and v.startswith(("+","▲")) else "#333"
            ax.text(cx,y,v,ha="left",va="center",fontsize=7.2,
                    color=c,transform=ax.transAxes)

draw_ranking_table(ax_s, df_short_top, "SHORT優位ランキング（順張り）",
                   "#1a3a7a", True)
draw_ranking_table(ax_l, df_long_top,  "LONG優位ランキング（逆張り）",
                   "#b03030", False)

plt.tight_layout(rect=[0,0,1,0.97])
fig.savefig(OUT_DIR/"ranking_table.png", dpi=140,
            bbox_inches="tight",facecolor="#f8f9fa")
plt.close(fig)

# ── 最終サマリー ─────────────────────────────────────────────
print("\n" + "="*75)
print("  バックテスト IS期間 全ペア総合")
print("="*75)
if len(df_bt_res):
    sv_total = bt_summary(df_bt_all)
    print(f"  総合: n={sv_total['n']:,}  PF={sv_total['pf']:.2f}  "
          f"損益={sv_total['total_pnl']:+,.0f}円  DD={sv_total['dd_pct']:.1f}%  "
          f"TailR={sv_total.get('tail_ratio',0):.3f}  "
          f"Omega={sv_total.get('omega',0):.3f}")
    print(f"\n  {'ペア':8s}  {'方向':6s}  {'n':>4s}  {'PF':>5s}  {'損益':>10s}  "
          f"{'DD%':>5s}  {'TailR':>7s}  {'Omega':>7s}")
    print("-"*75)
    for _,r in df_bt_res.sort_values("total_pnl",ascending=False).iterrows():
        tag="★" if r["pf"]>=1.2 else "  "
        print(f"  {tag}{r['pair']:8s}  {r['direction']:6s}  {r['n']:4.0f}  "
              f"{r['pf']:5.2f}  {r['total_pnl']:+10,.0f}  "
              f"{r['dd_pct']:5.1f}  {r.get('tail_ratio',0):7.4f}  "
              f"{r.get('omega',0):7.4f}")

print(f"\n保存先: {OUT_DIR}")
print("完了")
