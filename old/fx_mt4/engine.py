# fx_mt4/engine.py  ─ シグナルエンジン（データ読み込み・シグナル生成・注文管理）
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    DATA_DIR, SIGNAL_FILE, STATUS_FILE, LOG_FILE, READY_FLAG,
    PAIR, RANGE_BARS, RANGE_PIPS, MIN_HOLD, STRENGTH_WIN, PIP,
    LOT_SIZE, ENTRY_COST_PIPS, PAIRS,
)


# ── ログ ─────────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [PY] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── データ読み込み ────────────────────────────────────────────────────────────
def load_pair(symbol: str) -> pd.DataFrame | None:
    f = DATA_DIR / f"{symbol}_M30.csv"
    if not f.exists():
        return None
    try:
        df = pd.read_csv(f)
        df["datetime"] = pd.to_datetime(df["datetime"], format="%Y.%m.%d %H:%M")
        df = df.set_index("datetime").sort_index()
        df.columns = [c.capitalize() for c in df.columns]
        return df
    except Exception as e:
        log(f"ERROR: {symbol} 読み込み失敗 {e}")
        return None


def load_all_pairs() -> dict[str, pd.DataFrame]:
    dfs = {}
    for p in PAIRS:
        df = load_pair(p)
        if df is not None:
            dfs[p] = df
    log(f"データ読み込み: {len(dfs)}/{len(PAIRS)}ペア")
    return dfs


# ── 強弱スコア（5分足parquetから計算してM30にリサンプル） ────────────────────
def compute_strength_diff(dfs: dict) -> pd.Series:
    """
    MT4から取得できないペアは既存の5分足parquetを使う。
    強弱スコアは30分足に合わせてリサンプル。
    """
    from fx_market_classifier.features import currency_strength, log_returns
    from fx_mt4.config import PAIRS

    PARQUET_DIR = Path(__file__).parent.parent / "data" / "dukascopy"

    # 各ペアのClose系列を収集（MT4 CSV → なければparquet）
    closes = {}
    for p in PAIRS:
        # まずMT4データを試みる
        df_mt4 = dfs.get(p)
        if df_mt4 is not None and len(df_mt4) > 20:
            closes[p] = df_mt4["Close"]
            continue
        # parquetから読み込み（5分足 → 30分足にリサンプル）
        pq = PARQUET_DIR / f"{p}_5min.parquet"
        if pq.exists():
            df5 = pd.read_parquet(pq)
            # タイムゾーンを除去してnaiveに統一
            if df5.index.tz is not None:
                df5.index = df5.index.tz_localize(None)
            df30 = df5["Close"].resample("30min", label="left",
                                         closed="left").last().dropna()
            closes[p] = df30
        else:
            log(f"WARN: {p} データなし（MT4・parquet両方）")

    if not closes:
        log("ERROR: 強弱計算用データなし")
        return pd.Series(dtype=float)

    # 共通インデックスで揃える
    common = pd.DataFrame(closes).dropna(how="all")
    rd = {p: common[p].pct_change().apply(lambda x: np.log(1+x) if x > -1 else np.nan)
          for p in common.columns}

    st  = currency_strength(rd)
    usd = st["USD"].rolling(STRENGTH_WIN).sum()
    jpy = st["JPY"].rolling(STRENGTH_WIN).sum()
    sd  = (usd - jpy).rename("sd")
    log(f"強弱スコア計算完了: 有効={sd.notna().sum()}件 / 最新={sd.dropna().iloc[-1]:.6f}" if sd.notna().any() else "強弱スコア: 全NaN")
    return sd


