# -*- coding: utf-8 -*-
"""
FX USDJPY 5分足 レンジブレイク バックテスト → モンテカルロシミュレーション
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

try:
    fm.fontManager.addfont(r"C:\Windows\Fonts\YuGothM.ttc")
    plt.rcParams["font.family"] = fm.FontProperties(
        fname=r"C:\Windows\Fonts\YuGothM.ttc").get_name()
except Exception:
    pass

# ── 設定 ──────────────────────────────────────────────────────────
PIP_VALUE     = 667       # 1pip = 667円（資金100万 / レバ10倍 / 6.7万通貨）
INITIAL_CAP   = 1_000_000
N_TRADES      = 1000
N_SIMULATIONS = 1000
SEED          = 42
IS_END        = "2024-01-01"

# ── データ読み込み ─────────────────────────────────────────────────
df = pd.read_csv("backtest_trades_range_break.csv", encoding="utf-8-sig")
df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
df["exit_time"]  = pd.to_datetime(df["exit_time"],  utc=True)
df["pnl_yen"]    = df["pnl_pips"] * PIP_VALUE

print("=" * 60)
print("  FX USDJPY 5分足 レンジブレイク バックテスト統計")
print(f"  bars=12  pips=10  hold=5  1pip={PIP_VALUE}円")
print("=" * 60)
p  = df["pnl_yen"]
w_ = p[p > 0]; l_ = p[p < 0]
print(f"  全期間 {df['entry_time'].min().date()}〜{df['exit_time'].max().date()}")
print(f"  件数{len(p):>5}  勝率{len(w_)/len(p)*100:>5.1f}%  "
      f"PF{w_.sum()/l_.abs().sum():>5.2f}  損益{p.sum():>+12,.0f}円")
print()

# ── 全期間で統計算出 ──────────────────────────────────────────────
actual_pnl = df["pnl_yen"].values
wins       = actual_pnl[actual_pnl > 0]
losses     = actual_pnl[actual_pnl < 0]
win_rate   = len(wins) / len(actual_pnl)
avg_win    = wins.mean()
avg_loss   = losses.mean()

print(f"  勝率     : {win_rate*100:.1f}%  ({len(wins)}勝{len(losses)}敗)")
print(f"  平均利益 : {avg_win:+,.0f}円")
print(f"  平均損失 : {avg_loss:+,.0f}円")
print(f"  PF       : {wins.sum()/np.abs(losses).sum():.2f}")
print(f"  期待値/T : {actual_pnl.mean():+,.0f}円")
print()

# ── シミュレーション①: 固定平均 ───────────────────────────────────
rng1 = np.random.default_rng(SEED)
final_fixed  = np.zeros(N_SIMULATIONS)
curves_fixed = np.zeros((N_SIMULATIONS, N_TRADES + 1))
for sim in range(N_SIMULATIONS):
    w  = rng1.random(N_TRADES) < win_rate
    p  = np.where(w, avg_win, avg_loss)
    eq = np.concatenate([[INITIAL_CAP], INITIAL_CAP + np.cumsum(p)])
    curves_fixed[sim] = eq
    final_fixed[sim]  = eq[-1]

# ── シミュレーション②: ブートストラップ ──────────────────────────
rng2 = np.random.default_rng(SEED + 1)
final_boot  = np.zeros(N_SIMULATIONS)
curves_boot = np.zeros((N_SIMULATIONS, N_TRADES + 1))
max_dd_arr  = np.zeros(N_SIMULATIONS)
for sim in range(N_SIMULATIONS):
    w      = rng2.random(N_TRADES) < win_rate
    w_samp = rng2.choice(wins,   size=N_TRADES, replace=True)
    l_samp = rng2.choice(losses, size=N_TRADES, replace=True)
    p      = np.where(w, w_samp, l_samp)
    eq     = np.concatenate([[INITIAL_CAP], INITIAL_CAP + np.cumsum(p)])
    curves_boot[sim] = eq
    final_boot[sim]  = eq[-1]
    peak  = np.maximum.accumulate(eq)
    dd    = (peak - eq) / peak * 100
    max_dd_arr[sim] = dd.max()

ret_fixed = (final_fixed - INITIAL_CAP) / INITIAL_CAP * 100
ret_boot  = (final_boot  - INITIAL_CAP) / INITIAL_CAP * 100

print("=" * 60)
print(f"  モンテカルロ結果（{N_SIMULATIONS}ケース × {N_TRADES}トレード）")
print("=" * 60)
print(f"  固定平均: 中央値{np.median(ret_fixed):+.1f}%  "
      f"下位10%{np.percentile(ret_fixed,10):+.1f}%  "
      f"上位10%{np.percentile(ret_fixed,90):+.1f}%")
print(f"  実際分布: 中央値{np.median(ret_boot):+.1f}%  "
      f"下位10%{np.percentile(ret_boot,10):+.1f}%  "
      f"上位10%{np.percentile(ret_boot,90):+.1f}%")
n_profit = (final_boot > INITIAL_CAP).sum()
n_bust   = (max_dd_arr >= 25).sum()
print(f"  黒字ケース: {n_profit}/{N_SIMULATIONS} ({n_profit/N_SIMULATIONS*100:.1f}%)")
print(f"  DD25%超え : {n_bust}/{N_SIMULATIONS} ({n_bust/N_SIMULATIONS*100:.1f}%)")
print(f"  最大DD 中央値: {np.median(max_dd_arr):.1f}%  上位10%: {np.percentile(max_dd_arr,90):.1f}%")

# ── グラフ生成 ────────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 14))
fig.patch.set_facecolor("#0f0f23")
gs  = gridspec.GridSpec(2, 2, figure=fig,
                        hspace=0.40, wspace=0.30,
                        left=0.07, right=0.96, top=0.88, bottom=0.07)
ax_dist = fig.add_subplot(gs[0, :])
ax_eq   = fig.add_subplot(gs[1, 0])
ax_hist = fig.add_subplot(gs[1, 1])

BG = "#1a1a3e"
for ax in [ax_dist, ax_eq, ax_hist]:
    ax.set_facecolor(BG)
    ax.tick_params(colors="#ccc", labelsize=10)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")
    ax.grid(alpha=0.15, color="#555")

x = np.arange(N_TRADES + 1)

# ─── 上段: 実際のP&L分布 ──────────────────────────────────────────
ax_dist.hist(wins   / 10000, bins=80, color="#2ecc71", alpha=0.85,
             label=f"勝ちトレード {len(wins)}件  平均{avg_win/10000:+.2f}万円")
ax_dist.hist(np.abs(losses) / 10000, bins=40, color="#e74c3c", alpha=0.75,
             label=f"負けトレード {len(losses)}件  平均{avg_loss/10000:.2f}万円")
ax_dist.axvline(avg_win    / 10000, color="#27ae60", lw=2.5, ls="--",
                label=f"勝ち平均 {avg_win/10000:.2f}万円")
ax_dist.axvline(abs(avg_loss) / 10000, color="#c0392b", lw=2.5, ls="--",
                label=f"負け平均 {abs(avg_loss)/10000:.2f}万円")

big = wins[wins > wins.mean() * 3]
if len(big) > 0:
    ax_dist.annotate(
        f"大勝ち {len(big)}件\n最大 {wins.max()/10000:.1f}万円\n→ 平均値では消える",
        xy=(wins.max() / 10000, 0.5),
        xytext=(wins.max() / 10000 * 0.5, 60),
        color="#f39c12", fontsize=11, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#f39c12", lw=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="#2c1810", ec="#f39c12", alpha=0.9),
    )

ax_dist.set_title(
    "実際のトレードP&L分布（FX USDJPY 5分足）  ─  右裾の大勝ちが平均値シミュレーションでは無視される",
    color="#eee", fontsize=13, fontweight="bold", pad=10)
ax_dist.set_xlabel("損益の絶対値（万円）", color="#ccc", fontsize=11)
ax_dist.set_ylabel("件数", color="#ccc", fontsize=11)
ax_dist.legend(fontsize=9.5, facecolor="#222", labelcolor="white",
               loc="upper right", framealpha=0.9)

# ─── 左下: エクイティカーブ比較 ──────────────────────────────────
cs_b = np.sort(curves_boot,  axis=0)
cs_f = np.sort(curves_fixed, axis=0)

ax_eq.fill_between(x, cs_b[int(0.10*N_SIMULATIONS)]/10000,
                      cs_b[int(0.90*N_SIMULATIONS)]/10000,
                   color="#e74c3c", alpha=0.20, label="実際分布 10〜90%ile")
ax_eq.plot(x, cs_b[int(0.50*N_SIMULATIONS)]/10000,
           color="#e74c3c", lw=2.5, label=f"実際分布 中央値")

ax_eq.fill_between(x, cs_f[int(0.10*N_SIMULATIONS)]/10000,
                      cs_f[int(0.90*N_SIMULATIONS)]/10000,
                   color="#3498db", alpha=0.20, label="固定平均 10〜90%ile")
ax_eq.plot(x, cs_f[int(0.50*N_SIMULATIONS)]/10000,
           color="#3498db", lw=2.5, label=f"固定平均 中央値")

ax_eq.axhline(INITIAL_CAP/10000, color="#888", lw=1, ls=":")
ax_eq.set_title("エクイティカーブ比較", color="#eee", fontsize=12, fontweight="bold")
ax_eq.set_xlabel("トレード数", color="#ccc", fontsize=11)
ax_eq.set_ylabel("資産（万円）", color="#ccc", fontsize=11)
ax_eq.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.9)

# ─── 右下: 最終収益率分布比較 ─────────────────────────────────────
all_min = min(ret_fixed.min(), ret_boot.min())
all_max = max(ret_fixed.max(), ret_boot.max())
bins_all = np.linspace(all_min, all_max, 55)

ax_hist.hist(ret_fixed, bins=bins_all, color="#3498db", alpha=0.65,
             label=f"固定平均  中央値{np.median(ret_fixed):+.1f}%")
ax_hist.hist(ret_boot,  bins=bins_all, color="#e74c3c", alpha=0.65,
             label=f"実際分布  中央値{np.median(ret_boot):+.1f}%")
ax_hist.axvline(np.median(ret_fixed), color="#3498db", lw=2.5, ls="--")
ax_hist.axvline(np.median(ret_boot),  color="#e74c3c", lw=2.5, ls="--")
ax_hist.axvline(np.percentile(ret_fixed,90), color="#3498db", lw=1.5, ls=":",
                label=f"固定平均 上位10% {np.percentile(ret_fixed,90):+.1f}%")
ax_hist.axvline(np.percentile(ret_boot, 90), color="#e74c3c", lw=1.5, ls=":",
                label=f"実際分布 上位10% {np.percentile(ret_boot,90):+.1f}%")
ax_hist.axvline(0, color="#888", lw=1, ls=":")
ax_hist.set_title("最終収益率 分布比較（1,000トレード後）",
                  color="#eee", fontsize=12, fontweight="bold")
ax_hist.set_xlabel("収益率（%）", color="#ccc", fontsize=11)
ax_hist.set_ylabel("ケース数", color="#ccc", fontsize=11)
ax_hist.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.9)

# ─── タイトル ─────────────────────────────────────────────────────
fig.suptitle(
    f"FX USDJPY 5分足 レンジブレイク  モンテカルロシミュレーション（全{len(df):,}件より）\n"
    f"勝率{win_rate*100:.1f}%　平均利益{avg_win:+,.0f}円　"
    f"平均損失{avg_loss:,.0f}円　PF{wins.sum()/np.abs(losses).sum():.2f}　"
    f"1pip={PIP_VALUE}円（100万円 / レバ10× / 6.7万通貨）",
    color="#eee", fontsize=12, fontweight="bold", y=0.97
)

out = Path("monte_carlo_fx5min.png")
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="#0f0f23")
plt.close(fig)
print(f"\n  グラフ保存: {out.resolve()}")
