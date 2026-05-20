"""30分足・1時間足 ISサーベイ + OOS開封"""
import numpy as np
import pandas as pd
import itertools
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR  = Path("data/dukascopy")
PIP       = 0.01; ENTRY_COST = 0.2; SW = 20
IS_START  = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START = "2024-01-01"; OOS_END   = "2025-01-01"
CAPITAL   = 1_000_000;    PIP_VAL   = 667

# サーベイグリッド
GRIDS = {
    "30min": dict(
        rule="30min", tf_min=30,
        bars=[4, 6, 8], pips=[15, 25, 35], holds=[2, 3, 4]
    ),
    "1h": dict(
        rule="1h", tf_min=60,
        bars=[3, 4, 6], pips=[25, 40, 60], holds=[2, 3, 4]
    ),
}

# データ準備
dfs5 = {p: pd.read_parquet(DATA_DIR/f"{p}_5min.parquet")
        for p in PAIRS if (DATA_DIR/f"{p}_5min.parquet").exists()}
rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
st   = currency_strength(rd)
sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())
df5  = dfs5["USDJPY"]


def resample(rule):
    df = df5.resample(rule, label="left", closed="left").agg(
        Open=("Open","first"), High=("High","max"),
        Low=("Low","min"),   Close=("Close","last"), Volume=("Volume","sum")
    ).dropna(subset=["Open"])
    sd = sd5.resample(rule, label="left", closed="left").last().reindex(df.index)
    return df, sd


def make_sig(df, sd, rb, rp):
    c  = df["Close"]
    rh = c.shift(1).rolling(rb).max()
    rl = c.shift(1).rolling(rb).min()
    ir = (rh - rl) <= rp * PIP
    s  = sd.reindex(df.index)
    return pd.DataFrame({"c":c,"o":df["Open"],
                         "ls":ir&(c>rh)&(s>0),
                         "ss":ir&(c<rl)&(s<0),
                         "rm":(rh+rl)/2})


def bt(sig, mh):
    c=sig["c"].values; o=sig["o"].values; rm=sig["rm"].values
    ls=sig["ls"].values; ss=sig["ss"].values; n=len(sig)
    pnls=[]; inT=False; d=0; ep=sp=0.0; eb=-1
    for i in range(1, n-1):
        if not inT:
            if ls[i-1]:   d=1;  ep=o[i]+ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
            elif ss[i-1]: d=-1; ep=o[i]-ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
        else:
            held=i-eb; unr=(c[i]-ep)*d/PIP; xp=None
            if d==1  and c[i]<=sp: xp=sp
            elif d==-1 and c[i]>=sp: xp=sp
            elif held>=mh and unr>0:
                if d==1  and c[i]<c[i-1]: xp=c[i]
                elif d==-1 and c[i]>c[i-1]: xp=c[i]
            if xp is not None:
                pnls.append((xp-ep)*d/PIP); inT=False; d=0
    return np.array(pnls)


def met(pnls):
    if len(pnls)==0:
        return dict(n=0,wr=0,pf=0,ev=0,jpy=0,dd=0,var95=0,cvar95=0,tr=0,
                    aw=0,al=0,sr=0)
    w=pnls[pnls>0]; l=pnls[pnls<=0]
    pf=w.sum()/abs(l.sum()) if l.sum()!=0 else 99.0
    eq=np.cumsum(pnls); pk=np.maximum.accumulate(np.maximum(eq,0))
    dd=(eq-pk).min()*PIP_VAL/CAPITAL*100
    var95=np.percentile(pnls,5)
    cvar95=pnls[pnls<=var95].mean() if (pnls<=var95).sum()>0 else var95
    p95=np.percentile(pnls,95)
    tr=abs(p95/var95) if var95!=0 else 99.0
    return dict(n=len(pnls),wr=len(w)/len(pnls)*100,pf=pf,ev=pnls.mean(),
                jpy=pnls.sum()*PIP_VAL,dd=dd,var95=var95,cvar95=cvar95,tr=tr,
                aw=w.mean() if len(w) else 0,
                al=l.mean() if len(l) else 0,
                sr=0)


def streak(pnls):
    mx=cur=0; best=cur_s=[]
    for v in pnls:
        if v<=0: cur+=1; cur_s.append(v)
        else:
            if cur>mx: mx=cur; best=cur_s[:]
            cur=0; cur_s=[]
    if cur>mx: mx=cur; best=cur_s[:]
    c3=sum(1 for i in range(len(pnls)-2) if all(pnls[i:i+3]<=0))
    c5=sum(1 for i in range(len(pnls)-4) if all(pnls[i:i+5]<=0))
    return mx, sum(best)*PIP_VAL, c3, c5


