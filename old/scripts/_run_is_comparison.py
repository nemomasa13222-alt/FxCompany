# -*- coding: utf-8 -*-
"""
IS期間 3年 公平比較
  ローリング窓版 (LeadLagEngine)  vs  日次累積版 (LogDailyEngine)
  同一データ: Dukascopy 5分足 2022-01-01 〜 2024-12-31

実行: python _run_is_comparison.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
import itertools
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

OUT_DIR = Path("docs") / "is_comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

import sys; sys.path.insert(0, str(Path(__file__).parent))
from fx_market_classifier.lead_lag      import LeadLagEngine, LeadLagConfig
from fx_market_classifier.log_daily_engine import LogDailyEngine, LogDailyConfig


# ══════════════════════════════════════════════════════════════════════
# データ読み込み（Dukascopy parquet）
# ══════════════════════════════════════════════════════════════════════

IS_START = "2022-01-01"
IS_END   = "2024-12-31"
DATA_DIR = Path("data") / "dukascopy"

AVAILABLE_PAIRS = [
    "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY",
    "NZDUSD", "AUDNZD",
]

def load_is_data() -> dict:
    """Dukascopy IS期間データ読み込み"""
    print(f"\nIS期間データ読み込み: {IS_START} 〜 {IS_END}")
    data = {}
    for pair in AVAILABLE_PAIRS:
        f = DATA_DIR / f"{pair}_5min.parquet"
        if not f.exists():
            print(f"  {pair}: ファイルなし → スキップ")
            continue
        df = pd.read_parquet(f)
        # タイムゾーン正規化
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC")
        else:
            df.index = df.index.tz_localize("UTC")
        # IS期間でフィルタ
        mask = (df.index >= pd.Timestamp(IS_START, tz="UTC")) & \
               (df.index <= pd.Timestamp(IS_END,   tz="UTC") + pd.Timedelta(days=1))
        df = df[mask][["Open", "High", "Low", "Close"]].dropna()
        if len(df) < 100:
            print(f"  {pair}: データ不足 → スキップ")
            continue
        data[pair] = df
        print(f"  {pair}: {len(df):,}本  "
              f"{df.index[0].date()} 〜 {df.index[-1].date()}")
    print(f"  → {len(data)}ペア使用")
    return data


# ══════════════════════════════════════════════════════════════════════
# ローリング窓版サーベイ（LeadLagEngine）
# ══════════════════════════════════════════════════════════════════════

def survey_rolling(price_data: dict) -> pd.DataFrame:
    """
    ローリング窓版 パラメータサーベイ
    entry_threshold × exit_ratio × window_size
    """
    entry_grid   = [0.0005, 0.001, 0.0015, 0.002, 0.003]
    exit_ratios  = [0.2, 0.5, 0.8]   # 元のlead_lagと同じ形式
    window_grid  = [6, 12, 24]        # 30分・1時間・2時間

    combos = list(itertools.product(window_grid, entry_grid, exit_ratios))
    print(f"\n[ローリング窓版] {len(combos)}通り")

    rows = []
    for k, (w, entry, er) in enumerate(combos, 1):
        cfg = LeadLagConfig(
            spread_window=w,
            entry_threshold=entry,
            exit_ratio=er,
            risk_pct=0.5,
            use_case_a=True,
        )
        eng = LeadLagEngine(price_data, cfg)
        eng.run()
        m = eng.metrics()
        if not m or m['trades'] == 0:
            continue

        exit_thr = entry * (1 - er)   # 比較用に絶対値に変換

        pf_s = f"{m['pf']:.3f}" if m['pf'] < 99 else "inf"
        rows.append({
            'method':          'rolling',
            'window':          w,
            'entry_threshold': entry,
            'exit_ratio':      er,
            'exit_threshold':  round(exit_thr, 6),
            'trades':          m['trades'],
            'win_rate':        m['win_rate'],
            'pf':              m['pf'],
            'total_pnl':       m['total_pnl'],
            'max_dd':          m['max_dd'],
            'case_a':          m['case_a'],
            'case_b':          m['case_b'],
            'stop_cnt':        m['stop_cnt'],
            'reduced_cnt':     m['reduced_cnt'],
        })
        if k % 10 == 0 or k == len(combos):
            print(f"  [{k:3d}/{len(combos)}] w={w:2d} entry={entry:.4f} "
                  f"er={er:.1f}  T={m['trades']:5d} "
                  f"win={m['win_rate']*100:.1f}% PF={pf_s} "
                  f"total={m['total_pnl']:+.2f}%")

    df = pd.DataFrame(rows).sort_values('pf', ascending=False).reset_index(drop=True)
    df.to_csv(OUT_DIR / 'survey_rolling.csv', index=False)
    return df


# ══════════════════════════════════════════════════════════════════════
# 日次累積版サーベイ（LogDailyEngine）
# ══════════════════════════════════════════════════════════════════════

def survey_log_daily(price_data: dict) -> pd.DataFrame:
    """
    日次累積版 パラメータサーベイ
    entry_threshold × exit_threshold × sort_mode
    """
    entry_grid = [0.0005, 0.001, 0.0015, 0.002, 0.003]
    exit_grid  = [0.0002, 0.0005, 0.001]
    sort_modes = ['spread', 'strength']

    combos = list(itertools.product(entry_grid, exit_grid, sort_modes))
    print(f"\n[日次累積版] {len(combos)}通り")

    rows = []
    for k, (entry, exit_t, sort) in enumerate(combos, 1):
        cfg = LogDailyConfig(
            entry_threshold=entry,
            exit_threshold=exit_t,
            sort_mode=sort,
            stop_loss_pct=1.5,
            time_limit_bars=60,
            risk_pct=0.5,
        )
        eng = LogDailyEngine(price_data, cfg)
        eng.run()
        m = eng.metrics()
        if not m or m['trades'] == 0:
            continue

        pf_s = f"{m['pf']:.3f}" if m['pf'] < 99 else "inf"
        rows.append({
            'method':          'log_daily',
            'window':          'daily',
            'entry_threshold': entry,
            'exit_threshold':  exit_t,
            'sort_mode':       sort,
            'trades':          m['trades'],
            'win_rate':        m['win_rate'],
            'pf':              m['pf'],
            'total_pnl':       m['total_pnl'],
            'max_dd':          m['max_dd'],
            'case_a':          m['case_a'],
            'case_b':          m['case_b'],
            'stop_cnt':        m['stop_cnt'],
            'reduced_cnt':     m['reduced_cnt'],
        })
        if k % 10 == 0 or k == len(combos):
            print(f"  [{k:3d}/{len(combos)}] "
                  f"entry={entry:.4f} exit={exit_t:.4f} sort={sort:<8}  "
                  f"T={m['trades']:5d} win={m['win_rate']*100:.1f}% "
                  f"PF={pf_s} total={m['total_pnl']:+.2f}%")

    df = pd.DataFrame(rows).sort_values('pf', ascending=False).reset_index(drop=True)
    df.to_csv(OUT_DIR / 'survey_log_daily.csv', index=False)
    return df


# ══════════════════════════════════════════════════════════════════════
# チャート
# ══════════════════════════════════════════════════════════════════════

def plot_comparison(df_roll: pd.DataFrame, df_daily: pd.DataFrame):
    """PF分布の比較チャート"""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.patch.set_facecolor('#F5F8FF')
    fig.suptitle('IS 3年 公平比較: ローリング窓 vs 日次累積',
                 fontproperties=_prop, fontsize=12)

    # 1. PF分布 ヒストグラム
    ax = axes[0]; ax.set_facecolor('#F5F8FF')
    ax.hist(df_roll['pf'].clip(0, 2),  bins=20, color='#2266AA',
            alpha=0.6, label=f'ローリング窓 (n={len(df_roll)})')
    ax.hist(df_daily['pf'].clip(0, 2), bins=20, color='#CC3333',
            alpha=0.6, label=f'日次累積 (n={len(df_daily)})')
    ax.axvline(1.0, color='#000', lw=1.5, ls='--', label='PF=1.0')
    ax.set_xlabel('PF', fontproperties=_prop)
    ax.set_ylabel('件数', fontproperties=_prop)
    ax.set_title('PF分布', fontproperties=_prop, fontsize=10)
    ax.legend(prop=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    # 2. entry_threshold × PF 散布図
    ax = axes[1]; ax.set_facecolor('#F5F8FF')
    for entry_val in sorted(df_roll.entry_threshold.unique()):
        sub_r = df_roll[df_roll.entry_threshold == entry_val]
        sub_d = df_daily[df_daily.entry_threshold == entry_val]
        ax.scatter([entry_val]*len(sub_r), sub_r['pf'],
                   color='#2266AA', alpha=0.5, s=30)
        ax.scatter([entry_val]*len(sub_d), sub_d['pf'],
                   color='#CC3333', alpha=0.5, s=30, marker='s')
    ax.axhline(1.0, color='#000', lw=1, ls='--')
    ax.set_xlabel('entry_threshold', fontproperties=_prop)
    ax.set_ylabel('PF', fontproperties=_prop)
    ax.set_title('entry別PF', fontproperties=_prop, fontsize=10)
    from matplotlib.lines import Line2D
    leg = [Line2D([0],[0],marker='o',color='#2266AA',label='ローリング窓',ls=''),
           Line2D([0],[0],marker='s',color='#CC3333',label='日次累積',ls='')]
    ax.legend(handles=leg, prop=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    # 3. ベスト設定 累積PnL（ローリング窓 最良 vs 日次累積 最良）
    ax = axes[2]; ax.set_facecolor('#F5F8FF')
    ax.set_title('最良設定 PF比較', fontproperties=_prop, fontsize=10)

    best_r = df_roll.head(5)[['window','entry_threshold','exit_ratio','pf','total_pnl','trades']]
    best_d = df_daily.head(5)[['entry_threshold','exit_threshold','sort_mode','pf','total_pnl','trades']]

    labels_r = [f"R:w={int(r.window)} e={r.entry_threshold:.4f}" for _, r in best_r.iterrows()]
    labels_d = [f"D:e={r.entry_threshold:.4f} ex={r.exit_threshold:.4f}" for _, r in best_d.iterrows()]

    y_r = list(range(len(labels_r)))
    y_d = [y + len(labels_r) + 1 for y in range(len(labels_d))]

    ax.barh(y_r, best_r['pf'].values, color='#2266AA', alpha=0.8)
    ax.barh(y_d, best_d['pf'].values, color='#CC3333', alpha=0.8)
    ax.set_yticks(y_r + y_d)
    ax.set_yticklabels(labels_r + labels_d, fontproperties=_prop, fontsize=7)
    ax.axvline(1.0, color='#000', lw=1, ls='--')
    ax.set_xlabel('PF', fontproperties=_prop)
    ax.grid(color='#D8E0F0', lw=0.4, axis='x')

    plt.tight_layout()
    out = OUT_DIR / 'comparison_chart.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  比較チャート保存: {out}")


def plot_best_pnl_curves(price_data, df_roll, df_daily):
    """最良設定の損益曲線を並べて表示"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.patch.set_facecolor('#F5F8FF')
    fig.suptitle('IS 3年 最良設定 累積損益曲線',
                 fontproperties=_prop, fontsize=12)

    # ローリング窓 最良
    best_r = df_roll.iloc[0]
    cfg_r = LeadLagConfig(
        spread_window=int(best_r.window),
        entry_threshold=best_r.entry_threshold,
        exit_ratio=best_r.exit_ratio,
        risk_pct=0.5,
    )
    eng_r = LeadLagEngine(price_data, cfg_r)
    df_r  = eng_r.run()

    ax = axes[0]; ax.set_facecolor('#F5F8FF')
    if not df_r.empty:
        cum_r = df_r['pnl_pct'].cumsum()
        ax.plot(cum_r.values, color='#2266AA', lw=1.5)
        ax.fill_between(range(len(cum_r)), cum_r.values, 0,
                        where=(cum_r.values >= 0), color='#2266AA', alpha=0.1)
        ax.fill_between(range(len(cum_r)), cum_r.values, 0,
                        where=(cum_r.values < 0), color='#CC3333', alpha=0.1)
    ax.axhline(0, color='#888', lw=0.8, ls='--')
    lbl_r = (f"ローリング窓 最良: w={int(best_r.window)} "
             f"entry={best_r.entry_threshold:.4f} er={best_r.exit_ratio:.1f}  "
             f"PF={best_r.pf:.3f}  T={int(best_r.trades)}")
    ax.set_title(lbl_r, fontproperties=_prop, fontsize=9)
    ax.set_ylabel('累積PnL (% of capital)', fontproperties=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    # 日次累積 最良
    best_d = df_daily.iloc[0]
    cfg_d = LogDailyConfig(
        entry_threshold=best_d.entry_threshold,
        exit_threshold=best_d.exit_threshold,
        sort_mode=best_d.sort_mode,
        risk_pct=0.5,
    )
    eng_d = LogDailyEngine(price_data, cfg_d)
    df_d  = eng_d.run()

    ax = axes[1]; ax.set_facecolor('#F5F8FF')
    if not df_d.empty:
        cum_d = df_d['capital_pnl'].cumsum()
        ax.plot(cum_d.values, color='#CC3333', lw=1.5)
        ax.fill_between(range(len(cum_d)), cum_d.values, 0,
                        where=(cum_d.values >= 0), color='#2266AA', alpha=0.1)
        ax.fill_between(range(len(cum_d)), cum_d.values, 0,
                        where=(cum_d.values < 0), color='#CC3333', alpha=0.1)
    ax.axhline(0, color='#888', lw=0.8, ls='--')
    lbl_d = (f"日次累積 最良: entry={best_d.entry_threshold:.4f} "
             f"exit={best_d.exit_threshold:.4f} sort={best_d.sort_mode}  "
             f"PF={best_d.pf:.3f}  T={int(best_d.trades)}")
    ax.set_title(lbl_d, fontproperties=_prop, fontsize=9)
    ax.set_ylabel('累積PnL (% of capital)', fontproperties=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    plt.tight_layout()
    out = OUT_DIR / 'best_pnl_curves.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  損益曲線保存: {out}")


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("IS期間 3年 公平比較")
    print("  ローリング窓版 (LeadLagEngine)")
    print("  日次累積版    (LogDailyEngine)")
    print(f"  IS期間: {IS_START} 〜 {IS_END} / Dukascopy 5分足")
    print("=" * 65)

    # データ読み込み
    data = load_is_data()
    if len(data) < 3:
        print("ERROR: データ不足")
        return

    # ── ローリング窓版 ─────────────────────────────────────────────
    df_roll = survey_rolling(data)

    print(f"\nローリング窓版 上位10件:")
    print(df_roll.head(10)[['window','entry_threshold','exit_ratio',
                             'trades','win_rate','pf','total_pnl','max_dd',
                             'reduced_cnt']].to_string())

    # ── 日次累積版 ────────────────────────────────────────────────
    df_daily = survey_log_daily(data)

    print(f"\n日次累積版 上位10件:")
    print(df_daily.head(10)[['entry_threshold','exit_threshold','sort_mode',
                              'trades','win_rate','pf','total_pnl','max_dd',
                              'reduced_cnt']].to_string())

    # ── サマリー比較 ──────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("サマリー比較")
    print("=" * 65)

    def summarize(df, label):
        above1 = (df.pf >= 1.0).sum()
        above11 = (df.pf >= 1.1).sum()
        n = len(df)
        best = df.iloc[0]
        print(f"\n【{label}】")
        print(f"  条件数: {n}  PF≥1.0: {above1}/{n}  PF≥1.1: {above11}/{n}")
        print(f"  最良PF: {best.pf:.3f}  "
              f"T={int(best.trades)}  win={best.win_rate*100:.1f}%  "
              f"total={best.total_pnl:+.2f}%  maxDD={best.max_dd:.2f}%")
        print(f"  中央値PF: {df.pf.median():.3f}  平均PF: {df.pf.mean():.3f}")

    summarize(df_roll,  "ローリング窓版")
    summarize(df_daily, "日次累積版")

    # 同一entry_thresholdでの直接比較
    print("\n─── entry_threshold別 最良PF 直接比較 ───")
    print(f"  {'entry':>8}  {'ローリング窓最良PF':>18}  {'日次累積最良PF':>14}")
    for entry in sorted(df_roll.entry_threshold.unique()):
        r = df_roll[df_roll.entry_threshold == entry]['pf'].max()
        d = df_daily[df_daily.entry_threshold == entry]['pf'].max() \
            if entry in df_daily.entry_threshold.values else float('nan')
        mark = "★" if r > 1.0 or d > 1.0 else ""
        print(f"  {entry:>8.4f}  {r:>18.3f}  {d:>14.3f}  {mark}")

    # ── チャート生成 ──────────────────────────────────────────────
    print("\n[チャート生成中]")
    plot_comparison(df_roll, df_daily)
    plot_best_pnl_curves(data, df_roll, df_daily)

    print(f"\n{'='*65}")
    print(f"完了!  出力先: {OUT_DIR.resolve()}")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
