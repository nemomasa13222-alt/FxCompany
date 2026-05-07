# -*- coding: utf-8 -*-
"""
クロスコリレーション分析
- セクター指数と個別株の時間差相関を計算
- 先行・中間・遅行を分類
"""

import numpy as np
import pandas as pd
from scipy import stats


MAX_LAG   = 5   # 最大ラグ日数（±5日）
CORR_WINDOW = 252  # 相関計算に使う過去日数（約1年）


def cross_correlation(sector: pd.Series, stock: pd.Series, max_lag: int = MAX_LAG) -> dict[int, float]:
    """
    セクターリターンと銘柄リターンのクロスコリレーションを計算。

    lag > 0 : 銘柄がセクターに N日遅れて動く（遅行株）
    lag < 0 : 銘柄がセクターより N日早く動く（先行株）
    lag = 0 : 同時に動く（中間株）

    戻り値: {lag: correlation}
    """
    s_ret = sector.pct_change().dropna()
    k_ret = stock.pct_change().dropna()

    # 共通期間に揃える
    common = s_ret.index.intersection(k_ret.index)
    s = s_ret.loc[common].values
    k = k_ret.loc[common].values

    result = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag == 0:
            if len(s) < 30:
                result[lag] = np.nan
                continue
            r, _ = stats.pearsonr(s, k)
        elif lag > 0:
            # stock lags sector: compare s[:-lag] with k[lag:]
            if len(s) - lag < 30:
                result[lag] = np.nan
                continue
            r, _ = stats.pearsonr(s[:-lag], k[lag:])
        else:
            # stock leads sector: compare s[-lag:] with k[:lag]
            if len(s) + lag < 30:
                result[lag] = np.nan
                continue
            r, _ = stats.pearsonr(s[-lag:], k[:lag])
        result[lag] = round(r, 4)
    return result


def best_lag(corr_dict: dict[int, float]) -> int:
    """最大相関を示すラグを返す"""
    valid = {k: v for k, v in corr_dict.items() if not np.isnan(v)}
    if not valid:
        return 0
    return max(valid, key=lambda k: valid[k])


def classify(lag: int) -> str:
    """ラグから先行/中間/遅行を分類"""
    if lag <= -2:
        return "先行株"
    elif lag >= 2:
        return "遅行株"
    else:
        return "中間株"


def analyze_sector(etf: pd.Series, stocks: dict[str, pd.Series],
                   window: int = CORR_WINDOW) -> pd.DataFrame:
    """
    セクター内の全銘柄を分析してDataFrameで返す。

    列: ticker / best_lag / classification / corr_at_best_lag / corr_at_0
    """
    # 直近 window 日分に絞る
    etf_w = etf.iloc[-window:] if len(etf) > window else etf

    rows = []
    for ticker, stock in stocks.items():
        stock_w = stock.iloc[-window:] if len(stock) > window else stock
        corr = cross_correlation(etf_w, stock_w)
        lag  = best_lag(corr)
        rows.append({
            "ticker"           : ticker,
            "best_lag"         : lag,
            "classification"   : classify(lag),
            "corr_best"        : corr.get(lag, np.nan),
            "corr_0"           : corr.get(0, np.nan),
            "corr_dict"        : corr,
        })

    df = pd.DataFrame(rows).sort_values("best_lag", ascending=False)
    return df.reset_index(drop=True)


def sector_trend(etf: pd.Series, lookback: int = 5) -> dict:
    """
    直近 lookback 日のセクターETFのトレンド状態を返す。
    """
    recent = etf.iloc[-lookback - 1:]
    change_pct = (recent.iloc[-1] / recent.iloc[0] - 1) * 100
    return {
        "lookback_days" : lookback,
        "change_pct"    : round(change_pct, 2),
        "is_up"         : change_pct > 0,
    }
