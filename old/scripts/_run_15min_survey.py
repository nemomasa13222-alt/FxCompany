"""15分足 ISサーベイ + OOS開封 + 5分足比較"""
import numpy as np
import pandas as pd
import itertools
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR  = Path("data/dukascopy")
PIP       = 0.01
ENTRY_COST= 0.2
SW        = 20
IS_START  = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START = "2024-01-01"; OOS_END   = "2025-01-01"
CAPITAL   = 1_000_000;    PIP_VAL   = 667

# データ準備
dfs5 = {p: pd.read_parquet(DATA_DIR/f"{p}_5min.parquet")
        for p in PAIRS if (DATA_DIR/f"{p}_5min.parquet").exists()}
rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
st   = currency_strength(rd)
sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())

df5  = dfs5["USDJPY"]
df15 = df5.resample("15min", label="left", closed="left").agg(
    Open=("Open","first"), High=("High","max"),
    Low=("Low","min"),   Close=("Close","last"), Volume=("Volume","sum")
).dropna(subset=["Open"])
sd15 = sd5.resample("15min", label="left", closed="left").last().reindex(df15.index)


def make_sig(df, sd, rb, rp):
    c = df["Close"]
    rh = c.shift(1).rolling(rb).max()
    rl = c.shift(1).rolling(rb).min()
    ir = (rh - rl) <= rp * PIP
    s  = sd.reindex(df.index)
    return pd.DataFrame({"c": c, "o": df["Open"],
                         "ls": ir & (c > rh) & (s > 0),
                         "ss": ir & (c < rl) & (s < 0),
                         "rm": (rh + rl) / 2})


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
    if len(pnls) == 0:
        return dict(n=0, wr=0, pf=0, jpy=0, dd=0)
    w = pnls[pnls>0]; l = pnls[pnls<=0]
    pf = w.sum()/abs(l.sum()) if l.sum() != 0 else 99.0
    eq = np.cumsum(pnls)
    pk = np.maximum.accumulate(np.maximum(eq, 0))
    dd = (eq - pk).min() * PIP_VAL / CAPITAL * 100
    return dict(n=len(pnls), wr=len(w)/len(pnls)*100, pf=pf,
                jpy=pnls.sum()*PIP_VAL, dd=dd)


# ── IS サーベイ（15min） ───────────────────────────────────────────────────────
df_is15  = df15.loc[IS_START:IS_END]
sd_is15  = sd15.reindex(df_is15.index)
df_oos15 = df15.loc[OOS_START:OOS_END]
sd_oos15 = sd15.reindex(df_oos15.index)

print("=" * 62)
print(" 15分足 ISパラメータサーベイ（27通り）")
print(f" IS:{IS_START}~{IS_END} / コスト0.2pips / レバ10倍")
print("=" * 62)
print(f"  {'bars':>4} {'pips':>4} {'hold':>4} | {'N':>5} {'WR%':>6} {'PF':>5} {'損益(万)':>9} {'DD%':>7}")
print("  " + "-" * 55)

results = []
for rb, rp, mh in itertools.product([4, 8, 12], [10, 15, 20], [2, 3, 5]):
    sig = make_sig(df_is15, sd_is15, rb, rp)
    m   = met(bt(sig, mh))
    results.append({"rb": rb, "rp": rp, "mh": mh, **m})

results.sort(key=lambda x: -x["pf"])
for r in results:
    mark = " <-- 採用候補" if r == results[0] else ""
    print(f"  {r['rb']:>4} {r['rp']:>4} {r['mh']:>4} | "
          f"{r['n']:>5} {r['wr']:>6.1f} {r['pf']:>5.2f} "
          f"{r['jpy']/10000:>+9.1f} {r['dd']:>+7.2f}%{mark}")


# ── OOS開封（ベストISパラメータ） ─────────────────────────────────────────────
best = results[0]
rb, rp, mh = best["rb"], best["rp"], best["mh"]
print(f"\nOOS開封: bars={rb}  pips={rp}  hold={mh}")

