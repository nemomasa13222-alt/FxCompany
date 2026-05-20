# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from fx_market_classifier.lead_lag import LeadLagConfig, LeadLagEngine
import pandas as pd

pairs = ["USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
         "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD"]
price_data = {}
for p in pairs:
    df = pd.read_parquet(f"data/dukascopy/{p}_5min.parquet")
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    price_data[p] = df.loc["2022-01-01":"2022-01-31"]

cfg_inc = LeadLagConfig(exclude_self=False, spread_window=6, entry_threshold=0.001,
                        exit_ratio=0.5, stop_dist_pct=1.0, use_case_a=False, use_realistic_cost=True)
cfg_exc = LeadLagConfig(exclude_self=True,  spread_window=6, entry_threshold=0.001,
                        exit_ratio=0.5, stop_dist_pct=1.0, use_case_a=False, use_realistic_cost=True)

eng_inc = LeadLagEngine(price_data, cfg_inc)
eng_exc = LeadLagEngine(price_data, cfg_exc)

print("=== synthetic_ret の差（自己参照除去確認）===")
for p in pairs:
    diff = (eng_inc.synthetic_ret[p] - eng_exc.synthetic_ret[p]).dropna()
    changed = (diff.abs() > 1e-10).sum()
    print(f"  {p}: {changed}バーで差あり")

m_inc = eng_inc.metrics()
m_exc = eng_exc.metrics()
print()
print(f"Include-Self: T={m_inc.get('trades',0)}  PF={m_inc.get('pf',0):.3f}")
print(f"Exclude-Self: T={m_exc.get('trades',0)}  PF={m_exc.get('pf',0):.3f}")
print("OK")
