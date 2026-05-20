# -*- coding: utf-8 -*-
"""
USDJPY コスト込み IS+OOS バックテスト
採用パラメータ: Q_EXTREME=0.04 / AC_MIN=0.20（ISサーベイで確定）
IS : 2022-01-01 ~ 2023-12-31  OOS: 2024-01-01 ~ 2024-12-31
コスト: DMM FX スプレッド 0.2pip（往復）/ 手数料なし
IS期間の分位点閾値をOOSに適用（先読みなし）
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
PB_PATH  = ROOT / "docs" / "strategy_judgment" / "playbook.csv"
OUT_DIR  = ROOT / "docs" / "usdjpy_is_oos"
OUT_DIR.mkdir(parents=True, exist_ok=True)

Q_EXTREME = 0.04
AC_MIN    = 0.20
IS_END    = "2023-12-31"
STRENGTH_WINDOW = 24; AC_WINDOW = 12; MAX_HOLD = 48
CAPITAL = 1_000_000; RISK_PCT = 0.005
PIP_SIZE = 0.01; PIP_VAL = 100; SPREAD = 0.2
JST = pd.Timedelta(hours=9)

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"),"EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"),"AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"),"CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"),"AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"),"EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"),"AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})
SESSIONS   = [("東京\n09-15JST",9,15),("欧州\n15-21JST",15,21),
               ("NY\n21-03JST",21,3),("深夜\n03-09JST",3,9)]

print("データ読込中（全ペア 2022-2024）...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None: df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
print(f"バー数: {len(common_idx):,}  ({common_idx.min()} -> {common_idx.max()})")

# 通貨強弱（全期間）
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW)) for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    r = pair_lr[pair]; raw_str[b]+=r; raw_str[q]-=r; cnt[b]+=1; cnt[q]+=1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)
diff_full = str_df["USD"] - str_df["JPY"]

# IS期間の閾値（OOSへの先読みなし）
Q_THRESH = float(diff_full[diff_full.index <= IS_END].quantile(Q_EXTREME))
print(f"IS分位点 q={Q_EXTREME} → 閾値: {Q_THRESH:.6f}")

# セッション
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e in SESSIONS:
        if s<e:
            if s<=h<e: return name
        else:
            if h>=s or h<e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# 自己相関（全期間）
print("自己相関・ATR計算中...")
df_u = dfs["USDJPY"]
ret = np.log(df_u["Close"]/df_u["Close"].shift(1))
arr = ret.values; res = np.full(len(arr), np.nan)
for i in range(AC_WINDOW-1, len(arr)):
    x = arr[i-AC_WINDOW+1:i+1]
    if np.any(np.isnan(x)): continue
    cc = np.corrcoef(x[:-1],x[1:]); res[i] = cc[0,1]
ac_s = pd.Series(res, index=common_idx)

hi,lo,cl = df_u["High"],df_u["Low"],df_u["Close"].shift(1)
atr_s = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1).rolling(14).mean()
bd_s  = df_u["Low"] < df_u["Low"].shift(1)

df_pb = pd.read_csv(PB_PATH, encoding="utf-8-sig") if PB_PATH.exists() else pd.DataFrame()

def run_bt(direction, mask):
    positions = np.where(mask.values)[0]; records = []
    for sp in positions:
        ep = sp+1
        if ep >= len(df_u): continue
        entry_p = df_u["Open"].iloc[ep]; atr_val = atr_s.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_pips = atr_val / PIP_SIZE
        if sl_pips <= 0: continue
        lot  = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VAL)
        cost = SPREAD * PIP_VAL * lot
        if direction == "short":
            best=entry_p; trail=entry_p+atr_val; exit_p=None; held=0
            for h in range(1, MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_u): break
                bh=df_u["High"].iloc[bp]; bl=df_u["Low"].iloc[bp]; held=h
                if bh>=trail: exit_p=trail; break
                if bl<best: best=bl; trail=min(trail,best+atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_u): exit_p=df_u["Close"].iloc[fp]
                else: continue
            pnl=(entry_p-exit_p)/PIP_SIZE*PIP_VAL*lot - cost
        else:
            best=entry_p; trail=entry_p-atr_val; exit_p=None; held=0
            for h in range(1, MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_u): break
                bh=df_u["High"].iloc[bp]; bl=df_u["Low"].iloc[bp]; held=h
                if bl<=trail: exit_p=trail; break
                if bh>best: best=bh; trail=max(trail,best-atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_u): exit_p=df_u["Close"].iloc[fp]
                else: continue
            pnl=(exit_p-entry_p)/PIP_SIZE*PIP_VAL*lot - cost
        records.append({"signal_bar":df_u.index[sp],"entry_bar":df_u.index[ep],
                        "session":sess_s.get(df_u.index[sp],"─"),"direction":direction,
                        "pnl_yen":pnl,"r_mult":pnl/(CAPITAL*RISK_PCT),"held":held})
    return pd.DataFrame(records)

print("\nバックテスト実行...")
all_records = []
if len(df_pb):
    df_pb_tmp = df_pb.copy()
    df_pb_tmp["sc"] = df_pb_tmp["session"].str.replace("\n"," ").str.strip()

for sname,s,e in SESSIONS:
    sm = sess_s == sname
    if len(df_pb):
        sc = sname.replace("\n"," ").strip()
        pb_row = df_pb_tmp[(df_pb_tmp["pair"]=="USDJPY")&(df_pb_tmp["sc"]==sc)]
    else:
        pb_row = pd.DataFrame()
    if not len(pb_row): continue
    jdg = pb_row["judge"].values[0]; flt = pb_row["filter"].values[0]
    if "SHORT" in jdg:
        direction = "short"
        mask = bd_s&(diff_full<=Q_THRESH)&(ac_s>AC_MIN)&ac_s.notna()&sm \
               if "ac>0" in (flt or "") else bd_s&(diff_full<=Q_THRESH)&sm
    elif "LONG" in jdg:
        direction = "long"
        mask = bd_s&(diff_full<=Q_THRESH)&(ac_s<-AC_MIN)&ac_s.notna()&sm \
               if "ac<0" in (flt or "") else bd_s&(diff_full<=Q_THRESH)&sm
    else:
        continue
    df_bt = run_bt(direction, mask)
    if len(df_bt):
        n_is  = len(df_bt[df_bt["signal_bar"]<=IS_END])
        n_oos = len(df_bt[df_bt["signal_bar"]>IS_END])
        print(f"  {sname.replace(chr(10),' ')} {direction}: IS={n_is} OOS={n_oos}")
        all_records.append(df_bt)

df_all = pd.concat(all_records, ignore_index=True).sort_values("signal_bar")
df_all["period"] = df_all["signal_bar"].apply(
    lambda x: "IS" if x <= pd.Timestamp(IS_END) else "OOS")

def sv(d, lbl):
    if len(d)==0: return dict(label=lbl,n=0,win_rate=0,pf=float("nan"),
                              total_pnl=0,max_dd=0,dd_pct=0,expectancy=0)
    w=d[d["pnl_yen"]>0]; l=d[d["pnl_yen"]<=0]
    gp=w["pnl_yen"].sum(); gl=l["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=d["pnl_yen"].cumsum(); dd=(cum.cummax()-cum).max()
    return dict(label=lbl, n=len(d), win_rate=len(w)/len(d)*100, pf=pf,
                total_pnl=d["pnl_yen"].sum(), max_dd=dd, dd_pct=dd/CAPITAL*100,
                expectancy=float(d["pnl_yen"].mean()))

results = {
    "IS":  sv(df_all[df_all["period"]=="IS"],  "IS (2022-2023)"),
    "OOS": sv(df_all[df_all["period"]=="OOS"], "OOS (2024)"),
    "ALL": sv(df_all, "全期間"),
}

print("\n" + "="*60)
print(f"採用パラメータ: Q={Q_EXTREME} / AC_MIN={AC_MIN} / スプレッド{SPREAD}pip")
print("="*60)
print(f"{'期間':14s}{'n':>6}{'勝率':>7}{'PF':>8}{'損益(万)':>10}{'DD%':>8}")
print("-"*55)
for k,v in results.items():
    print(f"{v['label']:14s}{v['n']:>6}{v['win_rate']:>7.1f}{v['pf']:>8.3f}"
          f"{v['total_pnl']/10000:>+10.1f}{v['dd_pct']:>8.1f}%")

# セッション別
print("\nセッション別:")
for sname,s,e in SESSIONS:
    d = df_all[df_all["session"]==sname]
    if len(d)==0: continue
    d_is=d[d["period"]=="IS"]; d_oos=d[d["period"]=="OOS"]
    for lab,dd in [("IS",d_is),("OOS",d_oos)]:
        if len(dd)==0: continue
        st=sv(dd,"")
        print(f"  {sname.replace(chr(10),' '):<12} {lab}: n={st['n']:3d} "
              f"PF={st['pf']:.3f} {st['total_pnl']/10000:+.1f}万")

df_all.to_csv(OUT_DIR/"bt_usdjpy.csv", index=False, encoding="utf-8-sig")
pd.DataFrame([{"period":k,**v} for k,v in results.items()]).to_csv(
    OUT_DIR/"summary_usdjpy.csv", index=False, encoding="utf-8-sig")
print(f"\n保存: {OUT_DIR}")
print("完了")
