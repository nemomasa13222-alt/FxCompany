# -*- coding: utf-8 -*-
"""
パラメータサーベイ: 通貨強弱差閾値 × 自己相関係数閾値
IS期間のみ（2022-01-01 ～ 2023-12-31）で評価
取引コスト: DMM FXスプレッド（往復）込み
実行: python _run_param_survey_cost.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
PB_PATH  = ROOT / "docs" / "strategy_judgment" / "playbook.csv"
OUT_DIR  = ROOT / "docs" / "param_survey"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START = "2022-01-01"; IS_END = "2023-12-31"

STRENGTH_WINDOW = 24; AC_WINDOW = 12
MAX_HOLD = 48
CAPITAL  = 1_000_000; RISK_PCT = 0.005
PIP_SIZE_JPY = 0.01;  PIP_VAL_JPY = 100
PIP_SIZE_USD = 0.0001; PIP_VAL_USD = 1000
JST = pd.Timedelta(hours=9)

# ── サーベイグリッド ──
Q_EXTREME_VALS = [0.04, 0.05, 0.07, 0.10]    # 通貨強弱差の下位分位点
AC_MIN_VALS    = [0.00, 0.05, 0.10, 0.15, 0.20]  # 自己相関係数の最低絶対値

SESSIONS = [
    ("東京\n09-15JST",  9, 15),
    ("欧州\n15-21JST", 15, 21),
    ("NY\n21-03JST",   21,  3),
    ("深夜\n03-09JST",  3,  9),
]
PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
JPY_PAIRS  = {p for p,(b,q) in PAIR_CURRENCIES.items() if q=="JPY"}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

SPREADS = {
    "USDJPY":0.2,"EURJPY":0.5,"GBPJPY":0.9,
    "AUDJPY":0.6,"NZDJPY":1.7,"CHFJPY":2.2,
    "GBPUSD":0.9,"AUDUSD":0.6,"NZDUSD":1.3,
    "EURGBP":0.8,"EURAUD":1.5,"AUDNZD":2.2,
}

# ════════════════════════════════════════════════
# データ読込（IS期間のみ）
# ════════════════════════════════════════════════
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    # IS期間に限定
    df = df[(df.index >= IS_START) & (df.index <= IS_END)]
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
print(f"IS期間バー数: {len(common_idx):,}  ({common_idx.min()} -> {common_idx.max()})")

# 通貨強弱（全IS期間で計算）
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    r = pair_lr[pair]
    raw_str[b] += r; raw_str[q] -= r
    cnt[b] += 1;     cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)

# セッション
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# 自己相関
print("自己相関算出中...")
ac_dict = {}
for pair,df in dfs.items():
    ret = np.log(df["Close"]/df["Close"].shift(1))
    arr = ret.values; res = np.full(len(arr), np.nan)
    for i in range(AC_WINDOW-1, len(arr)):
        x = arr[i-AC_WINDOW+1:i+1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-1], x[1:]); res[i] = c[0,1]
    ac_dict[pair] = pd.Series(res, index=common_idx)

# ATR事前計算
print("ATR事前計算中...")
atr_dict = {}
for pair,df in dfs.items():
    hi,lo,cl = df["High"],df["Low"],df["Close"].shift(1)
    tr = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr_dict[pair] = tr.rolling(14).mean()

# ブレイクダウン判定
bd_dict = {pair: (dfs[pair]["Low"] < dfs[pair]["Low"].shift(1))
           for pair in dfs}

# プレイブック読込
df_pb = pd.read_csv(PB_PATH, encoding="utf-8-sig") if PB_PATH.exists() else pd.DataFrame()

def get_pip(pair):
    if pair in JPY_PAIRS: return PIP_SIZE_JPY, PIP_VAL_JPY
    return PIP_SIZE_USD, PIP_VAL_USD

def run_bt_fast(pair, direction, mask):
    """マスクに基づく高速バックテスト（ATR・スプレッドコスト込み）"""
    df_p = dfs[pair]
    atr  = atr_dict[pair]
    pip_sz, pip_val = get_pip(pair)
    spread_pips = SPREADS.get(pair, 1.0)
    positions = np.where(mask.values)[0]
    pnls = []
    for sp in positions:
        ep = sp+1
        if ep >= len(df_p): continue
        entry_p = df_p["Open"].iloc[ep]
        atr_val = atr.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_pips = atr_val / pip_sz
        if sl_pips <= 0: continue
        lot = (CAPITAL * RISK_PCT) / (sl_pips * pip_val)
        spread_cost = spread_pips * pip_val * lot
        if direction == "short":
            best=entry_p; trail=entry_p+atr_val; exit_p=None; held=0
            for h in range(1, MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_p): break
                bh=df_p["High"].iloc[bp]; bl=df_p["Low"].iloc[bp]; held=h
                if bh>=trail: exit_p=trail; break
                if bl<best: best=bl; trail=min(trail,best+atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_p): exit_p=df_p["Close"].iloc[fp]
                else: continue
            pnls.append((entry_p-exit_p)/pip_sz*pip_val*lot - spread_cost)
        else:
            best=entry_p; trail=entry_p-atr_val; exit_p=None; held=0
            for h in range(1, MAX_HOLD+1):
                bp=ep+h
                if bp>=len(df_p): break
                bh=df_p["High"].iloc[bp]; bl=df_p["Low"].iloc[bp]; held=h
                if bl<=trail: exit_p=trail; break
                if bh>best: best=bh; trail=max(trail,best-atr_val)
            if exit_p is None:
                fp=ep+held
                if fp<len(df_p): exit_p=df_p["Close"].iloc[fp]
                else: continue
            pnls.append((exit_p-entry_p)/pip_sz*pip_val*lot - spread_cost)
    return np.array(pnls)

def calc_stats(pnls):
    if len(pnls) == 0:
        return dict(n=0, win_rate=0.0, pf=float("nan"),
                    total_pnl=0.0, max_dd=0.0, dd_pct=0.0)
    wins = pnls[pnls>0]; loss = pnls[pnls<=0]
    gp = wins.sum(); gl = np.abs(loss).sum()
    pf = gp/gl if gl>0 else (float("inf") if gp>0 else float("nan"))
    cum = np.cumsum(pnls)
    dd  = float((np.maximum.accumulate(cum)-cum).max())
    return dict(n=len(pnls),
                win_rate=len(wins)/len(pnls)*100,
                pf=round(pf,4),
                total_pnl=round(float(pnls.sum())/10000,2),
                max_dd=round(dd/10000,2),
                dd_pct=round(dd/CAPITAL*100,2))

# ════════════════════════════════════════════════
# サーベイ実行
# ════════════════════════════════════════════════
total_runs = len(Q_EXTREME_VALS) * len(AC_MIN_VALS)
run_idx = 0
survey_rows = []

print(f"\nサーベイ開始: {total_runs}条件")
print("="*70)

for q_ext in Q_EXTREME_VALS:
    # 通貨強弱差の分位点（IS全期間）
    q_thresh = {pair: (str_df[bc]-str_df[qc]).quantile(q_ext)
                for pair,(bc,qc) in PAIR_CURRENCIES.items() if pair in dfs}

    for ac_min in AC_MIN_VALS:
        run_idx += 1
        all_pnls = []

        for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
            if pair not in dfs: continue
            diff = str_df[base_c] - str_df[quote_c]
            qt   = q_thresh[pair]
            ac   = ac_dict[pair]
            bd   = bd_dict[pair]

            if len(df_pb):
                df_pb_tmp = df_pb.copy()
                df_pb_tmp["session_clean"] = df_pb_tmp["session"].str.replace("\n"," ").str.strip()
            else:
                df_pb_tmp = pd.DataFrame()

            for sname,s,e in SESSIONS:
                sm = sess_s == sname
                if len(df_pb_tmp):
                    sname_clean = sname.replace("\n"," ").strip()
                    pb_row = df_pb_tmp[(df_pb_tmp["pair"]==pair) &
                                      (df_pb_tmp["session_clean"]==sname_clean)]
                else:
                    pb_row = pd.DataFrame()

                if len(pb_row):
                    jdg = pb_row["judge"].values[0]
                    flt = pb_row["filter"].values[0]
                else:
                    jdg = "─"; flt = "─"

                if "SHORT" in jdg:
                    direction = "short"
                    if "ac>0" in flt:
                        mask = bd & (diff<=qt) & (ac>ac_min) & ac.notna() & sm
                    else:
                        mask = bd & (diff<=qt) & sm
                elif "LONG" in jdg:
                    direction = "long"
                    if "ac<0" in flt:
                        mask = bd & (diff<=qt) & (ac<-ac_min) & ac.notna() & sm
                    else:
                        mask = bd & (diff<=qt) & sm
                else:
                    continue

                pnls = run_bt_fast(pair, direction, mask)
                if len(pnls): all_pnls.append(pnls)

        pnl_all = np.concatenate(all_pnls) if all_pnls else np.array([])
        st = calc_stats(pnl_all)

        row = {"q_ext": q_ext, "ac_min": ac_min, **st}
        survey_rows.append(row)

        flag = " ★PF>1" if st["pf"] > 1.0 else ""
        print(f"[{run_idx:2d}/{total_runs}] q={q_ext:.2f} ac>={ac_min:.2f} | "
              f"n={st['n']:5d} 勝率={st['win_rate']:5.1f}% "
              f"PF={st['pf']:6.3f} 損益={st['total_pnl']:+7.1f}万 "
              f"DD={st['dd_pct']:5.1f}%{flag}")

print("="*70)

df_survey = pd.DataFrame(survey_rows)
out_csv = OUT_DIR / "param_survey_is.csv"
df_survey.to_csv(out_csv, index=False, encoding="utf-8-sig")
print(f"\nCSV保存: {out_csv}")

# ── PF>1.0 の条件を抽出して表示
good = df_survey[df_survey["pf"] > 1.0].sort_values("pf", ascending=False)
if len(good):
    print(f"\n★ IS期間 PF>1.0 の条件 ({len(good)}件)")
    print(f"{'q_ext':>6} {'ac_min':>7} {'n':>6} {'勝率':>6} {'PF':>7} {'損益(万)':>9} {'DD%':>6}")
    print("-"*55)
    for _,r in good.iterrows():
        print(f"{r['q_ext']:6.2f} {r['ac_min']:7.2f} {r['n']:6.0f} "
              f"{r['win_rate']:6.1f} {r['pf']:7.3f} {r['total_pnl']:+9.1f} {r['dd_pct']:6.1f}")
else:
    print("\n★ IS期間でPF>1.0の条件は見つかりませんでした。")
    best = df_survey.sort_values("pf", ascending=False).head(5)
    print("上位5条件（PF順）:")
    print(f"{'q_ext':>6} {'ac_min':>7} {'n':>6} {'PF':>7} {'損益(万)':>9}")
    for _,r in best.iterrows():
        print(f"{r['q_ext']:6.2f} {r['ac_min']:7.2f} {r['n']:6.0f} {r['pf']:7.3f} {r['total_pnl']:+9.1f}")

print("\n完了")
