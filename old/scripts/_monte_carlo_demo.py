# -*- coding: utf-8 -*-
"""
株デモ バックテストOOS統計 → モンテカルロシミュレーション
1000トレード × 1000ケース
"""
import sys, glob
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

# 日本語フォント
try:
    fm.fontManager.addfont(r"C:\Windows\Fonts\YuGothM.ttc")
    plt.rcParams["font.family"] = fm.FontProperties(fname=r"C:\Windows\Fonts\YuGothM.ttc").get_name()
except Exception:
    pass

# ── OSSデータ読み込み ─────────────────────────────────────────────
ps_files = sorted(glob.glob("japan_stocks/results/backtest_v2/per_sector_full_*.csv"))
ps = pd.read_csv(ps_files[-1], encoding="utf-8-sig")
ps["exit_date"] = pd.to_datetime(ps["exit_date"])

OOS_START     = "2024-01-01"
INITIAL_CAP   = 1_000_000
N_TRADES      = 1000
N_SIMULATIONS = 1000
DD_STOP       = 25.0   # 本番停止ライン(%)
SEED          = 42

oos = ps.copy()  # IS + OOS 全期間

# ── 統計算出 ─────────────────────────────────────────────────────
pnl      = oos["net_pnl_jpy"]
wins     = pnl[pnl > 0]
losses   = pnl[pnl < 0]

win_rate = len(wins) / len(pnl)
avg_win  = float(wins.mean())
avg_loss = float(losses.mean())   # 負の値
n_oos    = len(pnl)

print("=" * 60)
print("  バックテストOOS 基礎統計")
print("=" * 60)
print(f"  期間     : IS + OOS 全期間（2022-01-01 ~ 2026-05-20）")
print(f"  件数     : {n_oos}")
print(f"  勝率     : {win_rate*100:.1f}%  ({len(wins)}勝{len(losses)}敗)")
print(f"  平均利益 : {avg_win:+,.0f}円")
print(f"  平均損失 : {avg_loss:+,.0f}円")
gp = wins.sum(); gl = losses.abs().sum()
print(f"  PF       : {gp/gl:.2f}")
print(f"  期待値/T : {pnl.mean():+,.0f}円")
print()

# ── モンテカルロシミュレーション ─────────────────────────────────
np.random.seed(SEED)
rng = np.random.default_rng(SEED)

final_equity  = np.zeros(N_SIMULATIONS)
max_dd_arr    = np.zeros(N_SIMULATIONS)
bust_arr      = np.zeros(N_SIMULATIONS, dtype=bool)
all_curves    = np.zeros((N_SIMULATIONS, N_TRADES + 1))

for sim in range(N_SIMULATIONS):
    # 各トレードを勝ち/負けでランダム決定
    outcomes = rng.random(N_TRADES) < win_rate
    pnls     = np.where(outcomes, avg_win, avg_loss)

    equity   = np.zeros(N_TRADES + 1)
    equity[0]= INITIAL_CAP
    bust     = False

    for i, p in enumerate(pnls):
        equity[i + 1] = equity[i] + p
        # 資金がゼロ以下になったら破産
        if equity[i + 1] <= 0:
            equity[i + 1:] = 0
            bust = True
            break

    all_curves[sim] = equity

    # 最大DD計算
    peak  = np.maximum.accumulate(equity)
    dd    = (peak - equity) / peak * 100
    max_dd_arr[sim]   = dd.max()
    final_equity[sim] = equity[-1]
    bust_arr[sim]     = bust or (max_dd_arr[sim] >= DD_STOP)

# ── 集計 ─────────────────────────────────────────────────────────
n_profit = (final_equity > INITIAL_CAP).sum()
n_bust   = bust_arr.sum()
p10, p25, p50, p75, p90 = np.percentile(final_equity, [10,25,50,75,90])
dd10, dd25, dd50, dd75, dd90 = np.percentile(max_dd_arr, [10,25,50,75,90])

