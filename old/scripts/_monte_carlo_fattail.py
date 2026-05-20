# -*- coding: utf-8 -*-
"""
固定平均値シミュレーション vs 実際の分布（ブートストラップ）比較
「平均値ベースより実態は有利」を可視化
"""
import sys, glob
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

# ── データ読み込み ─────────────────────────────────────────────────
ps = pd.read_csv(
    sorted(glob.glob("japan_stocks/results/backtest_v2/per_sector_full_*.csv"))[-1],
    encoding="utf-8-sig"
)
actual_pnl = ps["net_pnl_jpy"].values

INITIAL_CAP   = 1_000_000
N_TRADES      = 1000
N_SIMULATIONS = 1000
SEED          = 42
rng = np.random.default_rng(SEED)

wins   = actual_pnl[actual_pnl > 0]
losses = actual_pnl[actual_pnl < 0]
win_rate = len(wins) / len(actual_pnl)
avg_win  = wins.mean()
avg_loss = losses.mean()

# ── シミュレーション①: 固定平均 ───────────────────────────────────
final_fixed  = np.zeros(N_SIMULATIONS)
curves_fixed = np.zeros((N_SIMULATIONS, N_TRADES + 1))
for sim in range(N_SIMULATIONS):
    w = rng.random(N_TRADES) < win_rate
    p = np.where(w, avg_win, avg_loss)
    eq = np.concatenate([[INITIAL_CAP], INITIAL_CAP + np.cumsum(p)])
    curves_fixed[sim] = eq
    final_fixed[sim]  = eq[-1]

# ── シミュレーション②: ブートストラップ（実際の分布からサンプリング）
rng2 = np.random.default_rng(SEED + 1)
final_boot  = np.zeros(N_SIMULATIONS)
curves_boot = np.zeros((N_SIMULATIONS, N_TRADES + 1))
for sim in range(N_SIMULATIONS):
    w      = rng2.random(N_TRADES) < win_rate
    w_samp = rng2.choice(wins,   size=N_TRADES, replace=True)
    l_samp = rng2.choice(losses, size=N_TRADES, replace=True)
    p      = np.where(w, w_samp, l_samp)
    eq     = np.concatenate([[INITIAL_CAP], INITIAL_CAP + np.cumsum(p)])
    curves_boot[sim] = eq
    final_boot[sim]  = eq[-1]

ret_fixed = (final_fixed - INITIAL_CAP) / INITIAL_CAP * 100
ret_boot  = (final_boot  - INITIAL_CAP) / INITIAL_CAP * 100

print(f"固定平均  中央値: {np.median(ret_fixed):+.1f}%  上位10%: {np.percentile(ret_fixed,90):+.1f}%")
print(f"実際分布  中央値: {np.median(ret_boot):+.1f}%  上位10%: {np.percentile(ret_boot,90):+.1f}%")

# ── グラフ（2行2列） ───────────────────────────────────────────────
fig = plt.figure(figsize=(20, 14))
fig.patch.set_facecolor("#0f0f23")
gs = gridspec.GridSpec(2, 2, figure=fig,
                       hspace=0.40, wspace=0.30,
                       left=0.07, right=0.96, top=0.88, bottom=0.07)

ax_dist  = fig.add_subplot(gs[0, :])   # 上段全幅: 実際のP&L分布
ax_eq    = fig.add_subplot(gs[1, 0])   # 左下: エクイティカーブ比較
ax_hist  = fig.add_subplot(gs[1, 1])   # 右下: 最終収益率分布比較

BG = "#1a1a3e"
for ax in [ax_dist, ax_eq, ax_hist]:
    ax.set_facecolor(BG)
    ax.tick_params(colors="#ccc", labelsize=10)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")
    ax.grid(alpha=0.15, color="#555")

# ─── 上段: 実際のP&L分布（対数スケール）────────────────────────────
ax = ax_dist

# 勝ちトレード
ax.hist(wins / 10000, bins=60, color="#2ecc71", alpha=0.85,
        label=f"勝ちトレード {len(wins)}件  平均+{avg_win/10000:.2f}万円")
# 負けトレード（反転して同じ軸に）
ax.hist(np.abs(losses) / 10000, bins=30, color="#e74c3c", alpha=0.70,
        label=f"負けトレード {len(losses)}件  平均{avg_loss/10000:.2f}万円")

ax.axvline(avg_win   / 10000, color="#27ae60", lw=2.5, ls="--",
           label=f"勝ち平均 {avg_win/10000:.2f}万円（シミュレーションで使う値）")
ax.axvline(abs(avg_loss) / 10000, color="#c0392b", lw=2.5, ls="--",
           label=f"負け平均 {abs(avg_loss)/10000:.2f}万円（シミュレーションで使う値）")