# ── シグナル生成 ──────────────────────────────────────────────────────────────
def generate_signal(dfs: dict) -> dict:
    """
    最新バーのシグナルを返す。
    Returns:
        {"action": "BUY"|"SELL"|"NONE", "stop_loss": float, "range_high": float, ...}
    """
    df = dfs.get(PAIR)
    if df is None or len(df) < RANGE_BARS + 5:
        log("USDJPY データ不足")
        return {"action": "NONE"}

    try:
        sd = compute_strength_diff(dfs)
    except Exception as e:
        log(f"強弱スコア計算エラー: {e}")
        return {"action": "NONE"}

    close = df["Close"]
    sd_a  = sd.reindex(df.index)

    # 直前バーでレンジ検出（最新バーはi=0=未確定の可能性があるため1つ前を使う）
    # MT4 EA はi=1以降の確定バーのみ書き出すので、最後の行が最新確定バー
    rh = close.shift(1).rolling(RANGE_BARS).max()
    rl = close.shift(1).rolling(RANGE_BARS).min()
    rm = (rh + rl) / 2
    in_range = (rh - rl) <= RANGE_PIPS * PIP

    # 最新確定バー（末尾）でシグナル判定
    last_close = close.iloc[-1]
    last_rh    = rh.iloc[-1]
    last_rl    = rl.iloc[-1]
    last_rm    = rm.iloc[-1]
    last_ir    = in_range.iloc[-1]
    last_sd    = sd_a.iloc[-1]

    if pd.isna(last_rh) or pd.isna(last_sd):
        log("データ不足（NaN）")
        return {"action": "NONE"}

    action = "NONE"
    if last_ir and last_close > last_rh and last_sd > 0:
        action = "BUY"
    elif last_ir and last_close < last_rl and last_sd < 0:
        action = "SELL"

    stop_loss = last_rm  # レンジ中値

    log(f"シグナル判定: {action}  close={last_close:.5f}  "
        f"range=[{last_rl:.5f}-{last_rh:.5f}]  sd={last_sd:.6f}")

    return {
        "action":     action,
        "symbol":     PAIR,
        "lots":       LOT_SIZE,
        "stop_loss":  round(float(stop_loss), 5),
        "range_high": round(float(last_rh), 5),
        "range_low":  round(float(last_rl), 5),
        "range_mid":  round(float(last_rm), 5),
        "strength":   round(float(last_sd), 6),
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "processed":  "false",
    }


# ── ポジション確認 ────────────────────────────────────────────────────────────
def get_status() -> dict:
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except:
        return {}


def has_position() -> bool:
    st = get_status()
    return len(st.get("positions", [])) > 0


def get_position() -> dict | None:
    st = get_status()
    pos = st.get("positions", [])
    return pos[0] if pos else None


# ── エグジット判定 ────────────────────────────────────────────────────────────
def should_exit(dfs: dict, pos: dict) -> bool:
    """
    利確条件: MIN_HOLD以上保有 & 含み益あり & 終値が前足終値を切り下げ/切り上げ
    損切り: EAのストップロスで自動処理（ここでは利確のみ判断）
    """
    df = dfs.get(PAIR)
    if df is None or pos is None:
        return False

    direction    = pos.get("type", "")
    open_price   = pos.get("open_price", 0)
    open_time_s  = pos.get("open_time", "")

    try:
        open_dt = pd.Timestamp(open_time_s)
        # 保有バー数（30分足）
        bars_held = int((df.index[-1] - open_dt).total_seconds() / 1800)
    except:
        return False

    if bars_held < MIN_HOLD:
        return False

    close = df["Close"]
    last  = close.iloc[-1]
    prev  = close.iloc[-2]
    unrealized = (last - open_price) if direction == "BUY" else (open_price - last)

    if unrealized <= 0:
        return False  # 含み損なら利確しない

    if direction == "BUY"  and last < prev:
        log(f"利確シグナル(Long): 終値切り下げ {prev:.5f}→{last:.5f} 保有{bars_held}本")
        return True
    if direction == "SELL" and last > prev:
        log(f"利確シグナル(Short): 終値切り上げ {prev:.5f}→{last:.5f} 保有{bars_held}本")
        return True

    return False


# ── シグナル書き込み ──────────────────────────────────────────────────────────
def write_signal(sig: dict):
    SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_FILE.write_text(json.dumps(sig, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    log(f"signal.json 書き込み: {sig['action']}")


def write_close_signal():
    sig = {
        "action":    "CLOSE",
        "symbol":    PAIR,
        "lots":      0,
        "stop_loss": 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "processed": "false",
    }
    write_signal(sig)


def signal_pending() -> bool:
    """未処理のシグナルが残っているか"""
    if not SIGNAL_FILE.exists():
        return False
    try:
        d = json.loads(SIGNAL_FILE.read_text(encoding="utf-8"))
        return d.get("processed") == "false" and d.get("action") != "NONE"
    except:
        return False