print("=" * 60)
print(f"  モンテカルロ結果  ({N_SIMULATIONS}ケース × {N_TRADES}トレード)")
print("=" * 60)
print(f"  初期資本     : {INITIAL_CAP:,}円")
print()
print(f"  【最終資産 分布】")
print(f"  下位10%  : {p10:>12,.0f}円  ({(p10-INITIAL_CAP)/INITIAL_CAP*100:+.1f}%)")
print(f"  下位25%  : {p25:>12,.0f}円  ({(p25-INITIAL_CAP)/INITIAL_CAP*100:+.1f}%)")
print(f"  中央値   : {p50:>12,.0f}円  ({(p50-INITIAL_CAP)/INITIAL_CAP*100:+.1f}%)")
print(f"  上位25%  : {p75:>12,.0f}円  ({(p75-INITIAL_CAP)/INITIAL_CAP*100:+.1f}%)")
print(f"  上位10%  : {p90:>12,.0f}円  ({(p90-INITIAL_CAP)/INITIAL_CAP*100:+.1f}%)")
print()
print(f"  黒字ケース : {n_profit}/{N_SIMULATIONS} ({n_profit/N_SIMULATIONS*100:.1f}%)")
print(f"  DD25%超え  : {n_bust}/{N_SIMULATIONS} ({n_bust/N_SIMULATIONS*100:.1f}%)")
print()
print(f"  【最大DD 分布】")
print(f"  中央値   : {dd50:.1f}%")
print(f"  上位25%  : {dd75:.1f}%")
print(f"  上位10%  : {dd90:.1f}%")
print(f"  DD>=25%  : {(max_dd_arr>=25).sum()}/{N_SIMULATIONS}ケース ({(max_dd_arr>=25).sum()/N_SIMULATIONS*100:.1f}%)")

# ── グラフ生成（2×2レイアウト） ──────────────────────────────────
fig = plt.figure(figsize=(20, 14))
fig.patch.set_facecolor("#0f0f23")

gs  = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.3,
                        left=0.07, right=0.96, top=0.90, bottom=0.07)
ax1 = fig.add_subplot(gs[0, :])   # 上段全幅: エクイティカーブ
ax2 = fig.add_subplot(gs[1, 0])   # 左下: 最終資産分布
ax3 = fig.add_subplot(gs[1, 1])   # 右下: 最大DD分布

for ax in [ax1, ax2, ax3]:
    ax.set_facecolor("#1a1a3e")
    ax.tick_params(colors="#ccc", labelsize=10)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")
    ax.grid(alpha=0.15, color="#555")

x = np.arange(N_TRADES + 1)

# ─── 上段: エクイティカーブ ────────────────────────────────────────
# 全曲線を薄く描画
for i in range(N_SIMULATIONS):
    col = "#2ecc71" if final_equity[i] >= INITIAL_CAP else "#e74c3c"
    ax1.plot(x, all_curves[i] / 10000, color=col, alpha=0.025, lw=0.6)

# パーセンタイル帯
curve_sorted = np.sort(all_curves, axis=0)
p10_curve  = curve_sorted[int(0.10 * N_SIMULATIONS)]
p25_curve  = curve_sorted[int(0.25 * N_SIMULATIONS)]
p50_curve  = curve_sorted[int(0.50 * N_SIMULATIONS)]
p75_curve  = curve_sorted[int(0.75 * N_SIMULATIONS)]
p90_curve  = curve_sorted[int(0.90 * N_SIMULATIONS)]

ax1.fill_between(x, p10_curve/10000, p90_curve/10000,
                 color="#3498db", alpha=0.20, label="10〜90%ile帯")
ax1.fill_between(x, p25_curve/10000, p75_curve/10000,
                 color="#3498db", alpha=0.35, label="25〜75%ile帯")
ax1.plot(x, p50_curve/10000, color="#f1c40f", lw=2.5, label="中央値", zorder=6)
ax1.plot(x, p10_curve/10000, color="#e74c3c", lw=1.5, ls="--", label="下位10%", zorder=5)
ax1.plot(x, p90_curve/10000, color="#2ecc71", lw=1.5, ls="--", label="上位10%", zorder=5)
ax1.axhline(INITIAL_CAP/10000, color="#888", lw=1.2, ls=":", label="初期資本100万")

ax1.set_title(f"エクイティカーブ（{N_SIMULATIONS}ケース × {N_TRADES}トレード）",
              color="#eee", fontsize=13, fontweight="bold", pad=10)
