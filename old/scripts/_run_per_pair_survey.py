# -*- coding: utf-8 -*-
"""
ペア別 IS パラメータサーベイ → OOS検証
対象: EURJPY / AUDJPY / USDJPY（低スプレッドJPY系3ペア）
実行: python _run_per_pair_survey.py
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
PB_PATH  = ROOT / "docs" / "strategy_judgment" / "playbook.csv"
OUT_DIR  = ROOT / "docs" / "per_pair_survey"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_PAIRS = ["EURJPY", "AUDJPY", "USDJPY"]
IS_END = "2023-12-31"
STRENGTH_WINDOW=24; AC_WINDOW=12; MAX_HOLD=48
CAPITAL=1_000_000; RISK_PCT=0.005
PIP_SIZE_JPY=0.01; PIP_VAL_JPY=100
JST=pd.Timedelta(hours=9)
MIN_TRADES = 30   # 最低取引件数（IS）

SPREADS = {"EURJPY":0.5, "AUDJPY":0.6, "USDJPY":0.2}

Q_VALS  = [0.03, 0.04, 0.05, 0.07, 0.10]
AC_VALS = [0.00, 0.05, 0.10, 0.15, 0.20]

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})
SESSIONS   = [("Tokyo",9,15),("London",15,21),("NY",21,3),("Late",3,9)]
SESS_LABEL = {"Tokyo":"東京\n09-15JST","London":"欧州\n15-21JST",
              "NY":"NY\n21-03JST","Late":"深夜\n03-09JST"}

# ════════════════════════════════════════════
# データ読込・共通計算（1回のみ）
# ════════════════════════════════════════════
print("データ読込中（全ペア 2022-2024）...")
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
print(f"バー数: {len(common_idx):,}")

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
for pair in TARGET_PAIRS:
    ret=np.log(dfs[pair]["Close"]/dfs[pair]["Close"].shift(1))
    arr=ret.values; res=np.full(len(arr),np.nan)
    for i in range(AC_WINDOW-1,len(arr)):
        x=arr[i-AC_WINDOW+1:i+1]
        if np.any(np.isnan(x)): continue
        cc=np.corrcoef(x[:-1],x[1:]); res[i]=cc[0,1]
    ac_dict[pair]=pd.Series(res,index=common_idx)

atr_dict={}
for pair in TARGET_PAIRS:
    df=dfs[pair]
    hi,lo,cl=df["High"],df["Low"],df["Close"].shift(1)
    tr=pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr_dict[pair]=tr.rolling(14).mean()

bd_dict={pair:(dfs[pair]["Low"]<dfs[pair]["Low"].shift(1)) for pair in TARGET_PAIRS}

df_pb=pd.read_csv(PB_PATH,encoding="utf-8-sig") if PB_PATH.exists() else pd.DataFrame()
if len(df_pb):
    df_pb["sc"]=df_pb["session"].str.replace("\n"," ").str.strip()

def run_bt(pair, direction, mask):
    df_p=dfs[pair]; atr=atr_dict[pair]
    spread_cost_pp=SPREADS[pair]*PIP_VAL_JPY
    positions=np.where(mask.values)[0]; pnls=[]
    for sp in positions:
        ep=sp+1
        if ep>=len(df_p): continue
        entry_p=df_p["Open"].iloc[ep]; atr_val=atr.iloc[sp]
        if atr_val<=0 or np.isnan(atr_val): continue
        sl_pips=atr_val/PIP_SIZE_JPY
        if sl_pips<=0: continue
        lot=(CAPITAL*RISK_PCT)/(sl_pips*PIP_VAL_JPY)
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
            pnl=(entry_p-exit_p)/PIP_SIZE_JPY*PIP_VAL_JPY*lot - cost
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
            pnl=(exit_p-entry_p)/PIP_SIZE_JPY*PIP_VAL_JPY*lot - cost
        pnls.append({"pnl":pnl,"period":period})
    return pd.DataFrame(pnls) if pnls else pd.DataFrame(columns=["pnl","period"])

def calc_stats(d):
    if len(d)==0: return dict(n=0,wr=0,pf=float("nan"),pnl_m=0,dd=0)
    w=d[d["pnl"]>0]; l=d[d["pnl"]<=0]
    gp=w["pnl"].sum(); gl=l["pnl"].abs().sum()
    pf=gp/gl if gl>0 else (float("inf") if gp>0 else float("nan"))
    cum=d["pnl"].cumsum()
    dd=(cum.cummax()-cum).max()/CAPITAL*100
    return dict(n=len(d),wr=len(w)/len(d)*100,pf=pf,pnl_m=d["pnl"].sum()/10000,dd=dd)

def get_sessions_for_pair(pair):
    """プレイブックからペアの有効セッション一覧を取得"""
    if not len(df_pb): return []
    rows=[]
    for sname,s,e in SESSIONS:
        lbl=SESS_LABEL[sname]
        sc=lbl.replace("\n"," ").strip()
        pb_row=df_pb[(df_pb["pair"]==pair)&(df_pb["sc"]==sc)]
        if not len(pb_row): continue
        jdg=pb_row["judge"].values[0]; flt=pb_row["filter"].values[0]
        if "SHORT" in jdg or "LONG" in jdg:
            rows.append((sname,jdg,flt))
    return rows

def run_pair_with_params(pair, q_ext, ac_min):
    """指定パラメータでペアを全期間バックテスト→IS/OOS DataFrameを返す"""
    bc,qc=PAIR_CURRENCIES[pair]
    diff=str_df[bc]-str_df[qc]
    # IS期間の分位点のみで閾値決定（先読みなし）
    qt=float(diff[diff.index<=IS_END].quantile(q_ext))
    ac=ac_dict[pair]; bd=bd_dict[pair]
    sessions_info=get_sessions_for_pair(pair)
    all_df=[]
    for sname,jdg,flt in sessions_info:
        sm=sess_s==sname
        if "SHORT" in jdg:
            direction="short"
            mask=bd&(diff<=qt)&(ac>ac_min)&ac.notna()&sm if "ac>0" in (flt or "") else bd&(diff<=qt)&sm
        else:
            direction="long"
            mask=bd&(diff<=qt)&(ac<-ac_min)&ac.notna()&sm if "ac<0" in (flt or "") else bd&(diff<=qt)&sm
        df_bt=run_bt(pair,direction,mask)
        if len(df_bt): all_df.append(df_bt)
    return pd.concat(all_df,ignore_index=True) if all_df else pd.DataFrame(columns=["pnl","period"])

# ════════════════════════════════════════════
# メインループ：ペア別サーベイ
# ════════════════════════════════════════════
all_best = {}   # pair -> best_params
survey_all = []

for pair in TARGET_PAIRS:
    spread=SPREADS[pair]
    print()
    print(f"{'='*65}")
    print(f"  {pair}  スプレッド:{spread}pip  IS期間パラメータサーベイ")
    print(f"{'='*65}")
    print(f"{'q':>5} {'ac>=':>5} {'IS件数':>7} {'IS勝率':>7} {'IS PF':>8} {'IS損益万':>9} {'IS DD%':>7}")
    print("-"*55)

    pair_survey_rows=[]
    for q_ext in Q_VALS:
        for ac_min in AC_VALS:
            df_bt=run_pair_with_params(pair,q_ext,ac_min)
            df_is=df_bt[df_bt["period"]=="IS"] if len(df_bt) else pd.DataFrame(columns=["pnl","period"])
            st=calc_stats(df_is)
            flag="  ★" if (st["pf"]>=1.2 and st["n"]>=MIN_TRADES) else \
                 "  ◎" if (st["pf"]>=1.0 and st["n"]>=MIN_TRADES) else \
                 "  (少)" if st["n"]<MIN_TRADES else ""
            pf_str=f"{st['pf']:8.3f}" if not np.isnan(st["pf"]) else "     inf"
            print(f"{q_ext:5.2f} {ac_min:5.2f} {st['n']:7d} {st['wr']:7.1f} "
                  f"{pf_str} {st['pnl_m']:+9.1f} {st['dd']:7.1f}{flag}")
            pair_survey_rows.append({
                "pair":pair,"q":q_ext,"ac_min":ac_min,
                **{f"is_{k}":v for k,v in st.items()}
            })
        print()

    # ── 最適パラメータ選択（IS: PF最大 かつ n>=MIN_TRADES）
    df_sv=pd.DataFrame(pair_survey_rows)
    valid=df_sv[(df_sv["is_n"]>=MIN_TRADES)&(df_sv["is_pf"].notna())]
    if len(valid)==0:
        print(f"  ※ {pair}: 有効条件なし（件数不足）")
        all_best[pair]=None; continue
    best_row=valid.loc[valid["is_pf"].idxmax()]
    best_q=best_row["q"]; best_ac=best_row["ac_min"]
    all_best[pair]={"q":best_q,"ac":best_ac,"is_pf":best_row["is_pf"],
                    "is_pnl":best_row["is_pnl_m"],"is_n":int(best_row["is_n"])}
    print(f"  ★ 最適パラメータ: q={best_q:.2f} / AC>={best_ac:.2f}  "
          f"(IS PF={best_row['is_pf']:.3f} n={int(best_row['is_n'])}件)")

    # CSV保存
    df_sv.to_csv(OUT_DIR/f"survey_{pair}.csv",index=False,encoding="utf-8-sig")

# ════════════════════════════════════════════
# OOS開封：各ペアの最適パラメータで検証
# ════════════════════════════════════════════
print()
print("="*70)
print("OOS開封（各ペアの最適パラメータで 2024年検証）")
print("="*70)

oos_results=[]
for pair in TARGET_PAIRS:
    if all_best[pair] is None:
        print(f"  {pair}: スキップ（IS最適解なし）"); continue
    bp=all_best[pair]
    df_bt=run_pair_with_params(pair,bp["q"],bp["ac"])
    df_is =df_bt[df_bt["period"]=="IS"]
    df_oos=df_bt[df_bt["period"]=="OOS"]
    st_is =calc_stats(df_is)
    st_oos=calc_stats(df_oos)

    # 月次OOS
    df_oos2=df_oos.copy()
    # (月次はデータなしの場合もある)

    flag_oos="★PF>=1.2" if st_oos["pf"]>=1.2 else "◎PF>=1.0" if st_oos["pf"]>=1.0 else "×赤字"
    print(f"\n  [{pair}] q={bp['q']:.2f} / AC>={bp['ac']:.2f} / スプレッド{SPREADS[pair]}pip")
    print(f"  IS : n={st_is['n']:4d} PF={st_is['pf']:.3f} {st_is['pnl_m']:+.1f}万 DD={st_is['dd']:.1f}%")
    print(f"  OOS: n={st_oos['n']:4d} PF={st_oos['pf']:.3f} {st_oos['pnl_m']:+.1f}万 DD={st_oos['dd']:.1f}%  [{flag_oos}]")

    oos_results.append({
        "pair":pair,"q":bp["q"],"ac":bp["ac"],"spread":SPREADS[pair],
        **{f"is_{k}":v for k,v in st_is.items()},
        **{f"oos_{k}":v for k,v in st_oos.items()},
    })

# ════════════════════════════════════════════
# 3ペア合算（各ペア最適パラメータ使用）
# ════════════════════════════════════════════
print()
print("="*70)
print("3ペア合算（各ペア個別最適パラメータ）")
print("="*70)
combined_is=[]; combined_oos=[]
for pair in TARGET_PAIRS:
    if all_best[pair] is None: continue
    bp=all_best[pair]
    df_bt=run_pair_with_params(pair,bp["q"],bp["ac"])
    combined_is.append(df_bt[df_bt["period"]=="IS"])
    combined_oos.append(df_bt[df_bt["period"]=="OOS"])

if combined_is:
    df_cis =pd.concat(combined_is, ignore_index=True)
    df_coos=pd.concat(combined_oos,ignore_index=True)
    st_cis =calc_stats(df_cis)
    st_coos=calc_stats(df_coos)
    print(f"  IS合算 : n={st_cis['n']:4d} PF={st_cis['pf']:.3f} {st_cis['pnl_m']:+.1f}万 DD={st_cis['dd']:.1f}%")
    print(f"  OOS合算: n={st_coos['n']:4d} PF={st_coos['pf']:.3f} {st_coos['pnl_m']:+.1f}万 DD={st_coos['dd']:.1f}%")

# 結果CSV保存
pd.DataFrame(oos_results).to_csv(OUT_DIR/"oos_results.csv",index=False,encoding="utf-8-sig")

print()
print("="*70)
print("採用パラメータまとめ")
print("="*70)
print(f"{'ペア':<8} {'q':>5} {'AC>=':>5} {'スプレッド':>10} {'IS PF':>7} {'IS損益万':>9} {'OOS PF':>7} {'OOS損益万':>10}")
print("-"*65)
for r in oos_results:
    print(f"{r['pair']:<8} {r['q']:>5.2f} {r['ac']:>5.2f} {r['spread']:>8.1f}pip "
          f"{r['is_pf']:>7.3f} {r['is_pnl_m']:>+9.1f} {r['oos_pf']:>7.3f} {r['oos_pnl_m']:>+10.1f}")

print(f"\n完了。結果: {OUT_DIR}")
