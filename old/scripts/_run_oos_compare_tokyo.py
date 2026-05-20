# -*- coding: utf-8 -*-
"""
パート1: OOS比較  w=24/thr=0.0（保守的）vs w=12/thr=0.15（IS最良）
パート2: 東京時間（09-15JST）逆張りロング分析
         ブレイクダウン → 買い（価格が戻る仮説）
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
OUT1     = BASE / "docs" / "strength_break" / "oos_compare"
OUT2     = BASE / "docs" / "strength_break" / "tokyo_long"
OUT1.mkdir(parents=True, exist_ok=True)
OUT2.mkdir(parents=True, exist_ok=True)

# ── 定数 ────────────────────────────────────────────────────
IS_START  = "2022-01-01";  IS_END   = "2023-12-31"
OOS_START = "2024-01-01"; OOS_END  = "2024-12-31"
STRENGTH_WINDOW = 24;  Q_THRESHOLD = 0.10
JST = pd.Timedelta(hours=9)
CAPITAL = 1_000_000;  RISK_PCT = 0.005
PIP_VALUE = 100;      PIP_SIZE  = 0.01
ATR_PERIOD = 14;      MAX_HOLD  = 48
HORIZONS = [1, 3, 6, 12, 24]

SESSIONS = [
    ("東京 09-15JST",  9, 15, "#f39c12"),
    ("欧州 15-21JST", 15, 21, "#27ae60"),
    ("NY   21-03JST", 21,  3, "#2980b9"),
    ("深夜 03-09JST",  3,  9, "#8e44ad"),
]

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

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
for pair in dfs: common_idx = common_idx.intersection(dfs[pair].index)
for pair in dfs: dfs[pair] = dfs[pair].reindex(common_idx)
usdjpy = dfs["USDJPY"].copy()

# ── 共通計算 ────────────────────────────────────────────────
# 通貨強弱
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p, df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]; raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)
strength_diff = str_df["USD"] - str_df["JPY"]
q10 = strength_diff.quantile(0.10)
q90 = strength_diff.quantile(0.90)   # 逆張り用（USD強・JPY弱）

# ATR
hi, lo_s, cl_p = usdjpy["High"], usdjpy["Low"], usdjpy["Close"].shift(1)
tr  = pd.concat([hi-lo_s,(hi-cl_p).abs(),(lo_s-cl_p).abs()],axis=1).max(axis=1)
atr = tr.rolling(ATR_PERIOD).mean()

# 自己相関
returns = np.log(usdjpy["Close"]/usdjpy["Close"].shift(1))
def rolling_ac(series, window):
    arr = series.values
    res = np.full(len(arr), np.nan)
    for i in range(window-1, len(arr)):
        x = arr[i-window+1:i+1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-1], x[1:])
        res[i] = c[0,1]
    return pd.Series(res, index=series.index)

print("自己相関算出中...")
ac12 = rolling_ac(returns, 12)
ac24 = rolling_ac(returns, 24)

# セッション
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e,_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return "深夜 03-09JST"
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# 期間マスク
is_mask  = (common_idx >= IS_START)  & (common_idx <= IS_END)
oos_mask = (common_idx >= OOS_START) & (common_idx <= OOS_END)

# ── バックテスト関数 ─────────────────────────────────────────
def run_bt(mask, direction="short"):
    """direction: 'short' or 'long'"""
    pos_list = np.where(mask)[0]
    records = []
    for sp in pos_list:
        ep = sp + 1
        if ep >= len(usdjpy): continue
        entry_bar   = usdjpy.index[ep]
        entry_price = usdjpy["Open"].iloc[ep]
        atr_val     = atr.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_dist  = atr_val
        sl_pips  = sl_dist / PIP_SIZE
        if sl_pips <= 0: continue
        lot_size = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

        if direction == "short":
            sl_price  = entry_price + sl_dist
            best_ext  = entry_price   # 最安値追跡
            trail     = sl_price
            exit_p    = None; reason = "time"; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep + h
                if bp >= len(usdjpy): break
                bh = usdjpy["High"].iloc[bp]
                bl = usdjpy["Low"].iloc[bp]
                held = h
                if bh >= trail: exit_p = trail; reason="stop"; break
                if bl < best_ext:
                    best_ext = bl
                    trail = min(trail, best_ext + sl_dist)
        else:  # long
            sl_price  = entry_price - sl_dist
            best_ext  = entry_price   # 最高値追跡
            trail     = sl_price
            exit_p    = None; reason = "time"; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep + h
                if bp >= len(usdjpy): break
                bh = usdjpy["High"].iloc[bp]
                bl = usdjpy["Low"].iloc[bp]
                held = h
                if bl <= trail: exit_p = trail; reason="stop"; break
                if bh > best_ext:
                    best_ext = bh
                    trail = max(trail, best_ext - sl_dist)

        if exit_p is None:
            fp = ep + held
            if fp >= len(usdjpy): continue
            exit_p = usdjpy["Close"].iloc[fp]; reason="time"

        if direction == "short":
            pnl_yen = (entry_price - exit_p) / PIP_SIZE * PIP_VALUE * lot_size
        else:
            pnl_yen = (exit_p - entry_price) / PIP_SIZE * PIP_VALUE * lot_size

        r_mult = pnl_yen / (CAPITAL * RISK_PCT)
        sig_bar = usdjpy.index[sp]
        records.append({
            "signal_bar": sig_bar, "entry_price": entry_price,
            "exit_price": exit_p,  "pnl_yen": pnl_yen,
            "r_mult": r_mult, "hold_bars": held, "exit_reason": reason,
            "session": sess_s.get(sig_bar,"不明"),
            "jst_hour": (sig_bar + JST).hour,
        })
    return pd.DataFrame(records)

def summarize(df):
    if len(df)==0: return {}
    wins=df[df["pnl_yen"]>0]; losses=df[df["pnl_yen"]<=0]
    gp=wins["pnl_yen"].sum(); gl=losses["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=df["pnl_yen"].cumsum()
    return {"n":len(df),"win_rate":len(wins)/len(df)*100,
            "pf":pf,"total_pnl":df["pnl_yen"].sum(),
            "avg_r":df["r_mult"].mean(),"skew_r":stats.skew(df["r_mult"]),
            "max_dd":(cum.cummax()-cum).max()}

# ════════════════════════════════════════════════════════════
# パート1: OOS比較
# ════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  パート1: OOS比較")
print("="*70)

breakdown = (usdjpy["Low"] < usdjpy["Low"].shift(1)) & strength_diff.notna()
base_short = breakdown & (strength_diff <= q10)

PARAMS = {
    "保守的 (w=24,thr>0.00)": (ac24, 0.00),
    "IS最良 (w=12,thr>0.15)": (ac12, 0.15),
}

oos_results = {}
for label, (ac_ser, thr) in PARAMS.items():
    sig_is  = base_short & is_mask  & (ac_ser > thr) & ac_ser.notna()
    sig_oos = base_short & oos_mask & (ac_ser > thr) & ac_ser.notna()
    df_is  = run_bt(sig_is,  "short")
    df_oos = run_bt(sig_oos, "short")
    oos_results[label] = {"IS": df_is, "OOS": df_oos}

    si = summarize(df_is); so = summarize(df_oos)
    print(f"\n  【{label}】")
    print(f"    IS : n={si.get('n',0):,}  PF={si.get('pf',0):.2f}  "
          f"損益={si.get('total_pnl',0):+,.0f}円  DD={si.get('max_dd',0):,.0f}円")
    print(f"    OOS: n={so.get('n',0):,}  PF={so.get('pf',0):.2f}  "
          f"損益={so.get('total_pnl',0):+,.0f}円  DD={so.get('max_dd',0):,.0f}円")

    print(f"    {'':5s}  {'セッション':16s}  IS_PF  OOS_PF  IS損益      OOS損益")
    for sname,*_ in SESSIONS:
        si2 = summarize(df_is[df_is["session"]==sname])
        so2 = summarize(df_oos[df_oos["session"]==sname])
        tag = "★" if si2.get("pf",0)>=1.2 and so2.get("pf",0)>=1.0 else "  "
        print(f"    {tag}  {sname:16s}  "
              f"{si2.get('pf',0):5.2f}  {so2.get('pf',0):5.2f}  "
              f"{si2.get('total_pnl',0):+10,.0f}  {so2.get('total_pnl',0):+10,.0f}")

# 図: IS vs OOS P&L 比較
fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("IS vs OOS 損益曲線比較  ─  パラメータ別 × セッション別",
             fontsize=13, fontweight="bold")

for row_axes, (label,(ac_ser,thr)) in zip([axes[0],axes[1]], PARAMS.items()):
    for ax, (period, mask_p) in zip(row_axes, [("IS",is_mask),("OOS",oos_mask)]):
        ax.set_facecolor("#f8f9fa")
        ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
        sig = base_short & mask_p & (ac_ser > thr) & ac_ser.notna()
        df_p = run_bt(sig, "short")
        sv = summarize(df_p)

        if len(df_p):
            cum = df_p["pnl_yen"].cumsum()
            ax.plot(range(len(cum)), cum.values, color="#2c3e50", lw=2.2,
                    label=f"全体 PF={sv.get('pf',0):.2f}  {sv.get('total_pnl',0):+,.0f}円")

        for sname,_,_,color in SESSIONS:
            sub = df_p[df_p["session"]==sname] if len(df_p) else pd.DataFrame()
            if len(sub)<5: continue
            cum_s = sub["pnl_yen"].cumsum()
            sv2 = summarize(sub)
            ax.plot(range(len(cum_s)), cum_s.values, color=color, lw=1.3, ls="--",
                    label=f"{sname.split()[0]} PF={sv2.get('pf',0):.2f}  {sv2.get('total_pnl',0):+,.0f}円")

        ax.set_title(f"{label}\n{period}", fontsize=9, fontweight="bold")
        ax.set_xlabel("トレード番号", fontsize=8)
        ax.set_ylabel("累積損益 (円)", fontsize=8)
        ax.legend(fontsize=7.5, framealpha=0.9)
        ax.grid(axis="y", alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

plt.tight_layout()
fig.savefig(OUT1/"oos_compare.png", dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)
print(f"\n  保存: {OUT1}/oos_compare.png")

# ════════════════════════════════════════════════════════════
# パート2: 東京時間 逆張りロング
# ════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  パート2: 東京時間 逆張りロング分析（IS期間）")
print("="*70)

tokyo_mask = (sess_s == "東京 09-15JST") & is_mask
breakdown_tokyo = breakdown & tokyo_mask

# 3パターンのフィルター比較
entry_price_s = usdjpy["Open"].shift(-1)
future_ret = {h: np.log(usdjpy["Close"].shift(-h) / entry_price_s) for h in HORIZONS}
# ロング目線: 正が利益 → r > 0 が望ましい

LONG_FILTERS = {
    "フィルターなし":              breakdown_tokyo & strength_diff.notna(),
    "USD弱/JPY強(Q10)":          breakdown_tokyo & (strength_diff <= q10),
    "USD強/JPY弱(Q90, 逆)":      breakdown_tokyo & (strength_diff >= q90),
}

print(f"\n  {'':22s} {'H':>4s}  {'Mean%':>9s}  {'Skew':>7s}  {'上昇率%':>7s}  {'n':>5s}")
print("-"*65)

long_summary = []
for fname, fmask in LONG_FILTERS.items():
    for h in HORIZONS:
        r = future_ret[h][fmask].dropna()
        if len(r) < 30: continue
        tag = "★" if r.mean() > 0 and stats.skew(r) > 0.3 else "  "
        print(f"  {tag}{fname:20s} {h:>3d}本  {r.mean()*100:+9.4f}  "
              f"{stats.skew(r):+7.3f}  {(r>0).mean()*100:>7.1f}  {len(r):5,}")
        long_summary.append({"filter":fname,"horizon":h,"n":len(r),
                              "mean":r.mean()*100,"skew":stats.skew(r),
                              "pos_rate":(r>0).mean()*100})
    print()

# 最良ロングフィルターを選定（6本後 Mean最大）
df_ls = pd.DataFrame(long_summary)
h6 = df_ls[df_ls["horizon"]==6].sort_values("mean", ascending=False)
best_long_filter = h6.iloc[0]["filter"]
print(f"  IS最良ロングフィルター（6本後 Mean最大）: {best_long_filter}")

# 自己相関フィルター（ロング用: 上げモメンタム = 下げ自己相関が負 → 反転狙い なので ac<閾値）
# もしくは: 短期の自己相関が負（反転しやすい） → -0.0以下でロング
# 東京でブレイクダウン後の反発 = 自己相関が負のほうが反転しやすい
print("\n  自己相関フィルター（逆方向）検討:")
print(f"  {'ac条件':18s} {'H':>4s}  {'Mean%':>9s}  {'Skew':>7s}  {'上昇率%':>7s}  {'n':>5s}")
print("-"*60)

best_long_mask = LONG_FILTERS[best_long_filter]
for ac_cond, ac_m in [
    ("ac12 < -0.05", ac12 < -0.05),
    ("ac12 < 0.00",  ac12 <  0.00),
    ("ac12 > 0.00",  ac12 >  0.00),
    ("ac12 > 0.10",  ac12 >  0.10),
]:
    fmask = best_long_mask & ac_m & ac12.notna()
    for h in [3, 6, 12]:
        r = future_ret[h][fmask].dropna()
        if len(r) < 30: continue
        tag = "★" if r.mean() > 0 and stats.skew(r) > 0.3 else "  "
        print(f"  {tag}{ac_cond:18s} {h:>3d}本  {r.mean()*100:+9.4f}  "
              f"{stats.skew(r):+7.3f}  {(r>0).mean()*100:>7.1f}  {len(r):5,}")
    print()

# 最良ロング設定でバックテスト（IS）
print("  バックテスト（東京逆張りロング）...")

# 最良フィルターを使用（自己相関なし・ありの2パターン）
long_configs = {}
base_long = LONG_FILTERS[best_long_filter]
long_configs["東京ロング（フィルターのみ）"]       = base_long
long_configs["東京ロング（+ac12<0.00）"] = base_long & (ac12 < 0.00) & ac12.notna()
long_configs["東京ロング（+ac12<-0.05）"] = base_long & (ac12 < -0.05) & ac12.notna()

print(f"\n  {'':30s} {'n':>5s}  {'勝率%':>6s}  {'PF':>5s}  {'損益(円)':>10s}  {'DD':>9s}")
print("-"*70)
best_long_dfs = {}
for clabel, cmask in long_configs.items():
    df_lt = run_bt(cmask, "long")
    sv = summarize(df_lt)
    if sv:
        tag = "★" if sv["pf"]>=1.2 else "  "
        print(f"  {tag}{clabel:28s} {sv['n']:5,}  {sv['win_rate']:6.1f}  "
              f"{sv['pf']:5.2f}  {sv['total_pnl']:+10,.0f}  {sv['max_dd']:9,.0f}")
        best_long_dfs[clabel] = df_lt
    else:
        print(f"    {clabel:28s}  データ不足")

# 図: 分布比較 + 損益曲線
fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("東京時間 逆張りロング分析  ─  IS期間（2022-2023）\n"
             "（ブレイクダウン後の反発を狙うカウンタートレード）",
             fontsize=12, fontweight="bold")

# 左上: 6本後リターン分布比較
ax = axes[0][0]
ax.set_facecolor("#f8f9fa")
ax.axvline(0, color="#333", lw=1.0, ls="--", alpha=0.6)
ax.set_title("フィルター別 6本後リターン分布（ロング目線）", fontsize=10, fontweight="bold")
colors_map = {"フィルターなし":"#95a5a6","USD弱/JPY強(Q10)":"#e74c3c",
              "USD強/JPY弱(Q90, 逆)":"#3498db"}
for fname, fmask in LONG_FILTERS.items():
    r = future_ret[6][fmask].dropna() * 100
    if len(r)<30: continue
    lo,hi = np.percentile(r,[1,99])
    ax.hist(r, bins=np.linspace(lo,hi,70), density=True,
            color=colors_map[fname], alpha=0.55, edgecolor="none",
            label=f"{fname}  μ={r.mean():+.4f}%  n={len(r):,}")
    try:
        kde=stats.gaussian_kde(r,bw_method=0.3)
        xs=np.linspace(lo,hi,300)
        ax.plot(xs,kde(xs),color=colors_map[fname],lw=2.0)
    except: pass
ax.set_xlabel("累積対数リターン % (正=上昇=ロング利益)", fontsize=8)
ax.set_ylabel("確率密度", fontsize=8)
ax.legend(fontsize=8, framealpha=0.9)

# 右上: horizon別期待値
ax = axes[0][1]
ax.set_facecolor("#f8f9fa")
ax.axhline(0, color="#333", lw=0.8, ls="--")
ax.set_title("フィルター別 期待値推移（ロング目線）", fontsize=10, fontweight="bold")
for fname, fmask in LONG_FILTERS.items():
    means=[future_ret[h][fmask].dropna().mean()*100 for h in HORIZONS]
    ax.plot(HORIZONS, means, marker="o", lw=2, color=colors_map[fname], label=fname)
ax.set_xlabel("先行バー数 (×5分)", fontsize=8)
ax.set_ylabel("Mean (%)", fontsize=8)
ax.set_xticks(HORIZONS)
ax.legend(fontsize=8)
ax.grid(axis="y", alpha=0.3)

# 左下・右下: バックテスト P&L曲線
plot_colors = ["#3498db","#e74c3c","#f39c12"]
for ax, ((clabel,cmask),(idx,color)) in zip(
    [axes[1][0], axes[1][1]],
    zip(list(long_configs.items())[:2], enumerate(plot_colors))
):
    ax.set_facecolor("#f8f9fa")
    ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
    df_lt = best_long_dfs.get(clabel, pd.DataFrame())
    sv = summarize(df_lt)
    if len(df_lt):
        cum = df_lt["pnl_yen"].cumsum()
        ax.plot(range(len(cum)), cum.values, color=color, lw=2.2)
        ax.set_title(f"{clabel}\nPF={sv.get('pf',0):.2f}  損益={sv.get('total_pnl',0):+,.0f}円  "
                     f"n={sv.get('n',0)}  DD={sv.get('max_dd',0):,.0f}円",
                     fontsize=9, fontweight="bold")
    ax.set_xlabel("トレード番号", fontsize=8)
    ax.set_ylabel("累積損益 (円)", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

plt.tight_layout()
fig.savefig(OUT2/"tokyo_long.png", dpi=150, bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終サマリー ────────────────────────────────────────────
print("\n" + "="*70)
print("  最終サマリー")
print("="*70)
print("\n【OOS比較】")
for label,(ac_ser,thr) in PARAMS.items():
    si = summarize(run_bt(base_short & is_mask  & (ac_ser>thr) & ac_ser.notna(),"short"))
    so = summarize(run_bt(base_short & oos_mask & (ac_ser>thr) & ac_ser.notna(),"short"))
    drift = so.get("pf",0) - si.get("pf",0)
    print(f"  {label:26s}  IS PF={si.get('pf',0):.2f} → OOS PF={so.get('pf',0):.2f}  "
          f"(乖離: {drift:+.2f})")

print("\n【東京逆張りロング IS結果】")
for clabel, df_lt in best_long_dfs.items():
    sv = summarize(df_lt)
    verdict = "★ 検討値あり" if sv.get("pf",0)>=1.1 else "△ 微妙"
    print(f"  {clabel:30s}  PF={sv.get('pf',0):.2f}  "
          f"損益={sv.get('total_pnl',0):+,.0f}円  {verdict}")

print(f"\n保存先: {OUT1}  /  {OUT2}")
print("完了")
