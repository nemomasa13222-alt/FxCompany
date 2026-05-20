# -*- coding: utf-8 -*-
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

df = pd.read_csv("docs/eurjpy/bt_eurjpy.csv", encoding="utf-8-sig")
df["signal_bar"] = pd.to_datetime(df["signal_bar"])
df["session"] = df["session"].str.strip()
IS_END = "2023-12-31"
df["period"] = df["signal_bar"].apply(lambda x: "IS" if x <= pd.Timestamp(IS_END) else "OOS")
CAP = 1_000_000

def stats(d, label=""):
    if len(d)==0:
        print(f"  {label:<30} n=   0 (データなし)")
        return
    w = d[d["pnl_yen"]>0]; l = d[d["pnl_yen"]<=0]
    g = w["pnl_yen"].sum(); lo = l["pnl_yen"].abs().sum()
    pf = g/lo if lo>0 else float("inf")
    cum = d["pnl_yen"].cumsum()
    dd = (cum.cummax()-cum).max()/CAP*100
    exp = d["pnl_yen"].mean()
    print(f"  {label:<30} n={len(d):4d} WR={len(w)/len(d)*100:5.1f}%"
          f" PF={pf:6.3f} PnL={d['pnl_yen'].sum()/10000:+7.1f}man DD={dd:5.1f}%"
          f" Exp={exp:+.0f}yen")

print("=== Session x Period ===")
for sess in sorted(df["session"].unique()):
    for period in ["IS","OOS"]:
        d = df[(df["session"]==sess)&(df["period"]==period)]
        stats(d, f"{sess[:12]} {period}")
    print()

print("=== 欧州ONLY ===")
for period in ["IS","OOS"]:
    d = df[(df["session"].str.contains("欧州"))&(df["period"]==period)]
    stats(d, f"欧州only {period}")

print()
print("=== NY ONLY ===")
for period in ["IS","OOS"]:
    d = df[(df["session"].str.contains("NY"))&(df["period"]==period)]
    stats(d, f"NY only {period}")

print()
print("=== 欧州+NY 合計 ===")
for period in ["IS","OOS"]:
    d = df[df["period"]==period]
    stats(d, f"合計 {period}")
