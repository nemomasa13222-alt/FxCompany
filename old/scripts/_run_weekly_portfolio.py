# -*- coding: utf-8 -*-
"""
週次複合スコアランキング → TOP6ペア×セッション選択バックテスト

Score = 期待値 × PF × sqrt(Trades) × Omega × Tail × RecentFactor × CostTolerance ÷ (1 + MaxDD)

定義:
  期待値        = mean(r_mult)            平均Rレシオ（リスク正規化済み）
  PF            = 総利益 / |総損失|
  sqrt(N)       = sqrt(トレード数)         サンプル信頼性補正
  Omega         = Σ正r / Σ|負r|
  Tail          = P95(r) / |P5(r)|        右裾の厚さ
  RecentFactor  = PF(直近1週) / PF(直近4週)  モメンタム [0.3, 3.0]
  CostTolerance = mean(pnl) / (mean(pnl) + COST_EST)  コスト耐性
  MaxDD         = 4週窓内最大DD（資金比）

3方式比較: 全組み合わせ / 前週PF TOP6 / 複合スコア TOP6
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.gridspec import GridSpec

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

ROOT    = Path(__file__).parent
IN_DIR  = ROOT / "docs" / "full_analysis"
OUT_DIR = ROOT / "docs" / "weekly_portfolio"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CAPITAL      = 1_000_000
TOP_N        = 6
WINDOW_WEEKS = 4      # メトリクス計算ウィンドウ（週）
MIN_TRADES   = 5      # 最低トレード数（これ未満はスコア0）
COST_EST     = 2_000  # 想定コスト JPY/trade（スプレッド+スリッページ）

# ── データ読込
print("データ読込中...")
df = pd.read_csv(IN_DIR / "bt_trades.csv", encoding="utf-8-sig")
df["signal_bar"] = pd.to_datetime(df["signal_bar"])
df["session"] = df["session"].str.strip()
df["combo"] = df["pair"] + "_" + df["session"]

iso = df["signal_bar"].dt.isocalendar()
df["year_week"] = iso["year"].astype(str) + "_" + iso["week"].astype(str).str.zfill(2)

weeks      = sorted(df["year_week"].unique())
combos_all = sorted(df["combo"].unique())
print(f"総週数: {len(weeks)}  コンビ数: {len(combos_all)}")

# ── スコア計算関数
def calc_pf(pnl):
    gains  = pnl[pnl > 0].sum()
    losses = pnl[pnl <= 0].abs().sum()
    if len(pnl) == 0: return np.nan
    if losses == 0:   return 999.0 if gains > 0 else np.nan
    return gains / losses

def calc_score(trades_w, trades_prev1):
    """複合スコアを計算。スコア0=除外"""
    if len(trades_w) < MIN_TRADES:
        return 0.0, {}

    pnl = trades_w["pnl_yen"].values
    r   = trades_w["r_mult"].values

    ev = float(np.mean(r))
    if ev <= 0:
        return 0.0, {}

    pf_4w = calc_pf(pd.Series(pnl))
    if pf_4w is None or np.isnan(pf_4w) or pf_4w <= 0:
        return 0.0, {}

    sqrt_n = float(np.sqrt(len(trades_w)))

    omega_pos = float(r[r > 0].sum())
    omega_neg = float(np.abs(r[r <= 0].sum()))
    omega = omega_pos / omega_neg if omega_neg > 1e-10 else 999.0

    p95 = float(np.percentile(r, 95))
    p5  = float(np.percentile(r, 5))
    tail = p95 / abs(p5) if abs(p5) > 1e-10 else 1.0

    cum   = np.cumsum(pnl)
    max_dd = float((np.maximum.accumulate(cum) - cum).max()) / CAPITAL
    max_dd = max(max_dd, 0.0)

    mean_pnl  = float(np.mean(pnl))
    cost_tol  = float(np.clip(mean_pnl / (mean_pnl + COST_EST), 0.01, 1.0)) \
                if mean_pnl > 0 else 0.01

    # RecentFactor = PF(直近1週) / PF(4週)
    pf_1w = calc_pf(trades_prev1["pnl_yen"]) if len(trades_prev1) >= 1 else np.nan
    if pf_1w is None or np.isnan(pf_1w) or pf_4w <= 0:
        recent = 1.0
    else:
        recent = float(np.clip(pf_1w / pf_4w, 0.3, 3.0))

    score = (ev * pf_4w * sqrt_n * omega * tail * recent * cost_tol) / (1 + max_dd)
    score = max(score, 0.0)

    components = {
        "EV": ev, "PF": pf_4w, "sqrtN": sqrt_n,
        "Omega": omega, "Tail": tail,
        "RecentF": recent, "CostTol": cost_tol,
        "MaxDD": max_dd, "Score": score,
    }
    return score, components

# ── ウォークフォワード: 3方式並行
START_I = WINDOW_WEEKS  # 十分な履歴が取れる週から開始

sel_pf_parts    = []  # 前週PF TOP6
sel_sc_parts    = []  # 複合スコア TOP6
weekly_log      = []  # 選択履歴
score_detail    = []  # スコア構成要素

for i, week in enumerate(weeks):
    if i < START_I:
        continue

    window_weeks = weeks[i - WINDOW_WEEKS:i]
    prev_week    = weeks[i - 1]

    # ── 前週PF方式
    pf_scores = {}
    for combo in combos_all:
        p1 = df[(df["year_week"] == prev_week) & (df["combo"] == combo)]
        pf_scores[combo] = calc_pf(p1["pnl_yen"]) or 0.0

    top6_pf = sorted(pf_scores, key=lambda c: pf_scores[c], reverse=True)[:TOP_N]
    top6_pf = [c for c in top6_pf if pf_scores[c] > 0]

    mask_pf = (df["year_week"] == week) & (df["combo"].isin(top6_pf))
    sel_pf_parts.append(df[mask_pf].copy())

    # ── 複合スコア方式
    sc_scores = {}
    for combo in combos_all:
        w4 = df[(df["year_week"].isin(window_weeks)) & (df["combo"] == combo)]
        p1 = df[(df["year_week"] == prev_week) & (df["combo"] == combo)]
        sc, comp = calc_score(w4, p1)
        sc_scores[combo] = sc
        if sc > 0:
            score_detail.append({"week": week, "combo": combo, **comp})

    top6_sc = sorted(sc_scores, key=lambda c: sc_scores[c], reverse=True)[:TOP_N]
    top6_sc = [c for c in top6_sc if sc_scores[c] > 0]

    mask_sc = (df["year_week"] == week) & (df["combo"].isin(top6_sc))
    sel_sc_parts.append(df[mask_sc].copy())

    weekly_log.append({
        "week":    week,
        "top6_pf": "|".join(top6_pf),
        "top6_sc": "|".join(top6_sc),
        "n_pf":    int(mask_pf.sum()),
        "n_sc":    int(mask_sc.sum()),
    })

# 開始週を揃えて公平比較
valid_weeks = weeks[START_I:]
df_base = df[df["year_week"].isin(valid_weeks)].sort_values("signal_bar")
df_pf   = pd.concat(sel_pf_parts, ignore_index=True).sort_values("signal_bar") \
          if sel_pf_parts else pd.DataFrame(columns=df.columns)
df_sc   = pd.concat(sel_sc_parts, ignore_index=True).sort_values("signal_bar") \
          if sel_sc_parts else pd.DataFrame(columns=df.columns)

# ── 統計サマリー
def summary(d, label):
    if len(d) == 0:
        return dict(label=label, n=0, win_rate=0, pf=0, total_pnl=0, max_dd=0, dd_pct=0)
    w  = d[d["pnl_yen"] > 0]
    l  = d[d["pnl_yen"] <= 0]
    gp = w["pnl_yen"].sum()
    gl = l["pnl_yen"].abs().sum()
    pf = gp / gl if gl > 0 else float("inf")
    cum = d["pnl_yen"].cumsum()
    dd  = (cum.cummax() - cum).max()
    return dict(label=label, n=len(d),
                win_rate=len(w)/len(d)*100, pf=pf,
                total_pnl=d["pnl_yen"].sum(),
                max_dd=dd, dd_pct=dd/CAPITAL*100)

sv = {
    "base": summary(df_base, "全組み合わせ"),
    "pf":   summary(df_pf,   "前週PF TOP6"),
    "sc":   summary(df_sc,   "複合スコア TOP6"),
}

labels_k = {"n":"トレード数","win_rate":"勝率(%)","pf":"PF",
             "total_pnl":"総損益(円)","max_dd":"最大DD(円)","dd_pct":"最大DD(%)"}
fmts_k   = {"n":",.0f","win_rate":".1f","pf":".3f",
             "total_pnl":"+,.0f","max_dd":",.0f","dd_pct":".1f"}

print("\n" + "=" * 75)
print(f"  {'指標':22s}  {'全組み合わせ':>14s}  {'前週PF TOP6':>12s}  {'複合スコア TOP6':>14s}")
print("=" * 75)
for k in labels_k:
    b = format(sv["base"][k], fmts_k[k])
    p = format(sv["pf"][k],   fmts_k[k])
    s = format(sv["sc"][k],   fmts_k[k])
    print(f"  {labels_k[k]:22s}  {b:>14s}  {p:>12s}  {s:>14s}")

# コンビ別選択回数（複合スコア）
df_log = pd.DataFrame(weekly_log)
sc_counts = pd.Series(
    [c for row in df_log["top6_sc"].str.split("|") for c in row if c]
).value_counts()
print("\n── コンビ別選択回数 複合スコア TOP10 ──")
for combo, cnt in sc_counts.head(10).items():
    print(f"  {combo:45s}  {cnt}週")

# ── CSV保存
df_sc.to_csv(OUT_DIR / "composite_trades.csv", index=False, encoding="utf-8-sig")
df_log.to_csv(OUT_DIR / "weekly_selection.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(score_detail).to_csv(OUT_DIR / "score_detail.csv", index=False, encoding="utf-8-sig")

sv_df = pd.DataFrame([sv["base"], sv["pf"], sv["sc"]])
sv_df.to_csv(OUT_DIR / "summary_comparison.csv", index=False, encoding="utf-8-sig")

# ── グラフ
fig = plt.figure(figsize=(18, 20))
fig.patch.set_facecolor("#f8f9fa")
gs  = GridSpec(3, 2, figure=fig, hspace=0.4, wspace=0.35)
fig.suptitle(
    "週次TOP6選択バックテスト  ─  3方式比較\n"
    "Score = 期待値×PF×√N×Omega×Tail×RecentFactor×CostTolerance ÷ (1+MaxDD)",
    fontsize=13, fontweight="bold"
)

palette = {"base": "#95a5a6", "pf": "#2980b9", "sc": "#e74c3c"}
lw_map  = {"base": 1.5,       "pf": 1.8,       "sc": 2.3}

# Panel 1: 累積損益
ax1 = fig.add_subplot(gs[0, :])
ax1.set_facecolor("#f8f8f8")
ax1.axhline(0, color="#333", lw=0.8, ls="--", alpha=0.5)
for key, d in [("base", df_base), ("pf", df_pf), ("sc", df_sc)]:
    if len(d) == 0: continue
    cum = d["pnl_yen"].cumsum().reset_index(drop=True)
    sv_ = sv[key]
    lbl = (f"{sv_['label']}  n={sv_['n']:,}  PF={sv_['pf']:.3f}  "
           f"DD={sv_['dd_pct']:.1f}%  {sv_['total_pnl']:+,.0f}円")
    ax1.plot(cum, color=palette[key], lw=lw_map[key], label=lbl,
             alpha=0.9 if key == "sc" else 0.7)
    if key == "sc":
        ax1.fill_between(range(len(cum)), cum, color=palette[key], alpha=0.05)
ax1.set_title("累積損益比較", fontsize=11, fontweight="bold")
ax1.set_ylabel("累積損益 (円)", fontsize=9)
ax1.legend(fontsize=8.5, framealpha=0.92)
ax1.grid(axis="y", alpha=0.2)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

# Panel 2: DD比較
ax2 = fig.add_subplot(gs[1, 0])
ax2.set_facecolor("#f8f8f8")
for key, d in [("base", df_base), ("pf", df_pf), ("sc", df_sc)]:
    if len(d) == 0: continue
    cum = d["pnl_yen"].cumsum().reset_index(drop=True)
    dd  = (cum.cummax() - cum) / CAPITAL * 100
    ax2.fill_between(range(len(dd)), -dd, color=palette[key], alpha=0.4,
                     label=f"{sv[key]['label']}  最大DD={sv[key]['dd_pct']:.1f}%")
ax2.set_title("ドローダウン比較", fontsize=11, fontweight="bold")
ax2.set_ylabel("DD (%)", fontsize=9)
ax2.legend(fontsize=8.5, framealpha=0.92)
ax2.grid(axis="y", alpha=0.2)

# Panel 3: コンビ別選択回数（複合スコア）
ax3 = fig.add_subplot(gs[1, 1])
ax3.set_facecolor("#f8f8f8")
top20 = sc_counts.head(20).sort_values()
q75   = top20.quantile(0.75)
colors_ = ["#e74c3c" if v >= q75 else "#e67e22" if v >= top20.median() else "#95a5a6"
           for v in top20]
bars = ax3.barh(range(len(top20)), top20.values, color=colors_,
                edgecolor="white", linewidth=0.4)
ax3.set_yticks(range(len(top20)))
ax3.set_yticklabels(top20.index, fontsize=7)
ax3.set_title(f"コンビ別選択回数（複合スコア）/ 総{len(valid_weeks)}週",
              fontsize=10, fontweight="bold")
ax3.set_xlabel("選択週数", fontsize=8)
for bar, val in zip(bars, top20.values):
    ax3.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
             str(val), va="center", fontsize=7.5)
ax3.grid(axis="x", alpha=0.2)

# Panel 4: スコア構成要素の箱ひげ図（選択されたコンビ）
ax4 = fig.add_subplot(gs[2, :])
ax4.set_facecolor("#f8f8f8")
if score_detail:
    df_sd = pd.DataFrame(score_detail)
    # 選択頻度上位8コンビのスコア推移
    top8_combos = sc_counts.head(8).index.tolist()
    df_sd_top = df_sd[df_sd["combo"].isin(top8_combos)]
    plot_data  = [df_sd_top[df_sd_top["combo"] == c]["Score"].values
                  for c in top8_combos]
    plot_data  = [x for x in plot_data if len(x) > 0]
    short_labels = [c.replace("_", "\n") for c in top8_combos if
                    len(df_sd_top[df_sd_top["combo"] == c]) > 0]
    bp = ax4.boxplot(plot_data, labels=short_labels, patch_artist=True,
                     medianprops=dict(color="#e74c3c", lw=2))
    for patch in bp["boxes"]:
        patch.set_facecolor("#ddeeff")
    ax4.set_title("選択頻度上位コンビのスコア分布（週次）", fontsize=11, fontweight="bold")
    ax4.set_ylabel("複合スコア", fontsize=9)
    ax4.tick_params(axis="x", labelsize=7)
    ax4.grid(axis="y", alpha=0.2)

out_path = OUT_DIR / "weekly_composite_backtest.png"
fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#f8f9fa")
plt.close(fig)
print(f"\n図保存: {out_path}")
print(f"保存先: {OUT_DIR}")
print("完了")
