"""
USDJPY レンジブレイク戦略 マルチタイムフレーム比較

対象TF: 1min / 5min / 15min / 30min / 1h / 4h
- 5min以上: 既存5分足をリサンプル
- 1min    : USDJPY_1min.parquet を使用（他ペアの強弱は5分足から補完）

各TFでパラメータを時間軸に合わせてスケール:
  range_bars × TF_minutes ≒ 同じ時間窓
  range_pips は典型ボラに合わせて調整
  min_hold も等時間になるよう調整

IS: 2022-01-01 ~ 2024-01-01
OOS: 2024-01-01 ~ 2025-01-01
コスト: DMMFX 0.2pips（エントリー時のみ）
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR  = Path("data/dukascopy")
PAIR      = "USDJPY"
PIP       = 0.01
IS_START  = "2022-01-01"
IS_END    = "2024-01-01"
OOS_START = "2024-01-01"
OOS_END   = "2025-01-01"

ENTRY_COST = 0.2   # pips（DMMFX）
STRENGTH_WINDOW_5MIN = 20   # 強弱スコアのベースウィンドウ（5分足換算）

# ── タイムフレーム設定 ──────────────────────────────────────────────────────────
# range_bars × tf_min ≒ 60分のレンジ窓を基準にスケール
TIMEFRAMES = {
    "1min":  dict(tf_min=1,   range_bars=60,  range_pips=3,   min_hold=25),
    "5min":  dict(tf_min=5,   range_bars=12,  range_pips=10,  min_hold=5),
    "15min": dict(tf_min=15,  range_bars=8,   range_pips=15,  min_hold=4),
    "30min": dict(tf_min=30,  range_bars=6,   range_pips=25,  min_hold=3),
    "1h":    dict(tf_min=60,  range_bars=4,   range_pips=40,  min_hold=2),
    "4h":    dict(tf_min=240, range_bars=3,   range_pips=80,  min_hold=2),
}

CAPITAL_JPY = 1_000_000
PIP_VAL_JPY = 667   # DMMFX 10倍レバ: 6.7万通貨, 1pip=667円


# ── データ準備 ────────────────────────────────────────────────────────────────

def load_5min() -> dict[str, pd.DataFrame]:
    return {p: pd.read_parquet(DATA_DIR / f"{p}_5min.parquet")
            for p in PAIRS if (DATA_DIR / f"{p}_5min.parquet").exists()}

def load_1min() -> pd.DataFrame | None:
    f = DATA_DIR / "USDJPY_1min.parquet"
    return pd.read_parquet(f) if f.exists() else None

def compute_strength_diff_5min(dfs5: dict) -> pd.Series:
    rd = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
    st = currency_strength(rd)
    w  = STRENGTH_WINDOW_5MIN
    return (st["USD"].rolling(w).sum() - st["JPY"].rolling(w).sum()).rename("sd")

def resample_ohlcv(df5: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df5.resample(rule, label="left", closed="left").agg(
        Open=("Open","first"), High=("High","max"),
        Low=("Low","min"), Close=("Close","last"), Volume=("Volume","sum")
    ).dropna(subset=["Open"])

def get_tf_df(dfs5: dict, tf_label: str, df_1min: pd.DataFrame | None) -> pd.DataFrame | None:
    df5 = dfs5.get(PAIR)
    if df5 is None:
        return None
    if tf_label == "1min":
        return df_1min
    elif tf_label == "5min":
        return df5
    else:
        rule_map = {"15min":"15min","30min":"30min","1h":"1h","4h":"4h"}
        return resample_ohlcv(df5, rule_map[tf_label])

def get_strength_for_tf(sd5: pd.Series, df_tf: pd.DataFrame, tf_label: str) -> pd.Series:
    """5分足強弱をTFに合わせて変換（1min以外はリサンプル、1minは5minを前方補完）"""
    if tf_label == "5min":
        return sd5.reindex(df_tf.index)
    elif tf_label == "1min":
        # 5分足強弱を1分足インデックスに前方補完
        combined = sd5.reindex(sd5.index.union(df_tf.index)).ffill()
        return combined.reindex(df_tf.index)
    else:
        rule_map = {"15min":"15min","30min":"30min","1h":"1h","4h":"4h"}
        return sd5.resample(rule_map[tf_label], label="left", closed="left").last().reindex(df_tf.index)


# ── シグナル・バックテスト ─────────────────────────────────────────────────────

def make_signals(df: pd.DataFrame, sd: pd.Series, range_bars: int, range_pips: int):
    close = df["Close"]
    rh    = close.shift(1).rolling(range_bars).max()
    rl    = close.shift(1).rolling(range_bars).min()
    rm    = (rh + rl) / 2
    inR   = (rh - rl) <= range_pips * PIP
    return pd.DataFrame({
        "close": close, "open": df["Open"],
        "long_sig":  inR & (close > rh) & (sd > 0),
        "short_sig": inR & (close < rl) & (sd < 0),
        "range_mid": rm,
    })

def run_backtest(signals: pd.DataFrame, min_hold: int) -> np.ndarray:
    close = signals["close"].values
    open_ = signals["open"].values
    rm    = signals["range_mid"].values
    ls    = signals["long_sig"].values
    ss    = signals["short_sig"].values
    n     = len(signals)

    pnls = []
    inT = False; d = 0; ep = sp = 0.0; eb = -1

    for i in range(1, n - 1):
        if not inT:
            if ls[i-1]: d=1; ep=open_[i]+ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
            elif ss[i-1]: d=-1; ep=open_[i]-ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
        else:
            held = i - eb
            unr  = (close[i] - ep) * d / PIP
            xp   = None
            if d==1 and close[i]<=sp: xp=sp
            elif d==-1 and close[i]>=sp: xp=sp
            elif held>=min_hold and unr>0:
                if d==1 and close[i]<close[i-1]: xp=close[i]
                elif d==-1 and close[i]>close[i-1]: xp=close[i]
            if xp is not None:
                pnls.append((xp - ep) * d / PIP)
                inT=False; d=0
    return np.array(pnls)

def metrics(pnls: np.ndarray) -> dict:
    if len(pnls) == 0:
        return dict(n=0, wr=0, pf=0, ev=0, total_jpy=0, dd_pct=0)
    wins = pnls[pnls>0]; loss = pnls[pnls<=0]
    wr   = len(wins)/len(pnls)*100
    pf   = wins.sum()/abs(loss.sum()) if loss.sum()!=0 else np.inf
    ev   = pnls.mean()
    eq   = np.cumsum(pnls)
    peak = np.maximum.accumulate(np.maximum(eq, 0))
    dd   = (eq - peak).min() * PIP_VAL_JPY / CAPITAL_JPY * 100
    return dict(n=len(pnls), wr=wr, pf=pf, ev=ev,
                total_jpy=pnls.sum()*PIP_VAL_JPY, dd_pct=dd)


# ── メイン ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print(f" USDJPY レンジブレイク マルチTF比較")
    print(f" IS:{IS_START}~{IS_END}  OOS:{OOS_START}~{OOS_END}")
    print(f" コスト: DMMFX {ENTRY_COST}pips / レバ10倍 1pip={PIP_VAL_JPY}円")
    print("=" * 72)

    print("\nデータ読み込み中...")
    dfs5   = load_5min()
    df_1m  = load_1min()
    sd5    = compute_strength_diff_5min(dfs5)

    rows_is  = []
    rows_oos = []

    for tf_label, cfg in TIMEFRAMES.items():
        tf_min     = cfg["tf_min"]
        range_bars = cfg["range_bars"]
        range_pips = cfg["range_pips"]
        min_hold   = cfg["min_hold"]

        df_tf = get_tf_df(dfs5, tf_label, df_1m)
        if df_tf is None:
            print(f"  {tf_label}: データなし スキップ")
            continue

        sd_tf = get_strength_for_tf(sd5, df_tf, tf_label)

        # IS
        df_is = df_tf.loc[IS_START:IS_END]
        sd_is = sd_tf.reindex(df_is.index)
        sig_is = make_signals(df_is, sd_is, range_bars, range_pips)
        pnls_is = run_backtest(sig_is, min_hold)
        m_is = metrics(pnls_is)
        m_is["tf"] = tf_label
        m_is["range_time"] = f"{range_bars*tf_min}分"
        m_is["hold_time"]  = f"{min_hold*tf_min}分"
        rows_is.append(m_is)

        # OOS
        df_oos = df_tf.loc[OOS_START:OOS_END]
        sd_oos = sd_tf.reindex(df_oos.index)
        sig_oos = make_signals(df_oos, sd_oos, range_bars, range_pips)
        pnls_oos = run_backtest(sig_oos, min_hold)
        m_oos = metrics(pnls_oos)
        m_oos["tf"] = tf_label
        rows_oos.append(m_oos)

        print(f"  {tf_label:>4} 完了: IS {m_is['n']}件 PF={m_is['pf']:.2f} / "
              f"OOS {m_oos['n']}件 PF={m_oos['pf']:.2f}")

    # ── IS結果表 ─────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  IS結果（{IS_START} ~ {IS_END}）  レバ10倍・1pip={PIP_VAL_JPY}円")
    print(f"{'='*72}")
    print(f"  {'TF':>4} {'レンジ窓':>6} {'保有目安':>6} | "
          f"{'N':>5} {'WR%':>6} {'PF':>5} {'期待値':>7} {'損益(万)':>8} {'DD%':>7}")
    print("  " + "-" * 65)
    for r in rows_is:
        pf_str = f"{r['pf']:.2f}" if r['pf'] != np.inf else " inf"
        mark = " ★" if r["tf"] == "5min" else ""
        print(f"  {r['tf']:>4} {r['range_time']:>6} {r['hold_time']:>6} | "
              f"{r['n']:>5} {r['wr']:>6.1f} {pf_str:>5} "
              f"{r['ev']:>+7.3f}p {r['total_jpy']/10000:>+8.1f} {r['dd_pct']:>+7.2f}%{mark}")

    # ── OOS結果表 ─────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  OOS結果（{OOS_START} ~ {OOS_END}）")
    print(f"{'='*72}")
    print(f"  {'TF':>4} | {'N':>5} {'WR%':>6} {'PF':>5} {'期待値':>7} {'損益(万)':>8} {'DD%':>7}")
    print("  " + "-" * 50)
    for r in rows_oos:
        pf_str = f"{r['pf']:.2f}" if r['pf'] != np.inf else " inf"
        mark = " ★" if r["tf"] == "5min" else ""
        print(f"  {r['tf']:>4} | {r['n']:>5} {r['wr']:>6.1f} {pf_str:>5} "
              f"{r['ev']:>+7.3f}p {r['total_jpy']/10000:>+8.1f} {r['dd_pct']:>+7.2f}%{mark}")

    # ── IS/OOS比較サマリー ────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  IS/OOS PF比較")
    print(f"{'='*72}")
    print(f"  {'TF':>4} | {'IS PF':>7} {'OOS PF':>8} {'乖離':>6} {'IS損益':>8} {'OOS損益':>8}")
    print("  " + "-" * 55)
    for is_r, oos_r in zip(rows_is, rows_oos):
        diff = abs(is_r["pf"] - oos_r["pf"]) if oos_r["pf"] != np.inf else 99
        mark = " ★" if is_r["tf"] == "5min" else ""
        print(f"  {is_r['tf']:>4} | {is_r['pf']:>7.2f} {oos_r['pf']:>8.2f} "
              f"{diff:>+6.2f} {is_r['total_jpy']/10000:>+8.1f}万 "
              f"{oos_r['total_jpy']/10000:>+8.1f}万{mark}")

    print(f"\n  パラメータ設定:")
    for tf_label, cfg in TIMEFRAMES.items():
        print(f"    {tf_label:>4}: range_bars={cfg['range_bars']} "
              f"range_pips={cfg['range_pips']} min_hold={cfg['min_hold']}")

    print("=" * 72)

if __name__ == "__main__":
    main()
