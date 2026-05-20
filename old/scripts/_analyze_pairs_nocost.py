# -*- coding: utf-8 -*-
"""12ペア コストなし IS期間 ペア別集計"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

ROOT=Path(__file__).parent; DATA_DIR=ROOT/"data"/"dukascopy"
PB_PATH=ROOT/"docs"/"strategy_judgment"/"playbook.csv"

IS_END="2023-12-31"
STRENGTH_WINDOW=24; AC_WINDOW=12; MAX_HOLD=48
CAPITAL=1_000_000; RISK_PCT=0.005
PIP_SIZE_JPY=0.01; PIP_VAL_JPY=100
PIP_SIZE_USD=0.0001; PIP_VAL_USD=1000
JST=pd.Timedelta(hours=9)

PAIR_CURRENCIES={
    "USDJPY":("USD","JPY"),"EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"),"AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"),"CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"),"AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"),"EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"),"AUDNZD":("AUD","NZD"),
}
JPY_PAIRS={p for p,(b,q) in PAIR_CURRENCIES.items() if q=="JPY"}
CURRENCIES=sorted({c for v in PAIR_CURRENCIES.values() for c in v})
SESSIONS=[("Tokyo",9,15),("London",15,21),("NY",21,3),("Late",3,9)]
SESS_LABEL={"Tokyo":"東京 09-15JST","London":"欧州 15-21JST",
            "NY":"NY 21-03JST","Late":"深夜 03-09JST"}

print("データ読込中...")
dfs={}
for pair in PAIR_CURRENCIES:
    f=DATA_DIR/f"{pair}_5min.parquet"
    if not f.exists(): continue
    df=pd.read_parquet(f)
    if df.index.tz is not None: df.index=df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair]=df[["Open","High","Low","Close"]]

common_idx=dfs["USDJPY"].index
for p in dfs: common_idx=common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p]=dfs[p].reindex(common_idx)

pair_lr={p:np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW)) for p,df in dfs.items()}
raw_str={c:pd.Series(0.0,index=common_idx) for c in CURRENCIES}
cnt={c:0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    r=pair_lr[pair]; raw_str[b]+=r; raw_str[q]-=r; cnt[b]+=1; cnt[q]+=1
for c in CURRENCIES:
    if cnt[c]: raw_str[c]/=cnt[c]
str_df=pd.DataFrame(raw_str)

jst_hour=(common_idx+JST).hour
def get_sess(h):
    for name,s,e in SESSIONS:
        if s<e:
            if s<=h<e: return name
        else:
            if h>=s or h<e: return name
    return "Late"
sess_s=pd.Series([get_sess(h) for h in jst_hour],index=common_idx)

print("AC・ATR計算中...")
ac_dict={}
for pair,df in dfs.items():
    ret=np.log(df["Close"]/df["Close"].shift(1))
    arr=ret.values; res=np.full(len(arr),np.nan)
    for i in range(AC_WINDOW-1,len(arr)):
        x=arr[i-AC_WINDOW+1:i+1]
        if np.any(np.isnan(x)): continue
        cc=np.corrcoef(x[:-1],x[1:]); res[i]=cc[0,1]
    ac_dict[pair]=pd.Series(res,index=common_idx)

atr_dict={}
for pair,df in dfs.items():
    hi,lo,cl=df["High"],df["Low"],df["Close"].shift(1)
    tr=pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr_dict[pair]=tr.rolling(14).mean()

df_pb=pd.read_csv(PB_PATH,encoding="utf-8-sig") if PB_PATH.exists() else pd.DataFrame()

def run_bt_nocost(pair, direction, mask):
    df_p=dfs[pair]; atr=atr_dict[pair]
    pip_sz,pip_val=(PIP_SIZE_JPY,PIP_VAL_JPY) if pair in JPY_PAIRS else (PIP_SIZE_USD,PIP_VAL_USD)
    positions=np.where(mask.values)[0]; recs=[]
    for sp in positions:
        ep=sp+1
        if ep>=len(df_p): continue
        entry_p=df_p["Open"].iloc[ep]; atr_val=atr.iloc[sp]
        if atr_val<=0 or np.isnan(atr_val): continue
        sl_pips=atr_val/pip_sz
        if sl_pips<=0: continue
        lot=(CAPITAL*RISK_PCT)/(sl_pips*pip_val)
        period="IS" if df_p.index[sp]<=pd.Timestamp(IS_END) else "OOS"
        if direction=="short":
            best=entry_p; trail=entry_p+atr_val; exit_p=None; held=0
            for h in range(1,MAX_HOLD+1):
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
            best=entry_p; trail=entry_p-atr_val; exit_p=None; held=0
            for h in range(1,MAX_HOLD+1):
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
        recs.append({"pair":pair,"session":SESS_LABEL.get(sess_s.iloc[sp],sess_s.iloc[sp]),
                     "combo":f"{pair}_{SESS_LABEL.get(sess_s.iloc[sp],'')}",
                     "direction":direction,"pnl":pnl,"period":period})
    return recs

print("バックテスト実行中（コストなし）...")
all_records=[]
if len(df_pb):
    df_pb_tmp=df_pb.copy()
    df_pb_tmp["sc"]=df_pb_tmp["session"].str.replace("\n"," ").str.strip()

for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    diff=str_df[base_c]-str_df[quote_c]
    q10=diff.quantile(0.10)
    ac=ac_dict[pair]
    bd=(dfs[pair]["Low"]<dfs[pair]["Low"].shift(1))
    for sname,s,e in SESSIONS:
        sm=sess_s==sname
        lbl=SESS_LABEL[sname]
        if len(df_pb_tmp):
            sc=lbl.replace("\n"," ").strip()
            pb_row=df_pb_tmp[(df_pb_tmp["pair"]==pair)&(df_pb_tmp["sc"]==sc)]
        else: pb_row=pd.DataFrame()
        if not len(pb_row): continue
        jdg=pb_row["judge"].values[0]; flt=pb_row["filter"].values[0]
        if "SHORT" in jdg:
            direction="short"
            mask=bd&(diff<=q10)&(ac>0)&ac.notna()&sm if "ac>0" in (flt or "") else bd&(diff<=q10)&sm
        elif "LONG" in jdg:
            direction="long"
            mask=bd&(diff<=q10)&(ac<0)&ac.notna()&sm if "ac<0" in (flt or "") else bd&(diff<=q10)&sm
        else: continue
        all_records.extend(run_bt_nocost(pair,direction,mask))

df_all=pd.DataFrame(all_records)
df_is=df_all[df_all["period"]=="IS"].copy()

def pf(d):
    g=d[d["pnl"]>0]["pnl"].sum(); l=d[d["pnl"]<=0]["pnl"].abs().sum()
    return g/l if l>0 else (float("inf") if g>0 else float("nan"))

# ── ペア×セッション別（IS） ──
print()
print("="*70)
print("IS期間 コストなし  ペア×セッション別（損益順）")
print("="*70)
print(f"{'コンビ':<28} {'件数':>5} {'勝率':>6} {'PF':>7} {'損益万':>8}")
print("-"*60)

grp=df_is.groupby(["pair","session"])
rows=[]
for (pair,sess),d in grp:
    rows.append({"combo":f"{pair}_{sess}","n":len(d),
                 "wr":len(d[d["pnl"]>0])/len(d)*100,
                 "pf":pf(d),"pnl_m":d["pnl"].sum()/10000})
for r in sorted(rows,key=lambda x:-x["pnl_m"]):
    flag=" *" if r["pf"]>=1.5 else ""
    print(f"{r['combo']:<28} {r['n']:>5} {r['wr']:>6.1f} {r['pf']:>7.3f} {r['pnl_m']:>+8.1f}{flag}")

# ── ペア別合計（IS） ──
print()
print("="*50)
print("IS期間 コストなし  ペア別合計（損益順）")
print("="*50)
print(f"{'ペア':<10} {'件数':>5} {'勝率':>6} {'PF':>7} {'損益万':>8} {'寄与率':>7}")
total_pnl=df_is["pnl"].sum()
pair_rows=[]
for pair,d in df_is.groupby("pair"):
    pair_rows.append({"pair":pair,"n":len(d),"wr":len(d[d["pnl"]>0])/len(d)*100,
                      "pf":pf(d),"pnl_m":d["pnl"].sum()/10000,
                      "contrib":d["pnl"].sum()/total_pnl*100})
for r in sorted(pair_rows,key=lambda x:-x["pnl_m"]):
    bar="*"*max(0,int(r["contrib"]/3))
    print(f"{r['pair']:<10} {r['n']:>5} {r['wr']:>6.1f} {r['pf']:>7.3f} {r['pnl_m']:>+8.1f} {r['contrib']:>6.1f}% {bar}")

print()
print(f"IS全体合計: {len(df_is)}件  PF={pf(df_is):.3f}  損益={df_is['pnl'].sum()/10000:+.1f}万")
