# -*- coding: utf-8 -*-
"""
通貨強弱 × ゴールデンクロス戦略 バックテスト
=============================================
スクリーニング : 東京セッション（9:00〜15:30 JST）の通貨強弱差が大きいペアを選定
エントリー     : ゴールデンクロス（MA10 > MA20）→ ロング
               : デッドクロス（MA10 < MA20）  → ショート
エグジット     : 反対方向のクロス / ストップロス1%
取引時間       : NYセッション〜ロンドンセッション（UTC 0:00〜8:00 = JST 9:00〜17:00前後）
                 実装: UTC 21:00〜6:00（NY 22:00〜London 6:00 JST）
対象           : 12通貨ペア全て
検証期間       : 2024-11-01 〜 2024-12-31（直近2ヶ月）

実行: python _run_golden_cross_strategy.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import time
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass
_p8  = fm.FontProperties(fname=FONT_PATH, size=8)
_p9  = fm.FontProperties(fname=FONT_PATH, size=9)
_p10 = fm.FontProperties(fname=FONT_PATH, size=10)

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "golden_cross"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALL_PAIRS = [
    "USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
    "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD",
]

START = "2024-11-01"
END   = "2024-12-31"

MA_TREND_S = 50      # トレンド方向フィルター（短期）
MA_TREND_L = 200     # トレンド方向フィルター（長期）
MA_ENTRY_S = 10      # エントリー用短期MA
MA_ENTRY_L = 20      # エントリー用長期MA
STOP_PCT   = 1.0     # ストップロス（%）
COST_PCT   = 0.0002  # 片道コスト（0.02%）
TOP_N      = 3       # 東京セッションで選ぶ上位ペア数

# 東京セッション（UTC: 0:00〜6:30 = JST 9:00〜15:30）
TOKYO_START_UTC = 0    # UTC 0:00
TOKYO_END_UTC   = 6    # UTC 6:00

# NYセッション〜ロンドン（UTC: 21:00〜6:00 翌日）
TRADE_START_UTC = 21   # UTC 21:00（=JST22:00, NY open前後）
TRADE_END_UTC   = 6    # UTC 6:00（=JST15:00, London morning）


# ══════════════════════════════════════════════════════════════════════
# 1. データ読み込み
# ══════════════════════════════════════════════════════════════════════

def load_data() -> dict:
    data = {}
    print(f"\nデータ読み込み: {START} 〜 {END}")
    for p in ALL_PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if not f.exists(): continue
        df = pd.read_parquet(f)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        sub = df.loc[START:END]
        if len(sub) < 100: continue
        data[p] = sub
        print(f"  {p}: {len(sub):,}本")
    return data


# ══════════════════════════════════════════════════════════════════════
# 2. 通貨強弱計算（LOO: Leave-One-Out）
# ══════════════════════════════════════════════════════════════════════

from fx_market_classifier.features import currency_strength
from fx_market_classifier.config   import PAIR_CURRENCIES

def compute_strength_loo(returns: dict) -> dict:
    """各ペアの通貨強弱差を LOO で計算"""
    strength_diff = {}
    for pair in returns:
        base, quote = PAIR_CURRENCIES.get(pair, (None, None))
        if not base or not quote: continue
        ret_loo = {p: r for p, r in returns.items() if p != pair}
        if not ret_loo: continue
        st_loo = currency_strength(ret_loo, PAIR_CURRENCIES)
        if base not in st_loo.columns or quote not in st_loo.columns:
            continue
        strength_diff[pair] = (st_loo[base] - st_loo[quote]).reindex(returns[pair].index)
    return strength_diff


# ══════════════════════════════════════════════════════════════════════
# 3. 東京セッションで通貨強弱差が大きいペアをランキング
# ══════════════════════════════════════════════════════════════════════

def select_pairs_daily(data: dict, strength_diff: dict, date: pd.Timestamp) -> list:
    """東京セッションの通貨強弱差（絶対値）でペアをランキングして上位N選択"""
    t_start = date + pd.Timedelta(hours=TOKYO_START_UTC)
    t_end   = date + pd.Timedelta(hours=TOKYO_END_UTC)

    scores = {}
    for pair, diff_series in strength_diff.items():
        window = diff_series.loc[t_start:t_end].dropna()
        if len(window) == 0: continue
        # 東京セッション終盤の強弱差（最後の30分の平均）
        scores[pair] = float(window.tail(6).abs().mean())

    if not scores: return []
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    selected = [p for p, _ in ranked[:TOP_N]]
    return selected


# ══════════════════════════════════════════════════════════════════════
# 4. バックテスト
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    pair:        str
    direction:   int       # +1=Long, -1=Short
    entry_price: float
    entry_time:  pd.Timestamp
    stop_price:  float

    def pnl(self, price: float) -> float:
        raw = self.direction * (price / self.entry_price - 1.0)
        return raw - 2 * COST_PCT

    def stopped(self, low: float, high: float) -> bool:
        if self.direction == 1:
            return low <= self.stop_price
        else:
            return high >= self.stop_price


def in_trade_window(ts: pd.Timestamp) -> bool:
    """NY〜Londonセッション（UTC 21:00〜翌6:00）かどうか"""
    h = ts.hour
    return h >= TRADE_START_UTC or h < TRADE_END_UTC


def run_backtest(data: dict) -> pd.DataFrame:
    """日次でペア選定し、ゴールデンクロス戦略を実行"""
    sys.path.insert(0, str(ROOT))

    # リターンと強弱計算
    returns = {}
    for p, df in data.items():
        returns[p] = np.log(df["Close"] / df["Close"].shift(1)).dropna()

    print("\n通貨強弱（LOO）計算中...")
    strength_diff = compute_strength_loo(returns)

    # MA計算（全期間で計算しておく）
    ma_ts = {p: df["Close"].rolling(MA_TREND_S).mean() for p, df in data.items()}
    ma_tl = {p: df["Close"].rolling(MA_TREND_L).mean() for p, df in data.items()}
    ma_es = {p: df["Close"].rolling(MA_ENTRY_S).mean() for p, df in data.items()}
    ma_el = {p: df["Close"].rolling(MA_ENTRY_L).mean() for p, df in data.items()}

    # 日次ループ
    trading_days = pd.bdate_range(START, END, freq="B")
    all_trades   = []
    positions    = {}   # pair → Position

    print(f"\nバックテスト実行中... {len(trading_days)}営業日")

    for day in trading_days:
        # 東京セッションで選定
        selected = select_pairs_daily(data, strength_diff, day)
        if not selected: continue

        # NYセッション〜Londonで取引
        trade_start = day + pd.Timedelta(hours=TRADE_START_UTC)
        trade_end   = day + pd.Timedelta(days=1, hours=TRADE_END_UTC)

        for pair in selected:
            df = data[pair]

            # セッション開始時点のMA50/200でトレンド方向を決定
            ts_open = trade_start
            try:
                ts_val   = ma_ts[pair].loc[:ts_open].dropna().iloc[-1]
                tl_val   = ma_tl[pair].loc[:ts_open].dropna().iloc[-1]
            except (IndexError, KeyError):
                continue
            if np.isnan(ts_val) or np.isnan(tl_val):
                continue

            # トレンド方向: +1=ロング許可, -1=ショート許可
            trend_dir = +1 if ts_val > tl_val else -1

            # 対象時間帯のバーを取得
            bars  = df.loc[trade_start:trade_end]
            es_b  = ma_es[pair].loc[trade_start:trade_end]
            el_b  = ma_el[pair].loc[trade_start:trade_end]
            if len(bars) < MA_ENTRY_L + 1: continue

            pos = positions.get(pair)

            for i in range(1, len(bars)):
                ts    = bars.index[i]
                close = float(bars["Close"].iloc[i])
                low   = float(bars["Low"].iloc[i])
                high  = float(bars["High"].iloc[i])
                es    = float(es_b.iloc[i])   if i < len(es_b) else np.nan
                el    = float(el_b.iloc[i])   if i < len(el_b) else np.nan
                es_p  = float(es_b.iloc[i-1]) if i-1 < len(es_b) else np.nan
                el_p  = float(el_b.iloc[i-1]) if i-1 < len(el_b) else np.nan

                if np.isnan(es) or np.isnan(el): continue

                # ストップチェック
                if pos is not None and pos.pair == pair:
                    if pos.stopped(low, high):
                        exit_price = pos.stop_price
                        pnl = pos.direction * (exit_price / pos.entry_price - 1.0) - 2*COST_PCT
                        all_trades.append({
                            "pair": pair, "direction": pos.direction,
                            "entry_time": pos.entry_time, "exit_time": ts,
                            "entry_price": pos.entry_price, "exit_price": exit_price,
                            "pnl_pct": pnl * 100, "exit_reason": "stop",
                            "trend": trend_dir,
                        })
                        positions.pop(pair)
                        pos = None

                # エントリー用クロス判定（MA10/20）
                golden = (es_p <= el_p) and (es > el)
                dead   = (es_p >= el_p) and (es < el)

                # MA50/200トレンドに順張りのみ許可
                if golden and trend_dir == +1 and (pos is None or pos.direction == -1):
                    if pos is not None:
                        pnl = pos.direction * (close / pos.entry_price - 1.0) - 2*COST_PCT
                        all_trades.append({
                            "pair": pair, "direction": pos.direction,
                            "entry_time": pos.entry_time, "exit_time": ts,
                            "entry_price": pos.entry_price, "exit_price": close,
                            "pnl_pct": pnl * 100, "exit_reason": "cross",
                            "trend": trend_dir,
                        })
                    stop = close * (1 - STOP_PCT/100)
                    positions[pair] = Position(pair, +1, close, ts, stop)
                    pos = positions[pair]

                elif dead and trend_dir == -1 and (pos is None or pos.direction == +1):
                    if pos is not None:
                        pnl = pos.direction * (close / pos.entry_price - 1.0) - 2*COST_PCT
                        all_trades.append({
                            "pair": pair, "direction": pos.direction,
                            "entry_time": pos.entry_time, "exit_time": ts,
                            "entry_price": pos.entry_price, "exit_price": close,
                            "pnl_pct": pnl * 100, "exit_reason": "cross",
                            "trend": trend_dir,
                        })
                    stop = close * (1 + STOP_PCT/100)
                    positions[pair] = Position(pair, -1, close, ts, stop)
                    pos = positions[pair]

            # セッション終了時に残ポジをクローズ
            if pos is not None and pos.pair == pair and pair in positions:
                last = bars["Close"].iloc[-1]
                last_ts = bars.index[-1]
                pnl = pos.direction * (float(last) / pos.entry_price - 1.0) - 2*COST_PCT
                all_trades.append({
                    "pair": pair, "direction": pos.direction,
                    "entry_time": pos.entry_time, "exit_time": last_ts,
                    "entry_price": pos.entry_price, "exit_price": float(last),
                    "pnl_pct": pnl * 100, "exit_reason": "session_end",
                    "trend": trend_dir,
                })
                positions.pop(pair)

    # 残ポジション強制クローズ
    for pair, pos in positions.items():
        df = data[pair]
        last_price = float(df["Close"].iloc[-1])
        pnl = pos.direction * (last_price / pos.entry_price - 1.0) - 2*COST_PCT
        all_trades.append({
            "pair": pair, "direction": pos.direction,
            "entry_time": pos.entry_time, "exit_time": df.index[-1],
            "entry_price": pos.entry_price, "exit_price": last_price,
            "pnl_pct": pnl * 100, "exit_reason": "end_of_data",
        })

    return pd.DataFrame(all_trades)


# ══════════════════════════════════════════════════════════════════════
# 5. チャート・集計
# ══════════════════════════════════════════════════════════════════════

def make_charts(df: pd.DataFrame):
    if df.empty: return

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.patch.set_facecolor("#F5F8FF")
    fig.suptitle(f"通貨強弱×ゴールデンクロス戦略  {START}〜{END}",
                 fontproperties=_p10, fontsize=12, y=1.01)

    # 1. 累積損益
    ax = axes[0][0]; ax.set_facecolor("#F5F8FF"); ax.grid(color="#D8E0F0", lw=0.4)
    cum = df["pnl_pct"].cumsum()
    ax.plot(range(len(cum)), cum.values, color="#2266AA", lw=1.5)
    ax.fill_between(range(len(cum)), cum.values, 0,
                    where=(cum.values >= 0), color="#2266AA", alpha=0.15)
    ax.fill_between(range(len(cum)), cum.values, 0,
                    where=(cum.values <  0), color="#CC3333", alpha=0.15)
    ax.axhline(0, color="#888", lw=0.8, ls="--")
    ax.set_title("累積損益（%）", fontproperties=_p9)
    ax.set_xlabel("トレード番号", fontproperties=_p8)
    ax.set_ylabel("累積PnL (%)", fontproperties=_p8)

    # 2. ペア別損益
    ax = axes[0][1]; ax.set_facecolor("#F5F8FF"); ax.grid(color="#D8E0F0", lw=0.4, axis="x")
    ps = df.groupby("pair")["pnl_pct"].sum().sort_values()
    colors = ["#22AA66" if v >= 0 else "#CC3333" for v in ps.values]
    ax.barh(ps.index, ps.values, color=colors, alpha=0.8, height=0.6)
    ax.axvline(0, color="#333", lw=1)
    ax.set_title("ペア別累積損益（%）", fontproperties=_p9)
    for i, (pair, v) in enumerate(ps.items()):
        ax.text(v + (0.05 if v >= 0 else -0.05), i, f"{v:+.2f}%",
                va="center", ha="left" if v >= 0 else "right",
                fontproperties=_p8)
    for tl in ax.get_yticklabels(): tl.set_fontproperties(_p8)

    # 3. エグジット理由
    ax = axes[1][0]; ax.set_facecolor("#F5F8FF")
    reasons = df["exit_reason"].value_counts()
    colors3 = {"cross":"#2266AA","stop":"#CC3333","end_of_data":"#888888"}
    ax.pie(reasons.values,
           labels=[f"{k}\n({v}件)" for k, v in reasons.items()],
           colors=[colors3.get(k,"#AAAAAA") for k in reasons.index],
           autopct="%1.1f%%", textprops={"fontsize":8})
    ax.set_title("エグジット理由", fontproperties=_p9)

    # 4. 方向別損益
    ax = axes[1][1]; ax.set_facecolor("#F5F8FF"); ax.grid(color="#D8E0F0", lw=0.4, axis="y")
    for direction, label, color in [(1,"Long","#2266AA"),(-1,"Short","#CC3333")]:
        sub = df[df["direction"]==direction]["pnl_pct"]
        if not sub.empty:
            ax.bar(label, sub.sum(), color=color, alpha=0.8, width=0.4,
                   label=f"{label}: {len(sub)}件")
    ax.axhline(0, color="#333", lw=0.8, ls="--")
    ax.set_title("ロング / ショート 別損益（%）", fontproperties=_p9)
    ax.legend(prop=_p8)

    plt.tight_layout()
    out = OUT_DIR / "golden_cross_result.png"
    plt.savefig(str(out), dpi=140, bbox_inches="tight", facecolor="#F5F8FF")
    plt.close(fig)
    print(f"  チャート保存: {out.name}")


def print_summary(df: pd.DataFrame):
    if df.empty:
        print("\n[結果] トレードなし")
        return
    pnl   = df["pnl_pct"]
    wins  = pnl[pnl > 0]; loses = pnl[pnl <= 0]
    pf    = wins.sum() / abs(loses.sum()) if loses.sum() != 0 else float("inf")
    cum   = pnl.cumsum()
    dd    = float((cum - cum.cummax()).min())

    print(f"\n{'='*55}")
    print(f"【結果サマリー】  {START} 〜 {END}")
    print(f"{'='*55}")
    print(f"  トレード数  : {len(df)}件")
    print(f"  勝率        : {(pnl>0).mean()*100:.1f}%  ({len(wins)}勝{len(loses)}敗)")
    print(f"  PF          : {pf:.3f}")
    print(f"  累積損益    : {pnl.sum():+.2f}%")
    print(f"  最大DD      : {dd:.2f}%")
    print(f"  平均損益    : {pnl.mean()*100:.3f}bp")
    print(f"\n--- エグジット理由 ---")
    for reason, cnt in df["exit_reason"].value_counts().items():
        print(f"  {reason:<15}: {cnt}件")
    print(f"\n--- ペア別成績（上位） ---")
    ps = df.groupby("pair")["pnl_pct"].agg(
        total_pnl="sum", trades="count",
        win_rate=lambda x: (x>0).mean()
    ).sort_values("total_pnl", ascending=False)
    print(ps.round(3).to_string())


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 55)
    print("通貨強弱 × ゴールデンクロス戦略")
    print(f"  期間 : {START} 〜 {END}")
    print(f"  トレンドMA: {MA_TREND_S}/{MA_TREND_L}本（方向フィルター）")
    print(f"  エントリーMA: {MA_ENTRY_S}/{MA_ENTRY_L}本（クロス判定）")
    print(f"  Stop : {STOP_PCT}%")
    print(f"  上位 : {TOP_N}ペア/日（東京セッション強弱差）")
    print(f"  取引 : UTC {TRADE_START_UTC}:00〜{TRADE_END_UTC}:00")
    print("=" * 55)

    data = load_data()
    if len(data) < 2:
        print("ERROR: データ不足"); return

    df = run_backtest(data)

    if not df.empty:
        df.to_csv(OUT_DIR/"golden_cross_trades.csv", index=False, encoding="utf-8-sig")

    print_summary(df)
    print("\n[チャート生成中...]")
    make_charts(df)

    elapsed = time.time() - t0
    print(f"\n完了: {elapsed:.0f}秒  出力: {OUT_DIR}")


if __name__ == "__main__":
    main()
