# -*- coding: utf-8 -*-
"""
ペア絞り込み効果検証
コスト込み（DMM FXスプレッド）でIS期間の上位N件ペアに集中した場合のPF
実行: python _run_top_pairs_survey.py
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
PB_PATH  = ROOT / "docs" / "strategy_judgment" / "playbook.csv"
OUT_DIR  = ROOT / "docs" / "param_survey"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END = "2023-12-31"; OOS_END = "2024-12-31"
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
SESS_LABEL={"Tokyo":"東京\n09-15JST","London":"欧州\n15-21JST",
            "NY":"NY\n21-03JST","Late":"深夜\n03-09JST"}

SPREADS={
    "USDJPY":0.2,"EURJPY":0.5,"GBPJPY":0.9,
    "AUDJPY":0.6,"NZDJPY":1.7,"CHFJPY":2.2,
    "GBPUSD":0.9,"AUDUSD":0.6,"NZDUSD":1.3,
    "EURGBP":0.8,"EURAUD":1.5,"AUDNZD":2.2,
}

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
if len(df_pb):
    df_pb["sc"]=df_pb["session"].str.replace("\n"," ").str.strip()

def run_bt(pair, direction, mask):
    df_p=dfs[pair]; atr=atr_dict[pair]
    pip_sz,pip_val=(PIP_SIZE_JPY,PIP_VAL_JPY) if pair in JPY_PAIRS else (PIP_SIZE_USD,PIP_VAL_USD)
    spread_cost_pp=SPREADS.get(pair,1.0)*pip_val
    positions=np.where(mask.values)[0]; recs=[]
    for sp in positions:
        ep=sp+1
        if ep>=len(df_p): continue
        entry_p=df_p["Open"].iloc[ep]; atr_val=atr_dict[pair].iloc[sp]
        if atr_val<=0 or np.isnan(atr_val): continue
        sl_pips=atr_val/pip_sz
        if sl_pips<=0: continue
        lot=(CAPITAL*RISK_PCT)/(sl_pips*pip_val)
        cost=spread_cost_pp*lot
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
            pnl=(entry_p-exit_p)/pip_sz*pip_val*lot - cost
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
            pnl=(exit_p-entry_p)/pip_sz*pip_val*lot - cost
        recs.append({"pair":pair,"pnl":pnl,"period":period})
    return recs

# ── 全ペア全期間バックテスト（コスト込み）
print("全ペアバックテスト実行中（コスト込み）...")
all_records=[]
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    diff=str_df[base_c]-str_df[quote_c]
    q10=diff.quantile(0.10)
    ac=ac_dict[pair]
    bd=(dfs[pair]["Low"]<dfs[pair]["Low"].shift(1))
    for sname,s,e in SESSIONS:
        sm=sess_s==sname
        lbl=SESS_LABEL[sname]
        if len(df_pb):
            sc=lbl.replace("\n"," ").strip()
            pb_row=df_pb[(df_pb["pair"]==pair)&(df_pb["sc"]==sc)]
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
        all_records.extend(run_bt(pair,direction,mask))

df_all=pd.DataFrame(all_records)

def pf(d):
    g=d[d["pnl"]>0]["pnl"].sum(); l=d[d["pnl"]<=0]["pnl"].abs().sum()
    return g/l if l>0 else (float("inf") if g>0 else float("nan"))

def stats(d):
    if len(d)==0: return {"n":0,"wr":0,"pf":float("nan"),"pnl_m":0,"dd":0}
    w=d[d["pnl"]>0]; l=d[d["pnl"]<=0]
    gp=w["pnl"].sum(); gl=l["pnl"].abs().sum()
    pf_v=gp/gl if gl>0 else (float("inf") if gp>0 else float("nan"))
    cum=d["pnl"].cumsum()
    dd=(cum.cummax()-cum).max()/CAPITAL*100
    return {"n":len(d),"wr":len(w)/len(d)*100,"pf":pf_v,
            "pnl_m":d["pnl"].sum()/10000,"dd":dd}

# ── ペア別 IS 成績
df_is=df_all[df_all["period"]=="IS"]
pair_is={}
for pair,d in df_is.groupby("pair"):
    pair_is[pair]=stats(d)

print()
print("="*65)
print("IS期間 コスト込み ペア別成績（PF順）")
print("="*65)
print(f"{'ペア':<10} {'件数':>5} {'勝率':>6} {'PF':>7} {'損益万':>8} {'スプレッド':>10}")
print("-"*55)
sorted_pairs=sorted(pair_is.keys(), key=lambda p:-pair_is[p]["pf"])
for pair in sorted_pairs:
    st=pair_is[pair]
    sp=SPREADS.get(pair,0)
    flag=" ★" if st["pf"]>=1.0 else ""
    print(f"{pair:<10} {st['n']:>5} {st['wr']:>6.1f} {st['pf']:>7.3f} "
          f"{st['pnl_m']:>+8.1f} {sp:>8.1f}pip{flag}")

# ── 上位N件に絞った場合のIS+OOS比較
print()
print("="*70)
print("上位N件ペア集中（IS基準PF順）— IS/OOS成績比較")
print("="*70)
print(f"{'N':>3} {'ペア選択':<42} {'IS PF':>7} {'IS損益':>8} {'OOS PF':>7} {'OOS損益':>8}")
print("-"*75)

df_oos=df_all[df_all["period"]=="OOS"]

for n in range(1, len(sorted_pairs)+1):
    top_n=sorted_pairs[:n]
    d_is_n =df_is[df_is["pair"].isin(top_n)]
    d_oos_n=df_oos[df_oos["pair"].isin(top_n)]
    st_is_n =stats(d_is_n)
    st_oos_n=stats(d_oos_n)
    pairs_str="+".join(top_n)
    flag_is =" ★" if st_is_n["pf"] >=1.0 else ""
    flag_oos=" ★" if st_oos_n["pf"]>=1.0 else ""
    print(f"{n:>3}  {pairs_str:<42} "
          f"{st_is_n['pf']:>7.3f}{flag_is:<2} {st_is_n['pnl_m']:>+7.1f}万  "
          f"{st_oos_n['pf']:>7.3f}{flag_oos:<2} {st_oos_n['pnl_m']:>+7.1f}万")

# ── 全12ペアを参考で表示
st_all_is =stats(df_is)
st_all_oos=stats(df_oos)
print(f" 12  {'全12ペア':<42} "
      f"{st_all_is['pf']:>7.3f}   {st_all_is['pnl_m']:>+7.1f}万  "
      f"{st_all_oos['pf']:>7.3f}   {st_all_oos['pnl_m']:>+7.1f}万")

# CSV保存
rows=[]
for n in range(1,len(sorted_pairs)+1):
    top_n=sorted_pairs[:n]
    d_is_n=df_is[df_is["pair"].isin(top_n)]
    d_oos_n=df_oos[df_oos["pair"].isin(top_n)]
    rows.append({"n":n,"pairs":"+".join(top_n),
                 **{f"is_{k}":v for k,v in stats(d_is_n).items()},
                 **{f"oos_{k}":v for k,v in stats(d_oos_n).items()}})
pd.DataFrame(rows).to_csv(OUT_DIR/"top_pairs_survey.csv",index=False,encoding="utf-8-sig")
print(f"\nCSV保存: {OUT_DIR/'top_pairs_survey.csv'}")
print("完了")
