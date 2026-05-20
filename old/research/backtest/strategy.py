# -*- coding: utf-8 -*-
# ============================================================
# 戦略: ロンドンブレイクアウト v1
#
# ロジック:
#   1. JST 3:00〜15:00 のアジアセッションの高値/安値をレンジとして記録
#   2. JST 15:00〜18:00（ロンドンオープン）にレンジを上抜け→買い、下抜け→売り
#   3. レンジ幅が MIN_RANGE_PIPS 未満の日はスキップ（だましの回避）
#   4. TP/SL に達するか JST 22:00 で強制決済
#
# ！注意！
#   条件を固定してから run.py を実行すること。
#   結果を見てから条件を変えて再実行するのは「カーブフィッティング」になる。
# ============================================================

import pandas as pd

# ── パラメータ ────────────────────────────────────────────────────────────
ASIAN_START_HOUR = 3    # アジアレンジ計測開始 (JST)
ASIAN_END_HOUR   = 15   # アジアレンジ計測終了 (JST、このhour未満)
ENTRY_START_HOUR = 15   # エントリー受付開始 (JST)
ENTRY_END_HOUR   = 18   # エントリー受付終了 (JST、このhour未満)
EOD_CLOSE_HOUR   = 22   # 強制決済時刻 (JST)
MIN_RANGE_PIPS   = 15   # アジアレンジの最小幅（これ未満の日はスキップ）
TAKE_PROFIT_PIPS = 20.0
STOP_LOSS_PIPS   = 10.0


def entry_condition(candles: pd.DataFrame) -> tuple[bool, str]:
    """
    引数:
        candles : 直近 LOOKBACK 本のローソク足（最新が末尾）
                  列: datetime / open / high / low / close / volume
    戻り値:
        (エントリーするか: bool, 売買方向: "buy" or "sell")
    """
    if len(candles) < 30:
        return False, ""

    current      = candles.iloc[-1]
    current_time = current["datetime"]
    current_hour = current_time.hour

    # ロンドンオープン時間帯のみ受け付ける
    if not (ENTRY_START_HOUR <= current_hour < ENTRY_END_HOUR):
        return False, ""

    # 当日のアジアセッション足を抽出
    today = current_time.date()
    asian = candles[
        (candles["datetime"].dt.date == today) &
        (candles["datetime"].dt.hour >= ASIAN_START_HOUR) &
        (candles["datetime"].dt.hour <  ASIAN_END_HOUR)
    ]

    # アジアセッションのデータが30本未満は信頼性なし → スキップ
    if len(asian) < 30:
        return False, ""

    asian_high       = asian["high"].max()
    asian_low        = asian["low"].min()
    asian_range_pips = (asian_high - asian_low) * 100

    # レンジが狭すぎる日はだましが多い → スキップ
    if asian_range_pips < MIN_RANGE_PIPS:
        return False, ""

    close = current["close"]

    if close > asian_high:
        return True, "buy"
    elif close < asian_low:
        return True, "sell"

    return False, ""


def exit_condition(candles: pd.DataFrame, position: dict) -> bool:
    """
    引数:
        candles  : 直近 LOOKBACK 本のローソク足（最新が末尾）
        position : 保有中のポジション情報
    戻り値:
        決済するか: bool
    """
    current       = candles.iloc[-1]
    current_close = current["close"]
    current_hour  = current["datetime"].hour

    # JST 22:00 で強制決済（翌日に持ち越さない）
    if current_hour >= EOD_CLOSE_HOUR:
        return True

    if position["side"] == "buy":
        pips = (current_close - position["entry_price"]) * 100
    else:
        pips = (position["entry_price"] - current_close) * 100

    return pips >= TAKE_PROFIT_PIPS or pips <= -STOP_LOSS_PIPS
