# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 デモ環境 日次シグナル生成・架空執行スクリプト
平日 16:10 に自動実行（demo_collect.py の後）

処理フロー:
  1. 昨日の pending エントリーを今日の寄り値で架空購入
  2. 保有ポジションのエグジットチェック（今日の引け値）
  3. 新規エントリーシグナル生成（明日寄り候補）
  4. 損益スナップショット保存
  5. 日次レポート出力

実行: python japan_stocks/demo_signal.py
登録: python japan_stocks/setup_scheduler.py demo_signal
"""

import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
import sector_index as si
from analyzer import cross_correlation, best_lag, classify as classify_lag
from run_backtest import (
    CANDIDATE_SECTORS, N_ACTIVE_SECTORS, SMA_WINDOW, RANKING_WINDOW,
    DATA_START,
)
from jquants import JQuantsClient

# ── 設定 ──────────────────────────────────────────────────────────────────────
DEMO_DIR     = Path(__file__).parent / "results" / "demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR      = Path(__file__).parent / "results" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE   = DEMO_DIR / "state.json"
TRADES_FILE  = DEMO_DIR / "trades.csv"
PNL_FILE     = DEMO_DIR / "pnl_history.csv"
LOG_FILE     = LOG_DIR  / "demo_signal.log"

# v2-f 確定パラメータ
SECTOR_MIN_RISE      = 2.0    # %
MIN_GAP              = 3.0    # %
RISK_PCT             = 0.5    # %
STOP_DIST_PCT        = 1.5    # %
MIN_CORR             = 0.60
TARGET_GAP_EXIT      = 0.5    # %
MAX_HOLD_DAYS        = 10
MAX_POSITIONS        = 3
SECTOR_LOOKBACK      = 5      # 日
CLASS_WINDOW         = 252    # 日
CLASS_INTERVAL       = 21     # 日（分類再計算間隔）
INITIAL_CAPITAL      = 1_000_000
TARGET_CLASSES       = ["遅行株", "中間株"]

MAX_STOCKS_PER_SECTOR = 20
MIN_STOCKS_PER_SECTOR = 5


# ── ログ ──────────────────────────────────────────────────────────────────────
def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── 状態ファイル管理 ───────────────────────────────────────────────────────────
def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    # 初期状態
    return {
        "capital":            INITIAL_CAPITAL,
        "peak_capital":       INITIAL_CAPITAL,
        "positions":          [],   # 保有中ポジション
        "pending":            [],   # 明日寄りで買うべき pending
        "last_run":           "",
        "total_realized_pnl": 0,
        "trade_count":        0,
    }


def _save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── データ読み込み ─────────────────────────────────────────────────────────────
def _to_yf(code: str) -> str:
    c = str(code).zfill(5)
    return (c[:4] if c.endswith("0") else c) + ".T"


def load_sector_data() -> tuple[dict, dict, dict]:
    """CANDIDATE_SECTORSのデータをキャッシュから読み込む"""
    client = JQuantsClient()
    master = client.get_stock_list()
    prime  = master[master["MktNm"].str.contains("プライム", na=False)].copy()
    prime["Code"] = prime["Code"].astype(str).str.zfill(4)

    sector_indices: dict[str, pd.Series]               = {}
    sector_stocks:  dict[str, dict[str, pd.DataFrame]] = {}
    sector_opens:   dict[str, dict[str, pd.Series]]    = {}

    for (_, s33_name), group in prime.groupby(["S33", "S33Nm"]):
        if s33_name not in CANDIDATE_SECTORS:
            continue
        codes   = sorted(group["Code"].tolist())[:MAX_STOCKS_PER_SECTOR]
        tickers = [_to_yf(c) for c in codes]

        stocks_prices: dict[str, pd.Series] = {}
        stocks_opens_:  dict[str, pd.Series] = {}
        for ticker in tickers:
            try:
                df = dt.fetch(ticker, start=DATA_START)
                if len(df) >= 120:
                    stocks_prices[ticker] = df["Close"]
                    if "Open" in df.columns:
                        stocks_opens_[ticker] = df["Open"]
            except Exception:
                pass

        if len(stocks_prices) < MIN_STOCKS_PER_SECTOR:
            continue

        idx = si.build_from_price_dict(stocks_prices, name=s33_name)
        if idx.empty:
            continue

        sector_indices[s33_name] = idx
        sector_stocks[s33_name]  = {t: c.rename("Close").to_frame()
                                     for t, c in stocks_prices.items()}
        sector_opens[s33_name]   = stocks_opens_

    return sector_indices, sector_stocks, sector_opens


# ── 動的セクター選別（今日） ──────────────────────────────────────────────────
def get_active_sectors_today(
    sector_indices: dict[str, pd.Series],
    today: pd.Timestamp,
) -> set[str]:
    """今日アクティブな上位N業種を返す"""
    all_dates = sorted(set().union(*[set(idx.index) for idx in sector_indices.values()]))

    try:
        date_i = all_dates.index(today)
    except ValueError:
        # 今日のデータがなければ最終営業日で代替
        avail = [d for d in all_dates if d <= today]
        if not avail:
            return set()
        today  = avail[-1]
        date_i = all_dates.index(today)

    min_window = max(SMA_WINDOW, RANKING_WINDOW)
    if date_i < min_window:
        return set()

    qualifying: dict[str, float] = {}
    past_dates = all_dates[:date_i + 1]
    rank_start = past_dates[-RANKING_WINDOW - 1]

    for sector, idx in sector_indices.items():
        if today not in idx.index:
            continue
        sma_slice = past_dates[-SMA_WINDOW:]
        try:
            sma_vals = idx.reindex(sma_slice).dropna()
            if len(sma_vals) < SMA_WINDOW * 0.8:
                continue
            sma_val  = float(sma_vals.mean())
            now_val  = float(idx[today])
            if now_val <= sma_val:
                continue
            past_val = float(idx.get(rank_start, np.nan))
            if np.isnan(past_val) or past_val <= 0:
                continue
            recent_ret = (now_val / past_val - 1) * 100
            if recent_ret <= 0:
                continue
            qualifying[sector] = recent_ret
        except Exception:
            continue

    top_n = sorted(qualifying.items(), key=lambda x: x[1], reverse=True)[:N_ACTIVE_SECTORS]
    return {s for s, _ in top_n}


# ── 銘柄分類（今日の最新ウィンドウ） ─────────────────────────────────────────
def classify_stocks_today(
    sector_idx: pd.Series,
    closes: dict[str, pd.Series],
    today: pd.Timestamp,
) -> dict[str, tuple[str, float]]:
    """今日時点の遅行/中間/先行分類を計算"""
    avail = [d for d in sector_idx.index if d <= today]
    if len(avail) < CLASS_WINDOW:
        return {}

    i = len(avail) - 1
    s_win = sector_idx.iloc[max(0, i - CLASS_WINDOW): i + 1]
    result: dict[str, tuple[str, float]] = {}

    for ticker, close in closes.items():
        try:
            k_win = close.iloc[max(0, i - CLASS_WINDOW): i + 1].dropna()
            if len(k_win) < 60:
                result[ticker] = (None, 0.0)
                continue
            corr_dict = cross_correlation(s_win, k_win)
            lag  = best_lag(corr_dict)
            cls  = classify_lag(lag)
            corr = float(corr_dict.get(lag, 0.0) or 0.0)
            result[ticker] = (cls, corr)
        except Exception:
            result[ticker] = (None, 0.0)

    return result


# ── Step 1: pending → 今日の寄り値で架空購入 ─────────────────────────────────
def execute_pending(
    state: dict,
    sector_opens: dict[str, dict[str, pd.Series]],
    today: pd.Timestamp,
) -> list[dict]:
    """昨日の pending を今日の寄り値で架空購入してpositionsに移す"""
    executed = []
    new_positions = list(state["positions"])
    remaining_pending = []
    capital = state["capital"]

    for p in state["pending"]:
        if len(new_positions) >= MAX_POSITIONS:
            remaining_pending.append(p)
            continue

        # 当日シグナルは翌日寄りで執行するため本日はスキップ
        if p.get("signal_date", "") >= today.strftime("%Y-%m-%d"):
            remaining_pending.append(p)
            continue

        # 有効期限チェック: バックテストと同様に1営業日（最大5暦日）超過で破棄
        signal_dt = pd.Timestamp(p.get("signal_date", "2000-01-01"))
        if (today - signal_dt).days > 5:
            _log(f"  [期限切れ破棄] {p['ticker']} signal_date={p['signal_date']}")
            continue

        ticker = p["ticker"]
        sector = p["sector"]

        # 今日の寄り値を取得（日足キャッシュ → 5分足フォールバック）
        open_price = None
        opens = sector_opens.get(sector, {})
        if ticker in opens:
            s = opens[ticker]
            avail = s[s.index <= today]
            if not avail.empty and avail.index[-1] == today:
                v = float(avail.iloc[-1])
                if not np.isnan(v) and v > 0:
                    open_price = v

        # 日足キャッシュに当日データがない場合は5分足の第1バーから寄り値を取得
        if open_price is None:
            try:
                import yfinance as _yf
                intra = _yf.download(ticker, period="1d", interval="5m", progress=False)
                if not intra.empty:
                    if isinstance(intra.columns, pd.MultiIndex):
                        intra.columns = intra.columns.get_level_values(0)
                    intra.index = intra.index.tz_convert("Asia/Tokyo").tz_localize(None)
                    today_bars = intra[intra.index.normalize() == today]
                    if not today_bars.empty:
                        v = float(today_bars["Open"].iloc[0])
                        if not np.isnan(v) and v > 0:
                            open_price = v
                            _log(f"  [5分足寄り値] {ticker} {v:,.0f}円")
            except Exception as e:
                _log(f"  [5分足取得失敗] {ticker}: {e}")

        if open_price is None:
            _log(f"  [警告] {ticker} の寄り値が取得できません。シグナル引け値を使用")

        entry_price = open_price or p["signal_close"]
        if entry_price <= 0:
            continue

        risk_amount   = capital * RISK_PCT / 100
        stop_dist_jpy = entry_price * STOP_DIST_PCT / 100
        shares = int(risk_amount / stop_dist_jpy)
        if shares < 1:
            continue

        pos = {
            "ticker":          ticker,
            "sector":          sector,
            "entry_date":      today.strftime("%Y-%m-%d"),
            "entry_price":     round(entry_price, 1),
            "shares":          shares,
            "stop_price":      round(entry_price * (1 - STOP_DIST_PCT / 100), 1),
            "sector_at_entry": p.get("sector_at_signal", 0),
            "days_held":       0,
            "signal_gap_pct":  p.get("gap_pct", 0),
            "corr":            p.get("corr", 0),
        }
        new_positions.append(pos)
        executed.append(pos)

        entry_jpy = round(entry_price * shares)
        pos_pct   = round(entry_jpy / capital * 100, 1)
        _log(f"  【架空購入】{ticker} ({sector}) "
             f"寄り{entry_price:,.0f}円 × {shares}株 "
             f"= {entry_jpy:,}円 ({pos_pct}%)")

    state["positions"] = new_positions
    state["pending"]   = remaining_pending
    return executed


# ── Step 2: エグジットチェック ────────────────────────────────────────────────
def check_exits(
    state: dict,
    sector_indices: dict[str, pd.Series],
    sector_stocks: dict[str, dict[str, pd.DataFrame]],
    today: pd.Timestamp,
) -> list[dict]:
    """保有ポジションのエグジット条件をチェック（今日の引け値）"""
    closed_trades = []
    still_open    = []
    capital       = state["capital"]

    for pos in state["positions"]:
        ticker = pos["ticker"]
        sector = pos["sector"]

        # 今日の引け値を取得
        close_price = None
        stocks = sector_stocks.get(sector, {})
        if ticker in stocks:
            df = stocks[ticker]
            col = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
            s   = df[col]
            avail = s[s.index <= today]
            if not avail.empty:
                v = float(avail.iloc[-1])
                if not np.isnan(v) and v > 0:
                    close_price = v

        if close_price is None:
            still_open.append(pos)
            continue

        pos["days_held"] = pos.get("days_held", 0) + 1
        reason     = None
        exit_price = close_price

        # ストップロス
        if close_price <= pos["stop_price"]:
            reason     = "stop"
            exit_price = pos["stop_price"]

        # 最大保有日数
        elif pos["days_held"] >= MAX_HOLD_DAYS:
            reason = "time"

        # 利確: 直近5日でセクターとの乖離が縮小
        else:
            idx = sector_indices.get(sector)
            stocks_close = sector_stocks.get(sector, {}).get(ticker)
            if idx is not None and stocks_close is not None:
                try:
                    col = "AdjustmentClose" if "AdjustmentClose" in stocks_close.columns else "Close"
                    sc = stocks_close[col]
                    idx_avail   = idx[idx.index <= today]
                    stock_avail = sc[sc.index <= today]
                    if len(idx_avail) > SECTOR_LOOKBACK and len(stock_avail) > SECTOR_LOOKBACK:
                        sec_now    = float(idx_avail.iloc[-1])
                        sec_past   = float(idx_avail.iloc[-1 - SECTOR_LOOKBACK])
                        stock_past = float(stock_avail.iloc[-1 - SECTOR_LOOKBACK])
                        if sec_past > 0 and stock_past > 0:
                            sec_chg   = (sec_now   / sec_past   - 1) * 100
                            stock_chg = (close_price / stock_past - 1) * 100
                            if sec_chg - stock_chg <= TARGET_GAP_EXIT:
                                reason = "target"
                except Exception:
                    pass

        if reason:
            cost    = pos["entry_price"] * pos["shares"] * 0.20 / 100
            pnl_raw = (exit_price - pos["entry_price"]) * pos["shares"]
            net_pnl = pnl_raw - cost
            capital += net_pnl
            state["total_realized_pnl"] = state.get("total_realized_pnl", 0) + net_pnl
            state["trade_count"]        = state.get("trade_count", 0) + 1

            trade = {
                "exit_date":    today.strftime("%Y-%m-%d"),
                "ticker":       ticker,
                "sector":       sector,
                "entry_date":   pos["entry_date"],
                "entry_price":  pos["entry_price"],
                "exit_price":   round(exit_price, 1),
                "shares":       pos["shares"],
                "exit_reason":  reason,
                "pnl_jpy":      round(net_pnl),
                "return_pct":   round((exit_price / pos["entry_price"] - 1) * 100, 2),
                "days_held":    pos["days_held"],
            }
            closed_trades.append(trade)
            sign = "+" if net_pnl >= 0 else ""
            _log(f"  【架空決済】{ticker} ({reason}) "
                 f"損益: {sign}{net_pnl:,.0f}円  "
                 f"({trade['return_pct']:+.2f}%)  {pos['days_held']}日保有")
        else:
            still_open.append(pos)

    state["positions"] = still_open
    state["capital"]   = capital
    state["peak_capital"] = max(state.get("peak_capital", capital), capital)
    return closed_trades


# ── Step 3: 新規エントリーシグナル生成 ────────────────────────────────────────
def generate_signals(
    state: dict,
    sector_indices: dict[str, pd.Series],
    sector_stocks: dict[str, dict[str, pd.DataFrame]],
    active_sectors: set[str],
    today: pd.Timestamp,
) -> list[dict]:
    """今日の引け後シグナル → 明日寄りの買い候補を生成"""
    open_tickers    = {p["ticker"] for p in state["positions"]}
    pending_tickers = {p["ticker"] for p in state["pending"]}
    # positions + pending の合計で MAX_POSITIONS を管理（バックテストと同等）
    slots = MAX_POSITIONS - len(state["positions"]) - len(state["pending"])
    if slots <= 0:
        return []

    all_candidates: list[dict] = []

    for sector in active_sectors:
        idx    = sector_indices.get(sector)
        stocks = sector_stocks.get(sector)
        if idx is None or not stocks:
            continue

        # セクター上昇チェック
        avail = idx[idx.index <= today]
        if len(avail) <= SECTOR_LOOKBACK:
            continue
        sec_now  = float(avail.iloc[-1])
        sec_past = float(avail.iloc[-1 - SECTOR_LOOKBACK])
        if sec_past == 0:
            continue
        sec_change = (sec_now / sec_past - 1) * 100
        if sec_change < SECTOR_MIN_RISE:
            continue

        # 銘柄分類（相関係数）
        closes_dict = {t: df["Close"] if "Close" in df.columns
                       else df[df.columns[0]]
                       for t, df in stocks.items()}
        _log(f"  [{sector}] 銘柄分類計算中（rise={sec_change:.1f}%）...")
        classifications = classify_stocks_today(idx, closes_dict, today)

        for ticker, (cls, corr) in classifications.items():
            if ticker in open_tickers or ticker in pending_tickers:
                continue
            if cls not in TARGET_CLASSES or corr < MIN_CORR:
                continue

            close = closes_dict.get(ticker)
            if close is None:
                continue
            avail_c = close[close.index <= today]
            if len(avail_c) <= SECTOR_LOOKBACK:
                continue
            now_close  = float(avail_c.iloc[-1])
            past_close = float(avail_c.iloc[-1 - SECTOR_LOOKBACK])
            if past_close == 0 or np.isnan(now_close) or np.isnan(past_close):
                continue

            stock_chg = (now_close / past_close - 1) * 100
            gap = sec_change - stock_chg
            if gap < MIN_GAP:
                continue

            all_candidates.append({
                "ticker":           ticker,
                "sector":           sector,
                "signal_date":      today.strftime("%Y-%m-%d"),
                "signal_close":     round(now_close, 1),
                "sector_at_signal": round(sec_now, 2),
                "sector_rise_pct":  round(sec_change, 2),
                "stock_rise_pct":   round(stock_chg, 2),
                "gap_pct":          round(gap, 2),
                "corr":             round(corr, 3),
                "classification":   cls,
            })

    # gap降順でソートして上位slots件を pending へ
    all_candidates.sort(key=lambda x: x["gap_pct"], reverse=True)
    selected = all_candidates[:slots]

    # 既存 pending に追加（重複排除）
    existing_pending_tickers = {p["ticker"] for p in state["pending"]}
    for c in selected:
        if c["ticker"] not in existing_pending_tickers:
            state["pending"].append(c)

    return selected


# ── Step 4: 損益スナップショット ──────────────────────────────────────────────
def save_pnl_snapshot(
    state: dict,
    sector_stocks: dict[str, dict[str, pd.DataFrame]],
    today: pd.Timestamp,
    closed_trades: list[dict],
    new_signals: list[dict],
):
    capital = state["capital"]

    # 含み損益を計算（ポジションごとに現在値も保存）
    unrealized = 0.0
    for pos in state["positions"]:
        stocks = sector_stocks.get(pos["sector"], {})
        df = stocks.get(pos["ticker"])
        if df is not None:
            col = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
            s = df[col]
            avail = s[s.index <= today]
            if not avail.empty:
                now_p = float(avail.iloc[-1])
                if not np.isnan(now_p):
                    pos_unreal = (now_p - pos["entry_price"]) * pos["shares"]
                    unrealized += pos_unreal
                    pos["current_price"]   = round(now_p, 1)
                    pos["unrealized_pnl"]  = round(pos_unreal)

    total_equity   = capital + unrealized
    realized_pnl   = state.get("total_realized_pnl", 0)
    peak           = state.get("peak_capital", INITIAL_CAPITAL)
    dd_pct         = max(0.0, (peak - total_equity) / peak * 100) if peak > 0 else 0.0
    ret_pct        = (total_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # PNL履歴CSVへ追記
    row = pd.DataFrame([{
        "date":             today.strftime("%Y-%m-%d"),
        "capital":          round(capital),
        "unrealized_pnl":   round(unrealized),
        "total_equity":     round(total_equity),
        "realized_pnl":     round(realized_pnl),
        "return_pct":       round(ret_pct, 2),
        "max_dd_pct":       round(dd_pct, 2),
        "open_positions":   len(state["positions"]),
        "pending":          len(state["pending"]),
        "trades_today":     len(closed_trades),
        "new_signals":      len(new_signals),
    }])
    if PNL_FILE.exists():
        existing = pd.read_csv(PNL_FILE, encoding="utf-8-sig")
        existing = existing[existing["date"] != today.strftime("%Y-%m-%d")]
        row = pd.concat([existing, row], ignore_index=True)
    row.to_csv(PNL_FILE, index=False, encoding="utf-8-sig")

    # 決済トレードをCSVへ追記
    if closed_trades:
        trades_df = pd.DataFrame(closed_trades)
        if TRADES_FILE.exists():
            existing_t = pd.read_csv(TRADES_FILE, encoding="utf-8-sig")
            trades_df = pd.concat([existing_t, trades_df], ignore_index=True)
        trades_df.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")

    return total_equity, ret_pct, dd_pct, unrealized


# ── 日次サマリー表示 ──────────────────────────────────────────────────────────
def print_daily_summary(
    state: dict,
    today: pd.Timestamp,
    executed: list[dict],
    closed_trades: list[dict],
    new_signals: list[dict],
    total_equity: float,
    ret_pct: float,
    dd_pct: float,
    unrealized: float,
):
    _log("")
    _log("=" * 60)
    _log(f"  デモ運用 日次レポート  {today.strftime('%Y-%m-%d')}")
    _log("=" * 60)
    sign = "+" if ret_pct >= 0 else ""
    _log(f"  資産評価額 : {total_equity:>12,.0f}円  "
         f"({sign}{ret_pct:.2f}%  初期比)")
    _log(f"  実現損益   : {state.get('total_realized_pnl', 0):>+12,.0f}円")
    _log(f"  含み損益   : {unrealized:>+12,.0f}円")
    _log(f"  最大DD     : {dd_pct:.1f}%")
    _log(f"  累計トレード: {state.get('trade_count', 0)}件")

    if executed:
        _log(f"\n  ── 本日 架空購入 ({len(executed)}件) ──")
        for p in executed:
            jpy = p["entry_price"] * p["shares"]
            _log(f"    {p['ticker']:>10} ({p['sector']})  "
                 f"{p['entry_price']:,.0f}円 × {p['shares']}株 = {jpy:,}円  "
                 f"stop: {p['stop_price']:,.0f}円")

    if closed_trades:
        _log(f"\n  ── 本日 架空決済 ({len(closed_trades)}件) ──")
        for t in closed_trades:
            sign_t = "+" if t["pnl_jpy"] >= 0 else ""
            _log(f"    {t['ticker']:>10} ({t['exit_reason']:6})  "
                 f"{sign_t}{t['pnl_jpy']:,}円  ({t['return_pct']:+.2f}%)  "
                 f"{t['days_held']}日")

    if state["positions"]:
        _log(f"\n  ── 保有中ポジション ({len(state['positions'])}件) ──")
        for pos in state["positions"]:
            _log(f"    {pos['ticker']:>10} ({pos['sector']})  "
                 f"取得{pos['entry_price']:,.0f}円  "
                 f"stop: {pos['stop_price']:,.0f}円  "
                 f"{pos['days_held']}日目")

    if new_signals:
        _log(f"\n  ── 明日 寄り候補 ({len(new_signals)}件) ──")
        for s in new_signals:
            _log(f"    {s['ticker']:>10} ({s['sector']})  "
                 f"引け{s['signal_close']:,.0f}円  "
                 f"gap={s['gap_pct']:.1f}%  corr={s['corr']:.2f}  "
                 f"[{s['classification']}]")
    else:
        _log("\n  ── 明日 寄り候補: なし ──")

    _log("=" * 60)
    _log("")


# ── メイン ─────────────────────────────────────────────────────────────────────
def main():
    today_dt = pd.Timestamp(datetime.today().date())
    _log("=" * 60)
    _log(f"デモシグナル生成 開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log("=" * 60)

    # 週末スキップ
    if datetime.today().weekday() >= 5:
        _log("本日は土日のためスキップ")
        return

    state = _load_state()

    # 同日二重実行ガード
    if state.get("last_run") == today_dt.strftime("%Y-%m-%d"):
        _log("本日は既に実行済みです（last_run が同日）。再実行する場合は state.json の last_run を変更してください。")
        return

    # データ読み込み
    _log("\nデータ読み込み中...")
    sector_indices, sector_stocks, sector_opens = load_sector_data()
    _log(f"  {len(sector_indices)}業種 読み込み完了")

    # アクティブセクター判定
    active_sectors = get_active_sectors_today(sector_indices, today_dt)
    _log(f"\nアクティブセクター（TOP{N_ACTIVE_SECTORS}）: "
         f"{', '.join(sorted(active_sectors)) if active_sectors else 'なし'}")

    # Step 1: pending を今日の寄り値で架空購入
    _log("\n--- Step 1: 昨日の pending を今日の寄りで架空購入 ---")
    executed = execute_pending(state, sector_opens, today_dt)
    if not executed:
        _log("  pending なし")

    # Step 2: エグジットチェック
    _log("\n--- Step 2: 保有ポジション エグジットチェック ---")
    closed_trades = check_exits(state, sector_indices, sector_stocks, today_dt)
    if not closed_trades:
        _log("  決済なし")

    # Step 3: 新規シグナル生成
    _log("\n--- Step 3: 新規エントリーシグナル生成 ---")
    new_signals = generate_signals(
        state, sector_indices, sector_stocks, active_sectors, today_dt
    )
    _log(f"  シグナル数: {len(new_signals)}件")

    # Step 4: 損益スナップショット保存
    total_equity, ret_pct, dd_pct, unrealized = save_pnl_snapshot(
        state, sector_stocks, today_dt, closed_trades, new_signals
    )

    # 状態保存
    state["last_run"] = today_dt.strftime("%Y-%m-%d")
    _save_state(state)

    # 日次サマリー
    print_daily_summary(
        state, today_dt, executed, closed_trades, new_signals,
        total_equity, ret_pct, dd_pct, unrealized,
    )


if __name__ == "__main__":
    main()
