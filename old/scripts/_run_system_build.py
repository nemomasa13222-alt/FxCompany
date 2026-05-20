# -*- coding: utf-8 -*-
"""
マルチペア統合システム 構築
────────────────────────────────────────────────────────────
Step1: 全12ペア × 4セッション プレイブック生成（IS期間）
Step2: ウォークフォワード週次ランキングバックテスト（IS期間）
Step3: 結果可視化
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
import warnings
warnings.filterwarnings("ignore")

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "system"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 定数 ────────────────────────────────────────────────────
IS_START  = "2022-01-01";  IS_END   = "2023-12-31"
STRENGTH_WINDOW = 24
JST        = pd.Timedelta(hours=9)
CAPITAL    = 1_000_000
RISK_PCT   = 0.005
PIP_VALUE  = 100      # 円/pip/lot（JPYペア）
PIP_SIZE_JPY = 0.01   # JPY建てペア（USDJPY等）
PIP_SIZE_USD = 0.0001 # USD建てペア（GBPUSD等）
ATR_PERIOD = 14
MAX_HOLD   = 48
AC_WINDOW  = 12       # 自己相関ウィンドウ
AC_SH_THR  =  0.00   # ショート用（順張り）
AC_LG_THR  =  0.00   # ロング用（逆張り: ac<0が条件）
TOP_N      = 3        # 週次選出ペア数
MIN_TRADES_RANK = 2   # ランキング有効の最低トレード数

SESSIONS = [
    ("東京 09-15",  9, 15, "#f39c12"),
    ("欧州 15-21", 15, 21, "#27ae60"),
    ("NY   21-03", 21,  3, "#2980b9"),
    ("深夜 03-09",  3,  9, "#8e44ad"),
]

# 全トレード対象ペア（7通貨12ペア）
PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
JPY_PAIRS = {p for p,(b,q) in PAIR_CURRENCIES.items() if q=="JPY" or b=="JPY"}
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
    print(f"  {pair}: {len(df):,}本")

common_idx = dfs[list(dfs.keys())[0]].index
for pair in dfs: common_idx = common_idx.intersection(dfs[pair].index)
for pair in dfs: dfs[pair] = dfs[pair].reindex(common_idx)
is_mask = (common_idx >= IS_START) & (common_idx <= IS_END)
print(f"共通バー数: {len(common_idx):,}  IS:{is_mask.sum():,}")

# ── 通貨強弱スコア ──────────────────────────────────────────
print("通貨強弱算出中...")
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
str_df = pd.DataFrame(raw_str)

# 各ペアの強弱差（正 = base強・quote弱、負 = base弱・quote強）
pair_str_diff = {}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if b in str_df.columns and q in str_df.columns:
        pair_str_diff[pair] = str_df[b] - str_df[q]

# セッション・ATR・自己相関
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e,_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return "深夜 03-09"
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# ATR（ペア別）
atr_dict = {}
for pair, df in dfs.items():
    hi,lo,cl = df["High"], df["Low"], df["Close"].shift(1)
    tr = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr_dict[pair] = tr.rolling(ATR_PERIOD).mean()

# 自己相関（ペア別）
def rolling_ac(series, window):
    arr = series.values; res = np.full(len(arr), np.nan)
    for i in range(window-1, len(arr)):
        x = arr[i-window+1:i+1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-1], x[1:])
        res[i] = c[0,1]
    return pd.Series(res, index=series.index)

print("自己相関算出中...")
ac_dict = {}
for pair, df in dfs.items():
    ret = np.log(df["Close"]/df["Close"].shift(1))
    ac_dict[pair] = rolling_ac(ret, AC_WINDOW)

# pip値（ペア別）
def get_pip_info(pair):
    if pair in JPY_PAIRS:
        return PIP_SIZE_JPY, PIP_VALUE
    else:
        return PIP_SIZE_USD, 1000   # USD建て: 1pip=0.0001, 1lot=1000円相当（簡略）

# ════════════════════════════════════════════════════════════
# Step1: プレイブック生成
# ════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  Step1: プレイブック生成（IS期間 × 全ペア × 全セッション）")
print("="*70)

PLAYBOOK = {}   # {pair: {session: {"dir": "short"/"long"/"none", "mean": ..., ...}}}

def analyze_direction(future_ret_h, mask, direction, h=6):
    """directionに応じた有利度スコアを返す"""
    r = future_ret_h[mask].dropna()
    if len(r) < 50: return None
    mean_v = r.mean() * 100
    skew_v = stats.skew(r)
    rate_v = (r < 0 if direction=="short" else r > 0).mean() * 100
    # スコア: 期待値が方向に有利かつskewも有利
    if direction == "short":
        score = -mean_v + max(0, -skew_v)   # 負のmean ＋ 負のskew が高スコア
    else:
        score =  mean_v + max(0,  skew_v)   # 正のmean ＋ 正のskew が高スコア
    return {"mean": mean_v, "skew": skew_v, "rate": rate_v, "n": len(r), "score": score}

for pair,(base,quote) in PAIR_CURRENCIES.items():
    if pair not in dfs or pair not in pair_str_diff: continue
    df_p  = dfs[pair]
    diff  = pair_str_diff[pair]
    q10   = diff.quantile(0.10)  # base弱・quote強（ブレイクダウン条件）

    # ブレイクダウンシグナル（base弱・quote強の時）
    breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & (diff <= q10) & diff.notna()
    entry_price = df_p["Open"].shift(-1)
    future_ret6 = np.log(df_p["Close"].shift(-6) / entry_price)

    PLAYBOOK[pair] = {}
    for sess_name, *_ in SESSIONS:
        sess_mask = (sess_s == sess_name) & is_mask & breakdown
        if sess_mask.sum() < 50:
            PLAYBOOK[pair][sess_name] = {"dir": "none", "score": 0}
            continue

        res_sh = analyze_direction(future_ret6, sess_mask, "short")
        res_lg = analyze_direction(future_ret6, sess_mask, "long")

        if res_sh is None and res_lg is None:
            PLAYBOOK[pair][sess_name] = {"dir": "none", "score": 0}
        elif res_sh is None:
            PLAYBOOK[pair][sess_name] = {"dir": "long",  **res_lg}
        elif res_lg is None:
            PLAYBOOK[pair][sess_name] = {"dir": "short", **res_sh}
        else:
            # スコアが高い方を採用（ただし score>0.5 が閾値）
            if res_sh["score"] > res_lg["score"] and res_sh["score"] > 0.5:
                PLAYBOOK[pair][sess_name] = {"dir": "short", **res_sh}
            elif res_lg["score"] > res_sh["score"] and res_lg["score"] > 0.5:
                PLAYBOOK[pair][sess_name] = {"dir": "long",  **res_lg}
            else:
                PLAYBOOK[pair][sess_name] = {"dir": "none", "score": 0}

# プレイブック出力
print(f"\n  {'ペア':8s}", end="")
for sname,*_ in SESSIONS: print(f"  {sname[:6]:>8s}", end="")
print()
print("-"*70)
playbook_rows = []
for pair in sorted(PLAYBOOK.keys()):
    print(f"  {pair:8s}", end="")
    for sname,*_ in SESSIONS:
        pb = PLAYBOOK[pair].get(sname, {"dir":"none"})
        d = pb["dir"]
        sym = "▼S" if d=="short" else "▲L" if d=="long" else " -"
        mean_v = pb.get("mean", 0)
        print(f"  {sym}({mean_v:+.3f})", end="")
        playbook_rows.append({
            "pair":pair,"session":sname,"dir":d,
            "mean":pb.get("mean",0),"skew":pb.get("skew",0),
            "rate":pb.get("rate",0),"n":pb.get("n",0),
        })
    print()

df_pb = pd.DataFrame(playbook_rows)
df_pb.to_csv(OUT_DIR/"playbook.csv", index=False, encoding="utf-8-sig")

# ════════════════════════════════════════════════════════════
# Step2: ウォークフォワード週次ランキングバックテスト
# ════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  Step2: ウォークフォワード週次ランキングバックテスト（IS期間）")
print("="*70)

def bt_pair_signal(pair, direction, mask):
    """1ペアの指定シグナルをバックテスト → トレードリストを返す"""
    if pair not in dfs: return []
    df_p = dfs[pair]
    atr  = atr_dict[pair]
    pip_sz, pip_val = get_pip_info(pair)
    positions = np.where(mask)[0]
    records = []
    for sp in positions:
        ep = sp + 1
        if ep >= len(df_p): continue
        entry_bar   = df_p.index[ep]
        entry_price = df_p["Open"].iloc[ep]
        atr_val     = atr.iloc[sp]
        if atr_val <= 0 or np.isnan(atr_val): continue
        sl_dist  = atr_val
        sl_pips  = sl_dist / pip_sz
        if sl_pips <= 0: continue
        lot_size = (CAPITAL * RISK_PCT) / (sl_pips * pip_val)

        if direction == "short":
            best_ext = entry_price; trail = entry_price + sl_dist
            exit_p = None; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep+h
                if bp >= len(df_p): break
                bh = df_p["High"].iloc[bp]; bl = df_p["Low"].iloc[bp]
                held = h
                if bh >= trail: exit_p = trail; break
                if bl < best_ext:
                    best_ext = bl; trail = min(trail, best_ext + sl_dist)
            if exit_p is None:
                fp = ep+held
                if fp >= len(df_p): continue
                exit_p = df_p["Close"].iloc[fp]
            pnl = (entry_price - exit_p) / pip_sz * pip_val * lot_size
        else:  # long
            best_ext = entry_price; trail = entry_price - sl_dist
            exit_p = None; held = 0
            for h in range(1, MAX_HOLD+1):
                bp = ep+h
                if bp >= len(df_p): break
                bh = df_p["High"].iloc[bp]; bl = df_p["Low"].iloc[bp]
                held = h
                if bl <= trail: exit_p = trail; break
                if bh > best_ext:
                    best_ext = bh; trail = max(trail, best_ext - sl_dist)
            if exit_p is None:
                fp = ep+held
                if fp >= len(df_p): continue
                exit_p = df_p["Close"].iloc[fp]
            pnl = (exit_p - entry_price) / pip_sz * pip_val * lot_size

        r_mult = pnl / (CAPITAL * RISK_PCT)
        sig_bar = df_p.index[sp]
        records.append({
            "pair": pair, "signal_bar": sig_bar, "entry_bar": entry_bar,
            "pnl_yen": pnl, "r_mult": r_mult, "held": held,
            "session": sess_s.get(sig_bar, "不明"),
            "week": (sig_bar + JST).to_period("W").start_time,
        })
    return records

# 全ペア × 全セッションのシグナル事前生成
print("全ペアシグナル生成中...")
all_trades_raw = []
for pair,(base,quote) in PAIR_CURRENCIES.items():
    if pair not in dfs or pair not in pair_str_diff: continue
    diff = pair_str_diff[pair]
    q10  = diff.quantile(0.10)
    df_p = dfs[pair]
    ac   = ac_dict[pair]
    breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & (diff <= q10) & diff.notna()

    for sess_name,*_ in SESSIONS:
        pb = PLAYBOOK[pair].get(sess_name, {"dir":"none"})
        if pb["dir"] == "none": continue
        direction = pb["dir"]
        ac_cond = (ac > AC_SH_THR) if direction=="short" else (ac < -AC_LG_THR)
        mask = breakdown & is_mask & (sess_s == sess_name) & ac_cond & ac.notna()
        if mask.sum() == 0: continue
        recs = bt_pair_signal(pair, direction, mask)
        all_trades_raw.extend(recs)
        print(f"  {pair} {sess_name[:6]} {direction:5s}: {len(recs):3d}件")

df_all = pd.DataFrame(all_trades_raw)
if len(df_all) == 0:
    print("トレードなし。終了。"); sys.exit()

df_all["week"] = pd.to_datetime(df_all["week"])
df_all.sort_values("signal_bar", inplace=True)
df_all.to_csv(OUT_DIR/"all_signals.csv", index=False, encoding="utf-8-sig")

# ── 週次ランキング + 実行フィルター ─────────────────────────
print("\n週次ランキングシミュレーション中...")
weeks = sorted(df_all["week"].unique())
week_pnl = []
selected_pairs_history = []
pair_weekly_r = {}   # {pair: [直近weekのavg_r]}
selected_pairs = list(PLAYBOOK.keys())[:TOP_N]  # 初週は全解放

executed_trades = []
for i, week_start in enumerate(weeks):
    # この週のトレード候補
    week_trades = df_all[df_all["week"] == week_start].copy()

    # 今週は選出ペアのみ執行
    exec_trades = week_trades[week_trades["pair"].isin(selected_pairs)]
    executed_trades.append(exec_trades)

    wpnl = exec_trades["pnl_yen"].sum()
    week_pnl.append({"week": week_start, "pnl": wpnl, "n": len(exec_trades),
                     "selected": list(selected_pairs)})

    # 今週の全候補でペア別avg_Rを更新（ランキング用）
    for pair_name, grp in week_trades.groupby("pair"):
        if len(grp) >= MIN_TRADES_RANK:
            avg_r = grp["r_mult"].mean()
        else:
            avg_r = pair_weekly_r.get(pair_name, [0])[-1] if pair_weekly_r.get(pair_name) else 0
        pair_weekly_r.setdefault(pair_name, []).append(avg_r)

    # 翌週の選出ペア決定（直近avg_Rでランク付け）
    rankings = []
    for pair_name, r_list in pair_weekly_r.items():
        recent_r = np.mean(r_list[-2:]) if len(r_list)>=2 else r_list[-1]  # 直近2週平均
        rankings.append((pair_name, recent_r))
    rankings.sort(key=lambda x: x[1], reverse=True)
    selected_pairs = [p for p,_ in rankings[:TOP_N]] if rankings else selected_pairs
    selected_pairs_history.append({"week": week_start, "ranking": rankings[:6]})

df_exec = pd.concat(executed_trades, ignore_index=True)
df_exec.to_csv(OUT_DIR/"executed_trades.csv", index=False, encoding="utf-8-sig")

# ── 集計 ────────────────────────────────────────────────────
def summarize(df):
    if len(df)==0: return {}
    wins=df[df["pnl_yen"]>0]; losses=df[df["pnl_yen"]<=0]
    gp=wins["pnl_yen"].sum(); gl=losses["pnl_yen"].abs().sum()
    pf=gp/gl if gl>0 else float("inf")
    cum=df["pnl_yen"].cumsum()
    return {"n":len(df),"win_rate":len(wins)/len(df)*100 if len(df)>0 else 0,
            "pf":pf,"total_pnl":df["pnl_yen"].sum(),
            "avg_r":df["r_mult"].mean(),"skew_r":stats.skew(df["r_mult"]),
            "max_dd":(cum.cummax()-cum).max()}

sv_exec = summarize(df_exec)
sv_all  = summarize(df_all)

print("\n" + "="*70)
print("  IS期間 バックテスト結果")
print("="*70)
print(f"\n  【全シグナル（フィルターなし）】")
print(f"  n={sv_all['n']:,}  勝率={sv_all['win_rate']:.1f}%  PF={sv_all['pf']:.2f}  "
      f"損益={sv_all['total_pnl']:+,.0f}円  DD={sv_all['max_dd']:,.0f}円")

print(f"\n  【週次ランキング上位{TOP_N}ペア選出後】")
print(f"  n={sv_exec['n']:,}  勝率={sv_exec['win_rate']:.1f}%  PF={sv_exec['pf']:.2f}  "
      f"損益={sv_exec['total_pnl']:+,.0f}円  DD={sv_exec['max_dd']:,.0f}円")

print(f"\n  ペア別貢献（執行済み）")
print(f"  {'ペア':8s}  {'n':>4s}  {'PF':>5s}  {'損益':>10s}  {'avgR':>7s}")
print("-"*50)
pair_contribs = []
for pair_name, grp in df_exec.groupby("pair"):
    sv2 = summarize(grp)
    tag = "★" if sv2["pf"] >= 1.2 else "  "
    print(f"  {tag}{pair_name:8s}  {sv2['n']:4d}  {sv2['pf']:5.2f}  "
          f"{sv2['total_pnl']:+10,.0f}  {sv2['avg_r']:+7.4f}")
    pair_contribs.append({"pair":pair_name,**sv2})

# ════════════════════════════════════════════════════════════
# Step3: 可視化
# ════════════════════════════════════════════════════════════
print("\n可視化中...")

# 図1: プレイブックヒートマップ
fig, axes = plt.subplots(1, 2, figsize=(20, 7))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("プレイブック  ─  全ペア × 全セッション\n"
             "（IS期間 2022-2023 / 強弱差Q10 + ブレイクダウン後）",
             fontsize=12, fontweight="bold")

pairs_list = sorted(PLAYBOOK.keys())
sess_list  = [s[0] for s in SESSIONS]

mean_mat = np.full((len(pairs_list), len(sess_list)), np.nan)
dir_mat  = np.zeros((len(pairs_list), len(sess_list)))  # 1=short,-1=long,0=none

for i,pair in enumerate(pairs_list):
    for j,sname in enumerate(sess_list):
        pb = PLAYBOOK[pair].get(sname, {"dir":"none","mean":0})
        mean_mat[i,j] = pb.get("mean",0)
        dir_mat[i,j]  = -1 if pb["dir"]=="short" else 1 if pb["dir"]=="long" else 0

for ax,(mat,title,cmap) in zip(axes,[
    (mean_mat,"6本後 期待値 (%)","RdYlGn_r"),
    (dir_mat, "方向 (▼ショート / ▲ロング / - なし)","RdBu"),
]):
    ax.set_facecolor("#f8f9fa")
    vmax = np.nanmax(np.abs(mat)) if not np.all(np.isnan(mat)) else 1
    im = ax.imshow(mat, cmap=cmap, aspect="auto", vmin=-vmax, vmax=vmax)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    ax.set_xticks(range(len(sess_list)))
    ax.set_xticklabels([s.split()[0] for s in sess_list], fontsize=9)
    ax.set_yticks(range(len(pairs_list)))
    ax.set_yticklabels(pairs_list, fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold")
    for i in range(len(pairs_list)):
        for j in range(len(sess_list)):
            pb = PLAYBOOK[pairs_list[i]].get(sess_list[j],{"dir":"none","mean":0})
            sym = "▼" if pb["dir"]=="short" else "▲" if pb["dir"]=="long" else "─"
            val = pb.get("mean",0)
            txt = f"{sym}\n{val:+.3f}" if pb["dir"]!="none" else "─"
            ax.text(j,i,txt,ha="center",va="center",fontsize=7.5,
                    color="white" if abs(val)>vmax*0.6 else "black")

plt.tight_layout()
fig.savefig(OUT_DIR/"playbook_heatmap.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# 図2: 累積損益（全シグナル vs 週次ランキング選出）
fig, axes = plt.subplots(2, 1, figsize=(18, 12))
fig.patch.set_facecolor("#fafafa")
fig.suptitle(f"IS期間 週次ランキングシステム  ─  上位{TOP_N}ペア選出\n"
             f"（全12ペア × 4セッション / SL:資金0.5% / TP:トレーリング）",
             fontsize=12, fontweight="bold")

# 上: 全シグナル vs 選出後
ax = axes[0]
ax.set_facecolor("#f8f9fa")
ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)

# 全シグナル
cum_all = df_all["pnl_yen"].cumsum()
ax.plot(range(len(cum_all)), cum_all.values, color="#bdc3c7", lw=1.5,
        label=f"全シグナル  PF={sv_all['pf']:.2f}  {sv_all['total_pnl']:+,.0f}円  n={sv_all['n']:,}")

# 週次選出後
cum_exec = df_exec["pnl_yen"].cumsum()
ax.plot(range(len(cum_exec)), cum_exec.values, color="#2c3e50", lw=2.5,
        label=f"週次ランキング選出  PF={sv_exec['pf']:.2f}  {sv_exec['total_pnl']:+,.0f}円  n={sv_exec['n']:,}")

ax.set_title("累積損益比較  ─  全シグナル vs 週次選出", fontsize=10, fontweight="bold")
ax.set_xlabel("トレード番号", fontsize=8)
ax.set_ylabel("累積損益 (円)", fontsize=8)
ax.legend(fontsize=9, framealpha=0.9)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

# 下: ペア別貢献（執行済み）
ax = axes[1]
ax.set_facecolor("#f8f9fa")
ax.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)

colors = plt.cm.tab20(np.linspace(0, 1, len(df_exec["pair"].unique())))
for (pair_name,grp), color in zip(df_exec.groupby("pair"), colors):
    cum_p = grp["pnl_yen"].cumsum()
    sv2 = summarize(grp)
    ax.plot(range(len(cum_p)), cum_p.values, color=color, lw=1.8,
            label=f"{pair_name} PF={sv2['pf']:.2f}  {sv2['total_pnl']:+,.0f}円  n={sv2['n']}")

ax.set_title("ペア別 累積損益（執行済み）", fontsize=10, fontweight="bold")
ax.set_xlabel("トレード番号（ペア内）", fontsize=8)
ax.set_ylabel("累積損益 (円)", fontsize=8)
ax.legend(fontsize=7.5, ncol=3, framealpha=0.9)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))

plt.tight_layout()
fig.savefig(OUT_DIR/"system_pnl.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# 図3: 週次損益バー
df_wpnl = pd.DataFrame(week_pnl)
fig, (ax1,ax2) = plt.subplots(2,1,figsize=(18,10))
fig.patch.set_facecolor("#fafafa")
fig.suptitle("週次損益 & 選出ペア推移", fontsize=12, fontweight="bold")

ax1.set_facecolor("#f8f9fa")
colors_bar = ["#2ecc71" if v>=0 else "#e74c3c" for v in df_wpnl["pnl"]]
ax1.bar(range(len(df_wpnl)), df_wpnl["pnl"], color=colors_bar, alpha=0.75, edgecolor="none")
ax1.axhline(0, color="#333", lw=0.8)
ax1.set_title("週次損益", fontsize=10, fontweight="bold")
ax1.set_xticks(range(len(df_wpnl)))
ax1.set_xticklabels([str(w.date()) for w in df_wpnl["week"]], rotation=45, fontsize=6.5)
ax1.set_ylabel("損益 (円)", fontsize=8)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))
ax1.grid(axis="y", alpha=0.3)

# 累積
ax2.set_facecolor("#f8f9fa")
ax2.plot(range(len(df_wpnl)), df_wpnl["pnl"].cumsum(), color="#2980b9", lw=2.5)
ax2.axhline(0, color="#333", lw=0.8)
ax2.set_title("累積損益（週次）", fontsize=10, fontweight="bold")
ax2.set_xticks(range(len(df_wpnl)))
ax2.set_xticklabels([str(w.date()) for w in df_wpnl["week"]], rotation=45, fontsize=6.5)
ax2.set_ylabel("累積損益 (円)", fontsize=8)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v,_: f"{int(v):,}"))
ax2.grid(axis="y", alpha=0.3)

plt.tight_layout()
fig.savefig(OUT_DIR/"weekly_pnl.png", dpi=150,
            bbox_inches="tight", facecolor="#fafafa")
plt.close(fig)

# ── 最終サマリー ────────────────────────────────────────────
print("\n" + "="*70)
print("  システム最終サマリー（IS期間）")
print("="*70)
print(f"\n  資金: {CAPITAL:,}円  リスク/トレード: {RISK_PCT*100:.1f}%")
print(f"  週次選出: 上位{TOP_N}ペア  最低ランキング基準: {MIN_TRADES_RANK}件/週")
print(f"\n  全シグナル:   PF={sv_all['pf']:.2f}  損益={sv_all['total_pnl']:+,.0f}円  DD={sv_all['max_dd']:,.0f}円")
print(f"  週次選出後:   PF={sv_exec['pf']:.2f}  損益={sv_exec['total_pnl']:+,.0f}円  DD={sv_exec['max_dd']:,.0f}円")
profit_weeks = sum(1 for r in week_pnl if r["pnl"]>0)
print(f"  週次勝率: {profit_weeks}/{len(week_pnl)} = {profit_weeks/len(week_pnl)*100:.1f}%")
print(f"\n保存先: {OUT_DIR}")
print("完了")