ax1.set_xlabel("トレード数", color="#ccc", fontsize=11)
ax1.set_ylabel("資産（万円）", color="#ccc", fontsize=11)
ax1.legend(fontsize=9, facecolor="#222", labelcolor="white",
           loc="upper left", framealpha=0.8)

# 右軸に収益率
ax1r = ax1.twinx()
ax1r.set_facecolor("#1a1a3e")
ymin, ymax = ax1.get_ylim()
ax1r.set_ylim((ymin - 100)*100/INITIAL_CAP*10000,
              (ymax - 100)*100/INITIAL_CAP*10000)
ax1r.set_ylabel("収益率（%）", color="#ccc", fontsize=11)
ax1r.tick_params(colors="#ccc")

# ─── 左下: 最終資産 ヒストグラム ──────────────────────────────────
ret_pct = (final_equity - INITIAL_CAP) / INITIAL_CAP * 100
bins_r  = np.linspace(ret_pct.min(), ret_pct.max(), 40)

profit_m = ret_pct >= 0
ax2.hist(ret_pct[profit_m],  bins=bins_r, color="#2ecc71", alpha=0.85,
         label=f"黒字 {profit_m.sum()}件")
ax2.hist(ret_pct[~profit_m], bins=bins_r, color="#e74c3c", alpha=0.85,
         label=f"赤字 {(~profit_m).sum()}件")
ax2.axvline(0,        color="#888",    lw=1.5, ls=":",  zorder=5)
ax2.axvline(np.percentile(ret_pct, 50), color="#f1c40f", lw=2.5,
            label=f"中央値 {np.percentile(ret_pct,50):.1f}%", zorder=6)
ax2.axvline(np.percentile(ret_pct, 10), color="#e74c3c", lw=1.5, ls="--",
            label=f"下位10% {np.percentile(ret_pct,10):.1f}%")
ax2.axvline(np.percentile(ret_pct, 90), color="#2ecc71", lw=1.5, ls="--",
            label=f"上位10% {np.percentile(ret_pct,90):.1f}%")

ax2.set_title(f"最終収益率 分布（{N_TRADES}トレード後）",
              color="#eee", fontsize=12, fontweight="bold")
ax2.set_xlabel("収益率（%）", color="#ccc", fontsize=11)
ax2.set_ylabel("ケース数", color="#ccc", fontsize=11)
ax2.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.8)

# ─── 右下: 最大DD ヒストグラム ────────────────────────────────────
ax3.hist(max_dd_arr, bins=50, color="#3498db", alpha=0.85, edgecolor="#111")
ax3.axvline(DD_STOP, color="#e74c3c", lw=2.5, ls="--",
            label=f"本番停止ライン {DD_STOP}%", zorder=6)
ax3.axvline(dd50,    color="#f1c40f", lw=2.5,
            label=f"中央値 {dd50:.1f}%", zorder=6)
ax3.axvline(dd90,    color="#ff9800", lw=1.5, ls="--",
            label=f"上位10% {dd90:.1f}%")

ax3.set_title("最大ドローダウン 分布",
              color="#eee", fontsize=12, fontweight="bold")
ax3.set_xlabel("最大DD（%）", color="#ccc", fontsize=11)
ax3.set_ylabel("ケース数", color="#ccc", fontsize=11)
ax3.legend(fontsize=9, facecolor="#222", labelcolor="white", framealpha=0.8)

# ─── タイトル ─────────────────────────────────────────────────────
fig.suptitle(
    f"株デモ モンテカルロシミュレーション（IS+OOS 1,003件より）\n"
    f"勝率 {win_rate*100:.1f}%　平均利益 +{avg_win:,.0f}円　"
    f"平均損失 {avg_loss:,.0f}円　PF {gp/gl:.2f}　"
    f"期待値 +{pnl.mean():,.0f}円/T",
    color="#eee", fontsize=12, fontweight="bold", y=0.97
)

out = Path("monte_carlo_result.png")
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="#0f0f23")
plt.close(fig)
print(f"\n  グラフ保存: {out.resolve()}")
print("=" * 60)