def run_tf(tf_label, cfg):
    print(f"\n{'='*62}")
    print(f"  {tf_label} ISサーベイ（27通り）")
    print(f"{'='*62}")
    print(f"  {'bars':>4} {'pips':>4} {'hold':>4} | "
          f"{'N':>5} {'WR%':>6} {'PF':>5} {'損益(万)':>9} {'DD%':>7}")
    print("  " + "-"*55)

    df, sd = resample(cfg["rule"])
    tf_min  = cfg["tf_min"]

    df_is   = df.loc[IS_START:IS_END]
    sd_is   = sd.reindex(df_is.index)
    df_oos  = df.loc[OOS_START:OOS_END]
    sd_oos  = sd.reindex(df_oos.index)

    results = []
    for rb, rp, mh in itertools.product(cfg["bars"], cfg["pips"], cfg["holds"]):
        sig = make_sig(df_is, sd_is, rb, rp)
        m   = met(bt(sig, mh))
        results.append({"rb":rb,"rp":rp,"mh":mh,**m})

    results.sort(key=lambda x: -x["pf"])

    for r in results:
        mark = " <-- 採用候補" if r == results[0] else ""
        print(f"  {r['rb']:>4} {r['rp']:>4} {r['mh']:>4} | "
              f"{r['n']:>5} {r['wr']:>6.1f} {r['pf']:>5.2f} "
              f"{r['jpy']/10000:>+9.1f} {r['dd']:>+7.2f}%{mark}")

    # 全条件の黒字確認
    n_black  = sum(1 for r in results if r["jpy"]>0)
    n_pf13   = sum(1 for r in results if r["pf"]>=1.3)
    n_pf12   = sum(1 for r in results if r["pf"]>=1.2)
    print(f"\n  全条件黒字: {n_black}/27  PF>=1.3: {n_pf13}/27  PF>=1.2: {n_pf12}/27")

    # OOS開封
    best = results[0]
    rb, rp, mh = best["rb"], best["rp"], best["mh"]
    print(f"\n  OOS開封: bars={rb}  pips={rp}  hold={mh}")
    print(f"  レンジ窓={rb*tf_min}分  保有目安={mh*tf_min}分")

    pnls_is  = bt(make_sig(df_is,  sd_is,  rb, rp), mh)
    pnls_oos = bt(make_sig(df_oos, sd_oos, rb, rp), mh)
    m_is     = met(pnls_is)
    m_oos    = met(pnls_oos)
    pf_diff  = abs(m_is["pf"] - m_oos["pf"])

    print(f"\n  {'':6} {'N':>6} {'WR':>6} {'PF':>5} {'期待値':>7} "
          f"{'損益(万)':>9} {'DD%':>7} {'VaR95':>7} {'CVaR95':>8} {'TailR':>6}")
    print("  " + "-"*72)
    for label, m in [("IS", m_is), ("OOS", m_oos)]:
        print(f"  {label:6} {m['n']:>6,} {m['wr']:>6.1f}% {m['pf']:>5.2f} "
              f"{m['ev']:>+7.3f}p {m['jpy']/10000:>+9.1f} {m['dd']:>+7.2f}% "
              f"{m['var95']:>+7.2f}p {m['cvar95']:>+8.2f}p {m['tr']:>6.2f}")

    print(f"\n  PF乖離: {pf_diff:.2f}  (基準<=0.30)")

    # 採否
    checks = [
        ("IS PF >= 1.30",         m_is["pf"]  >= 1.30),
        ("OOS PF >= 1.10",        m_oos["pf"] >= 1.10),
        ("OOS 損益 > 0",          m_oos["jpy"] > 0),
        ("OOS DD <= IS×1.5",      abs(m_oos["dd"]) <= abs(m_is["dd"])*1.5),
        ("IS/OOS PF乖離 <= 0.30", pf_diff <= 0.30),
    ]
    all_ok = all(c for _,c in checks)
    print("\n  [採否判定]")
    for lbl, ok in checks:
        print(f"    [{'OK' if ok else 'NG'}] {lbl}")
    print(f"\n  --> {'採用' if all_ok else 'NG'}")

    # 連続負け
    mx, wl, c3, c5 = streak(pnls_is)
    print(f"\n  連続負け（IS）: 最大{mx}連敗  最悪損失{wl:,.0f}円({wl/CAPITAL*100:.1f}%)")
    print(f"  3連敗以上:{c3}回  5連敗以上:{c5}回")

    return m_is, m_oos, all_ok


# 5分足ベースライン
print("5分足ベースライン（比較用）")
df5_is  = df5.loc[IS_START:IS_END];  sd5_is  = sd5.reindex(df5_is.index)
df5_oos = df5.loc[OOS_START:OOS_END]; sd5_oos = sd5.reindex(df5_oos.index)
m5is  = met(bt(make_sig(df5_is,  sd5_is,  12, 10), 5))
m5oos = met(bt(make_sig(df5_oos, sd5_oos, 12, 10), 5))

results_all = {"5min": (m5is, m5oos, True)}
for tf_label, cfg in GRIDS.items():
    m_is, m_oos, ok = run_tf(tf_label, cfg)
    results_all[tf_label] = (m_is, m_oos, ok)

# 最終比較表
print(f"\n{'='*72}")
print("  全TF比較サマリー（5min含む）")
print(f"{'='*72}")
print(f"  {'TF':>5} | {'IS件数':>6} {'IS PF':>6} {'IS損益':>8} {'IS DD':>7} | "
      f"{'OOS件数':>7} {'OOS PF':>7} {'OOS損益':>9} {'OOS DD':>8} | {'採否':>4}")
print("  " + "-"*85)
for tf, (mi, mo, ok) in results_all.items():
    mark = "★採用" if tf=="5min" else ("OK" if ok else "NG")
    print(f"  {tf:>5} | {mi['n']:>6,} {mi['pf']:>6.2f} {mi['jpy']/10000:>+8.1f}万 "
          f"{mi['dd']:>+7.2f}% | {mo['n']:>7,} {mo['pf']:>7.2f} "
          f"{mo['jpy']/10000:>+9.1f}万 {mo['dd']:>+8.2f}% | {mark}")
print("="*72)
