# -*- coding: utf-8 -*-
"""
Daily-Open Lead-Lag 戦略 — パラメータサーベイ実行スクリプト
実行: python _run_daily_open_survey.py

データ: yfinance 5分足 直近50日（12通貨ペア）
出力:  docs/daily_open/ に CSV / PNG を保存
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ── フォント設定 ──────────────────────────────────────────────────────
FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
_prop = fm.FontProperties(fname=FONT_PATH, size=9)
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

OUT_DIR = Path("docs") / "daily_open"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ROOT = Path(__file__).parent
import sys; sys.path.insert(0, str(ROOT))

from fx_market_classifier.config import PAIRS
from fx_market_classifier.data_fetcher import fetch_ohlcv
from fx_market_classifier.daily_open_engine import (
    DailyOpenEngine, DailyOpenConfig, param_survey
)


# ══════════════════════════════════════════════════════════════════════
# データ読み込み
# ══════════════════════════════════════════════════════════════════════

def load_data(lookback_days: int = 55) -> dict:
    """yfinance から5分足データを取得"""
    print(f"\nデータ取得: yfinance 5分足 直近{lookback_days}日")
    data = fetch_ohlcv(pairs=PAIRS, interval="5m", lookback_days=lookback_days)
    print(f"取得済み: {list(data.keys())}")
    return data


# ══════════════════════════════════════════════════════════════════════
# チャート生成
# ══════════════════════════════════════════════════════════════════════

def plot_spread_example(price_data: dict, out_dir: Path):
    """USDJPY の Real vs Synthetic の可視化"""
    if 'USDJPY' not in price_data:
        return

    cfg    = DailyOpenConfig()
    engine = DailyOpenEngine(price_data, cfg)

    pair   = 'USDJPY'
    if pair not in engine.rp.columns or pair not in engine.sp.columns:
        return

    rp  = engine.rp[pair].dropna()
    sp  = engine.sp[pair].dropna()
    spd = engine.spread[pair].dropna()

    # 直近3日分
    last_date = rp.index[-1].normalize()
    start     = last_date - pd.Timedelta(days=3)
    mask      = rp.index >= start
    rp_p  = rp[mask];  sp_p  = sp[mask];  spd_p = spd[mask]

    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    fig.patch.set_facecolor('#F5F8FF')

    ax = axes[0]
    ax.set_facecolor('#F5F8FF')
    ax.plot(rp_p.index,  rp_p.values,  lw=1.5, color='#2266AA', label='Real %')
    ax.plot(sp_p.index,  sp_p.values,  lw=1.5, color='#CC6600', label='Synthetic %', ls='--')
    ax.axhline(0, color='#888', lw=0.5, ls=':')
    ax.set_ylabel('日足始値からの変化率 (%)', fontproperties=_prop)
    ax.set_title(f'USDJPY — Real vs Synthetic（直近3日）', fontproperties=_prop, fontsize=11)
    ax.legend(prop=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    ax = axes[1]
    ax.set_facecolor('#F5F8FF')
    colors = ['#CC3333' if v > 3 else ('#2266AA' if v < -3 else '#AAAAAA')
              for v in spd_p.values]
    ax.bar(spd_p.index, spd_p.values, color=colors, width=pd.Timedelta(minutes=4), alpha=0.8)
    ax.axhline(3,  color='#CC3333', lw=1.2, ls='--', label='+3% (entry)')
    ax.axhline(-3, color='#2266AA', lw=1.2, ls='--', label='-3% (entry)')
    ax.axhline(1,  color='#FF8800', lw=0.8, ls=':', label='+1% (exit)')
    ax.axhline(-1, color='#FF8800', lw=0.8, ls=':', label='-1% (exit)')
    ax.set_ylabel('Spread = Real% - Synthetic%', fontproperties=_prop)
    ax.set_title('Spread（乖離）', fontproperties=_prop, fontsize=11)
    ax.legend(prop=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    plt.tight_layout()
    out = out_dir / 'spread_example.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  チャート保存: {out}")


def plot_survey_heatmap(df: pd.DataFrame, sort_mode: str, out_dir: Path):
    """entry × exit の PF ヒートマップ"""
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

    fig, ax = plt.subplots(figsize=(6, 4))
    fig.patch.set_facecolor('#F5F8FF')
    ax.set_facecolor('#F5F8FF')

    im = ax.imshow(pf_mat, cmap='RdYlGn', vmin=0.8, vmax=1.5, aspect='auto')
    plt.colorbar(im, ax=ax, label='PF')

    ax.set_xticks(range(len(exit_vals)))
    ax.set_xticklabels([f'{v}%' for v in exit_vals], fontproperties=_prop)
    ax.set_yticks(range(len(entry_vals)))
    ax.set_yticklabels([f'{v}%' for v in entry_vals], fontproperties=_prop)
    ax.set_xlabel('exit_threshold', fontproperties=_prop)
    ax.set_ylabel('entry_threshold', fontproperties=_prop)
    ax.set_title(f'PF ヒートマップ (sort={sort_mode})', fontproperties=_prop, fontsize=11)

    for i in range(len(entry_vals)):
        for j in range(len(exit_vals)):
            v = pf_mat[i, j]
            if not np.isnan(v):
                ax.text(j, i, f'{v:.2f}', ha='center', va='center',
                        fontsize=9, fontweight='bold',
                        color='white' if v < 0.9 or v > 1.4 else 'black')

    plt.tight_layout()
    out = out_dir / f'heatmap_{sort_mode}.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  ヒートマップ保存: {out}")


def plot_pnl_curve(price_data: dict, cfg: DailyOpenConfig, label: str, out_dir: Path):
    """最良設定での累積損益曲線"""
    engine = DailyOpenEngine(price_data, cfg)
    df     = engine.run()
    if df.empty:
        return

    cum = df['capital_pnl'].cumsum()

    fig, axes = plt.subplots(2, 1, figsize=(12, 6))
    fig.patch.set_facecolor('#F5F8FF')

    ax = axes[0]
    ax.set_facecolor('#F5F8FF')
    ax.plot(cum.values, color='#2266AA', lw=2)
    ax.fill_between(range(len(cum)), cum.values, 0,
                    where=(cum.values >= 0), color='#2266AA', alpha=0.15)
    ax.fill_between(range(len(cum)), cum.values, 0,
                    where=(cum.values < 0),  color='#CC3333', alpha=0.15)
    ax.axhline(0, color='#888', lw=0.8, ls='--')
    ax.set_title(f'累積損益曲線 — {label}', fontproperties=_prop, fontsize=11)
    ax.set_ylabel('累積PnL (% of capital)', fontproperties=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    # ペア別内訳
    ax = axes[1]
    ax.set_facecolor('#F5F8FF')
    pair_pnl = df.groupby('pair')['capital_pnl'].sum().sort_values()
    colors   = ['#CC3333' if v < 0 else '#2266AA' for v in pair_pnl.values]
    ax.barh(pair_pnl.index, pair_pnl.values, color=colors, alpha=0.8)
    ax.axvline(0, color='#888', lw=0.8)
    ax.set_xlabel('累積PnL (% of capital)', fontproperties=_prop)
    ax.set_title('ペア別損益', fontproperties=_prop, fontsize=11)
    ax.grid(color='#D8E0F0', lw=0.4, axis='x')
    for i, (pair, val) in enumerate(pair_pnl.items()):
        ax.text(val + (0.01 if val >= 0 else -0.01), i,
                f'{val:+.2f}%', va='center',
                ha='left' if val >= 0 else 'right',
                fontsize=8)

    plt.tight_layout()
    safe_label = label.replace(' ', '_').replace('=', '').replace('%', 'pct')
    out = out_dir / f'pnl_curve_{safe_label}.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  PnLカーブ保存: {out}")

    # ペア別サマリーCSV
    pair_df = engine.metrics_by_pair()
    pair_df.to_csv(out_dir / f'pair_pnl_{safe_label}.csv')

    return df


def plot_exit_breakdown(df_trades: pd.DataFrame, label: str, out_dir: Path):
    """エグジット理由の内訳"""
    if df_trades is None or df_trades.empty:
        return

    reasons = df_trades['exit_reason'].value_counts()
    colors  = {
        'spread_reduced': '#2266AA',
        'stop':           '#CC3333',
        'time_limit':     '#FF8800',
        'day_end':        '#888888',
        'end_of_data':    '#AAAAAA',
    }

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fig.patch.set_facecolor('#F5F8FF')

    ax = axes[0]
    ax.set_facecolor('#F5F8FF')
    clrs = [colors.get(r, '#999') for r in reasons.index]
    ax.pie(reasons.values, labels=reasons.index, colors=clrs,
           autopct='%1.1f%%', startangle=90,
           textprops={'fontproperties': _prop})
    ax.set_title(f'エグジット理由 ({label})', fontproperties=_prop, fontsize=10)

    # 勝敗別PnL分布
    ax = axes[1]
    ax.set_facecolor('#F5F8FF')
    wins  = df_trades[df_trades.capital_pnl > 0]['capital_pnl']
    loses = df_trades[df_trades.capital_pnl <= 0]['capital_pnl']
    if not wins.empty:
        ax.hist(wins.values,  bins=20, color='#2266AA', alpha=0.7, label=f'勝({len(wins)})')
    if not loses.empty:
        ax.hist(loses.values, bins=20, color='#CC3333', alpha=0.7, label=f'負({len(loses)})')
    ax.axvline(0, color='#888', lw=1, ls='--')
    ax.set_xlabel('PnL (% of capital)', fontproperties=_prop)
    ax.set_ylabel('件数', fontproperties=_prop)
    ax.set_title('PnL分布', fontproperties=_prop, fontsize=10)
    ax.legend(prop=_prop)
    ax.grid(color='#D8E0F0', lw=0.4)

    plt.tight_layout()
    safe_label = label.replace(' ', '_').replace('=', '').replace('%', 'pct')
    out = out_dir / f'exit_breakdown_{safe_label}.png'
    plt.savefig(str(out), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  エグジット分布保存: {out}")


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Daily-Open Lead-Lag 戦略 パラメータサーベイ")
    print("=" * 60)

    # データ取得
    price_data = load_data(lookback_days=55)
    if len(price_data) < 4:
        print("ERROR: 取得ペア数不足。yfinanceの接続を確認してください。")
        return

    # ── Spread可視化 ─────────────────────────────────────────────────
    print("\n[1] Spread例チャート生成中...")
    plot_spread_example(price_data, OUT_DIR)

    # ── スプレッド分布確認 ────────────────────────────────────────────
    print("\n[スプレッド分布確認]")
    from fx_market_classifier.daily_open_engine import DailyOpenEngine, DailyOpenConfig
    _eng = DailyOpenEngine(price_data, DailyOpenConfig(entry_threshold=0.01))
    for pair in _eng.spread.columns:
        s = _eng.spread[pair].dropna()
        q99 = s.abs().quantile(0.99)
        q95 = s.abs().quantile(0.95)
        p03 = (s.abs() > 0.3).mean() * 100
        p01 = (s.abs() > 0.1).mean() * 100
        print(f"  {pair}: 99th={q99:.3f}%  95th={q95:.3f}%  >0.1%:{p01:.1f}%  >0.3%:{p03:.2f}%")

    # ── パラメータサーベイ ────────────────────────────────────────────
    # FXイントラデイのスプレッドは日本株より2桁小さい（最大0.3〜1.5%）
    # entry [0.10, 0.20, 0.30]% × exit [0.03, 0.05, 0.10]% × sort × 2
    print("\n[2] パラメータサーベイ実行中（18通り）...")
    survey_df = param_survey(
        price_data,
        entry_grid=[0.10, 0.20, 0.30],
        exit_grid=[0.03, 0.05, 0.10],
        sort_modes=['spread', 'strength'],
        stop_loss_pct=1.5,
        time_limit_bars=60,
        risk_pct=0.5,
    )

    survey_df.to_csv(OUT_DIR / 'survey_results.csv', index=False)
    print(f"\nサーベイ結果保存: {OUT_DIR}/survey_results.csv")
    print("\n上位5件:")
    print(survey_df.head(5)[['entry_threshold','exit_threshold','sort_mode',
                              'trades','win_rate','pf','total_pnl','max_dd']].to_string())

    # ── ヒートマップ ──────────────────────────────────────────────────
    print("\n[3] ヒートマップ生成中...")
    for smode in ['spread', 'strength']:
        plot_survey_heatmap(survey_df, smode, OUT_DIR)

    # ── 最良設定での詳細分析 ──────────────────────────────────────────
    print("\n[4] 最良設定での詳細分析...")
    if not survey_df.empty:
        # Sort mode 別に最良設定を取得
        for smode in ['spread', 'strength']:
            best = survey_df[survey_df.sort_mode == smode].iloc[0]
            label = (f"entry={best.entry_threshold}% "
                     f"exit={best.exit_threshold}% "
                     f"sort={smode}")
            print(f"\n  最良（{smode}）: {label}")
            print(f"    PF={best.pf:.3f}  trades={int(best.trades)}"
                  f"  win={best.win_rate*100:.1f}%  total={best.total_pnl:+.2f}%")

            cfg = DailyOpenConfig(
                entry_threshold=best.entry_threshold,
                exit_threshold=best.exit_threshold,
                sort_mode=smode,
                stop_loss_pct=1.5,
                time_limit_bars=60,
                risk_pct=0.5,
            )
            df_trades = plot_pnl_curve(price_data, cfg, label, OUT_DIR)
            if df_trades is not None:
                plot_exit_breakdown(df_trades, label, OUT_DIR)

                # ベストトレード一覧
                best_trades = (df_trades.sort_values('capital_pnl', ascending=False)
                               .head(20))
                best_trades.to_csv(
                    OUT_DIR / f'best_trades_{smode}.csv', index=False)

    print(f"\n{'='*60}")
    print(f"完了! 出力先: {OUT_DIR.resolve()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
