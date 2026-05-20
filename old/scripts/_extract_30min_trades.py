# -*- coding: utf-8 -*-
"""
USDJPY 30分足 レンジブレイク バックテスト → トレードデータ抽出
→ モンテカルロシミュレーション
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.gridspec as gridspec
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

try:
    fm.fontManager.addfont(r"C:\Windows\Fonts\YuGothM.ttc")
    plt.rcParams["font.family"] = fm.FontProperties(
        fname=r"C:\Windows\Fonts\YuGothM.ttc").get_name()
except Exception:
    pass

# ── 設定 ──────────────────────────────────────────────────────────
DATA_DIR   = Path("data/dukascopy")
PIP        = 0.01
IS_START   = "2022-01-01"
IS_END     = "2024-01-01"
OOS_START  = "2024-01-01"
OOS_END    = "2025-01-01"
ENTRY_COST = 0.2
SW         = 20        # 強弱ウィンドウ（5分足ベース）
TF_MIN     = 30
RANGE_BARS = 6
RANGE_PIPS = 25
MIN_HOLD   = 3
CAPITAL_JPY  = 1_000_000
PIP_VAL_JPY  = 667
N_TRADES      = 1000
N_SIMULATIONS = 1000
SEED = 42


# ── データ読み込み・30分リサンプル ────────────────────────────────
print("データ読み込み中...")
dfs5 = {p: pd.read_parquet(DATA_DIR / f"{p}_5min.parquet")
        for p in PAIRS if (DATA_DIR / f"{p}_5min.parquet").exists()}

# タイムゾーン統一
for p in dfs5:
    if dfs5[p].index.tz is not None:
        dfs5[p].index = dfs5[p].index.tz_localize(None)

# 強弱差（5分足ベース）
rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
st   = currency_strength(rd)
sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())

# 30分にリサンプル
usdjpy5 = dfs5["USDJPY"]
usdjpy30 = usdjpy5.resample("30min").agg({
    "Open": "first", "High": "max", "Low": "min",
    "Close": "last", "Volume": "sum"
}).dropna(subset=["Close"])
sd30 = sd5.resample("30min").last().reindex(usdjpy30.index)

print(f"  30分足バー数: {len(usdjpy30):,}  期間: {usdjpy30.index[0].date()} ~ {usdjpy30.index[-1].date()}")


# ── シグナル生成 ───────────────────────────────────────────────────
close = usdjpy30["Close"]
rh    = close.shift(1).rolling(RANGE_BARS).max()
rl    = close.shift(1).rolling(RANGE_BARS).min()
rm    = (rh + rl) / 2
inR   = (rh - rl) <= RANGE_PIPS * PIP

long_sig  = inR & (close > rh) & (sd30 > 0)
short_sig = inR & (close < rl) & (sd30 < 0)

sig = pd.DataFrame({
    "close": close, "open": usdjpy30["Open"],
    "long_sig": long_sig, "short_sig": short_sig,
    "range_mid": rm,
})


# ── バックテスト（全期間・個別トレード記録） ──────────────────────
def run_backtest_full(sig: pd.DataFrame, min_hold: int):
    close  = sig["close"].values
    open_  = sig["open"].values
    rm_arr = sig["range_mid"].values
    ls     = sig["long_sig"].values
    ss     = sig["short_sig"].values
    idx    = sig.index

    trades = []
    inT = False; d = 0; ep = sp = 0.0; eb = -1

    for i in range(1, len(sig) - 1):
        if not inT:
            if ls[i-1]:
                d=1;  ep=open_[i]+ENTRY_COST*PIP; sp=rm_arr[i-1]; eb=i; inT=True
            elif ss[i-1]:
                d=-1; ep=open_[i]-ENTRY_COST*PIP; sp=rm_arr[i-1]; eb=i; inT=True
        else:
            held = i - eb
            unr  = (close[i] - ep) * d / PIP
            xp   = None
            reason = ""
            if d==1  and close[i] <= sp: xp=sp;       reason="stop"
            elif d==-1 and close[i] >= sp: xp=sp;     reason="stop"
            elif held >= min_hold and unr > 0:
                if d==1  and close[i] < close[i-1]: xp=close[i]; reason="tp"
                elif d==-1 and close[i] > close[i-1]: xp=close[i]; reason="tp"
            if xp is not None:
                pnl_pip = (xp - ep) * d / PIP
                pnl_jpy = pnl_pip * PIP_VAL_JPY
                trades.append({
                    "entry_time":  idx[eb],
                    "exit_time":   idx[i],
                    "direction":   "LONG" if d==1 else "SHORT",
                    "pnl_pips":   round(pnl_pip, 2),
                    "pnl_yen":    round(pnl_jpy, 0),
                    "exit_reason": reason,
                    "hold_bars":  held,
                })
                inT=False; d=0

    return pd.DataFrame(trades)


print("\nバックテスト実行中（IS+OOS全期間）...")
trades_df = run_backtest_full(sig, MIN_HOLD)
print(f"  全期間トレード数: {len(trades_df)}")

# IS / OOS 分割
is_df  = trades_df[trades_df["entry_time"] <  pd.Timestamp(IS_END)]
oos_df = trades_df[(trades_df["entry_time"] >= pd.Timestamp(OOS_START)) &
                   (trades_df["entry_time"] <  pd.Timestamp(OOS_END))]

print(f"\n{'='*60}")
print(f"  USDJPY 30分足 レンジブレイク バックテスト統計")
print(f"  bars={RANGE_BARS}  pips={RANGE_PIPS}  hold={MIN_HOLD}  1pip={PIP_VAL_JPY}円")
print(f"{'='*60}")
for label, d in [("IS  2022〜2024", is_df), ("OOS 2024〜2025", oos_df), ("全期間       ", trades_df)]:
    if len(d) == 0:
        print(f"  {label}: データなし"); continue
    p   = d["pnl_yen"]
    w   = p[p > 0]; l = p[p < 0]
    wr  = len(w)/len(p)*100
    pf  = w.sum()/l.abs().sum() if len(l)>0 else 999
    print(f"  {label}: 件数{len(p):>5}  勝率{wr:>5.1f}%  "
          f"PF{pf:>5.2f}  損益{p.sum():>+12,.0f}円  "
          f"期待値{p.mean():>+8,.0f}円/T")

# 月間トレード数
months = (trades_df["exit_time"].max() - trades_df["entry_time"].min()).days / 30.44
print(f"\n  月間トレード数: {len(trades_df)/months:.1f}件/月（全{months:.1f}ヶ月）")
monthly = trades_df.groupby(trades_df["exit_time"].dt.to_period("M")).size()
print(f"  月別: 最小{monthly.min()}件 最大{monthly.max()}件 中央値{monthly.median():.0f}件")

# ── モンテカルロ ─────────────────────────────────────────────────
actual_pnl = trades_df["pnl_yen"].values
wins   = actual_pnl[actual_pnl > 0]
losses = actual_pnl[actual_pnl < 0]
win_rate = len(wins) / len(actual_pnl)
avg_win  = wins.mean()
avg_loss = losses.mean()

rng1 = np.random.default_rng(SEED)
final_fixed = np.zeros(N_SIMULATIONS)
curves_fixed = np.zeros((N_SIMULATIONS, N_TRADES+1))
for sim in range(N_SIMULATIONS):
    w  = rng1.random(N_TRADES) < win_rate
    p  = np.where(w, avg_win, avg_loss)
    eq = np.concatenate([[CAPITAL_JPY], CAPITAL_JPY + np.cumsum(p)])
    curves_fixed[sim] = eq; final_fixed[sim] = eq[-1]

rng2 = np.random.default_rng(SEED+1)
final_boot = np.zeros(N_SIMULATIONS)
curves_boot = np.zeros((N_SIMULATIONS, N_TRADES+1))
max_dd_arr  = np.zeros(N_SIMULATIONS)
for sim in range(N_SIMULATIONS):
    w      = rng2.random(N_TRADES) < win_rate
    w_samp = rng2.choice(wins,   size=N_TRADES, replace=True)
    l_samp = rng2.choice(losses, size=N_TRADES, replace=True)
    p      = np.where(w, w_samp, l_samp)
    eq     = np.concatenate([[CAPITAL_JPY], CAPITAL_JPY + np.cumsum(p)])
    curves_boot[sim] = eq; final_boot[sim] = eq[-1]
    peak = np.maximum.accumulate(eq)
    max_dd_arr[sim] = ((peak-eq)/peak*100).max()

ret_fixed = (final_fixed-CAPITAL_JPY)/CAPITAL_JPY*100
ret_boot  = (final_boot -CAPITAL_JPY)/CAPITAL_JPY*100

print(f"\n{'='*60}")
print(f"  モンテカルロ（{N_SIMULATIONS}ケース × {N_TRADES}トレード）")
print(f"{'='*60}")
print(f"  勝率{win_rate*100:.1f}%  平均利益{avg_win:+,.0f}円  平均損失{avg_loss:,.0f}円")
print(f"  固定平均: 中央値{np.median(ret_fixed):+.1f}%  "
      f"下位10%{np.percentile(ret_fixed,10):+.1f}%  上位10%{np.percentile(ret_fixed,90):+.1f}%")
print(f"  実際分布: 中央値{np.median(ret_boot):+.1f}%  "
      f"下位10%{np.percentile(ret_boot,10):+.1f}%  上位10%{np.percentile(ret_boot,90):+.1f}%")
print(f"  黒字ケース: {(final_boot>CAPITAL_JPY).sum()}/{N_SIMULATIONS}")
print(f"  DD25%超え : {(max_dd_arr>=25).sum()}/{N_SIMULATIONS}")
print(f"  最大DD 中央値{np.median(max_dd_arr):.1f}%  上位10%{np.percentile(max_dd_arr,90):.1f}%")

# ── グラフ ────────────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 14))
fig.patch.set_facecolor("#0f0f23")
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.30,
                        left=0.07, right=0.96, top=0.88, bottom=0.07)
ax_d = fig.add_subplot(gs[0, :])
ax_e = fig.add_subplot(gs[1, 0])
ax_h = fig.add_subplot(gs[1, 1])
BG = "#1a1a3e"
for ax in [ax_d, ax_e, ax_h]:
    ax.set_facecolor(BG); ax.tick_params(colors="#ccc", labelsize=10)
    for sp in ax.spines.values(): sp.set_edgecolor("#333")
    ax.grid(alpha=0.15, color="#555")

x = np.arange(N_TRADES+1)

# 上段: P&L分布
ax_d.hist(wins/10000,          bins=80, color="#2ecc71", alpha=0.85,
          label=f"勝ち {len(wins)}件  平均{avg_win/10000:+.2f}万円")
ax_d.hist(np.abs(losses)/10000, bins=40, color="#e74c3c", alpha=0.75,
          label=f"負け {len(losses)}件  平均{avg_loss/10000:.2f}万円")
ax_d.axvline(avg_win/10000,       color="#27ae60", lw=2.5, ls="--",
             label=f"勝ち平均 {avg_win/10000:.2f}万円")
ax_d.axvline(abs(avg_loss)/10000, color="#c0392b", lw=2.5, ls="--",
             label=f"負け平均 {abs(avg_loss)/10000:.2f}万円")
big = wins[wins > wins.mean()*3]
if len(big) > 0:
    ax_d.annotate(
        f"大勝ち {len(big)}件\n最大 {wins.max()/10000:.1f}万円",
        xy=(wins.max()/10000, 0.5), xytext=(wins.max()/10000*0.5, 30),
        color="#f39c12", fontsize=11, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#f39c12", lw=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="#2c1810", ec="#f39c12", alpha=0.9))
ax_d.set_title("実際のトレードP&L分布（USDJPY 30分足）  ─  右裾の大勝ちが平均値では消える",
               color="#eee", fontsize=13, fontweight="bold", pad=10)
ax_d.set_xlabel("損益の絶対値（万円）", color="#ccc", fontsize=11)
ax_d.set_ylabel("件数", color="#ccc", fontsize=11)
ax_d.legend(fontsize=9.5, facecolor="#222", labelcolor="white", loc="upper right", framealpha=0.9)

# 左下: エクイティカーブ
cs_b = np.sort(curves_boot,  axis=0)
cs_f = np.sort(curves_fixed, axis=0)
ax_e.fill_between(x, cs_b[int(0.10*N_SIMULATIONS)]/10000, cs_b[int(0.90*N_SIMULATIONS)]/10000,
                  color="#e74c3c", alpha=0.20, label="実際分布 10〜90%ile")
ax_e.plot(x, cs_b[int(0.50*N_SIMULATIONS)]/10000, color="#e74c3c", lw=2.5, label="実際分布 中央値")
ax_e.fill_between(x, cs_f[int(0.10*N_SIMULATIONS)]/10000, cs_f[int(0.90*N_SIMULATIONS)]/10000,
                  color="#3498db", alpha=0.20, label="固定平均 10〜90%ile")
ax_e.plot(x, cs_f[int(0.50*N_SIMULATIONS)]/10000, color="#3498db", lw=2.5, label="固定平均 中央値")
ax_e.axhline(CAPITAL_JPY/10000, color="#888", lw=1, ls=":")
ax_e.set_title("エクイティカーブ比較", color="#eee", fontsize=12, fontweight="bold")
ax_e.set_xlabel("トレード数", color="#ccc", fontsize=11)
ax_e.set_ylabel("資産（万円）", color="#ccc", fontsize=11)
ax_e.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.9)

# 右下: 最終収益率分布
all_mn = min(ret_fixed.min(), ret_boot.min())
all_mx = max(ret_fixed.max(), ret_boot.max())
bins_a = np.linspace(all_mn, all_mx, 55)
ax_h.hist(ret_fixed, bins=bins_a, color="#3498db", alpha=0.65,
          label=f"固定平均 中央値{np.median(ret_fixed):+.1f}%")
ax_h.hist(ret_boot,  bins=bins_a, color="#e74c3c", alpha=0.65,
          label=f"実際分布 中央値{np.median(ret_boot):+.1f}%")
ax_h.axvline(np.median(ret_fixed), color="#3498db", lw=2.5, ls="--")
ax_h.axvline(np.median(ret_boot),  color="#e74c3c", lw=2.5, ls="--")
ax_h.axvline(np.percentile(ret_boot, 90), color="#e74c3c", lw=1.5, ls=":",
             label=f"実際分布 上位10% {np.percentile(ret_boot,90):+.1f}%")
ax_h.axvline(np.percentile(ret_fixed,90), color="#3498db", lw=1.5, ls=":",
             label=f"固定平均 上位10% {np.percentile(ret_fixed,90):+.1f}%")
ax_h.axvline(0, color="#888", lw=1, ls=":")
ax_h.set_title("最終収益率 分布比較（1,000トレード後）",
               color="#eee", fontsize=12, fontweight="bold")
ax_h.set_xlabel("収益率（%）", color="#ccc", fontsize=11)
ax_h.set_ylabel("ケース数", color="#ccc", fontsize=11)
ax_h.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.9)

fig.suptitle(
    f"FX USDJPY 30分足 レンジブレイク  モンテカルロシミュレーション（{len(trades_df):,}件より）\n"
    f"勝率{win_rate*100:.1f}%　平均利益{avg_win:+,.0f}円　"
    f"平均損失{avg_loss:,.0f}円　PF{wins.sum()/np.abs(losses).sum():.2f}　"
    f"1pip={PIP_VAL_JPY}円（100万円 / レバ10× / 6.7万通貨）",
    color="#eee", fontsize=12, fontweight="bold", y=0.97)

out = Path("monte_carlo_fx30min.png")
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="#0f0f23")
plt.close(fig)
print(f"\n  グラフ保存: {out.resolve()}")
