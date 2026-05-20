# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

df = pd.read_csv("docs/crosslag/backtest_IS.csv")
cols = ["leader","follower","lag","corr","trades","win_rate","pf","total_pnl","max_dd","ev_bp"]

print(f"総結果: {len(df)}件  PF>=1.0: {(df.pf>=1.0).sum()}件  PF>=1.2: {(df.pf>=1.2).sum()}件")
print()
print("=== 上位15件（PF順）===")
print(df[cols].head(15).to_string(index=False))

print()
print("=== 市場状態別サマリー ===")
st = pd.read_csv("docs/crosslag/state_IS.csv")
print(st.groupby("state")[["pf","win_rate","trades"]].mean().round(3).to_string())

print()
print("=== Leader別 黒字件数 ===")
print(df[df.pf>=1.0].groupby("leader").size().sort_values(ascending=False).to_string())

print()
print("=== Follower別 黒字件数 ===")
print(df[df.pf>=1.0].groupby("follower").size().sort_values(ascending=False).to_string())
