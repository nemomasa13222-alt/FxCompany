# -*- coding: utf-8 -*-
"""
ミネルヴィニ・トレンドテンプレート スクリーナー
マーク・ミネルヴィニの8条件に基づいて銘柄を評価する
"""

import numpy as np
import pandas as pd


# ── RS Rating 計算 ────────────────────────────────────────────────────────

def rs_raw_score(close: pd.Series) -> float:
    """
    IBD RS Ratingの近似値（rawスコア）を計算する。
    12ヶ月を4分割してウェイト付き。
    直近3ヶ月×0.4 + 前3ヶ月×0.2 + 前々3ヶ月×0.2 + 最初3ヶ月×0.2
    """
    if len(close) < 252:
        return np.nan
    try:
        q1 = close.iloc[-1]   / close.iloc[-64]  - 1   # 直近3ヶ月
        q2 = close.iloc[-64]  / close.iloc[-127] - 1
        q3 = close.iloc[-127] / close.iloc[-190] - 1
        q4 = close.iloc[-190] / close.iloc[-252] - 1
        return q1 * 0.4 + q2 * 0.2 + q3 * 0.2 + q4 * 0.2
    except IndexError:
        return np.nan


def calc_rs_percentiles(closes: dict[str, pd.Series]) -> dict[str, float]:
    """
    銘柄ユニバース全体でRSを計算し、パーセンタイル(1-99)を返す。
    closes: {ticker: pd.Series}
    """
    scores = {t: rs_raw_score(s) for t, s in closes.items()}
    valid = {t: v for t, v in scores.items() if not np.isnan(v)}
    if not valid:
        return {t: np.nan for t in closes}

    sorted_tickers = sorted(valid, key=lambda t: valid[t])
    n = len(sorted_tickers)
    percentiles = {}
    for i, t in enumerate(sorted_tickers):
        pct = round((i / (n - 1)) * 98 + 1) if n > 1 else 50
        percentiles[t] = pct

    for t in closes:
        if t not in percentiles:
            percentiles[t] = np.nan

    return percentiles


# ── 200日移動平均の傾き判定 ───────────────────────────────────────────────

def is_ma200_rising(close: pd.Series, lookback_days: int = 20) -> bool:
    """MA200が lookback_days 日前より高ければ上昇トレンドと判定"""
    if len(close) < 200 + lookback_days:
        return False
    ma200_now  = close.iloc[-200:].mean()
    ma200_prev = close.iloc[-(200 + lookback_days):-lookback_days].mean()
    return ma200_now > ma200_prev


# ── 8条件チェック ─────────────────────────────────────────────────────────

def check(close: pd.Series, rs_percentile: float) -> dict | None:
    """
    8条件を評価して結果dictを返す。データ不足なら None。

    Parameters
    ----------
    close        : 終値Series（252日以上推奨）
    rs_percentile: 銘柄ユニバース内のRS百分位（1-99）

    Returns
    -------
    dict:
        passed_all  : 8条件すべて合格か
        score       : 合格条件数（0-8）
        details     : 各条件の結果リスト
        price, ma50, ma150, ma200, high_52w, low_52w, rs_rating 等
    """
    if len(close) < 220:
        return None

    price    = float(close.iloc[-1])
    ma50     = float(close.iloc[-50:].mean())
    ma150    = float(close.iloc[-150:].mean())
    ma200    = float(close.iloc[-200:].mean())
    high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
    low_52w  = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())

    c1 = price > ma150 and price > ma200
    c2 = ma150 > ma200
    c3 = is_ma200_rising(close)
    c4 = ma50 > ma150 and ma50 > ma200
    c5 = price >= low_52w * 1.25
    c6 = price >= high_52w * 0.75
    c7 = (not np.isnan(rs_percentile)) and rs_percentile >= 70
    c8 = price > ma50

    conditions = [c1, c2, c3, c4, c5, c6, c7, c8]
    labels = [
        "株価 > MA150・MA200",
        "MA150 > MA200",
        "MA200 上昇トレンド（1ヶ月）",
        "MA50 > MA150・MA200",
        "52週安値から25%以上上昇",
        "52週高値から25%以内",
        f"RS Rating ≥ 70（現在: {rs_percentile:.0f}）" if not np.isnan(rs_percentile) else "RS Rating ≥ 70（データ不足）",
        "株価 > MA50",
    ]

    details = [{"no": i+1, "label": lbl, "passed": cond}
               for i, (cond, lbl) in enumerate(zip(conditions, labels))]

    # MA20からの乖離率（直近ベース離れ具合）: +15%超は追いかけリスク大
    ma20 = float(close.iloc[-20:].mean())
    ext_from_ma20 = round((price / ma20 - 1) * 100, 1)

    return {
        "passed_all"         : all(conditions),
        "score"              : sum(conditions),
        "details"            : details,
        "price"              : round(price, 1),
        "ma20"               : round(ma20, 1),
        "ma50"               : round(ma50, 1),
        "ma150"              : round(ma150, 1),
        "ma200"              : round(ma200, 1),
        "high_52w"           : round(high_52w, 1),
        "low_52w"            : round(low_52w, 1),
        "rs_rating"          : round(rs_percentile) if not np.isnan(rs_percentile) else None,
        "rise_from_low_pct"  : round((price / low_52w - 1) * 100, 1),
        "dist_from_high_pct" : round((price / high_52w - 1) * 100, 1),
        "ext_from_ma20_pct"  : ext_from_ma20,   # +15%超は要注意
    }


def format_result(ticker: str, result: dict) -> str:
    """結果を人が読みやすい形式でフォーマット"""
    mark = "★ 全条件クリア" if result["passed_all"] else f"  {result['score']}/8 条件"
    lines = [
        f"[{ticker}]  {mark}  株価:{result['price']}円  RS:{result['rs_rating']}",
        f"  MA50:{result['ma50']} / MA150:{result['ma150']} / MA200:{result['ma200']}",
        f"  52週高値:{result['high_52w']} ({result['dist_from_high_pct']:+.1f}%) "
        f"/ 52週安値:{result['low_52w']} (+{result['rise_from_low_pct']:.1f}%)",
    ]
    for d in result["details"]:
        icon = "✓" if d["passed"] else "✗"
        lines.append(f"  {icon} {d['no']}. {d['label']}")
    return "\n".join(lines)