# 大勝ちアノテーション（右裾）
big_wins = wins[wins > 20000]
if len(big_wins) > 0:
    ax.annotate(
        f"大勝ち {len(big_wins)}件\n（例: +{wins.max()/10000:.1f}万円）\n→ 平均値シミュレーションでは無視される！",
        xy=(wins.max() / 10000, 1),
        xytext=(wins.max() / 10000 * 0.55, 25),
        color="#f39c12", fontsize=11, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#f39c12", lw=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="#2c1810", ec="#f39c12", alpha=0.9),
    )

ax.set_title("実際のトレードP&L分布  ─  右裾の「大勝ち」が平均値シミュレーションで消える",
             color="#eee", fontsize=13, fontweight="bold", pad=10)
ax.set_xlabel("損益の絶対値（万円）", color="#ccc", fontsize=11)
ax.set_ylabel("件数", color="#ccc", fontsize=11)
ax.legend(fontsize=9.5, facecolor="#222", labelcolor="white",
          loc="upper right", framealpha=0.9)

# ─── 左下: エクイティカーブ比較 ─────────────────────────────────
ax = ax_eq
x  = np.arange(N_TRADES + 1)

# ブートストラップの10〜90%ile帯
cs_b = np.sort(curves_boot, axis=0)
ax.fill_between(x, cs_b[int(0.10*N_SIMULATIONS)]/10000,
                   cs_b[int(0.90*N_SIMULATIONS)]/10000,
                color="#e74c3c", alpha=0.20, label="実際分布 10〜90%ile")
ax.plot(x, cs_b[int(0.50*N_SIMULATIONS)]/10000,
        color="#e74c3c", lw=2.5, label=f"実際分布 中央値")

# 固定平均の10〜90%ile帯
cs_f = np.sort(curves_fixed, axis=0)
ax.fill_between(x, cs_f[int(0.10*N_SIMULATIONS)]/10000,
                   cs_f[int(0.90*N_SIMULATIONS)]/10000,
                color="#3498db", alpha=0.20, label="固定平均 10〜90%ile")
ax.plot(x, cs_f[int(0.50*N_SIMULATIONS)]/10000,
        color="#3498db", lw=2.5, label=f"固定平均 中央値")

ax.axhline(INITIAL_CAP/10000, color="#888", lw=1, ls=":")
ax.set_title("エクイティカーブ比較", color="#eee", fontsize=12, fontweight="bold")
ax.set_xlabel("トレード数", color="#ccc", fontsize=11)
ax.set_ylabel("資産（万円）", color="#ccc", fontsize=11)
ax.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.9)

# ─── 右下: 最終収益率分布比較 ─────────────────────────────────────
ax = ax_hist
all_min = min(ret_fixed.min(), ret_boot.min())
all_max = max(ret_fixed.max(), ret_boot.max())
bins_all = np.linspace(all_min, all_max, 50)

ax.hist(ret_fixed, bins=bins_all, color="#3498db", alpha=0.65,
        label=f"固定平均  中央値{np.median(ret_fixed):+.1f}%")
ax.hist(ret_boot,  bins=bins_all, color="#e74c3c", alpha=0.65,
        label=f"実際分布  中央値{np.median(ret_boot):+.1f}%")

# 各中央値縦線
ax.axvline(np.median(ret_fixed), color="#3498db", lw=2.5, ls="--")
ax.axvline(np.median(ret_boot),  color="#e74c3c", lw=2.5, ls="--")

# 上位10%ラベル
p90_f = np.percentile(ret_fixed, 90)
p90_b = np.percentile(ret_boot,  90)
ax.axvline(p90_f, color="#3498db", lw=1.5, ls=":", alpha=0.7,
           label=f"固定平均 上位10% {p90_f:+.1f}%")
ax.axvline(p90_b, color="#e74c3c", lw=1.5, ls=":", alpha=0.7,
           label=f"実際分布 上位10% {p90_b:+.1f}%")

ax.set_title("最終収益率 分布比較（1,000トレード後）",
             color="#eee", fontsize=12, fontweight="bold")
ax.set_xlabel("収益率（%）", color="#ccc", fontsize=11)
ax.set_ylabel("ケース数", color="#ccc", fontsize=11)
ax.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.9)

# ─── 全体タイトル ─────────────────────────────────────────────────
fig.suptitle(
    "「平均値シミュレーション」は保守的な試算\n"
    "実際の勝ちトレードには大勝ちが含まれるため、右上方向にシフトする可能性が高い",
    color="#f1c40f", fontsize=13, fontweight="bold", y=0.97
)

out = Path("monte_carlo_fattail.png")
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="#0f0f23")
plt.close(fig)
print(f"保存: {out.resolve()}")
