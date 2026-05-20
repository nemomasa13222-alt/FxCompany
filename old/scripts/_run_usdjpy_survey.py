# -*- coding: utf-8 -*-
"""USDJPY限定 IS期間パラメータサーベイ"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

ROOT=Path(__file__).parent
DATA_DIR=ROOT/"data"/"dukascopy"
PB_PATH=ROOT/"docs"/"strategy_judgment"/"playbook.csv"

IS_START="2022-01-01"; IS_END="2023-12-31"
STRENGTH_WINDOW=24; AC_WINDOW=12; MAX_HOLD=48
CAPITAL=1_000_000; RISK_PCT=0.005
PIP_SIZE_JPY=0.01; PIP_VAL_JPY=100
JST=pd.Timedelta(hours=9)
SPREAD_USDJPY=0.2  # DMM FX

PAIR_CURRENCIES={
    "USDJPY":("USD","JPY"),"EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"),"AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"),"CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"),"AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"),"EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"),"AUDNZD":("AUD","NZD"),
}
CURRENCIES=sorted({c for v in PAIR_CURRENCIES.values() for c in v})
SESSIONS=[("Tokyo",9,15),("London",15,21),("NY",21,3),("Late",3,9)]
SESS_LABEL={"Tokyo":"東京\n09-15JST","London":"欧州\n15-21JST",
            "NY":"NY\n21-03JST","Late":"深夜\n03-09JST"}

print("データ読込中...")
dfs={}
for pair in PAIR_CURRENCIES:
    f=DATA_DIR/f"{pair}_5min.parquet"
    if not f.exists(): continue
    df=pd.read_parquet(f)
    if df.index.tz is not None: df.index=df.index.tz_convert("UTC").tz_localize(None)
    df=df[(df.index>=IS_START)&(df.index<=IS_END)]
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
ac={}
for pair,df in dfs.items():
    ret=np.log(df["Close"]/df["Close"].shift(1))
    arr=ret.values; res=np.full(len(arr),np.nan)
    for i in range(AC_WINDOW-1,len(arr)):
        x=arr[i-AC_WINDOW+1:i+1]
        if np.any(np.isnan(x)): continue
        cc=np.corrcoef(x[:-1],x[1:]); res[i]=cc[0,1]
    ac[pair]=pd.Series(res,index=common_idx)

atr={}
for pair,df in dfs.items():
    hi,lo,cl=df["High"],df["Low"],df["Close"].shift(1)
    tr=pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr[pair]=tr.rolling(14).mean()

bd_usdjpy=dfs["USDJPY"]["Low"]<dfs["USDJPY"]["Low"].shift(1)
diff_usdjpy=str_df["USD"]-str_df["JPY"]
ac_usdjpy=ac["USDJPY"]
atr_usdjpy=atr["USDJPY"]
df_ohlc=dfs["USDJPY"]

df_pb=pd.read_csv(PB_PATH,encoding="utf-8-sig") if PB_PATH.exists() else pd.DataFrame()

def get_pb_info(sname_label):
    if not len(df_pb): return None,None
    tmp=df_pb.copy()
    tmp["sc"]=tmp["session"].str.replace("\n"," ").str.strip()
    sc=sname_label.replace("\n"," ").strip()
    row=tmp[(tmp["pair"]=="USDJPY")&(tmp["sc"]==sc)]
    if not len(row): return None,None
    return row["judge"].values[0], row["filter"].values[0]

def run_bt(direction, mask):
    positions=np.where(mask.values)[0]; pnls=[]
    for sp in positions:
        ep=sp+1
        if ep>=len(df_ohlc): continue
        entry_p=df_ohlc["Open"].iloc[ep]; atr_val=atr_usdjpy.iloc[sp]
        if atr_val<=0 or np.isnan(atr_val): continue
        sl_pips=atr_val/PIP_SIZE_JPY
        if sl_pips<=0: continue
        lot=(CAPITAL*RISK_PCT)/(sl_pips*PIP_VAL_JPY)
        cost=SPREAD_USDJPY*PIP_VAL_JPY*lot
        if direction=="short":
            best=entry_p; trail=entry_p+atr_val; exit_p=None; held=0
            for h in range(1,MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_ohlc): break
                bh=df_ohlc["High"].iloc[bp]; bl=df_ohlc["Low"].iloc[bp]; held=h
                if bh>=trail: exit_p=trail; break
                if bl<best: best=bl; trail=min(trail,best+atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_ohlc): exit_p=df_ohlc["Close"].iloc[fp]
                else: continue
            pnls.append((entry_p-exit_p)/PIP_SIZE_JPY*PIP_VAL_JPY*lot - cost)
        else:
            best=entry_p; trail=entry_p-atr_val; exit_p=None; held=0
            for h in range(1,MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_ohlc): break
                bh=df_ohlc["High"].iloc[bp]; bl=df_ohlc["Low"].iloc[bp]; held=h
                if bl<=trail: exit_p=trail; break
                if bh>best: best=bh; trail=max(trail,best-atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_ohlc): exit_p=df_ohlc["Close"].iloc[fp]
                else: continue
            pnls.append((exit_p-entry_p)/PIP_SIZE_JPY*PIP_VAL_JPY*lot - cost)
    return np.array(pnls)

def stats(pnls):
    if len(pnls)==0: return None
    w=pnls[pnls>0]; l=pnls[pnls<=0]
    gp=w.sum(); gl=np.abs(l).sum()
    pf=gp/gl if gl>0 else (float("inf") if gp>0 else float("nan"))
    wr=len(w)/len(pnls)*100
    pnl_m=pnls.sum()/10000
    cum=np.cumsum(pnls); dd=(np.maximum.accumulate(cum)-cum).max()/CAPITAL*100
    return dict(n=len(pnls),wr=wr,pf=pf,pnl=pnl_m,dd=dd)

Q_VALS=[0.03,0.04,0.05,0.07,0.10]
AC_VALS=[0.00,0.05,0.10,0.15,0.20]

print()
print("USDJPY IS期間パラメータサーベイ（DMM FXスプレッド 0.2pip込み）")
print(f"{'q':>5} {'ac>=':>5} {'n':>6} {'勝率%':>6} {'PF':>7} {'損益万':>8} {'DD%':>6} {'':>4}")
print("-"*52)

rows=[]
for q_ext in Q_VALS:
    qt=diff_usdjpy.quantile(q_ext)
    for ac_min in AC_VALS:
        pnls_all=[]
        for sname,s,e in SESSIONS:
            lbl=SESS_LABEL[sname]
            sm=sess_s==sname
            jdg,flt=get_pb_info(lbl)
            if jdg is None: continue
            if "SHORT" in jdg:
                d="short"
                if "ac>0" in (flt or ""):
                    mask=bd_usdjpy&(diff_usdjpy<=qt)&(ac_usdjpy>ac_min)&ac_usdjpy.notna()&sm
                else:
                    mask=bd_usdjpy&(diff_usdjpy<=qt)&sm
            elif "LONG" in jdg:
                d="long"
                if "ac<0" in (flt or ""):
                    mask=bd_usdjpy&(diff_usdjpy<=qt)&(ac_usdjpy<-ac_min)&ac_usdjpy.notna()&sm
                else:
                    mask=bd_usdjpy&(diff_usdjpy<=qt)&sm
            else:
                continue
            p=run_bt(d,mask)
            if len(p): pnls_all.append(p)

        pnls=np.concatenate(pnls_all) if pnls_all else np.array([])
        st=stats(pnls)
        if st is None:
            print(f"{q_ext:5.2f} {ac_min:5.2f} {'0':>6}")
            continue
        flag="  ★PF>=1.2" if st["pf"]>=1.2 else "  ◎PF>=1.0" if st["pf"]>=1.0 else ""
        print(f"{q_ext:5.2f} {ac_min:5.2f} {st['n']:6d} {st['wr']:6.1f} {st['pf']:7.3f} {st['pnl']:+8.1f} {st['dd']:6.1f}{flag}")
        rows.append({"q":q_ext,"ac_min":ac_min,**st})

print()
good=sorted([r for r in rows if r["pf"]>=1.0],key=lambda x:-x["pf"])
print(f"PF>=1.0の条件: {len(good)}件")
if good:
    print("\nPF>=1.0 上位条件:")
    print(f"{'q':>5} {'ac>=':>5} {'n':>6} {'PF':>7} {'損益万':>8} {'DD%':>6}")
    for r in good[:10]:
        print(f"{r['q']:5.2f} {r['ac_min']:5.2f} {r['n']:6d} {r['pf']:7.3f} {r['pnl']:+8.1f} {r['dd']:6.1f}")

pd.DataFrame(rows).to_csv(ROOT/"docs"/"param_survey"/"usdjpy_survey_is.csv",
                          index=False,encoding="utf-8-sig")
print("\n完了")
