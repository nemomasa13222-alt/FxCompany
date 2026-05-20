"""
FX Market State Monitor — Streamlit Dashboard

起動:
    streamlit run fx_market_classifier/streamlit_app.py

機能:
    - 通貨強弱ランキング (USD/JPY/EUR/GBP/AUD/NZD/CHF)
    - 12ペア分類テーブル (Trend / Mean Rev / Chop)
    - 経済カレンダー (ForexFactory, High/Medium イベント)
    - 1分自動更新
    - CSV保存 (monitor_log/monitor_YYYYMMDD.csv)
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as _fm
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# ── FX Classifier モジュール ─────────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from fx_market_classifier.classifier import MarketClassifier, MarketState
from fx_market_classifier.config import PAIRS, PAIR_CURRENCIES, CURRENCIES
from fx_market_classifier.data_fetcher import fetch_ohlcv
from fx_market_classifier.event_calendar import (
    fetch_calendar, get_today_events, is_event_near, format_event_time
)
from fx_market_classifier.visualizer import (
    plot_heatmap, plot_strength, plot_pair_detail
)

# ── 定数 ─────────────────────────────────────────────────────────────────────
REFRESH_SEC = 60
LOG_DIR     = Path("monitor_log")

_STATE_LABEL = {
    MarketState.TREND:          "Trend",
    MarketState.MEAN_REVERSION: "Mean Rev",
    MarketState.NO_TRADE:       "Chop",
}
_STATE_BG = {
    "Trend":    "background-color: #BBDEFB",
    "Mean Rev": "background-color: #FFE0B2",
    "Chop":     "background-color: #F0F0F0",
}
_IMPACT_ICON = {"High": "🔴", "Medium": "🟡", "Low": "⚪"}

# ── matplotlib 日本語フォント ─────────────────────────────────────────────────
_JP_FONTS   = ["Yu Gothic", "Meiryo", "MS Gothic", "IPAexGothic"]
_available  = {f.name for f in _fm.fontManager.ttflist}
_jp_font    = next((f for f in _JP_FONTS if f in _available), None)
_mpl_params = {"font.size": 8, "axes.grid": True, "grid.linewidth": 0.5}
if _jp_font:
    _mpl_params["font.family"] = _jp_font
matplotlib.rcParams.update(_mpl_params)


# ── データ取得（キャッシュ） ──────────────────────────────────────────────────

@st.cache_resource(ttl=60)
def load_market_data(_tick: int = 0) -> MarketClassifier | None:
    """5分足データを取得して MarketClassifier を構築（TTL=60秒）。"""
    try:
        price_data = fetch_ohlcv(lookback_days=7)
        if not price_data:
            return None
        return MarketClassifier(price_data)
    except Exception:
        return None


@st.cache_data(ttl=3600)
def load_calendar_cached() -> pd.DataFrame:
    """ForexFactory カレンダーを取得（TTL=1時間）。"""
    return fetch_calendar()


# ── CSV保存 ──────────────────────────────────────────────────────────────────

def save_csv(
    clf:            MarketClassifier,
    current_states: dict[str, MarketState],
    events_df:      pd.DataFrame,
    now_utc:        datetime,
) -> None:
    """毎分1回、monitor_log/monitor_YYYYMMDD.csv に追記する。"""
    # 重複書き込み防止（同一分に複数回呼ばれても1回のみ）
    key = "last_csv_min"
    now_min = now_utc.replace(second=0, microsecond=0)
    if st.session_state.get(key) == now_min:
        return
    st.session_state[key] = now_min

    try:
        LOG_DIR.mkdir(exist_ok=True)
        fname  = LOG_DIR / f"monitor_{now_utc.strftime('%Y%m%d')}.csv"
        latest = clf.latest_strength
        rows   = []

        for pair, state in current_states.items():
            base, quote = PAIR_CURRENCIES.get(pair, (None, None))
            if base is None:
                continue
            diff    = float(latest.get(base, 0.0)) - float(latest.get(quote, 0.0))
            acf_val = float(clf.acf[pair].iloc[-1]) if not clf.acf[pair].empty else float("nan")
            has_ev  = is_event_near(pair, events_df, minutes=30)

            rows.append({
                "datetime":      now_utc.isoformat(),
                "pair":          pair,
                "acf":           round(acf_val, 6) if not math.isnan(acf_val) else "",
                "strength_diff": round(diff, 6),
                "state":         state.value,
                "has_event":     has_ev,
            })

        header = not fname.exists()
        pd.DataFrame(rows).to_csv(fname, mode="a", header=header, index=False)
    except Exception:
        pass  # CSV失敗はサイレントに無視


# ── テーブルビルダー ──────────────────────────────────────────────────────────

def build_strength_df(clf: MarketClassifier) -> pd.DataFrame:
    """通貨強弱ランキング用 DataFrame を構築。"""
    latest = clf.latest_strength.sort_values(ascending=False)
    rows = []
    for rank, (ccy, val) in enumerate(latest.items(), 1):
        rows.append({
            "順位": rank,
            "通貨": ccy,
            "強弱値": f"{val:+.6f}",
            "方向":  "▲ 強" if val >= 0 else "▼ 弱",
        })
    return pd.DataFrame(rows)


def build_pair_df(
    clf:            MarketClassifier,
    current_states: dict[str, MarketState],
    events_df:      pd.DataFrame,
) -> pd.DataFrame:
    """ペア分類テーブル用 DataFrame を構築（状態順にソート）。"""
    _order = {MarketState.TREND: 0, MarketState.MEAN_REVERSION: 1, MarketState.NO_TRADE: 2}
    latest = clf.latest_strength
    rows   = []

    for pair in sorted(current_states, key=lambda p: (_order.get(current_states[p], 9), p)):
        state       = current_states[pair]
        base, quote = PAIR_CURRENCIES.get(pair, ("?", "?"))
        base_s      = float(latest.get(base,  0.0))
        quote_s     = float(latest.get(quote, 0.0))
        diff        = base_s - quote_s
        acf_val     = float(clf.acf[pair].iloc[-1]) if not clf.acf[pair].empty else float("nan")
        has_ev      = is_event_near(pair, events_df, minutes=30)

        diff_label  = f"{base}>{quote}" if diff >= 0 else f"{quote}>{base}"
        acf_tag     = ("(+)" if acf_val > 0 else "(-)" if acf_val < 0 else "( )")
        state_label = _STATE_LABEL.get(state, "?")

        if state == MarketState.TREND:
            direction = "Buy" if diff > 0 else "Sell"
        elif state == MarketState.MEAN_REVERSION:
            direction = "Fade"
        else:
            direction = "---"

        rows.append({
            "Event": "●" if has_ev else "",
            "Pair":  pair,
            "StrengthDiff": f"{diff:+.5f} {diff_label}",
            "ACF":          f"{acf_val:+.3f} {acf_tag}" if not math.isnan(acf_val) else "N/A",
            "State":        state_label,
            "Direction":    direction,
        })

    return pd.DataFrame(rows)


def style_pair_row(row: pd.Series) -> list[str]:
    """pd.Styler.apply(axis=1) 用: State に応じて行背景色を設定。"""
    css = _STATE_BG.get(row["State"], "")
    return [css] * len(row)


# ── レンダリング ──────────────────────────────────────────────────────────────

def render_header(now_utc: datetime, remaining: int) -> None:
    c1, c2, c3 = st.columns([4, 3, 3])
    c1.markdown("## 📊 FX Market State Monitor")
    c2.metric("最終更新", now_utc.strftime("%H:%M:%S UTC"))
    c3.metric("次の更新まで", f"{remaining}秒")


def render_strength(clf: MarketClassifier) -> None:
    st.subheader("通貨強弱ランキング")
    df  = build_strength_df(clf)

    def color_direction(val: str) -> str:
        return "color: #1565C0; font-weight: bold" if "強" in val else "color: #C62828; font-weight: bold"

    styled = df.style.map(color_direction, subset=["方向"])
    st.dataframe(styled, width="stretch", hide_index=True, height=280)


def render_calendar(events_df: pd.DataFrame) -> None:
    st.subheader("経済カレンダー（今日/明日）")
    if events_df.empty:
        st.caption("取得不可 または 該当イベントなし")
        return

    for _, row in events_df.iterrows():
        icon  = _IMPACT_ICON.get(row["impact"], "⚪")
        etime = format_event_time(row["event_time"])
        st.markdown(
            f"{icon} `{etime}` **{row['country']}**  {row['title']}"
        )


def render_pair_table(
    clf:            MarketClassifier,
    current_states: dict[str, MarketState],
    events_df:      pd.DataFrame,
) -> None:
    st.subheader("ペア分類")
    df     = build_pair_df(clf, current_states, events_df)
    styled = df.style.apply(style_pair_row, axis=1)

    st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        height=460,
        column_config={
            "Event":        st.column_config.TextColumn("📅", width=40),
            "Pair":         st.column_config.TextColumn("ペア",         width=80),
            "StrengthDiff": st.column_config.TextColumn("強弱差",        width=160),
            "ACF":          st.column_config.TextColumn("ACF (lag=1)",   width=130),
            "State":        st.column_config.TextColumn("状態",          width=90),
            "Direction":    st.column_config.TextColumn("方向",          width=80),
        },
    )

    # 状態サマリー
    t = sum(1 for v in current_states.values() if v == MarketState.TREND)
    m = sum(1 for v in current_states.values() if v == MarketState.MEAN_REVERSION)
    n = sum(1 for v in current_states.values() if v == MarketState.NO_TRADE)
    st.caption(
        f"🔵 Trend: {t}ペア  　"
        f"🟠 Mean Rev: {m}ペア  　"
        f"⚪ Chop: {n}ペア"
    )


def render_charts(clf: MarketClassifier) -> None:
    tab1, tab2, tab3 = st.tabs(["ヒートマップ", "通貨強弱チャート", "ペア詳細チャート"])

    with tab1:
        fig = plot_heatmap(clf.states, last_n=576)   # ~2日分
        st.pyplot(fig, width="stretch")
        plt.close(fig)

    with tab2:
        fig = plot_strength(clf.strength, last_n=576)
        st.pyplot(fig, width="stretch")
        plt.close(fig)

    with tab3:
        pair = st.selectbox("ペアを選択", PAIRS, key="detail_pair_select")
        if pair and pair in clf.states.columns and pair in clf.price_data:
            sd  = clf.strength_diff(pair)
            fig = plot_pair_detail(
                pair         = pair,
                price_df     = clf.price_data[pair],
                acf_series   = clf.acf[pair],
                strength_diff= sd,
                state_series = clf.states[pair],
                bb1          = clf.bb1[pair],
                bb3          = clf.bb3[pair],
                last_n       = 576,
            )
            st.pyplot(fig, width="stretch")
            plt.close(fig)


# ── サイドバー ────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 判定ルール")
        st.markdown(
            "**🔵 Trend**  \n"
            "`|強弱差| ≥ 0.0008` AND `ACF ≥ +0.05`  \n"
            "→ 強弱差が大 + 系列相関あり（モメンタム継続）\n\n"
            "**🟠 Mean Rev**  \n"
            "`|強弱差| ≥ 0.0008` AND `ACF ≤ -0.05`  \n"
            "→ 強弱差が大 + 反転傾向（大きな動きが戻る）\n\n"
            "**⚪ Chop**  \n"
            "`|強弱差| < 0.0008` または `ACF が中立`  \n"
            "→ 方向感なし・待機\n\n"
            "**📅 Event**  \n"
            "次30分以内に関連通貨の高/中インパクト経済指標あり"
        )
        st.divider()
        st.markdown("### データソース")
        st.caption("価格: yfinance (5分足, 直近7日)")
        st.caption("カレンダー: ForexFactory (1時間キャッシュ)")
        st.divider()
        st.markdown("### ログ保存先")
        st.caption(f"`monitor_log/monitor_YYYYMMDD.csv`")


# ── メイン ───────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title = "FX Monitor",
        page_icon  = "📈",
        layout     = "wide",
        initial_sidebar_state = "expanded",
    )

    # ── 自動更新 ──────────────────────────────────────────────────────────────
    remaining = REFRESH_SEC
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=REFRESH_SEC * 1000, key="fx_autorefresh")
    except ImportError:
        # フォールバック: session_state で60秒タイマー管理
        now_ts = time.time()
        if "last_refresh_ts" not in st.session_state:
            st.session_state.last_refresh_ts = now_ts
        elapsed   = now_ts - st.session_state.last_refresh_ts
        remaining = max(0, int(REFRESH_SEC - elapsed))
        if remaining <= 0:
            st.session_state.last_refresh_ts = now_ts
            st.cache_data.clear()
            st.rerun()

    now_utc = datetime.now(timezone.utc)

    # ── データ取得 ─────────────────────────────────────────────────────────────
    # tick を分単位で変えることで毎分キャッシュを破棄して再取得
    tick = int(now_utc.timestamp() // REFRESH_SEC)
    clf  = load_market_data(tick)

    cal_df    = load_calendar_cached()
    events_df = get_today_events(df=cal_df)

    # ── レイアウト ─────────────────────────────────────────────────────────────
    render_sidebar()
    render_header(now_utc, remaining)

    if clf is None:
        st.error("データ取得に失敗しました。ネット接続を確認してください。")
        st.stop()

    current_states = clf.current_state()

    # CSV保存
    save_csv(clf, current_states, events_df, now_utc)

    # 上段: ペア分類テーブル
    render_pair_table(clf, current_states, events_df)

    st.divider()

    # 中段: 強弱ランキング ＋ カレンダー
    col1, col2 = st.columns([1, 1])
    with col1:
        render_strength(clf)
    with col2:
        render_calendar(events_df)

    st.divider()

    # 下段: チャートタブ
    render_charts(clf)


if __name__ == "__main__":
    main()
