# -*- coding: utf-8 -*-
"""
EURJPY 通貨強弱×自己相関スキャルピング戦略
デモ運用 シグナル生成・架空執行スクリプト

処理フロー:
  1. data/dukascopy/EURJPY_5min.parquet を読み込む
  2. 全12ペアから通貨強弱（EUR-JPY差）を計算
  3. IS期間（2022-2023）の分位点で Q_THRESH を固定
  4. オープンポジション管理（トレイリングストップ / タイム決済）
  5. 新規シグナル検出（直近24〜48時間）
  6. trades.csv / summary.json を更新
  7. コンソールにサマリーを出力

実行:
  python fx_demo/eurjpy_signal.py
  python fx_demo/eurjpy_signal.py --dry-run  # 状態変更なし

GitHub Actions: 毎日 JST 8:00 （= UTC 23:00 前日）に自動実行
"""
import sys, json, argparse, uuid
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# ── ベースパス ────────────────────────────────────────────────
BASE     = Path(__file__).parent.parent
DATA_DIR = BASE / "data" / "dukascopy"
DEMO_DIR = Path(__file__).parent
TRADES_CSV  = DEMO_DIR / "trades.csv"
SUMMARY_JSON= DEMO_DIR / "summary.json"

# ── 確定パラメータ ─────────────────────────────────────────────
IS_START  = "2022-01-01"
IS_END    = "2023-12-31"

Q_EXTREME       = 0.03    # 強弱差 IS期間 下位3%
AC_MIN          = 0.10    # 自己相関係数 閾値
STRENGTH_WINDOW = 24      # 強弱スコアウィンドウ（5min×24=2時間）
AC_WINDOW       = 12      # 自己相関ウィンドウ（5min×12=1時間）
MAX_HOLD        = 48      # 最大保有バー数（48×5min=4時間）

SPREAD_PIPS = 0.5         # スプレッド
PIP_VALUE   = 100         # 1lot×1pip=100円
PIP_SIZE    = 0.01        # EURJPY 1pip=0.01
CAPITAL     = 1_000_000
RISK_PCT    = 0.005       # 0.5%
ATR_PERIOD  = 14

# 最新シグナル検索範囲（バー数: 48bar=4h, 576bar=48h）
SIGNAL_LOOKBACK = 576     # 直近48時間分

JST = pd.Timedelta(hours=9)

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# EURJPYセッション別プレイブック
# (name, start_jst, end_jst, direction +1=LONG/-1=SHORT, ac_sign)
SESSIONS = [
    ("東京 09-15JST",  9, 15, +1, "ac<0"),   # △long, ac<-0.10
    ("欧州 15-21JST", 15, 21, -1, "ac>0"),   # ▼SHORT（主力）, ac>+0.10
    ("NY   21-03JST", 21,  3, +1, "ac<0"),   # ▲LONG（主力）, ac<-0.10
    ("深夜 03-09JST",  3,  9, +1, "ac<0"),   # △long, ac<-0.10
]

# ── ログユーティリティ ─────────────────────────────────────────
def _log(msg: str, dry_run: bool = False):
    prefix = "[DRY-RUN] " if dry_run else ""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {prefix}{msg}")


# ── データ読み込み ─────────────────────────────────────────────
def load_data():
    """全12ペアの5分足データを読み込み、共通インデックスに整列"""
    dfs = {}
    for pair in PAIR_CURRENCIES:
        f = DATA_DIR / f"{pair}_5min.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        dfs[pair] = df[["Open","High","Low","Close"]]

    if "EURJPY" not in dfs:
        raise FileNotFoundError("EURJPY_5min.parquet が見つかりません")

    common_idx = dfs["EURJPY"].index
    for p in dfs:
        common_idx = common_idx.intersection(dfs[p].index)
    for p in dfs:
        dfs[p] = dfs[p].reindex(common_idx)

    return dfs, common_idx