m_is  = met(bt(make_sig(df_is15,  sd_is15,  rb, rp), mh))
m_oos = met(bt(make_sig(df_oos15, sd_oos15, rb, rp), mh))
pf_diff = abs(m_is["pf"] - m_oos["pf"])

print(f"  IS : N={m_is['n']:,}  WR={m_is['wr']:.1f}%  PF={m_is['pf']:.2f}  "
      f"損益={m_is['jpy']/10000:+.1f}万  DD={m_is['dd']:+.2f}%")
print(f"  OOS: N={m_oos['n']:,}  WR={m_oos['wr']:.1f}%  PF={m_oos['pf']:.2f}  "
      f"損益={m_oos['jpy']/10000:+.1f}万  DD={m_oos['dd']:+.2f}%")
print(f"  PF乖離: {pf_diff:.2f}  (基準<=0.30)")

checks = [
    ("IS PF >= 1.30",         m_is["pf"] >= 1.30),
    ("OOS PF >= 1.10",        m_oos["pf"] >= 1.10),
    ("OOS 損益 > 0",          m_oos["jpy"] > 0),
    ("OOS DD <= IS×1.5",      abs(m_oos["dd"]) <= abs(m_is["dd"]) * 1.5),
    ("IS/OOS PF乖離 <= 0.30", pf_diff <= 0.30),
]
all_ok = all(ok for _, ok in checks)
print("\n  [採否判定]")
for label, ok in checks:
    print(f"    [{'OK' if ok else 'NG'}] {label}")
print(f"\n  --> {'採用' if all_ok else '不採用'}")


# ── 5分 vs 15分 並列比較 ──────────────────────────────────────────────────────
df_is5  = df5.loc[IS_START:IS_END];  sd_is5  = sd5.reindex(df_is5.index)
df_oos5 = df5.loc[OOS_START:OOS_END]; sd_oos5 = sd5.reindex(df_oos5.index)
m5is  = met(bt(make_sig(df_is5,  sd_is5,  12, 10), 5))
m5oos = met(bt(make_sig(df_oos5, sd_oos5, 12, 10), 5))

print("\n" + "=" * 72)
print("  5分足 vs 15分足 比較（各ベストパラメータ）")
print("=" * 72)
hdr = f"  {'TF':>5} | {'IS件数':>6} {'IS WR':>7} {'IS PF':>6} {'IS損益':>9} {'IS DD':>8} | {'OOS件数':>7} {'OOS WR':>7} {'OOS PF':>7} {'OOS損益':>9} {'OOS DD':>8}"
print(hdr)
print("  " + "-" * (len(hdr) - 2))

def row(label, mi, mo):
    return (f"  {label:>5} | {mi['n']:>6,} {mi['wr']:>7.1f}% {mi['pf']:>6.2f} "
            f"{mi['jpy']/10000:>+9.1f}万 {mi['dd']:>+8.2f}% | "
            f"{mo['n']:>7,} {mo['wr']:>7.1f}% {mo['pf']:>7.2f} "
            f"{mo['jpy']/10000:>+9.1f}万 {mo['dd']:>+8.2f}%")

print(row("5min★", m5is, m5oos))
print(row("15min", m_is, m_oos))

# 差分
print("\n  [差分: 15分 - 5分]")
for label, key, fmt in [
    ("PF (IS)",    "pf",  "+.2f"),
    ("PF (OOS)",   "pf",  "+.2f"),
    ("損益IS(万)", "jpy", "+.1f"),
    ("DD IS(%)",   "dd",  "+.2f"),
]:
    if "OOS" in label:
        diff = m_oos[key] - m5oos[key]
    elif "IS" in label and "損益" not in label:
        diff = m_is[key] - m5is[key]
    elif "損益IS" in label:
        diff = (m_is["jpy"] - m5is["jpy"]) / 10000
    else:
        diff = m_is[key] - m5is[key]
    sign = "+" if diff > 0 else ""
    print(f"    {label:<12}: {sign}{diff:{fmt}}")
print("=" * 72)
