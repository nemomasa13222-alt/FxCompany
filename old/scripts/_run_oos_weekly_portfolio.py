# -*- coding: utf-8 -*-
"""
IS+OOS 全期間 週次TOP6選択バックテスト
────────────────────────────────────────
IS : 2022-01-01 ～ 2023-12-31
OOS: 2024-01-01 ～ 2024-12-31

Phase 1: 全期間バックテスト（プレイブック適用）
Phase 2: 週次TOP6選択（前週PF / 複合スコア）
Phase 3: IS vs OOS 比較レポート
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
from matplotlib.gridspec import GridSpec

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
PB_PATH  = ROOT / "docs" / "strategy_judgment" / "playbook.csv"
OUT_DIR  = ROOT / "docs" / "weekly_portfolio_full"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START = "2022-01-01"; IS_END   = "2023-12-31"
OOS_START= "2024-01-01"; OOS_END  = "2024-12-31"

STRENGTH_WINDOW = 24; AC_WINDOW = 12
Q_EXTREME = 0.10; MAX_HOLD = 48
CAPITAL   = 1_000_000; RISK_PCT = 0.005
PIP_SIZE_JPY = 0.01;  PIP_VAL_JPY = 100
PIP_SIZE_USD = 0.0001; PIP_VAL_USD = 1000
JST = pd.Timedelta(hours=9)

SESSIONS = [
    ("東京\n09-15JST",  9, 15),
    ("欧州\n15-21JST", 15, 21),
    ("NY\n21-03JST",   21,  3),
    ("深夜\n03-09JST",  3,  9),
]
PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
JPY_PAIRS  = {p for p,(b,q) in PAIR_CURRENCIES.items() if q=="JPY"}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# ════════════════════════════════════════════════════════════
# PHASE 1: 全期間バックテスト
# ════════════════════════════════════════════════════════════
print("=" * 60)
print("PHASE 1: 全期間バックテスト (2022-2024)")
print("=" * 60)

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
print(f"共通バー数: {len(common_idx):,}  期間: {common_idx.min()} -> {common_idx.max()}")

# 通貨強弱
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
    for name,s,e in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

print("自己相関算出中...")
ac_dict = {}
for pair,df in dfs.items():
    ret = np.log(df["Close"]/df["Close"].shift(1))
    arr = ret.values; res = np.full(len(arr), np.nan)
    for i in range(AC_WINDOW-1, len(arr)):
        x = arr[i-AC_WINDOW+1:i+1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-1], x[1:]); res[i] = c[0,1]
    ac_dict[pair] = pd.Series(res, index=common_idx)

def get_pip(pair):
    if pair in JPY_PAIRS: return PIP_SIZE_JPY, PIP_VAL_JPY
    return PIP_SIZE_USD, PIP_VAL_USD

# DMM FX 原則固定スプレッド（pips）。変動スプレッド通貨は平均値を保守的に設定
SPREADS = {
    "USDJPY": 0.2, "EURJPY": 0.5, "GBPJPY": 0.9,
    "AUDJPY": 0.6, "NZDJPY": 1.7, "CHFJPY": 2.2,
    "GBPUSD": 0.9, "AUDUSD": 0.6, "NZDUSD": 1.3,
    "EURGBP": 0.8, "EURAUD": 1.5, "AUDNZD": 2.2,
}

def run_bt(pair, direction, mask):
    df_p = dfs[pair]
    hi,lo,cl = df_p["High"],df_p["Low"],df_p["Close"].shift(1)
    tr  = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    pip_sz, pip_val = get_pip(pair)
    spread_pips = SPREADS.get(pair, 1.0)
    positions = np.where(mask.values)[0]
    records = []
    for sp in positions:
        ep = sp+1
        if ep >= len(df_p): continue
        entry_p = df_p["Open"].iloc[ep]
        atr_val = atr.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_pips = atr_val / pip_sz
        if sl_pips <= 0: continue
        lot = (CAPITAL * RISK_PCT) / (sl_pips * pip_val)
        spread_cost = spread_pips * pip_val * lot  # 往復スプレッドコスト（円）
        if direction == "short":
            best=entry_p; trail=entry_p+atr_val; exit_p=None; held=0
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
            pnl=(entry_p-exit_p)/pip_sz*pip_val*lot - spread_cost
        else:
            best=entry_p; trail=entry_p-atr_val; exit_p=None; held=0
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
            pnl=(exit_p-entry_p)/pip_sz*pip_val*lot - spread_cost
        r_mult = pnl/(CAPITAL*RISK_PCT)
        records.append({
            "pair":pair,"direction":direction,
            "signal_bar":df_p.index[sp],"entry_bar":df_p.index[ep],
            "pnl_yen":pnl,"r_mult":r_mult,"held":held,
            "session":sess_s.get(df_p.index[sp],"─"),
        })
    return pd.DataFrame(records)

df_pb = pd.read_csv(PB_PATH, encoding="utf-8-sig") if PB_PATH.exists() else pd.DataFrame()

print("バックテスト実行中（全期間）...")
all_records = []
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    diff = str_df[base_c] - str_df[quote_c]
    q10  = diff.quantile(Q_EXTREME)
    ac   = ac_dict[pair]
    bd   = (dfs[pair]["Low"] < dfs[pair]["Low"].shift(1)) & diff.notna()

    for sname,s,e in SESSIONS:
        sm = sess_s == sname
        if len(df_pb):
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
            mask = bd & (diff<=q10) & (ac>0) & ac.notna() & sm \
                   if "ac>0" in flt else bd & (diff<=q10) & sm
        elif "LONG" in jdg:
            direction = "long"
            mask = bd & (diff<=q10) & (ac<0) & ac.notna() & sm \
                   if "ac<0" in flt else bd & (diff<=q10) & sm
        else:
            continue

        df_bt = run_bt(pair, direction, mask)
        if len(df_bt):
            all_records.append(df_bt)
            print(f"  {pair} {sname.replace(chr(10),' ')}: {direction} n={len(df_bt)}")

df_all = pd.concat(all_records, ignore_index=True).sort_values("signal_bar")
df_all["combo"] = df_all["pair"] + "_" + df_all["session"]
df_all["period"] = df_all["signal_bar"].apply(
    lambda x: "IS" if x <= pd.Timestamp(IS_END) else "OOS")

iso = df_all["signal_bar"].dt.isocalendar()
df_all["year_week"] = iso["year"].astype(str) + "_" + iso["week"].astype(str).str.zfill(2)

df_all.to_csv(OUT_DIR / "bt_trades_full.csv", index=False, encoding="utf-8-sig")
print(f"\n全期間トレード: {len(df_all):,}件  IS={len(df_all[df_all['period']=='IS']):,}  OOS={len(df_all[df_all['period']=='OOS']):,}")

# ════════════════════════════════════════════════════════════
# PHASE 2: 週次TOP6選択（ウォークフォワード）
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 2: 週次TOP6選択")
print("=" * 60)

WINDOW_WEEKS = 4; TOP_N = 6; MIN_TRADES = 5; COST_EST = 2_000

weeks      = sorted(df_all["year_week"].unique())
combos_all = sorted(df_all["combo"].unique())

def calc_pf(pnl_series):
    gains  = pnl_series[pnl_series > 0].sum()
    losses = pnl_series[pnl_series <= 0].abs().sum()
    if len(pnl_series) == 0: return np.nan
    if losses == 0: return 999.0 if gains > 0 else np.nan
    return round(gains / losses, 4)

def calc_score(w4, p1):
    if len(w4) < MIN_TRADES: return 0.0
    pnl = w4["pnl_yen"].values; r = w4["r_mult"].values
    ev = float(np.mean(r))
    if ev <= 0: return 0.0
    pf_4w = calc_pf(pd.Series(pnl))
    if not pf_4w or np.isnan(pf_4w) or pf_4w <= 0: return 0.0
    sqrt_n = float(np.sqrt(len(w4)))
    op = float(r[r>0].sum()); on = float(np.abs(r[r<=0].sum()))
    omega = op/on if on>1e-10 else 999.0
    p95=float(np.percentile(r,95)); p5=float(np.percentile(r,5))
    tail = p95/abs(p5) if abs(p5)>1e-10 else 1.0
    cum = np.cumsum(pnl)
    max_dd = float((np.maximum.accumulate(cum)-cum).max())/CAPITAL
    mean_pnl = float(np.mean(pnl))
    cost_tol = float(np.clip(mean_pnl/(mean_pnl+COST_EST),0.01,1.0)) if mean_pnl>0 else 0.01
    pf_1w = calc_pf(p1["pnl_yen"]) if len(p1)>=1 else np.nan
    recent = float(np.clip(pf_1w/pf_4w,0.3,3.0)) \
             if (pf_1w and not np.isnan(pf_1w) and pf_4w>0) else 1.0
    score = (ev*pf_4w*sqrt_n*omega*tail*recent*cost_tol)/(1+max_dd)
    return max(score, 0.0)

sel_pf_parts = []; sel_sc_parts = []

for i, week in enumerate(weeks):
    if i < WINDOW_WEEKS: continue
    window_weeks = weeks[i-WINDOW_WEEKS:i]; prev_week = weeks[i-1]

    pf_scores = {}; sc_scores = {}
    for combo in combos_all:
        p1 = df_all[(df_all["year_week"]==prev_week) & (df_all["combo"]==combo)]
        w4 = df_all[(df_all["year_week"].isin(window_weeks)) & (df_all["combo"]==combo)]
        pf_scores[combo] = calc_pf(p1["pnl_yen"]) or 0.0
        sc_scores[combo] = calc_score(w4, p1)

    top6_pf = sorted(pf_scores, key=lambda c: pf_scores[c], reverse=True)[:TOP_N]
    top6_pf = [c for c in top6_pf if pf_scores[c]>0]
    top6_sc = sorted(sc_scores, key=lambda c: sc_scores[c], reverse=True)[:TOP_N]
    top6_sc = [c for c in top6_sc if sc_scores[c]>0]

    sel_pf_parts.append(df_all[(df_all["year_week"]==week) & (df_all["combo"].isin(top6_pf))].copy())
    sel_sc_parts.append(df_all[(df_all["year_week"]==week) & (df_all["combo"].isin(top6_sc))].copy())

valid_weeks = weeks[WINDOW_WEEKS:]
df_base = df_all[df_all["year_week"].isin(valid_weeks)].sort_values("signal_bar")
df_pf   = pd.concat(sel_pf_parts, ignore_index=True).sort_values("signal_bar") if sel_pf_parts else pd.DataFrame()
df_sc   = pd.concat(sel_sc_parts, ignore_index=True).sort_values("signal_bar") if sel_sc_parts else pd.DataFrame()

# ════════════════════════════════════════════════════════════
# PHASE 3: IS vs OOS 比較
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 3: IS vs OOS 比較")
print("=" * 60)

def summary(d, label):
    if len(d)==0: return dict(label=label,n=0,win_rate=0,pf=0,total_pnl=0,max_dd=0,dd_pct=0)
    w=d[d["pnl_yen"]>0]; l=d[d["pnl_yen"]<=0]
    gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=d["pnl_yen"].cumsum(); dd=(cum.cummax()-cum).max()
    return dict(label=label,n=len(d),win_rate=len(w)/len(d)*100,
                pf=pf,total_pnl=d["pnl_yen"].sum(),max_dd=dd,dd_pct=dd/CAPITAL*100)

results = {}
for key, df_ in [("全組み合わせ",df_base),("前週PF",df_pf),("複合スコア",df_sc)]:
    results[key] = {
        "IS":  summary(df_[df_["period"]=="IS"],  f"{key} IS"),
        "OOS": summary(df_[df_["period"]=="OOS"], f"{key} OOS"),
        "ALL": summary(df_, f"{key} 全期間"),
    }

# 印字
header = f"  {'手法':12s}  {'期間':6s}  {'n':>6s}  {'勝率':>6s}  {'PF':>6s}  {'損益(万)':>9s}  {'DD%':>6s}"
print(header)
print("-" * 75)
for key in ["全組み合わせ","前週PF","複合スコア"]:
    for period in ["IS","OOS","ALL"]:
        sv = results[key][period]
        pnl_m = sv["total_pnl"]/10000
        print(f"  {key:12s}  {period:6s}  "
              f"{sv['n']:>6,.0f}  {sv['win_rate']:>6.1f}  "
              f"{sv['pf']:>6.3f}  {pnl_m:>+9.1f}万  {sv['dd_pct']:>6.1f}%")
    print()

# ── CSV保存
sv_rows = []
for key in results:
    for period in ["IS","OOS","ALL"]:
        row = {"method":key,"period":period, **results[key][period]}
        sv_rows.append(row)
pd.DataFrame(sv_rows).to_csv(OUT_DIR/"summary_is_oos.csv", index=False, encoding="utf-8-sig")

# ════════════════════════════════════════════════════════════
# グラフ
# ════════════════════════════════════════════════════════════
print("\n図生成中...")
palette = {"全組み合わせ":"#95a5a6","前週PF":"#2980b9","複合スコア":"#e74c3c"}

fig = plt.figure(figsize=(18, 22))
fig.patch.set_facecolor("#f8f9fa")
gs  = GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.3)
fig.suptitle(
    "IS+OOS 全期間バックテスト  ─  週次TOP6選択（3手法比較）\n"
    "IS: 2022-2023  /  OOS: 2024  /  元本100万円  /  リスク0.5%/trade",
    fontsize=13, fontweight="bold"
)

# P1: 全期間累積損益
ax1 = fig.add_subplot(gs[0, :])
ax1.set_facecolor("#f8f8f8")
ax1.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
is_end_ts = pd.Timestamp(IS_END)
for key, df_ in [("全組み合わせ",df_base),("前週PF",df_pf),("複合スコア",df_sc)]:
    if len(df_)==0: continue
    cum = df_["pnl_yen"].cumsum().reset_index(drop=True)
    sv_ = results[key]["ALL"]
    lbl = (f"{key}  PF={sv_['pf']:.3f}  DD={sv_['dd_pct']:.1f}%  "
           f"{sv_['total_pnl']:+,.0f}円")
    ax1.plot(cum, color=palette[key], lw=1.8 if key=="全組み合わせ" else 2.2,
             label=lbl, alpha=0.8 if key!="複合スコア" else 1.0)
# IS/OOS境界線
if len(df_base):
    is_n = len(df_base[df_base["period"]=="IS"])
    ax1.axvline(is_n, color="#e67e22", lw=1.5, ls="--", alpha=0.8)
    ax1.text(is_n+10, ax1.get_ylim()[1]*0.9 if ax1.get_ylim()[1]!=0 else 100,
             "OOS開始\n(2024-01)", fontsize=8, color="#e67e22")
ax1.set_title("全期間累積損益（IS+OOS）", fontsize=11, fontweight="bold")
ax1.set_ylabel("累積損益 (円)", fontsize=9)
ax1.legend(fontsize=8.5, framealpha=0.92)
ax1.grid(axis="y", alpha=0.2)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# P2-P3: IS / OOS 個別累積損益
for col_i, period in enumerate(["IS","OOS"]):
    ax = fig.add_subplot(gs[1, col_i])
    ax.set_facecolor("#f8f8f8")
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
    for key, df_ in [("全組み合わせ",df_base),("前週PF",df_pf),("複合スコア",df_sc)]:
        sub = df_[df_["period"]==period]
        if len(sub)==0: continue
        cum = sub["pnl_yen"].cumsum().reset_index(drop=True)
        sv_ = results[key][period]
        lbl = f"{key}  PF={sv_['pf']:.3f}  DD={sv_['dd_pct']:.1f}%"
        ax.plot(cum, color=palette[key], lw=1.8, label=lbl, alpha=0.85)
        ax.fill_between(range(len(cum)), cum, color=palette[key], alpha=0.04)
    ax.set_title(f"{'IS期間 (2022-2023)' if period=='IS' else 'OOS期間 (2024)'} 累積損益",
                 fontsize=10, fontweight="bold")
    ax.set_ylabel("累積損益 (円)", fontsize=9)
    ax.legend(fontsize=8, framealpha=0.92)
    ax.grid(axis="y", alpha=0.2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# P4-P5: PF / DD 比較バー（IS vs OOS）
for col_i, (metric, title, thr) in enumerate([
    ("pf", "PF比較", 1.0),
    ("dd_pct", "最大DD(%) 比較", None),
]):
    ax = fig.add_subplot(gs[2, col_i])
    ax.set_facecolor("#f8f8f8")
    methods = ["全組み合わせ","前週PF","複合スコア"]
    x = np.arange(len(methods)); w = 0.35
    is_vals  = [results[m]["IS"][metric]  for m in methods]
    oos_vals = [results[m]["OOS"][metric] for m in methods]
    bars_is  = ax.bar(x-w/2, is_vals,  w, label="IS",  color="#2c3e50", alpha=0.75)
    bars_oos = ax.bar(x+w/2, oos_vals, w, label="OOS", color="#e74c3c", alpha=0.75)
    if thr: ax.axhline(thr, color="#CC3333", lw=1.0, ls="--", alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(methods, fontsize=8.5)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.legend(fontsize=8.5)
    ax.grid(axis="y", alpha=0.2)
    for bar, v in zip(list(bars_is)+list(bars_oos), is_vals+oos_vals):
        ax.text(bar.get_x()+bar.get_width()/2, v+0.005,
                f"{v:.2f}" if metric=="pf" else f"{v:.1f}",
                ha="center", va="bottom", fontsize=8)

# P6: OOS月次損益（複合スコア）
ax6 = fig.add_subplot(gs[3, 0])
ax6.set_facecolor("#f8f8f8")
sub_oos_sc = df_sc[df_sc["period"]=="OOS"].copy()
if len(sub_oos_sc):
    sub_oos_sc["month"] = sub_oos_sc["signal_bar"].dt.to_period("M")
    monthly = sub_oos_sc.groupby("month")["pnl_yen"].sum()
    colors_ = ["#27ae60" if v>=0 else "#e74c3c" for v in monthly.values]
    ax6.bar(range(len(monthly)), monthly.values/10000, color=colors_,
            edgecolor="white", linewidth=0.5)
    ax6.axhline(0, color="#333", lw=0.8)
    ax6.set_xticks(range(len(monthly)))
    ax6.set_xticklabels([str(m) for m in monthly.index], rotation=45, fontsize=7.5)
    ax6.set_title("OOS月次損益（複合スコア TOP6）", fontsize=10, fontweight="bold")
    ax6.set_ylabel("損益（万円）", fontsize=9)
    ax6.grid(axis="y", alpha=0.2)
    ax6.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{v:+.1f}万"))

# P7: IS/OOS PF乖離サマリー
ax7 = fig.add_subplot(gs[3, 1])
ax7.axis("off")
ax7.set_facecolor("#f8f9fa")

tbl_data = [["手法","IS PF","OOS PF","乖離","IS DD%","OOS DD%"]]
for key in ["全組み合わせ","前週PF","複合スコア"]:
    is_pf  = results[key]["IS"]["pf"]
    oos_pf = results[key]["OOS"]["pf"]
    gap    = oos_pf - is_pf
    is_dd  = results[key]["IS"]["dd_pct"]
    oos_dd = results[key]["OOS"]["dd_pct"]
    tbl_data.append([key, f"{is_pf:.3f}", f"{oos_pf:.3f}",
                     f"{gap:+.3f}", f"{is_dd:.1f}%", f"{oos_dd:.1f}%"])

tbl = ax7.table(cellText=tbl_data[1:], colLabels=tbl_data[0],
                loc="center", cellLoc="center")
tbl.auto_set_font_size(False)
tbl.set_fontsize(8.5)
tbl.scale(1.2, 1.8)
for (r, c), cell in tbl.get_celld().items():
    if r == 0:
        cell.set_facecolor("#1a3a7a"); cell.set_text_props(color="white", fontweight="bold")
    elif r % 2 == 0:
        cell.set_facecolor("#eef2ff")
ax7.set_title("IS vs OOS サマリー", fontsize=10, fontweight="bold", pad=12)

out_path = OUT_DIR / "is_oos_comparison.png"
fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#f8f9fa")
plt.close(fig)
print(f"図保存: {out_path}")
print(f"保存先: {OUT_DIR}")
print("完了")
