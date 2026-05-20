# -*- coding: utf-8 -*-
"""
USD/JPY デュアルシステム  OOS開封（2024年）
────────────────────────────────────────────────────────────
IS期間: 2022-01-01 〜 2023-12-31  （参照）
OOS期間: 2024-01-01 〜 2024-12-31  ← ここで初めて開封

採用パラメータ（IS確定値）:
  強弱窓: 24本 / Q閾値: 10% / ATR: 14 / ac窓: 12
  戦略A（SHORT）: NY 21-03JST / ac > 0.15
  戦略B（LONG） : 東京 09-15JST / ac < 0.00
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats
from pathlib import Path

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "usdjpy_dual"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START  = "2022-01-01"; IS_END   = "2023-12-31"
OOS_START = "2024-01-01"; OOS_END  = "2024-12-31"
STRENGTH_WINDOW = 24; Q_THRESHOLD = 0.10
JST       = pd.Timedelta(hours=9)
CAPITAL   = 1_000_000; RISK_PCT = 0.005
PIP_VALUE = 100; PIP_SIZE = 0.01
ATR_PERIOD = 14; MAX_HOLD = 48; AC_WINDOW = 12
AC_A_THR = 0.15; AC_B_THR = 0.00

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"),"EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"),"AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"),"CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"),"AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"),"EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"),"AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

SESSIONS_ALL = [
    ("東京 09-15JST",  9, 15, "#f39c12"),
    ("欧州 15-21JST", 15, 21, "#27ae60"),
    ("NY   21-03JST", 21,  3, "#2980b9"),
    ("深夜 03-09JST",  3,  9, "#8e44ad"),
]

# ── データ読込 ──────────────────────────────────────────────
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
usdjpy = dfs["USDJPY"].copy()
print(f"  データ範囲: {common_idx[0].date()} 〜 {common_idx[-1].date()}")

is_idx  = (common_idx >= IS_START)  & (common_idx <= IS_END)
oos_idx = (common_idx >= OOS_START) & (common_idx <= OOS_END)
print(f"  IS : {is_idx.sum():,}本 / OOS: {oos_idx.sum():,}本")

# ── 共通計算 ────────────────────────────────────────────────
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]; raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]

strength_diff = pd.DataFrame(raw_str)["USD"] - pd.DataFrame(raw_str)["JPY"]
q10 = strength_diff.quantile(Q_THRESHOLD)

hi,lo,cl = usdjpy["High"],usdjpy["Low"],usdjpy["Close"].shift(1)
tr  = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
atr = tr.rolling(ATR_PERIOD).mean()

ret = np.log(usdjpy["Close"]/usdjpy["Close"].shift(1))
def rolling_ac(series, w):
    arr=series.values; res=np.full(len(arr),np.nan)
    for i in range(w-1,len(arr)):
        x=arr[i-w+1:i+1]
        if np.any(np.isnan(x)): continue
        c=np.corrcoef(x[:-1],x[1:]); res[i]=c[0,1]
    return pd.Series(res, index=series.index)
ac = rolling_ac(ret, AC_WINDOW)

jst_hour = (common_idx + JST).hour
def in_sess(h,s,e):
    if s < e: return (h>=s)&(h<e)
    return (h>=s)|(h<e)

h_s = pd.Series(jst_hour, index=common_idx)
sess_NY    = in_sess(h_s, 21, 3)
sess_Tokyo = in_sess(h_s,  9, 15)
sess_map   = {s[0]: in_sess(h_s, s[1], s[2]) for s in SESSIONS_ALL}

breakdown = (usdjpy["Low"] < usdjpy["Low"].shift(1)) & (strength_diff <= q10) & strength_diff.notna()

# ── バックテスト ─────────────────────────────────────────────
def run_bt(mask, direction):
    pos = np.where(mask)[0]; records = []
    for sp in pos:
        ep = sp+1
        if ep >= len(usdjpy): continue
        ep_bar = usdjpy.index[ep]
        entry  = usdjpy["Open"].iloc[ep]
        av     = atr.iloc[sp]
        if av<=0 or np.isnan(av): continue
        sl_pips= av/PIP_SIZE
        if sl_pips<=0: continue
        lot    = (CAPITAL*RISK_PCT)/(sl_pips*PIP_VALUE)

        if direction=="short":
            best=entry; trail=entry+av; exit_p=None; held=0
            for h in range(1,MAX_HOLD+1):
                bp=ep+h
                if bp>=len(usdjpy): break
                bh=usdjpy["High"].iloc[bp]; bl=usdjpy["Low"].iloc[bp]; held=h
                if bh>=trail: exit_p=trail; break
                if bl<best: best=bl; trail=min(trail,best+av)
            if exit_p is None:
                fp=ep+held
                if fp<len(usdjpy): exit_p=usdjpy["Close"].iloc[fp]
                else: continue
            pnl=(entry-exit_p)/PIP_SIZE*PIP_VALUE*lot
        else:
            best=entry; trail=entry-av; exit_p=None; held=0
            for h in range(1,MAX_HOLD+1):
                bp=ep+h
                if bp>=len(usdjpy): break
                bh=usdjpy["High"].iloc[bp]; bl=usdjpy["Low"].iloc[bp]; held=h
                if bl<=trail: exit_p=trail; break
                if bh>best: best=bh; trail=max(trail,best-av)
            if exit_p is None:
                fp=ep+held
                if fp<len(usdjpy): exit_p=usdjpy["Close"].iloc[fp]
                else: continue
            pnl=(exit_p-entry)/PIP_SIZE*PIP_VALUE*lot

        sig_bar = usdjpy.index[sp]
        r_mult  = pnl/(CAPITAL*RISK_PCT)
        sess    = next((s for s,m in sess_map.items() if m.iloc[sp]), "不明")
        records.append({
            "signal_bar":sig_bar,"entry_bar":ep_bar,
            "entry_price":entry,"exit_price":exit_p,
            "pnl_yen":pnl,"r_mult":r_mult,"hold_bars":held,
            "direction":direction,"session":sess,
            "jst_hour":(sig_bar+JST).hour,
            "month":(sig_bar+JST).to_period("M"),
        })
    return pd.DataFrame(records)

def summarize(df):
    if len(df)==0: return {}
    from scipy import stats as sc
    wins=df[df["pnl_yen"]>0]; losses=df[df["pnl_yen"]<=0]
    gp=wins["pnl_yen"].sum(); gl=losses["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=df["pnl_yen"].cumsum()
    return {"n":len(df),"win_rate":len(wins)/len(df)*100,
            "pf":pf,"total_pnl":df["pnl_yen"].sum(),
            "avg_r":df["r_mult"].mean(),"skew_r":sc.skew(df["r_mult"]),
            "max_dd":(cum.cummax()-cum).max(),
            "max_dd_pct":(cum.cummax()-cum).max()/CAPITAL*100}

# IS & OOS 両方実行
print("バックテスト実行中...")
for period, idx in [("IS", is_idx), ("OOS", oos_idx)]:
    sig_A = breakdown & idx & sess_NY    & (ac > AC_A_THR) & ac.notna()
    sig_B = breakdown & idx & sess_Tokyo & (ac < AC_B_THR) & ac.notna()
    df_A  = run_bt(sig_A, "short")
    df_B  = run_bt(sig_B, "long")
    df_C  = pd.concat([df_A, df_B], ignore_index=True)
    df_A["strategy"] = "戦略A 順張りショート"
    df_B["strategy"] = "戦略B 逆張りロング"
    df_C["strategy"] = df_A["strategy"].tolist() + df_B["strategy"].tolist()
    df_C.sort_values("signal_bar", inplace=True)
    df_C.to_csv(OUT_DIR/f"trades_{period.lower()}.csv",
                index=False, encoding="utf-8-sig")
    if period == "IS":
        df_A_is, df_B_is, df_C_is = df_A, df_B, df_C
    else:
        df_A_oos, df_B_oos, df_C_oos = df_A, df_B, df_C
    print(f"  {period}: A={len(df_A)}件 B={len(df_B)}件")

# ── コンソール出力 ───────────────────────────────────────────
sv_is  = {k: summarize(df) for k,df in [("A",df_A_is),("B",df_B_is),("C",df_C_is)]}
sv_oos = {k: summarize(df) for k,df in [("A",df_A_oos),("B",df_B_oos),("C",df_C_oos)]}

print("\n" + "="*75)
print("  IS vs OOS 比較")
print("="*75)
print(f"\n  {'':26s}  {'IS(22-23)':>8s}  {'OOS(24)':>8s}  {'乖離':>7s}")
print("-"*55)
metrics = [
    ("n（件数）",       "n",           "{:,.0f}",  None),
    ("勝率 (%)",        "win_rate",    "{:.1f}",   None),
    ("PF",              "pf",          "{:.2f}",   None),
    ("総損益 (円)",     "total_pnl",   "{:+,.0f}", None),
    ("MaxDD (円)",      "max_dd",      "{:,.0f}",  None),
    ("MaxDD (%)",       "max_dd_pct",  "{:.1f}",   None),
    ("平均R",           "avg_r",       "{:+.4f}",  None),
]

for strat, key in [("統合A+B", "C"), ("戦略A ショート", "A"), ("戦略B ロング", "B")]:
    print(f"\n  【{strat}】")
    si = sv_is.get(key, {}); so = sv_oos.get(key, {})
    for label, mkey, fmt, _ in metrics:
        vi = si.get(mkey, 0); vo = so.get(mkey, 0)
        if mkey == "pf":
            drift = f"{vo-vi:+.2f}"
            marker = "OK" if vo >= 1.0 else "NG"
        elif mkey == "total_pnl":
            drift = f"{vo-vi:+,.0f}円"
            marker = "+" if vo > 0 else "-"
        else:
            drift = "-"
            marker = ""
        print(f"    {label:16s}  {fmt.format(vi):>10s}  {fmt.format(vo):>8s}  {drift:>9s} {marker}")

# セッション別OOS
print(f"\n  【OOS セッション別（A+B合計）】")
print(f"  {'セッション':18s}  {'n':>5s}  {'PF':>5s}  {'損益(円)':>10s}  {'DD%':>5s}")
print("-"*55)
for sess_name, *_ in SESSIONS_ALL:
    sub = df_C_oos[df_C_oos["session"]==sess_name]
    if len(sub) < 3: continue
    sv2 = summarize(sub)
    tag = "★" if sv2["pf"]>=1.2 else "  "
    print(f"  {tag}{sess_name:16s}  {sv2['n']:5,}  {sv2['pf']:5.2f}  "
          f"{sv2['total_pnl']:+10,.0f}  {sv2['max_dd_pct']:5.1f}")

# ── 可視化 ──────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 20))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("USD/JPY デュアルシステム  IS vs OOS 比較\n"
             "IS: 2022-2023（確認済み）  /  OOS: 2024（初回開封）",
             fontsize=13, fontweight="bold", y=0.99)
gs = fig.add_gridspec(3, 2, hspace=0.45, wspace=0.3)

C_IS  = "#2980b9"; C_OOS = "#e74c3c"
C_A   = "#3498db"; C_B   = "#e67e22"

# ① IS 累積P&L
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor("#f8f9fa")
ax1.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
for df_p, label, color in [(df_A_is,"戦略A ショート",C_A),(df_B_is,"戦略B ロング",C_B)]:
    sv2=summarize(df_p); cum=df_p["pnl_yen"].cumsum()
    ax1.plot(range(len(cum)), cum.values, color=color, lw=1.5, ls="--",
             label=f"{label} PF={sv2['pf']:.2f} {sv2['total_pnl']:+,.0f}円")
cum_c=df_C_is["pnl_yen"].cumsum(); sv2=summarize(df_C_is)
ax1.plot(range(len(cum_c)), cum_c.values, color=C_IS, lw=2.5,
         label=f"統合 PF={sv2['pf']:.2f} {sv2['total_pnl']:+,.0f}円")
ax1.set_title(f"IS期間 累積損益（2022-2023）", fontsize=10, fontweight="bold")
ax1.set_xlabel("トレード番号", fontsize=8); ax1.set_ylabel("累積損益 (円)", fontsize=8)
ax1.legend(fontsize=8, framealpha=0.9); ax1.grid(axis="y", alpha=0.3)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# ② OOS 累積P&L
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor("#f8f9fa")
ax2.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
for df_p, label, color in [(df_A_oos,"戦略A ショート",C_A),(df_B_oos,"戦略B ロング",C_B)]:
    if len(df_p)==0: continue
    sv2=summarize(df_p); cum=df_p["pnl_yen"].cumsum()
    ax2.plot(range(len(cum)), cum.values, color=color, lw=1.5, ls="--",
             label=f"{label} PF={sv2['pf']:.2f} {sv2['total_pnl']:+,.0f}円")
if len(df_C_oos):
    cum_c=df_C_oos["pnl_yen"].cumsum(); sv2=summarize(df_C_oos)
    ax2.plot(range(len(cum_c)), cum_c.values, color=C_OOS, lw=2.5,
             label=f"統合 PF={sv2['pf']:.2f} {sv2['total_pnl']:+,.0f}円")
ax2.set_title(f"OOS期間 累積損益（2024）← 初回開封", fontsize=10, fontweight="bold",
              color="#c0392b")
ax2.set_xlabel("トレード番号", fontsize=8); ax2.set_ylabel("累積損益 (円)", fontsize=8)
ax2.legend(fontsize=8, framealpha=0.9); ax2.grid(axis="y", alpha=0.3)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# ③ 月別損益（IS）
ax3 = fig.add_subplot(gs[1, 0])
ax3.set_facecolor("#f8f9fa"); ax3.axhline(0, color="#333", lw=0.8)
if len(df_C_is):
    monthly_is = df_C_is.groupby("month")["pnl_yen"].sum()
    bars = ax3.bar(range(len(monthly_is)), monthly_is.values,
                   color=["#2ecc71" if v>=0 else "#e74c3c" for v in monthly_is.values],
                   alpha=0.75, edgecolor="none")
    ax3.set_xticks(range(len(monthly_is)))
    ax3.set_xticklabels([str(m) for m in monthly_is.index], rotation=45, fontsize=7)
ax3.set_title("IS 月別損益", fontsize=10, fontweight="bold")
ax3.set_ylabel("損益 (円)", fontsize=8); ax3.grid(axis="y", alpha=0.3)
ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# ④ 月別損益（OOS）
ax4 = fig.add_subplot(gs[1, 1])
ax4.set_facecolor("#f8f9fa"); ax4.axhline(0, color="#333", lw=0.8)
if len(df_C_oos):
    monthly_oos = df_C_oos.groupby("month")["pnl_yen"].sum()
    ax4.bar(range(len(monthly_oos)), monthly_oos.values,
            color=["#2ecc71" if v>=0 else "#e74c3c" for v in monthly_oos.values],
            alpha=0.75, edgecolor="none")
    ax4.set_xticks(range(len(monthly_oos)))
    ax4.set_xticklabels([str(m) for m in monthly_oos.index], rotation=45, fontsize=7)
ax4.set_title("OOS 月別損益（2024）", fontsize=10, fontweight="bold", color="#c0392b")
ax4.set_ylabel("損益 (円)", fontsize=8); ax4.grid(axis="y", alpha=0.3)
ax4.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# ⑤ PF比較バー（IS vs OOS）
ax5 = fig.add_subplot(gs[2, 0])
ax5.set_facecolor("#f8f9fa")
ax5.axhline(1.0, color="#e74c3c", lw=1.2, ls="--", alpha=0.7, label="PF=1.0")
labels5 = ["統合A+B", "戦略A\nショート", "戦略B\nロング"]
pf_is  = [sv_is["C"].get("pf",0),  sv_is["A"].get("pf",0),  sv_is["B"].get("pf",0)]
pf_oos = [sv_oos["C"].get("pf",0), sv_oos["A"].get("pf",0), sv_oos["B"].get("pf",0)]
x = np.arange(len(labels5)); w=0.35
b1=ax5.bar(x-w/2, pf_is,  w, color=C_IS,  alpha=0.8, label="IS 2022-23")
b2=ax5.bar(x+w/2, pf_oos, w, color=C_OOS, alpha=0.8, label="OOS 2024")
for bar in list(b1)+list(b2):
    h=bar.get_height()
    ax5.text(bar.get_x()+bar.get_width()/2, h+0.01, f"{h:.2f}",
             ha="center", va="bottom", fontsize=9, fontweight="bold")
ax5.set_title("PF比較  IS vs OOS", fontsize=10, fontweight="bold")
ax5.set_xticks(x); ax5.set_xticklabels(labels5, fontsize=9)
ax5.set_ylabel("Profit Factor", fontsize=9); ax5.legend(fontsize=9)
ax5.set_ylim(0, max(pf_is+pf_oos)*1.25); ax5.grid(axis="y", alpha=0.3)

# ⑥ R分布比較（統合）
ax6 = fig.add_subplot(gs[2, 1])
ax6.set_facecolor("#f8f9fa")
ax6.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6)
for df_p, label, color, alpha in [
    (df_C_is,  "IS 2022-23", C_IS,  0.5),
    (df_C_oos, "OOS 2024",   C_OOS, 0.7),
]:
    if len(df_p)==0: continue
    r = df_p["r_mult"]; lo,hi=np.percentile(r,[1,99])
    ax6.hist(r.clip(lo,hi), bins=60, density=True,
             color=color, alpha=alpha, edgecolor="none",
             label=f"{label}  μ={r.mean():+.4f}R  n={len(r)}")
    try:
        kde=stats.gaussian_kde(r.clip(lo,hi),bw_method=0.3)
        xs=np.linspace(lo,hi,300); ax6.plot(xs,kde(xs),color=color,lw=2.0)
    except: pass
ax6.set_title("R倍率分布比較", fontsize=10, fontweight="bold")
ax6.set_xlabel("R倍率 (1R=資金0.5%)", fontsize=8)
ax6.set_ylabel("確率密度", fontsize=8)
ax6.legend(fontsize=9, framealpha=0.9); ax6.grid(axis="y", alpha=0.3)

plt.savefig(OUT_DIR/"oos_comparison.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終判定 ────────────────────────────────────────────────
sv_oos_C = sv_oos["C"]
pf_oos_v   = sv_oos_C.get("pf",0)
dd_oos_v   = sv_oos_C.get("max_dd_pct",99)
pnl_oos_v  = sv_oos_C.get("total_pnl",0)
pf_drift   = pf_oos_v - sv_is["C"].get("pf",0)

print("\n" + "="*65)
print("  OOS 最終判定")
print("="*65)
verdict_items = [
    ("OOS黒字",     pnl_oos_v > 0,      f"損益 {pnl_oos_v:+,.0f}円"),
    ("OOS PF≥1.0",  pf_oos_v >= 1.0,    f"PF {pf_oos_v:.2f}"),
    ("DD≤25%",      dd_oos_v <= 25,     f"MaxDD {dd_oos_v:.1f}%"),
    ("PF乖離≤0.3",  abs(pf_drift)<=0.3, f"乖離 {pf_drift:+.2f}"),
]
ok_count = 0
for label, ok, detail in verdict_items:
    mark = "OK" if ok else "NG"
    ok_count += int(ok)
    print(f"  {mark}  {label:16s}  {detail}")

overall = "合格" if ok_count == 4 else "条件付き合格" if ok_count >= 3 else "要再検討"
print(f"\n  総合: {ok_count}/4 項目  →  {overall}")
print(f"\n保存先: {OUT_DIR}")
print("完了")
