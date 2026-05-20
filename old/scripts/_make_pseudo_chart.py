# -*- coding: utf-8 -*-
"""
リアルUSDJPY vs 疑似USDJPY 比較チャート（参考画像スタイル）
  ・全IS期間（日次）：価格レベル（円）で比較
  ・ズームパネル（20日）：エントリー事例を表示
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass
_p8  = fm.FontProperties(fname=FONT_PATH, size=8)
_p9  = fm.FontProperties(fname=FONT_PATH, size=9)
_p10 = fm.FontProperties(fname=FONT_PATH, size=10)
_p11 = fm.FontProperties(fname=FONT_PATH, size=11)

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "loo_comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_START = "2022-01-01"
IS_END   = "2023-12-31"
TARGET   = "USDJPY"
WINDOW   = 3
THRESHOLD = 0.003

ALL_PAIRS = [
    "USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
    "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD",
]

sys.path.insert(0, str(ROOT))
from fx_market_classifier.features import log_returns, currency_strength
from fx_market_classifier.config   import PAIR_CURRENCIES


def load_data():
    data = {}
    for p in ALL_PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if not f.exists(): continue
        df = pd.read_parquet(f)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        data[p] = df.loc[IS_START:IS_END]
    return data


def build_series(data):
    """LOO版でUSDJPYのreal/pseudo/spread系列を構築"""
    returns = {p: log_returns(df["Close"]) for p, df in data.items()}

    # LOO: USDJPYを除外して通貨強弱を計算
    returns_loo = {p: r for p, r in returns.items() if p != TARGET}
    strength_loo = currency_strength(returns_loo, PAIR_CURRENCIES)

    base, quote = PAIR_CURRENCIES[TARGET]
    usd_s = strength_loo.get(base,  pd.Series(dtype=float))
    jpy_s = strength_loo.get(quote, pd.Series(dtype=float))
    if isinstance(usd_s, pd.DataFrame): usd_s = usd_s.squeeze()
    if isinstance(jpy_s, pd.DataFrame): jpy_s = jpy_s.squeeze()

    synthetic_ret = (usd_s - jpy_s).reindex(returns[TARGET].index)
    actual_ret    = returns[TARGET]

    # cum_spread（シグナル用）
    spread     = actual_ret - synthetic_ret
    cum_spread = spread.rolling(WINDOW, min_periods=1).sum()

    # 価格系列を日次に集約
    close_real  = data[TARGET]["Close"].resample("1D").last().dropna()

    # 疑似価格：synthetic_retを積み上げてrealの起点に合わせる
    synth_daily = synthetic_ret.resample("1D").sum()
    synth_price = (1 + synth_daily.fillna(0)).cumprod()
    synth_price = synth_price / synth_price.iloc[0] * float(close_real.iloc[0])
    synth_price = synth_price.reindex(close_real.index)

    # スプレッド（円単位）
    spread_jpy = (close_real - synth_price).dropna()

    # cum_spreadも日次
    cum_spread_daily = cum_spread.resample("1D").last().dropna()

    return close_real, synth_price, spread_jpy, cum_spread_daily, actual_ret, cum_spread


def find_zoom_window(cum_spread_5min, close_real, n_days=20):
    """エントリーシグナルが最も密な連続20日間を探す"""
    sig = cum_spread_5min[cum_spread_5min.abs() > THRESHOLD]
    if sig.empty:
        s = close_real.index[0]
        return s, s + pd.Timedelta(days=n_days)

    dates = sig.index.normalize().unique()
    dr    = pd.date_range(dates.min(), dates.max(), freq="D")
    cnt   = pd.Series(0, index=dr)
    for d in dates:
        if d in cnt.index: cnt[d] += 1

    best_s, best_c = cnt.index[0], 0
    for i in range(max(1, len(cnt) - n_days)):
        c = cnt.iloc[i:i+n_days].sum()
        if c > best_c:
            best_c = c; best_s = cnt.index[i]

    return best_s, best_s + pd.Timedelta(days=n_days)


def make_chart(data):
    real, synth, spread_jpy, cum_daily, actual_ret, cum_5min = build_series(data)

    # 統計
    corr = real.corr(synth)
    sp_mean  = spread_jpy.mean()
    sp_std   = spread_jpy.std()
    sp_max   = spread_jpy.max()
    sp_min   = spread_jpy.min()

    # ズームウィンドウ
    z_start, z_end = find_zoom_window(cum_5min, real, n_days=20)
    print(f"  ズームウィンドウ: {z_start.date()} 〜 {z_end.date()}")

    # ── フィギュア構成 ──────────────────────────────────────────────
    fig = plt.figure(figsize=(16, 14))
    fig.patch.set_facecolor("#FAFBFF")
    gs = GridSpec(3, 2, figure=fig,
                  height_ratios=[2.5, 1.2, 2.0],
                  hspace=0.35, wspace=0.08)

    ax_full   = fig.add_subplot(gs[0, :])   # 全期間価格比較
    ax_sp_all = fig.add_subplot(gs[1, :])   # 全期間スプレッド
    ax_zoom   = fig.add_subplot(gs[2, 0])   # ズーム価格
    ax_sp_zm  = fig.add_subplot(gs[2, 1])   # ズームcum_spread

    BG   = "#F5F8FF"
    GRID = "#D8E0F0"
    for ax in [ax_full, ax_sp_all, ax_zoom, ax_sp_zm]:
        ax.set_facecolor(BG)
        ax.grid(color=GRID, lw=0.5, alpha=0.8)
        ax.tick_params(colors="#333", labelsize=7)
        for sp in ax.spines.values(): sp.set_color("#C0C8E0")

    # ── パネル1: 全期間価格比較 ───────────────────────────────────
    ax_full.plot(real.index, real.values,  color="#1A5FB4", lw=1.8,
                 label="リアルUSDJPY（終値）", zorder=3)
    ax_full.plot(synth.index, synth.values, color="#CC3333", lw=1.3,
                 ls="--", label="疑似USDJPY (Synthetic)\n（通貨強弱ベース・LOO）",
                 alpha=0.85, zorder=2)
    ax_full.fill_between(real.index, real.values, synth.values,
                          where=(real.values > synth.values),
                          color="#1A5FB4", alpha=0.08, label="Real > Pseudo")
    ax_full.fill_between(real.index, real.values, synth.values,
                          where=(real.values <= synth.values),
                          color="#CC3333", alpha=0.08, label="Pseudo > Real")

    # ズームウィンドウ範囲を矩形でハイライト
    ylim_full = (real.min()*0.995, real.max()*1.005)
    ax_full.add_patch(mpatches.FancyBboxPatch(
        (mdates.date2num(z_start), ylim_full[0]),
        mdates.date2num(z_end) - mdates.date2num(z_start),
        ylim_full[1] - ylim_full[0],
        boxstyle="square,pad=0",
        linewidth=1.5, edgecolor="#FF8800", facecolor="#FF880015", zorder=4))
    ax_full.text(z_start, ylim_full[1]*1.001, "↓ 下段ズーム範囲",
                 fontproperties=_p8, color="#FF8800")

    ax_full.set_title(
        f"疑似ドル円 vs リアルドル円（{IS_START} 〜 {IS_END}）",
        fontproperties=_p11, fontsize=12, pad=10, color="#1A1A2E")
    ax_full.text(0.5, 1.035,
        "通貨強弱（Leave-One-Out方式）による疑似レートと実際のUSDJPYの比較",
        transform=ax_full.transAxes, ha="center",
        fontproperties=_p9, color="#555")
    ax_full.set_ylabel("価格（JPY）", fontproperties=_p9)
    ax_full.legend(prop=_p8, loc="upper left", framealpha=0.9)
    ax_full.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_full.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax_full.get_xticklabels(), rotation=0, ha="center")

    # 相関係数ボックス
    ax_full.text(1.001, 0.98,
        f"相関係数（価格レベル）\n{corr:.2f}\n（非常に高い）",
        transform=ax_full.transAxes, va="top", ha="left",
        fontproperties=_p9, color="#1A5FB4",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                  edgecolor="#1A5FB4", lw=1.5))

    # 統計ボックス
    ax_full.text(1.001, 0.60,
        f"統計情報\n平均乖離率: {sp_mean/real.mean()*100:.2f}%\n"
        f"最大乖離率: {max(sp_max,-sp_min)/real.mean()*100:.2f}%\n"
        f"標準偏差:   {sp_std:.2f} JPY",
        transform=ax_full.transAxes, va="top", ha="left",
        fontproperties=_p8, color="#333",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#F0F4FF",
                  edgecolor="#8899BB", lw=1.0))

    # ── パネル2: 全期間スプレッド（円）───────────────────────────
    pos = spread_jpy.clip(lower=0)
    neg = spread_jpy.clip(upper=0)
    ax_sp_all.fill_between(spread_jpy.index, spread_jpy.values, 0,
                            where=(spread_jpy.values > 0),
                            color="#FF9999", alpha=0.5, label="Real > Pseudo")
    ax_sp_all.fill_between(spread_jpy.index, spread_jpy.values, 0,
                            where=(spread_jpy.values <= 0),
                            color="#99BBFF", alpha=0.5, label="Pseudo > Real")
    ax_sp_all.plot(spread_jpy.index, spread_jpy.values,
                   color="#333", lw=0.8, alpha=0.7)
    ax_sp_all.axhline(0, color="#666", lw=1, ls="--")
    ax_sp_all.set_ylabel("スプレッド（JPY）", fontproperties=_p9)
    ax_sp_all.set_title("スプレッド（リアル − 疑似）の推移",
                         fontproperties=_p10, fontsize=10)
    ax_sp_all.legend(prop=_p8, loc="upper right")
    ax_sp_all.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_sp_all.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    # スプレッド統計
    ax_sp_all.text(1.001, 0.98,
        f"スプレッド統計\n平均: {sp_mean:+.2f} JPY\n"
        f"標準偏差: {sp_std:.2f} JPY\n"
        f"最大: {sp_max:+.2f} JPY\n最小: {sp_min:+.2f} JPY",
        transform=ax_sp_all.transAxes, va="top", ha="left",
        fontproperties=_p8, color="#333",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#F0F4FF",
                  edgecolor="#8899BB", lw=1.0))

    # ── パネル3: ズーム価格（20日）──────────────────────────────
    zm = (real.index >= z_start) & (real.index <= z_end)
    r_zm  = real[zm];   s_zm  = synth[zm]

    ax_zoom.plot(r_zm.index, r_zm.values, color="#1A5FB4", lw=2.0,
                 label="リアルUSDJPY")
    ax_zoom.plot(s_zm.index, s_zm.values, color="#CC3333", lw=1.5,
                 ls="--", label="疑似USDJPY（LOO）", alpha=0.85)
    ax_zoom.fill_between(r_zm.index, r_zm.values, s_zm.values,
                          where=(r_zm.values > s_zm.values),
                          color="#1A5FB4", alpha=0.15)
    ax_zoom.fill_between(r_zm.index, r_zm.values, s_zm.values,
                          where=(r_zm.values <= s_zm.values),
                          color="#CC3333", alpha=0.15)

    # エントリーシグナル（5分足cum_spreadを日次にまとめてマーカー）
    zm5  = (cum_5min.index >= z_start) & (cum_5min.index <= z_end)
    cs_z = cum_5min[zm5]
    long_dates  = cs_z[cs_z < -THRESHOLD].index.normalize().unique()
    short_dates = cs_z[cs_z >  THRESHOLD].index.normalize().unique()

    entry_long_y  = [float(real[real.index == d].values[0])
                     for d in long_dates  if d in real.index]
    entry_short_y = [float(real[real.index == d].values[0])
                     for d in short_dates if d in real.index]
    valid_ld = [d for d in long_dates  if d in real.index]
    valid_sd = [d for d in short_dates if d in real.index]

    if valid_ld:
        ax_zoom.scatter(valid_ld, entry_long_y,
                        marker="^", s=80, color="#22C55E", zorder=5,
                        label=f"LONGシグナル ({len(valid_ld)}件)")
    if valid_sd:
        ax_zoom.scatter(valid_sd, entry_short_y,
                        marker="v", s=80, color="#EF4444", zorder=5,
                        label=f"SHORTシグナル ({len(valid_sd)}件)")

    ax_zoom.set_title(
        f"ズーム: {z_start.strftime('%Y/%m/%d')} 〜 {z_end.strftime('%Y/%m/%d')}（エントリー事例）",
        fontproperties=_p9, fontsize=9)
    ax_zoom.set_ylabel("価格（JPY）", fontproperties=_p8)
    ax_zoom.legend(prop=_p8, loc="upper left")
    ax_zoom.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax_zoom.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    plt.setp(ax_zoom.get_xticklabels(), rotation=45, ha="right", fontsize=7)

    # ── パネル4: ズームcum_spread ────────────────────────────────
    cs_d_zm = cum_daily[(cum_daily.index >= z_start) & (cum_daily.index <= z_end)]

    ax_sp_zm.plot(cs_d_zm.index, cs_d_zm.values,
                  color="#7C3AED", lw=1.5, label="cum_spread")
    ax_sp_zm.axhline( THRESHOLD, color="#EF4444", lw=1.2, ls="--",
                      label=f"+{THRESHOLD}（SHORTシグナル）", alpha=0.8)
    ax_sp_zm.axhline(-THRESHOLD, color="#22C55E", lw=1.2, ls="--",
                      label=f"-{THRESHOLD}（LONGシグナル）",  alpha=0.8)
    ax_sp_zm.axhline(0, color="#888", lw=0.6)
    ax_sp_zm.fill_between(cs_d_zm.index, cs_d_zm.values, -THRESHOLD,
                           where=(cs_d_zm.values < -THRESHOLD),
                           color="#22C55E", alpha=0.2)
    ax_sp_zm.fill_between(cs_d_zm.index, cs_d_zm.values,  THRESHOLD,
                           where=(cs_d_zm.values >  THRESHOLD),
                           color="#EF4444", alpha=0.2)
    ax_sp_zm.set_title("cum_spread とエントリー閾値",
                        fontproperties=_p9, fontsize=9)
    ax_sp_zm.set_ylabel("cum_spread（log-return）", fontproperties=_p8)
    ax_sp_zm.legend(prop=_p8, loc="upper right", fontsize=7, ncol=1)
    ax_sp_zm.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax_sp_zm.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    plt.setp(ax_sp_zm.get_xticklabels(), rotation=45, ha="right", fontsize=7)

    # ── 注釈フッター ─────────────────────────────────────────────
    footer = (
        "【ポイント】\n"
        "・疑似USDJPY（LOO方式）はUSDJPY自身を除いた他ペアの通貨強弱から算出。自己参照なし。\n"
        "・スプレッド（乖離）が閾値を超えた場合、実価格の収束を狙いエントリー（Case B: Pseudo先行→Long）。\n"
        "・LOO版ではPF<1.0（100設定中0件がPF≥1.0）。Include-Self版の利益は循環参照アーティファクト。"
    )
    fig.text(0.02, 0.01, footer, fontproperties=_p8, color="#444",
             verticalalignment="bottom",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#EEF3FF",
                       edgecolor="#AABBDD", lw=0.8))

    plt.suptitle("", y=1.0)
    plt.tight_layout(rect=[0, 0.07, 1.0, 1.0])

    out = OUT_DIR / "pseudo_vs_real_usdjpy.png"
    plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    print(f"  保存: {out}")
    return out


def main():
    print("=" * 55)
    print("リアル vs 疑似USDJPY 比較チャート生成（参考スタイル）")
    print("=" * 55)
    print("\nデータ読み込み中...")
    data = load_data()
    print("\nチャート生成中...")
    out = make_chart(data)
    print(f"\n完了: {out}")


if __name__ == "__main__":
    main()