# ── 通貨強弱スコア ─────────────────────────────────────────────
def calc_strength(dfs, common_idx):
    pair_lr = {p: np.log(df["Close"] / df["Close"].shift(STRENGTH_WINDOW))
               for p, df in dfs.items()}
    raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
    cnt = {c: 0 for c in CURRENCIES}
    for pair, (b, q) in PAIR_CURRENCIES.items():
        if pair not in pair_lr: continue
        raw_str[b] += pair_lr[pair]
        raw_str[q] -= pair_lr[pair]
        cnt[b] += 1; cnt[q] += 1
    for c in CURRENCIES:
        if cnt[c]: raw_str[c] /= cnt[c]
    str_df = pd.DataFrame(raw_str)
    return str_df["EUR"] - str_df["JPY"]


# ── 自己相関 ───────────────────────────────────────────────────
def rolling_autocorr(series, window, lag=1):
    arr = series.values
    result = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        x = arr[i - window + 1: i + 1]
        if np.any(np.isnan(x)): continue
        c = np.corrcoef(x[:-lag], x[lag:])
        result[i] = c[0, 1]
    return pd.Series(result, index=series.index)


# ── ATR ───────────────────────────────────────────────────────
def calc_atr(df, period=ATR_PERIOD):
    hi = df["High"]; lo = df["Low"]; cl_prev = df["Close"].shift(1)
    tr = pd.concat([(hi-lo), (hi-cl_prev).abs(), (lo-cl_prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── セッション判定 ─────────────────────────────────────────────
def get_session(jst_hour):
    for name, s, e, direction, ac_sign in SESSIONS:
        if s < e:
            if s <= jst_hour < e: return name
        else:
            if jst_hour >= s or jst_hour < e: return name
    return SESSIONS[-1][0]


# ── trades.csv 読み込み ────────────────────────────────────────
TRADES_COLS = [
    "id","pair","session","direction","signal_dt","entry_dt","entry_price",
    "lot","sl_price","status","exit_dt","exit_price","pnl_yen","r_mult","note"
]

def load_trades() -> pd.DataFrame:
    if not TRADES_CSV.exists():
        return pd.DataFrame(columns=TRADES_COLS)
    df = pd.read_csv(TRADES_CSV, dtype={"id": str, "status": str})
    for col in TRADES_COLS:
        if col not in df.columns:
            df[col] = ""
    for dt_col in ["signal_dt","entry_dt","exit_dt"]:
        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
    for num_col in ["entry_price","lot","sl_price","exit_price","pnl_yen","r_mult"]:
        df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    return df


def save_trades(df: pd.DataFrame):
    df.to_csv(TRADES_CSV, index=False, encoding="utf-8")


# ── オープンポジション管理 ──────────────────────────────────────
def manage_open_positions(df_trades: pd.DataFrame, eurjpy: pd.DataFrame,
                          atr: pd.Series, dry_run: bool = False):
    """
    オープンポジションのトレイリングストップ / タイム決済チェック
    Returns: (df_trades_updated, n_closed)
    """
    if len(df_trades) == 0:
        return df_trades, 0

    open_trades = df_trades[df_trades["status"] == "open"].copy()
    if len(open_trades) == 0:
        return df_trades, 0

    n_closed = 0
    df_updated = df_trades.copy()

    for idx, trade in open_trades.iterrows():
        entry_dt    = pd.Timestamp(trade["entry_dt"])
        entry_price = float(trade["entry_price"])
        sl_price    = float(trade["sl_price"])
        lot         = float(trade["lot"])
        direction   = trade["direction"]  # "LONG" or "SHORT"
        session     = trade["session"]

        # entry_dt 以降のバーを取得
        future_bars = eurjpy[eurjpy.index > entry_dt]
        if len(future_bars) == 0:
            continue

        atr_entry = atr.get(entry_dt, np.nan)
        if np.isnan(atr_entry) or atr_entry <= 0:
            # ATR不明の場合はSL固定
            sl_dist = abs(entry_price - sl_price)
        else:
            sl_dist = atr_entry

        spread_cost = SPREAD_PIPS * PIP_SIZE

        exit_price  = None
        exit_reason = "open"
        held_bars   = 0

        if direction == "SHORT":
            trail_stop  = sl_price
            best_price  = entry_price
            for h, (bar_dt, bar) in enumerate(future_bars.iterrows()):
                held_bars = h + 1
                if bar["High"] >= trail_stop:
                    exit_price  = trail_stop
                    exit_reason = "stop"
                    break
                if bar["Low"] < best_price:
                    best_price = bar["Low"]
                    trail_stop = min(trail_stop, best_price + sl_dist)
                if held_bars >= MAX_HOLD:
                    exit_price  = bar["Close"]
                    exit_reason = "time"
                    break
        else:  # LONG
            trail_stop  = sl_price
            best_price  = entry_price
            for h, (bar_dt, bar) in enumerate(future_bars.iterrows()):
                held_bars = h + 1
                if bar["Low"] <= trail_stop:
                    exit_price  = trail_stop
                    exit_reason = "stop"
                    break
                if bar["High"] > best_price:
                    best_price = bar["High"]
                    trail_stop = max(trail_stop, best_price - sl_dist)
                if held_bars >= MAX_HOLD:
                    exit_price  = bar["Close"]
                    exit_reason = "time"
                    break

        if exit_price is None:
            continue  # まだオープン

        # 決済価格調整（スプレッド）
        if direction == "SHORT":
            exit_price_adj = exit_price + spread_cost / 2
            pnl_pips = (entry_price - exit_price_adj) / PIP_SIZE
        else:
            exit_price_adj = exit_price - spread_cost / 2
            pnl_pips = (exit_price_adj - entry_price) / PIP_SIZE

        pnl_yen = pnl_pips * PIP_VALUE * lot
        r_mult  = pnl_yen / (CAPITAL * RISK_PCT)

        exit_bar_dt = future_bars.index[held_bars - 1] if held_bars > 0 else entry_dt

        result_str = f"+{pnl_yen/10000:.2f}万" if pnl_yen >= 0 else f"{pnl_yen/10000:.2f}万"
        _log(f"  決済: {trade['id'][:8]}  {session} {direction}"
             f"  {entry_price:.3f}→{exit_price_adj:.3f}  "
             f"{exit_reason}  {result_str}  {held_bars}bars", dry_run)

        if not dry_run:
            df_updated.loc[idx, "status"]     = "closed"
            df_updated.loc[idx, "exit_dt"]    = exit_bar_dt
            df_updated.loc[idx, "exit_price"] = round(exit_price_adj, 5)
            df_updated.loc[idx, "pnl_yen"]    = round(pnl_yen, 0)
            df_updated.loc[idx, "r_mult"]     = round(r_mult, 3)
            df_updated.loc[idx, "note"]       = exit_reason
        n_closed += 1

    return df_updated, n_closed


# ── 新規シグナル検出 ───────────────────────────────────────────
def detect_new_signals(eurjpy, eur_jpy_diff, ac, atr, q_thresh,
                       df_trades, dry_run=False):
    """
    直近 SIGNAL_LOOKBACK バーのシグナルを検出し、新規エントリーを記録
    Returns: (df_trades_updated, n_new)
    """
    # 対象バー（最新 SIGNAL_LOOKBACK 本）
    scan_df    = eurjpy.iloc[-SIGNAL_LOOKBACK:]
    scan_diff  = eur_jpy_diff.reindex(scan_df.index)
    scan_ac    = ac.reindex(scan_df.index)
    scan_atr   = atr.reindex(scan_df.index)

    jst_hour   = (scan_df.index + JST).hour
    base_signal = (scan_diff <= q_thresh) & scan_diff.notna()

    spread_cost = SPREAD_PIPS * PIP_SIZE

    # 既存シグナルの entry_dt セットを作成（重複防止）
    existing_signal_dts = set()
    if len(df_trades) > 0:
        existing_signal_dts = set(pd.to_datetime(df_trades["signal_dt"]).dt.floor("5min"))

    new_rows = []

    for i, (bar_dt, bar) in enumerate(scan_df.iterrows()):
        if i + 1 >= len(scan_df): break   # 次足がない

        h = jst_hour[i]
        if not base_signal.iloc[i]: continue

        # どのセッション？
        sess_name = None
        direction = None
        ac_sign   = None
        for sn, s_h, e_h, dir_, ac_s in SESSIONS:
            if s_h < e_h:
                in_sess = s_h <= h < e_h
            else:
                in_sess = h >= s_h or h < e_h
            if in_sess:
                sess_name = sn; direction = dir_; ac_sign = ac_s
                break
        if sess_name is None: continue

        ac_val = scan_ac.iloc[i]
        if np.isnan(ac_val): continue

        # 自己相関フィルター
        if ac_sign == "ac>0":
            if ac_val <= AC_MIN: continue
        else:  # ac<0
            if ac_val >= -AC_MIN: continue

        # 重複チェック
        sig_floor = pd.Timestamp(bar_dt).floor("5min")
        if sig_floor in existing_signal_dts:
            continue

        # エントリーバー（次の5分足）
        entry_bar_dt    = scan_df.index[i + 1]
        entry_open      = scan_df["Open"].iloc[i + 1]
        atr_val         = scan_atr.iloc[i]
        if np.isnan(atr_val) or atr_val <= 0: continue

        if direction == -1:  # SHORT
            entry_price = entry_open - spread_cost / 2
            sl_price    = entry_price + atr_val
        else:  # LONG
            entry_price = entry_open + spread_cost / 2
            sl_price    = entry_price - atr_val

        sl_pips  = atr_val / PIP_SIZE
        if sl_pips <= 0: continue
        lot_size = (CAPITAL * RISK_PCT) / (sl_pips * PIP_VALUE)

        trade_id    = str(uuid.uuid4())
        dir_str     = "SHORT" if direction == -1 else "LONG"
        flt_str     = f"Q{Q_EXTREME*100:.0f}%+ac{'>'  + str(AC_MIN) if ac_sign=='ac>0' else '<-'  + str(AC_MIN)}"

        _log(f"  新規シグナル: {sess_name}  {dir_str}  "
             f"entry={entry_price:.3f}  sl={sl_price:.3f}  "
             f"lot={lot_size:.2f}  ac={ac_val:.3f}  diff={scan_diff.iloc[i]:.5f}",
             dry_run)

        new_rows.append({
            "id":           trade_id,
            "pair":         "EURJPY",
            "session":      sess_name,
            "direction":    dir_str,
            "signal_dt":    bar_dt,
            "entry_dt":     entry_bar_dt,
            "entry_price":  round(entry_price, 5),
            "lot":          round(lot_size, 2),
            "sl_price":     round(sl_price, 5),
            "status":       "open",
            "exit_dt":      "",
            "exit_price":   "",
            "pnl_yen":      "",
            "r_mult":       "",
            "note":         flt_str,
        })
        existing_signal_dts.add(sig_floor)

    n_new = len(new_rows)
    if n_new > 0 and not dry_run:
        df_new = pd.DataFrame(new_rows)[TRADES_COLS]
        df_trades = pd.concat([df_trades, df_new], ignore_index=True)

    return df_trades, n_new


# ── summary.json 更新 ──────────────────────────────────────────
def update_summary(df_trades: pd.DataFrame, dry_run: bool = False):
    closed = df_trades[df_trades["status"] == "closed"].copy()
    open_t = df_trades[df_trades["status"] == "open"].copy()

    n_total  = len(closed)
    n_open   = len(open_t)
    pnl_vals = pd.to_numeric(closed["pnl_yen"], errors="coerce").dropna()
    cum_pnl  = round(pnl_vals.sum(), 0)
    wins     = int((pnl_vals > 0).sum())
    win_rate = round(wins / n_total * 100, 1) if n_total > 0 else 0.0

    gp = pnl_vals[pnl_vals > 0].sum()
    gl = pnl_vals[pnl_vals < 0].abs().sum()
    pf = round(gp / gl, 3) if gl > 0 else None

    # 最大DD
    if n_total > 0:
        cumsum   = pnl_vals.cumsum()
        run_max  = cumsum.cummax()
        max_dd   = round(((run_max - cumsum) / CAPITAL * 100).max(), 1)
    else:
        max_dd = 0.0

    summary = {
        "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_total":      n_total,
        "n_open":       n_open,
        "n_wins":       wins,
        "win_rate_pct": win_rate,
        "profit_factor":pf,
        "cum_pnl_yen":  cum_pnl,
        "cum_pnl_man":  round(cum_pnl / 10000, 2),
        "max_dd_pct":   max_dd,
        "capital":      CAPITAL,
    }

    if not dry_run:
        with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary


# ── メイン ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="EURJPY Demo Signal")
    parser.add_argument("--dry-run", action="store_true",
                        help="シグナル検出のみ。trades.csv / summary.json は更新しない")
    args = parser.parse_args()
    dry_run = args.dry_run

    today = datetime.now().strftime("%Y-%m-%d")
    _log(f"===== EURJPY デモ運用 シグナル生成 {today} =====" + (" [DRY-RUN]" if dry_run else ""))

    # ── データ読み込み ──────────────────────────────────────────
    _log("データ読み込み中...")
    dfs, common_idx = load_data()
    eurjpy = dfs["EURJPY"]
    _log(f"  共通インデックス: {len(common_idx):,}bars  最終: {common_idx[-1]}")

    # ── 通貨強弱・AC・ATR計算 ───────────────────────────────────
    _log("通貨強弱・自己相関・ATR計算中...")
    eur_jpy_diff = calc_strength(dfs, common_idx)
    returns_ej   = np.log(eurjpy["Close"] / eurjpy["Close"].shift(1))
    ac           = rolling_autocorr(returns_ej, AC_WINDOW)
    atr          = calc_atr(eurjpy)

    # ── IS期間の分位点で閾値を固定 ─────────────────────────────
    is_mask  = (common_idx >= IS_START) & (common_idx <= IS_END)
    q_thresh = eur_jpy_diff[is_mask].quantile(Q_EXTREME)
    _log(f"  Q_THRESH (IS期間 Q{Q_EXTREME*100:.0f}%): {q_thresh:.6f}")

    # ── オープンポジション管理 ──────────────────────────────────
    _log("オープンポジション管理中...")
    df_trades = load_trades()
    n_open_before = int((df_trades["status"] == "open").sum()) if len(df_trades) > 0 else 0
    _log(f"  既存トレード: {len(df_trades)}件  オープン: {n_open_before}件")

    df_trades, n_closed = manage_open_positions(df_trades, eurjpy, atr, dry_run)

    # ── 新規シグナル検出 ────────────────────────────────────────
    _log(f"新規シグナル検出中（直近{SIGNAL_LOOKBACK}bar={SIGNAL_LOOKBACK*5//60}時間）...")
    df_trades, n_new = detect_new_signals(eurjpy, eur_jpy_diff, ac, atr, q_thresh,
                                          df_trades, dry_run)

    # ── 保存 ────────────────────────────────────────────────────
    if not dry_run:
        save_trades(df_trades)
        _log(f"  trades.csv 保存: {TRADES_CSV}  ({len(df_trades)}行)")

    summary = update_summary(df_trades, dry_run)

    # ── コンソール出力 ──────────────────────────────────────────
    _log("=" * 55)
    _log(f"処理結果サマリー  {today}")
    _log("-" * 55)
    _log(f"  新規シグナル:    {n_new}件")
    _log(f"  決済:            {n_closed}件")
    _log(f"  オープン:        {summary['n_open']}件")
    _log(f"  累積損益:        {summary['cum_pnl_man']:+.2f}万円")
    _log(f"  通算成績:        {summary['n_total']}件  勝率={summary['win_rate_pct']:.1f}%"
         + (f"  PF={summary['profit_factor']:.3f}" if summary['profit_factor'] else ""))
    _log(f"  最大DD:          {summary['max_dd_pct']:.1f}%")
    if dry_run:
        _log("[DRY-RUN] trades.csv / summary.json は更新されませんでした")
    _log("=" * 55)


if __name__ == "__main__":
    main()
