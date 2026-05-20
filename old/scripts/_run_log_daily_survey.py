# -*- coding: utf-8 -*-
"""
Log-Return × 日次累積スプレッド — パラメータサーベイ
実行: python _run_log_daily_survey.py

[元] cum_spread = rolling_sum(spread, window)  ← ローリング窓
[新] cum_spread = cumsum(spread, since_day_open) ← 当日始値から累積

この変更でローリング窓の機械的平均回帰が除去される。
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

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
_prop = fm.FontProperties(fname=FONT_PATH, size=9)
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

OUT_DIR = Path("docs") / "log_daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)

import sys; sys.path.insert(0, str(Path(__file__).parent))
from fx_market_classifier.config import PAIRS
from fx_market_classifier.data_fetcher import fetch_ohlcv
from fx_market_classifier.log_daily_engine import (
    LogDailyEngine, LogDailyConfig, param_survey
)


# ══════════════════════════════════════════════════════════════════════
# 分布確認
# ══════════════════════════════════════════════════════════════════════

def check_distribution(price_data: dict):
    """cum_spreadの分布を確認してから閾値を決定する"""
    print("\n[cum_spread 分布確認]")
    print(f"  {'ペア':<10} {'abs_99th':>10} {'abs_95th':>10} "
          f"{'abs_75th':>10} {'>0.001':>8} {'>0.002':>8} {'>0.003':>8}")
    print("  " + "-" * 75)

    cfg = LogDailyConfig(entry_threshold=0.00001)  # 実質全件
    eng = LogDailyEngine(price_data, cfg)

    for pair in eng.cum_spread.columns:
        s = eng.cum_spread[pair].dropna()
        s = s[s != 0]  # ゼロ（日初バー）を除く
        if s.empty:
            continue
        q99 = s.abs().quantile(0.99)
        q95 = s.abs().quantile(0.95)
        q75 = s.abs().quantile(0.75)
        p1  = (s.abs() > 0.001).mean() * 100
        p2  = (s.abs() > 0.002).mean() * 100
        p3  = (s.abs() > 0.003).mean() * 100
        print(f"  {pair:<10} {q99:>10.5f} {q95:>10.5f} "
              f"{q75:>10.5f} {p1:>7.2f}% {p2:>7.2f}% {p3:>7.2f}%")

    # ローリング窓版との比較（window=6）
    print()
    print("  [参考] ローリング6バー版との比較（USDJPY）")
    if 'USDJPY' in eng.cum_spread.columns:
        from fx_market_classifier.features import log_returns, currency_strength
        from fx_market_classifier.config import PAIR_CURRENCIES
        pair = 'USDJPY'
        close = price_data[pair]['Close']
        lr    = np.log(close / close.shift(1))
        s_daily = eng.cum_spread[pair].dropna()
        s_daily = s_daily[s_daily != 0]
        # ローリング6バー版の概算
        from fx_market_classifier.lead_lag import LeadLagEngine, LeadLagConfig
        eng2 = LeadLagEngine(price_data,
                             LeadLagConfig(spread_window=6, entry_threshold=0.00001))
        s_roll = eng2.cum_spread[pair].dropna()
        print(f"  日次累積版  99th={s_daily.abs().quantile(0.99):.5f}"
              f"  中央値={s_daily.abs().median():.5f}")
        print(f"  ローリング6バー版  99th={s_roll.abs().quantile(0.99):.5f}"
              f"  中央値={s_roll.abs().median():.5f}")


# ══════════════════════════════════════════════════════════════════════
# チャート
# ══════════════════════════════════════════════════════════════════════

def plot_cumspread_comparison(price_data: dict):
    """日次累積 vs ローリング窓 の比較チャート（USDJPY）"""
    pair = 'USDJPY'
    if pair not in price_data:
        return

    from fx_market_classifier.lead_lag import LeadLagEngine, LeadLagConfig

    cfg_daily = LogDailyConfig(entry_threshold=0.00001)
    eng_daily = LogDailyEngine(price_data, cfg_daily)

    cfg_roll6  = LeadLagConfig(spread_window=6,  entry_threshold=0.00001)
    cfg_roll24 = LeadLagConfig(spread_window=24, entry_threshold=0.00001)
    eng_roll6  = LeadLagEngine(price_data, cfg_roll6)
    eng_roll24 = LeadLagEngine(price_data, cfg_roll24)

    # 直近5日
    last_date = eng_daily.cum_spread.index[-1].normalize()
    start     = last_date - pd.Timedelta(days=5)

    cum_daily = eng_daily.cum_spread[pair]
    cum_roll6 = eng_roll6.cum_spread[pair]
    cum_roll24 = eng_roll24.cum_spread[pair]

    mask = cum_daily.index >= start
    cd = cum_daily[mask]; cr6 = cum_roll6.reindex(cd.index).ffill()
    cr24 = cum_roll24.reindex(cd.index).ffill()

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.patch.set_facecolor('#F5F8FF')
    fig.suptitle(f'USDJPY cum_spread 比較 — 日次累積 vs ローリング窓',
                 fontproperties=_prop, fontsize=12, y=0.98)

    labels = [
        ('日次累積 (新)', cd,   '#CC3333', 0.0015),
        ('ローリング6バー (元)', cr6,  '#2266AA', 0.0015),
        ('ローリング24バー', cr24, '#228844', 0.003),
    ]
    for ax, (title, s, color, thr) in zip(axes, labels):
        ax.set_facecolor('#F5F8FF')
        ax.plot(s.index, s.values, lw=1.2, color=color, label=title)
        ax.axhline(thr,  color='#999', lw=0.8, ls='--', label=f'+{thr}')
        ax.axhline(-thr, color='#999', lw=0.8, ls='--', label=f'-{thr}')
        ax.axhline(0, color='#666', lw=0.5)
        ax.set_ylabel('cum_spread', fontproperties=_prop)
        ax.set_title(title, fontproperties=_prop, fontsize=10)
        ax.legend(prop=_prop, loc='upper right')
        ax.grid(color='#D8E0F0', lw=0.4)

    plt.tight_layout()
    out = OUT_DIR / 'cumspread_comparison.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  比較チャート保存: {out}")


def plot_survey_heatmap(df: pd.DataFrame, sort_mode: str, zero_cost: bool = False):
    sub = df[df.sort_mode == sort_mode].copy()
    if sub.empty:
        return

    entry_vals = sorted(sub.entry_threshold.unique())
    exit_vals  = sorted(sub.exit_threshold.unique())
    pf_mat = np.full((len(entry_vals), len(exit_vals)), np.nan)
    for _, row in sub.iterrows():
        i = entry_vals.index(row.entry_threshold)
        j = exit_vals.index(row.exit_threshold)
        pf_mat[i, j] = min(row.pf, 3.0)

    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_facecolor('#F5F8FF')
    ax.set_facecolor('#F5F8FF')
    im = ax.imshow(pf_mat, cmap='RdYlGn', vmin=0.8, vmax=1.5, aspect='auto')
    plt.colorbar(im, ax=ax, label='PF')
    ax.set_xticks(range(len(exit_vals)))
    ax.set_xticklabels([f'{v:.4f}' for v in exit_vals], fontproperties=_prop)
    ax.set_yticks(range(len(entry_vals)))
    ax.set_yticklabels([f'{v:.4f}' for v in entry_vals], fontproperties=_prop)
    ax.set_xlabel('exit_threshold', fontproperties=_prop)
    ax.set_ylabel('entry_threshold', fontproperties=_prop)
    suffix = '0コスト' if zero_cost else 'コストあり'
    ax.set_title(f'PF ヒートマップ (sort={sort_mode}, {suffix})\n'
                 f'[日次累積版]', fontproperties=_prop, fontsize=10)
    for i in range(len(entry_vals)):
        for j in range(len(exit_vals)):
            v = pf_mat[i, j]
            if not np.isnan(v):
                ax.text(j, i, f'{v:.2f}', ha='center', va='center',
                        fontsize=9, fontweight='bold',
                        color='white' if v < 0.9 or v > 1.4 else 'black')
    plt.tight_layout()
    tag = 'nocost' if zero_cost else 'cost'
    out = OUT_DIR / f'heatmap_{sort_mode}_{tag}.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  ヒートマップ保存: {out}")


def plot_pnl_curve(price_data: dict, cfg: LogDailyConfig, label: str):
    eng = LogDailyEngine(price_data, cfg)
    df  = eng.run()
    if df.empty:
        return None

    fig, axes = plt.subplots(2, 1, figsize=(13, 7))
    fig.patch.set_facecolor('#F5F8FF')

    cum = df['capital_pnl'].cumsum()
    ax  = axes[0]; ax.set_facecolor('#F5F8FF')
    ax.plot(cum.values, color='#2266AA', lw=2)
    ax.fill_between(range(len(cum)), cum.values, 0,
                    where=(cum.values >= 0), color='#2266AA', alpha=0.15)
    ax.fill_between(range(len(cum)), cum.values, 0,
                    where=(cum.values < 0),  color='#CC3333', alpha=0.15)
    ax.axhline(0, color='#888', lw=0.8, ls='--')
    ax.set_title(f'累積損益曲線 [{label}]', fontproperties=_prop, fontsize=11)
    ax.set_ylabel('累積PnL (% of capital)', fontproperties=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    ax = axes[1]; ax.set_facecolor('#F5F8FF')
    pair_pnl = df.groupby('pair')['capital_pnl'].sum().sort_values()
    clrs = ['#CC3333' if v < 0 else '#2266AA' for v in pair_pnl.values]
    ax.barh(pair_pnl.index, pair_pnl.values, color=clrs, alpha=0.8)
    ax.axvline(0, color='#888', lw=0.8)
    ax.set_xlabel('累積PnL (% of capital)', fontproperties=_prop)
    ax.set_title('ペア別損益', fontproperties=_prop, fontsize=11)
    ax.grid(color='#D8E0F0', lw=0.4, axis='x')

    plt.tight_layout()
    safe = label.replace(' ', '_').replace('=', '').replace('.', 'p')
    out  = OUT_DIR / f'pnl_{safe}.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  PnLカーブ保存: {out}")
    return df, eng


def plot_exit_breakdown(df_trades: pd.DataFrame, label: str):
    if df_trades is None or df_trades.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fig.patch.set_facecolor('#F5F8FF')

    reasons = df_trades['exit_reason'].value_counts()
    clr_map = {'spread_reduced': '#2266AA', 'stop': '#CC3333',
               'time_limit': '#FF8800', 'day_end': '#888', 'end_of_data': '#AAA'}
    ax = axes[0]; ax.set_facecolor('#F5F8FF')
    clrs = [clr_map.get(r, '#999') for r in reasons.index]
    ax.pie(reasons.values, labels=reasons.index, colors=clrs,
           autopct='%1.1f%%', startangle=90,
           textprops={'fontproperties': _prop})
    ax.set_title(f'エグジット理由 [{label}]', fontproperties=_prop, fontsize=9)

    ax = axes[1]; ax.set_facecolor('#F5F8FF')
    wins  = df_trades[df_trades.capital_pnl > 0]['capital_pnl']
    loses = df_trades[df_trades.capital_pnl <= 0]['capital_pnl']
    if not wins.empty:
        ax.hist(wins.values,  bins=20, color='#2266AA', alpha=0.7,
                label=f'勝({len(wins)})')
    if not loses.empty:
        ax.hist(loses.values, bins=20, color='#CC3333', alpha=0.7,
                label=f'負({len(loses)})')
    ax.axvline(0, color='#888', lw=1, ls='--')
    ax.set_xlabel('PnL (% of capital)', fontproperties=_prop)
    ax.legend(prop=_prop)
    ax.set_title('PnL分布', fontproperties=_prop, fontsize=10)
    ax.grid(color='#D8E0F0', lw=0.4)

    plt.tight_layout()
    safe = label.replace(' ', '_').replace('=', '').replace('.', 'p')
    out  = OUT_DIR / f'exit_{safe}.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  エグジット内訳保存: {out}")


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("Log-Return × 日次累積スプレッド — パラメータサーベイ")
    print("[変更点] cum_spread: ローリング窓 → 当日始値からの累積")
    print("=" * 65)

    data = fetch_ohlcv(pairs=PAIRS, interval="5m", lookback_days=55)
    if len(data) < 4:
        print("ERROR: データ取得失敗")
        return

    # ── 分布確認 ─────────────────────────────────────────────────────
    check_distribution(data)

    # ── 比較チャート ─────────────────────────────────────────────────
    print("\n[比較チャート生成中]")
    plot_cumspread_comparison(data)

    # ── サーベイ（コストあり）───────────────────────────────────────
    print("\n[コストあり パラメータサーベイ（30通り）]")
    df_cost = param_survey(
        data,
        entry_grid=[0.0005, 0.001, 0.0015, 0.002, 0.003],
        exit_grid=[0.0002, 0.0005, 0.001],
        sort_modes=['spread', 'strength'],
        stop_loss_pct=1.5, time_limit_bars=60, risk_pct=0.5,
    )
    df_cost.to_csv(OUT_DIR / 'survey_cost.csv', index=False)
    print("\n上位8件（コストあり）:")
    print(df_cost.head(8)[['entry_threshold', 'exit_threshold', 'sort_mode',
                            'trades', 'win_rate', 'pf', 'total_pnl', 'max_dd',
                            'reduced_cnt', 'stop_cnt']].to_string())

    # ── サーベイ（0コスト）─────────────────────────────────────────
    print("\n[0コスト パラメータサーベイ（30通り）]")
    df_nc = param_survey(
        data,
        entry_grid=[0.0005, 0.001, 0.0015, 0.002, 0.003],
        exit_grid=[0.0002, 0.0005, 0.001],
        sort_modes=['spread', 'strength'],
        stop_loss_pct=1.5, time_limit_bars=60, risk_pct=0.5,
    )
    # 0コストで再実行
    rows_nc = []
    import itertools
    for entry, exit_t, sort in itertools.product(
            [0.0005, 0.001, 0.0015, 0.002, 0.003],
            [0.0002, 0.0005, 0.001],
            ['spread', 'strength']):
        cfg = LogDailyConfig(entry_threshold=entry, exit_threshold=exit_t,
                             sort_mode=sort, spread_cost_pct=0.0,
                             stop_loss_pct=1.5, time_limit_bars=60)
        eng = LogDailyEngine(data, cfg); eng.run()
        m   = eng.metrics()
        if m:
            pf_s = f"{m['pf']:.2f}" if m['pf'] < 99 else "inf"
            rows_nc.append({'entry_threshold': entry, 'exit_threshold': exit_t,
                            'sort_mode': sort, **{k: m[k] for k in
                            ['trades','win_rate','pf','total_pnl','max_dd',
                             'reduced_cnt','stop_cnt','time_cnt']}})
            print(f"  entry={entry:.4f} exit={exit_t:.4f} sort={sort:<8}  "
                  f"T={m['trades']:4d} win={m['win_rate']*100:.1f}% "
                  f"PF={pf_s}  total={m['total_pnl']:+.2f}%")
    df_nc = pd.DataFrame(rows_nc).sort_values('pf', ascending=False)
    df_nc.to_csv(OUT_DIR / 'survey_nocost.csv', index=False)
    print("\n上位5件（0コスト）:")
    print(df_nc.head(5)[['entry_threshold','exit_threshold','sort_mode',
                          'trades','win_rate','pf','total_pnl']].to_string())

    # ── ヒートマップ ─────────────────────────────────────────────────
    print("\n[ヒートマップ生成中]")
    for smode in ['spread', 'strength']:
        plot_survey_heatmap(df_cost, smode, zero_cost=False)
        plot_survey_heatmap(df_nc,   smode, zero_cost=True)

    # ── 最良設定 詳細分析 ────────────────────────────────────────────
    print("\n[最良設定 詳細分析]")
    for smode in ['spread', 'strength']:
        best = df_cost[df_cost.sort_mode == smode].iloc[0]
        label = (f"entry={best.entry_threshold:.4f} "
                 f"exit={best.exit_threshold:.4f} sort={smode}")
        print(f"\n  最良（{smode}）: {label}")
        print(f"  PF={best.pf:.3f}  T={int(best.trades)}"
              f"  win={best.win_rate*100:.1f}%  total={best.total_pnl:+.2f}%"
              f"  spread_reduced={int(best.reduced_cnt)}")

        cfg = LogDailyConfig(
            entry_threshold=best.entry_threshold,
            exit_threshold=best.exit_threshold,
            sort_mode=smode, stop_loss_pct=1.5, time_limit_bars=60,
        )
        result = plot_pnl_curve(data, cfg, label)
        if result:
            df_t, eng = result
            plot_exit_breakdown(df_t, label)

            # エグジット理由別勝率
            print(f"\n  エグジット理由別 (sort={smode}):")
            for reason in ['spread_reduced', 'stop', 'time_limit', 'day_end']:
                sub = df_t[df_t.exit_reason == reason]
                if not sub.empty:
                    wr  = (sub.capital_pnl > 0).mean()
                    avg = sub.capital_pnl.mean()
                    print(f"    {reason:<16} N={len(sub):4d}  "
                          f"win={wr*100:.1f}%  avg={avg:+.4f}%")

            # ペア別
            pair_stats = df_t.groupby('pair').agg(
                T=('capital_pnl','count'),
                win=('capital_pnl', lambda x: (x>0).mean()),
                total=('capital_pnl','sum')
            ).sort_values('total', ascending=False)
            pair_stats.to_csv(OUT_DIR / f'pair_pnl_{smode}.csv')
            print(f"\n  ペア別損益 (sort={smode}):")
            print(pair_stats.round(3).to_string())

    print(f"\n{'='*65}")
    print(f"完了!  出力先: {OUT_DIR.resolve()}")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
