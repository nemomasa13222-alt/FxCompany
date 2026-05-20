"""
ローリング窓サイズ比較: 30 / 50 / 75 / 100 トレード
最適窓を選んで _ev_pid.py に反映する
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.rcParams["font.family"] = "Yu Gothic"
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR  = Path("data/dukascopy")
PIP       = 0.01; ENTRY_COST = 0.2; SW = 20
IS_START  = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START = "2024-01-01"; OOS_END   = "2025-01-01"

PID_KP  = 0.5; PID_KI = 0.05; PID_KD = 0.1
LOT_MIN = 0.3; LOT_MAX = 2.0

WINDOWS = [30, 50, 75, 100]

TF_CONFIGS = {
    "5min":  dict(rule="5min",  rb=12, rp=10, mh=5,  color="#3498db", target_ev=1.164),
    "30min": dict(rule="30min", rb=6,  rp=15, mh=3,  color="#e67e22", target_ev=5.344),
    "1h":    dict(rule="1h",    rb=4,  rp=25, mh=2,  color="#2ecc71", target_ev=7.480),
}

OUT_PDF = Path("ev_pid_window.pdf")

# ── データ準備 ────────────────────────────────────────────────────────────────
dfs5 = {p: pd.read_parquet(DATA_DIR/f"{p}_5min.parquet")
        for p in PAIRS if (DATA_DIR/f"{p}_5min.parquet").exists()}
rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
st   = currency_strength(rd)
sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())
df5  = dfs5["USDJPY"]

def resample(rule):
    if rule == "5min": return df5, sd5.reindex(df5.index)
    df = df5.resample(rule, label="left", closed="left").agg(
        Open=("Open","first"), High=("High","max"),
        Low=("Low","min"), Close=("Close","last"), Volume=("Volume","sum")
    ).dropna(subset=["Open"])
    sd = sd5.resample(rule, label="left", closed="left").last().reindex(df.index)
    return df, sd

def make_sig(df, sd, rb, rp):
    c = df["Close"]
    rh = c.shift(1).rolling(rb).max(); rl = c.shift(1).rolling(rb).min()
    ir = (rh-rl) <= rp * PIP; s = sd.reindex(df.index)
    return pd.DataFrame({"c":c,"o":df["Open"],
                         "ls":ir&(c>rh)&(s>0),"ss":ir&(c<rl)&(s<0),"rm":(rh+rl)/2})

def run_bt(sig, mh):
    c=sig["c"].values; o=sig["o"].values; rm=sig["rm"].values
    ls=sig["ls"].values; ss=sig["ss"].values; idx=sig.index; n=len(sig)
    pnls=[]; times=[]; inT=False; d=0; ep=sp=0.0; eb=-1
    for i in range(1,n-1):
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
                pnls.append((xp-ep)*d/PIP); times.append(idx[i])
                inT=False; d=0
    return np.array(pnls), pd.DatetimeIndex(times)

def rolling_ev(pnls, times, window):
    evs = [pnls[max(0,i-window+1):i+1].mean() for i in range(len(pnls))]
    return pd.Series(evs, index=times)

def pid_sim(ev_series, target_ev):
    integral=0.0; prev_err=0.0; lots=[]
    for ev in ev_series:
        norm = ev / target_ev
        if ev <= 0:
            lots.append(0.0); integral=0.0; prev_err=0.0; continue
        err      = 1.0 - norm
        integral = np.clip(integral + err, -10.0, 10.0)
        u        = PID_KP*err + PID_KI*integral + PID_KD*(err-prev_err)
        lot      = LOT_MIN if norm < 0.5 else np.clip(1.0 + u, LOT_MIN, LOT_MAX)
        lots.append(lot); prev_err=err
    return pd.Series(lots, index=ev_series.index)

def eff_pnl(pnls, lot_series):
    lot_arr = lot_series.values
    lots_prev = np.roll(lot_arr, 1); lots_prev[0] = 1.0
    return (pnls * lots_prev).sum()

# ── 全TF・全窓でバックテスト ─────────────────────────────────────────────────
print("計算中...")
bt_cache = {}
for tf, cfg in TF_CONFIGS.items():
    df, sd = resample(cfg["rule"])
    sig = make_sig(df, sd, cfg["rb"], cfg["rp"])
    pnls, times = run_bt(sig, cfg["mh"])
    bt_cache[tf] = (pnls, times, cfg["target_ev"])

# 結果テーブル
print(f"\n{'='*72}")
print(f"  ローリング窓サイズ比較（EV-PID制御）")
print(f"  固定1.0×との比較: 差分がプラスなら制御が機能している")
print(f"{'='*72}")

all_results = {}

for tf in TF_CONFIGS:
    pnls, times, target_ev = bt_cache[tf]
    tz = times.tz
    is_ts = pd.Timestamp(IS_START, tz=tz); ie_ts = pd.Timestamp(IS_END, tz=tz)
    os_ts = pd.Timestamp(OOS_START, tz=tz); oe_ts = pd.Timestamp(OOS_END, tz=tz)
    is_m  = (times>=is_ts)&(times<ie_ts)
    oos_m = (times>=os_ts)&(times<=oe_ts)

    fixed_is  = pnls[is_m].sum()
    fixed_oos = pnls[oos_m].sum()

    print(f"\n  [{tf}]  固定1.0×: IS={fixed_is:+.1f}p  OOS={fixed_oos:+.1f}p")
    print(f"  {'窓':>4} | {'IS 損益':>9} {'vs固定':>7} {'停止率':>6} {'avg倍率':>7}"
          f" | {'OOS 損益':>9} {'vs固定':>7} {'停止率':>6} {'avg倍率':>7}")
    print("  " + "-"*65)

    tf_res = {}
    for w in WINDOWS:
        ev_all  = rolling_ev(pnls, times, w)
        lot_all = pid_sim(ev_all, target_ev)

        for label, mask, fixed in [("IS", is_m, fixed_is), ("OOS", oos_m, fixed_oos)]:
            ep   = eff_pnl(pnls[mask], lot_all[mask])
            lots = lot_all[mask]
            stop_r = (lots==0.0).sum()/len(lots)*100
            avg_l  = lots.mean()
            diff   = ep - fixed
            if label == "IS":
                tf_res.setdefault(w, {})["is_ep"]   = ep
                tf_res[w]["is_diff"]  = diff
                tf_res[w]["is_stop"]  = stop_r
                tf_res[w]["is_lot"]   = avg_l
                row_is = f"{ep:>+9.1f}p {diff:>+7.1f}p {stop_r:>5.1f}% {avg_l:>7.2f}×"
            else:
                tf_res[w]["oos_ep"]   = ep
                tf_res[w]["oos_diff"] = diff
                tf_res[w]["oos_stop"] = stop_r
                tf_res[w]["oos_lot"]  = avg_l
                row_oos = f"{ep:>+9.1f}p {diff:>+7.1f}p {stop_r:>5.1f}% {avg_l:>7.2f}×"

        print(f"  {w:>4} | {row_is} | {row_oos}")

    all_results[tf] = tf_res

# ── 推奨窓サイズの選定 ───────────────────────────────────────────────────────
print(f"\n{'='*72}")
print("  総合推奨窓サイズ（OOS改善率の合計）")
print(f"{'='*72}")

window_scores = {w: 0.0 for w in WINDOWS}
for tf in TF_CONFIGS:
    pnls, times, target_ev = bt_cache[tf]
    oos_m = (times>=pd.Timestamp(OOS_START,tz=times.tz)) & \
            (times<=pd.Timestamp(OOS_END,tz=times.tz))
    fixed_oos = pnls[oos_m].sum()
    for w in WINDOWS:
        ev_all  = rolling_ev(pnls, times, w)
        lot_all = pid_sim(ev_all, target_ev)
        ep      = eff_pnl(pnls[oos_m], lot_all[oos_m])
        # 改善率（固定1.0×を1.0として）
        improvement = ep / fixed_oos if fixed_oos > 0 else 0
        window_scores[w] += improvement

best_w = max(window_scores, key=window_scores.get)
print(f"  {'窓':>4} | {'OOS改善率合計':>14}")
print("  " + "-"*22)
for w, sc in window_scores.items():
    mark = " ★推奨" if w == best_w else ""
    print(f"  {w:>4} | {sc:>14.3f}{mark}")

print(f"\n  推奨: ローリング窓 = {best_w} トレード")

# ── グラフ（推奨窓でのEV推移） ────────────────────────────────────────────────
print("\nグラフ生成中...")
with PdfPages(OUT_PDF) as pdf:

    # ページ1: 窓サイズ別 ロット倍率比較（各TF・OOS期間）
    fig, axes = plt.subplots(len(TF_CONFIGS), 1, figsize=(16, 11),
                              sharex=False, facecolor="#1a1a2e")
    fig.suptitle(f"ローリング窓サイズ比較（OOS期間: {OOS_START}〜{OOS_END}）",
                 fontsize=12, color="white")

    colors_w = {30:"#e74c3c", 50:"#f39c12", 75:"#2ecc71", 100:"#3498db"}
    for ax_i, (tf, cfg) in enumerate(TF_CONFIGS.items()):
        ax = axes[ax_i]
        ax.set_facecolor("#16213e")
        pnls, times, target_ev = bt_cache[tf]
        tz   = times.tz
        os_s = pd.Timestamp(OOS_START, tz=tz)
        oe_s = pd.Timestamp(OOS_END,   tz=tz)
        oos_m = (times>=os_s)&(times<=oe_s)
        t_oos = times[oos_m]

        ax.axhline(1.0, color="#aaa", linewidth=0.7, linestyle=":", alpha=0.5)
        ax.axhline(LOT_MIN, color="#e74c3c", linewidth=0.5, linestyle="--", alpha=0.4)
        for w, col in colors_w.items():
            ev_all  = rolling_ev(pnls, times, w)
            lot_all = pid_sim(ev_all, target_ev)
            ax.plot(t_oos, lot_all[oos_m].values, color=col,
                    linewidth=1.2, alpha=0.8, label=f"窓={w}")
        ax.set_ylabel("ロット倍率", color="white", fontsize=9)
        ax.set_title(f"{tf}  target_EV={target_ev:.3f}p", color=cfg["color"],
                     fontsize=10, loc="left")
        ax.legend(loc="upper right", fontsize=8, facecolor="#1a1a2e",
                  labelcolor="white", framealpha=0.8, ncol=4)
        ax.tick_params(colors="white")
        ax.set_ylim(-0.1, 2.3)
        for s in ax.spines.values(): s.set_edgecolor("#444")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    pdf.savefig(fig, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

    # ページ2: 推奨窓でのIS+OOS ローリングEV
    fig, axes = plt.subplots(len(TF_CONFIGS), 1, figsize=(16, 11),
                              sharex=False, facecolor="#1a1a2e")
    fig.suptitle(f"推奨窓（{best_w}トレード）でのローリングEV推移",
                 fontsize=12, color="white")

    for ax_i, (tf, cfg) in enumerate(TF_CONFIGS.items()):
        ax = axes[ax_i]
        ax.set_facecolor("#16213e")
        pnls, times, target_ev = bt_cache[tf]
        tz   = times.tz
        is_s = pd.Timestamp(IS_START,  tz=tz); ie_s = pd.Timestamp(IS_END, tz=tz)
        os_s = pd.Timestamp(OOS_START, tz=tz); oe_s = pd.Timestamp(OOS_END, tz=tz)

        ev_all  = rolling_ev(pnls, times, best_w)
        lot_all = pid_sim(ev_all, target_ev)

        full_m = (times>=is_s)&(times<=oe_s)
        t_full = times[full_m]
        ev_f   = ev_all[full_m]
        lot_f  = lot_all[full_m]

        # EV
        ax.axhline(0, color="#e74c3c", linewidth=0.8, linestyle="--", alpha=0.6)
        ax.axhline(target_ev, color=cfg["color"], linewidth=0.8,
                   linestyle=":", alpha=0.6, label=f"target {target_ev:.2f}p")
        ax.fill_between(t_full, 0, ev_f, where=(ev_f>0), alpha=0.3, color=cfg["color"])
        ax.fill_between(t_full, 0, ev_f, where=(ev_f<=0), alpha=0.4, color="#e74c3c")
        ax.plot(t_full, ev_f, color=cfg["color"], linewidth=1.0, alpha=0.7)

        # ロット倍率（右軸）
        ax2 = ax.twinx()
        ax2.plot(t_full, lot_f, color="#f1c40f", linewidth=1.0,
                 alpha=0.6, linestyle="--", label="ロット倍率")
        ax2.set_ylim(-0.2, 2.5)
        ax2.set_ylabel("ロット倍率", color="#f1c40f", fontsize=8)
        ax2.tick_params(colors="#f1c40f", labelsize=7)

        ax.axvline(ie_s, color="#fff", linewidth=1.0, linestyle="--", alpha=0.5)
        ax.axvspan(is_s, ie_s, alpha=0.05, color="#3498db")
        ax.axvspan(ie_s, oe_s, alpha=0.05, color="#e67e22")
        ax.set_title(f"{tf}  窓={best_w}トレード", color=cfg["color"],
                     fontsize=10, loc="left")
        ax.set_ylabel("ローリングEV (pips)", color="white", fontsize=9)
        ax.tick_params(colors="white")
        ax.legend(loc="upper left", fontsize=8, facecolor="#1a1a2e",
                  labelcolor="white", framealpha=0.8)
        for s in ax.spines.values(): s.set_edgecolor("#444")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    pdf.savefig(fig, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

print(f"保存: {OUT_PDF.resolve()}")
print(f"推奨窓: {best_w}トレード → _ev_pid.py の ROLL_WIN を更新してください")
