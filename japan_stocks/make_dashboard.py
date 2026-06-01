# -*- coding: utf-8 -*-
"""
デモ口座 ダッシュボード HTML 生成スクリプト
state.json / pnl_history.csv / trades.csv を読み込み docs/index.html を生成する。

実行: python japan_stocks/make_dashboard.py
"""

import sys, json, base64
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime
from io import BytesIO
import pandas as pd

DEMO_DIR  = Path(__file__).parent / "results" / "demo"
DOCS_DIR  = Path(__file__).parent.parent / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE  = DEMO_DIR / "state.json"
PNL_FILE    = DEMO_DIR / "pnl_history.csv"
TRADES_FILE = DEMO_DIR / "trades.csv"

INITIAL_CAPITAL = 1_000_000
PW_HASH         = "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"


def load_data() -> tuple[dict, list, list]:
    state  = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    pnl    = pd.read_csv(PNL_FILE,    encoding="utf-8-sig").to_dict("records") if PNL_FILE.exists()    else []
    trades = pd.read_csv(TRADES_FILE, encoding="utf-8-sig").to_dict("records") if TRADES_FILE.exists() else []
    return state, pnl, trades


# ── チャート生成 ───────────────────────────────────────────────────────────────

def _b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="#0f172a")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def chart_sectors(days: int = 60) -> tuple[str, list[dict]]:
    """
    demo_signal.py が保存した独自セクター指数（等加重）の
    直近 days 日間の推移チャートとパフォーマンステーブルを返す。
    Returns: (base64_png, sector_perf_list)
    """
    idx_file = DEMO_DIR / "sector_indices.csv"
    if not idx_file.exists():
        print("  [chart_sectors] sector_indices.csv が見つかりません")
        return "", []

    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib as mpl
        mpl.rcParams["font.family"] = "Meiryo"

        df = pd.read_csv(idx_file, index_col=0, parse_dates=True, encoding="utf-8-sig")
        df = df.sort_index().tail(days)
        if df.empty or len(df) < 5:
            return "", []

        COLORS = [
            "#22d3ee", "#a78bfa", "#34d399", "#fb923c",
            "#f472b6", "#facc15", "#60a5fa", "#f87171",
        ]

        fig, ax = plt.subplots(figsize=(13, 5))
        fig.patch.set_facecolor("#0f172a")
        ax.set_facecolor("#0f172a")

        perf_rows: list[dict] = []

        for i, name in enumerate(df.columns):
            s = df[name].dropna()
            if len(s) < 5:
                continue
            norm  = s / s.iloc[0] * 100
            color = COLORS[i % len(COLORS)]
            ax.plot(norm.index, norm.values, color=color, linewidth=1.8,
                    label=name, alpha=0.9)

            last  = float(s.iloc[-1])
            ret5  = (last / float(s.iloc[-6])  - 1) * 100 if len(s) >= 6  else float("nan")
            ret20 = (last / float(s.iloc[-21]) - 1) * 100 if len(s) >= 21 else float("nan")
            ret60 = (last / float(s.iloc[0])   - 1) * 100
            perf_rows.append({
                "name": name, "ret5": ret5, "ret20": ret20, "ret60": ret60,
                "color": color,
            })

        perf_rows.sort(key=lambda r: r["ret20"] if not pd.isna(r["ret20"]) else -999,
                       reverse=True)

        ax.axhline(100, color="#475569", linewidth=0.8, linestyle="--", alpha=0.6)
        ax.set_ylabel("指数（初日=100）", fontsize=10, color="#94a3b8")
        ax.set_title(f"セクター指数推移（直近{days}日・等加重合成）",
                     fontsize=12, color="#e2e8f0", pad=10)
        ax.tick_params(colors="#64748b")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.grid(True, color="#1e293b", linewidth=0.6)
        ax.legend(loc="upper left", fontsize=8, framealpha=0.2,
                  labelcolor="#e2e8f0", facecolor="#1e293b",
                  ncol=2, borderpad=0.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")

        fig.tight_layout()
        return _b64(fig), perf_rows

    except Exception as e:
        print(f"  [chart_sectors エラー] {e}")
        return "", []


def chart_divergence() -> str:
    """
    pending・保有株とセクター指数の乖離チャート。
    demo_signal.py が保存した divergence_data.csv を読む（ライブ取得なし）。
    """
    div_file = DEMO_DIR / "divergence_data.csv"
    if not div_file.exists():
        return ""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib as mpl
        mpl.rcParams["font.family"] = "Meiryo"

        df = pd.read_csv(div_file, parse_dates=["date"], encoding="utf-8")
        if df.empty:
            return ""

        sectors = df[df["kind"] == "sector"]["sector"].unique().tolist()
        n = len(sectors)
        if n == 0:
            return ""

        fig, axes = plt.subplots(1, n, figsize=(7 * n, 4.5), squeeze=False)
        fig.patch.set_facecolor("#0f172a")

        STOCK_COLORS = ["#facc15", "#fb923c", "#f472b6", "#a78bfa", "#34d399"]

        for col, sector in enumerate(sectors):
            ax = axes[0][col]
            ax.set_facecolor("#0f172a")

            sec = df[(df["sector"] == sector) & (df["kind"] == "sector")].sort_values("date")
            stocks = df[(df["sector"] == sector) & (df["kind"] == "stock")]
            tickers = stocks["label"].unique().tolist()

            if sec.empty:
                continue

            # セクター指数（白・太線）
            ax.plot(sec["date"], sec["norm"], color="#e2e8f0", linewidth=2.5,
                    label=sector, zorder=3)

            # 個別株（色付き細線）
            for i, ticker in enumerate(tickers):
                s = stocks[stocks["label"] == ticker].sort_values("date")
                color = STOCK_COLORS[i % len(STOCK_COLORS)]
                ax.plot(s["date"], s["norm"], color=color, linewidth=1.6,
                        label=ticker, linestyle="--", zorder=2, alpha=0.9)

                # 末尾の乖離をアノテーション
                if not s.empty and not sec.empty:
                    last_date = s["date"].iloc[-1]
                    sec_match = sec[sec["date"] == last_date]
                    if not sec_match.empty:
                        gap = float(s["norm"].iloc[-1]) - float(sec_match["norm"].iloc[-1])
                        clr = "#f87171" if gap < 0 else "#22c55e"
                        ax.annotate(
                            f"{gap:+.1f}%",
                            xy=(last_date, float(s["norm"].iloc[-1])),
                            xytext=(6, 0), textcoords="offset points",
                            color=clr, fontsize=8, va="center",
                        )

            ax.axhline(100, color="#475569", linewidth=0.8, linestyle=":", alpha=0.6)
            ax.set_title(sector, fontsize=11, color="#e2e8f0", pad=8)
            ax.set_ylabel("正規化（窓初日=100）", fontsize=8, color="#94a3b8")
            ax.tick_params(colors="#64748b", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#334155")
            ax.grid(True, color="#1e293b", linewidth=0.5)
            ax.legend(loc="upper left", fontsize=7.5, framealpha=0.2,
                      labelcolor="#e2e8f0", facecolor="#1e293b", borderpad=0.4)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")

        fig.suptitle("セクター指数 vs 保有・候補銘柄（乖離チャート）",
                     color="#cbd5e1", fontsize=12, y=1.02)
        fig.tight_layout()
        return _b64(fig)
    except Exception as e:
        print(f"  [chart_divergence エラー] {e}")
        return ""


def _mpf_style():
    import mplfinance as mpf
    return mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        facecolor="#0f172a", figcolor="#0f172a",
        gridcolor="#1e293b", gridstyle="-",
        rc={
            "axes.labelcolor": "#94a3b8",
            "xtick.color": "#64748b",
            "ytick.color": "#64748b",
            "font.family": "Meiryo",
        },
    )


def chart_position(ticker: str, entry_price: float, stop_price: float, entry_date_str: str) -> str:
    """保有ポジション: 当日5分足チャート（エントリーライン・ストップライン付き）"""
    try:
        import yfinance as yf
        import mplfinance as mpf
        import matplotlib as mpl
        import matplotlib.pyplot as plt
        mpl.rcParams["font.family"] = "Meiryo"

        df = yf.download(ticker, period="1d", interval="5m", progress=False)
        if df.empty:
            return ""
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_convert("Asia/Tokyo")
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if len(df) < 3:
            return ""

        apds = [
            mpf.make_addplot([entry_price] * len(df), color="#22d3ee", linestyle="--", width=1.5),
            mpf.make_addplot([stop_price]  * len(df), color="#f87171", linestyle="--", width=1.5),
        ]
        fig, axes = mpf.plot(
            df, type="candle", style=_mpf_style(), addplot=apds,
            volume=True, figsize=(11, 5), returnfig=True,
            tight_layout=True, datetime_format="%H:%M", xrotation=0,
        )
        ax = axes[0]
        price_range = df["High"].max() - df["Low"].min()
        offset = price_range * 0.04

        ax.plot(0, entry_price - offset, marker="^", color="#22d3ee", markersize=14, zorder=5)
        ax.text(2, entry_price + offset * 0.3,
                f"買い: {entry_price:,.0f}円", color="#22d3ee", fontsize=10, fontweight="bold")
        ax.text(2, stop_price  + offset * 0.3,
                f"ストップ: {stop_price:,.0f}円", color="#f87171", fontsize=10)

        last_close = float(df["Close"].iloc[-1])
        ax.axhline(last_close, color="#fbbf24", linestyle=":", linewidth=1.2)
        ax.text(len(df) * 0.82, last_close + offset * 0.3,
                f"引け: {last_close:,.0f}円", color="#fbbf24", fontsize=9)

        ax.set_title(f"{ticker}  {entry_date_str}  5分足", color="#e2e8f0", fontsize=12, pad=10)
        fig.patch.set_facecolor("#0f172a")
        return _b64(fig)
    except Exception as e:
        print(f"  [chart_position エラー] {ticker}: {e}")
        return ""


def chart_trade(ticker: str, entry_date_str: str, entry_price: float,
                exit_date_str: str, exit_price: float, exit_reason: str) -> str:
    """決済済みトレード: エントリー/エグジットをチャート上にマーク"""
    try:
        import yfinance as yf
        import mplfinance as mpf
        import matplotlib as mpl
        import matplotlib.pyplot as plt
        mpl.rcParams["font.family"] = "Meiryo"

        same_day = entry_date_str == exit_date_str
        reason_map = {"stop": "損切", "target": "利確", "time": "時間切れ"}
        exit_colors = {"stop": "#f87171", "target": "#22c55e", "time": "#fb923c"}
        label  = reason_map.get(exit_reason, exit_reason)
        ec     = exit_colors.get(exit_reason, "#94a3b8")

        if same_day:
            today_str = datetime.today().strftime("%Y-%m-%d")
            if exit_date_str == today_str:
                df = yf.download(ticker, period="1d", interval="5m", progress=False)
            else:
                end_dt = (pd.Timestamp(exit_date_str) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                df = yf.download(ticker, start=exit_date_str, end=end_dt, interval="5m", progress=False)
            if df.empty: return ""
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = df.index.tz_convert("Asia/Tokyo")
            # 指定日のバーだけに絞る
            df = df[df.index.normalize().strftime("%Y-%m-%d") == exit_date_str]
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            fmt = "%H:%M"
            xi_entry = 0
            xi_exit  = len(df) - 1
        else:
            start = (pd.Timestamp(entry_date_str) - pd.Timedelta(days=15)).strftime("%Y-%m-%d")
            end   = (pd.Timestamp(exit_date_str)  + pd.Timedelta(days=10)).strftime("%Y-%m-%d")
            df = yf.download(ticker, start=start, end=end, progress=False)
            if df.empty: return ""
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            fmt = "%m/%d"
            dates = [d.strftime("%Y-%m-%d") for d in df.index]
            xi_entry = next((i for i, d in enumerate(dates) if d == entry_date_str), 0)
            xi_exit  = next((i for i, d in enumerate(reversed(dates)) if d == exit_date_str),
                            len(df) - 1)
            xi_exit  = len(df) - 1 - xi_exit

        if len(df) < 2: return ""

        price_range = df["High"].max() - df["Low"].min()
        offset = max(price_range * 0.04, entry_price * 0.005)

        fig, axes = mpf.plot(
            df, type="candle", style=_mpf_style(),
            volume=True, figsize=(11, 5), returnfig=True,
            tight_layout=True, datetime_format=fmt, xrotation=0,
        )
        ax = axes[0]

        # エントリーマーカー
        ax.plot(xi_entry, entry_price - offset, marker="^", color="#22d3ee", markersize=14, zorder=5)
        ax.text(xi_entry, entry_price - offset * 2.2,
                f"買い\n{entry_price:,.0f}", color="#22d3ee", fontsize=8, ha="center")

        # エグジットマーカー
        ax.plot(xi_exit, exit_price + offset, marker="v", color=ec, markersize=14, zorder=5)
        ax.text(xi_exit, exit_price + offset * 2.2,
                f"{label}\n{exit_price:,.0f}", color=ec, fontsize=8, ha="center")

        pnl_pct = (exit_price / entry_price - 1) * 100
        ax.set_title(
            f"{ticker}  買い({entry_date_str}) → {label}({exit_date_str})  ({pnl_pct:+.2f}%)",
            color="#e2e8f0", fontsize=11, pad=10,
        )
        fig.patch.set_facecolor("#0f172a")
        return _b64(fig)
    except Exception as e:
        print(f"  [chart_trade エラー] {ticker}: {e}")
        return ""


# ── HTML生成 ──────────────────────────────────────────────────────────────────

def build_html(state: dict, pnl: list, trades: list, pw_hash: str = PW_HASH) -> str:
    last_run     = state.get("last_run", "—")
    capital      = state.get("capital", INITIAL_CAPITAL)
    peak         = state.get("peak_capital", INITIAL_CAPITAL)
    positions    = state.get("positions", [])
    pending      = state.get("pending", [])
    realized_pnl = state.get("total_realized_pnl", 0)
    trade_count  = state.get("trade_count", 0)

    latest_pnl   = pnl[-1] if pnl else {}
    total_equity = latest_pnl.get("total_equity", capital)
    unrealized   = latest_pnl.get("unrealized_pnl", 0)
    ret_pct      = latest_pnl.get("return_pct", 0)
    max_dd       = latest_pnl.get("max_dd_pct", 0)

    ret_color = "#22c55e" if ret_pct >= 0 else "#ef4444"
    ret_sign  = "+" if ret_pct >= 0 else ""

    # ── セクター指数チャート ───────────────────────────────────────────────────
    print("  セクター指数チャート生成中...")
    sector_chart_b64, sector_perf = chart_sectors(days=60)
    print(f"    → {len(sector_perf)} セクター取得")

    # ── 乖離チャート ─────────────────────────────────────────────────────────
    print("  乖離チャート生成中...")
    div_chart_b64 = chart_divergence()
    print(f"    → {'OK' if div_chart_b64 else 'データなし'}")

    # ── チャートデータ生成 ─────────────────────────────────────────────────────
    charts: dict[str, str] = {}

    print("  保有ポジションのチャート生成中...")
    for p in positions:
        key = f"pos_{p['ticker']}"
        print(f"    {p['ticker']} ...", end=" ", flush=True)
        charts[key] = chart_position(
            p["ticker"], p["entry_price"], p["stop_price"], p["entry_date"]
        )
        print("OK" if charts[key] else "スキップ")

    print("  決済トレードのチャート生成中...")
    for t in trades:
        key = f"trade_{t['ticker']}_{t['exit_date']}"
        if key not in charts:
            print(f"    {t['ticker']} ({t['exit_date']}) ...", end=" ", flush=True)
            charts[key] = chart_trade(
                t["ticker"], t["entry_date"], t["entry_price"],
                t["exit_date"], t["exit_price"], t["exit_reason"],
            )
            print("OK" if charts[key] else "スキップ")

    charts_json = json.dumps(charts)

    # ── Chart data ────────────────────────────────────────────────────────────
    chart_dates  = json.dumps([r["date"] for r in pnl])
    chart_equity = json.dumps([round(r["total_equity"] / 10000, 1) for r in pnl])
    chart_dd     = json.dumps([round(-r["max_dd_pct"], 2) for r in pnl])

    # ── 保有ポジション行 ───────────────────────────────────────────────────────
    pos_rows = ""
    for p in positions:
        days   = p.get("days_held", 0)
        stop   = p.get("stop_price", 0)
        entry  = p.get("entry_price", 0)
        shares = p.get("shares", 0)
        invest = round(entry * shares)
        cur    = p.get("current_price")
        unreal = p.get("unrealized_pnl")
        key    = f"pos_{p['ticker']}"
        clickable = "cursor-pointer hover:text-cyan-300 underline" if charts.get(key) else ""
        onclick   = f'onclick="showChart(\'{key}\')"' if charts.get(key) else ""

        if cur is not None:
            ret_p      = (cur / entry - 1) * 100 if entry else 0
            cur_str    = f"{cur:,.0f}"
            ret_col    = "#22c55e" if ret_p >= 0 else "#ef4444"
            unreal_str = (f"{'+'if unreal>=0 else ''}{unreal:,.0f}円"
                          f"<br><span style='font-size:11px'>({ret_p:+.2f}%)</span>")
        else:
            cur_str    = "—"
            ret_col    = "#64748b"
            unreal_str = "—"

        pos_rows += f"""
        <tr class="hover:bg-slate-750 transition-colors">
          <td class="px-4 py-3 font-mono font-bold text-cyan-400 {clickable}" {onclick}>{p['ticker']}</td>
          <td class="px-4 py-3 text-slate-300">{p['sector']}</td>
          <td class="px-4 py-3 text-right">{entry:,.0f}</td>
          <td class="px-4 py-3 text-right font-bold">{cur_str}</td>
          <td class="px-4 py-3 text-right font-bold" style="color:{ret_col}">{unreal_str}</td>
          <td class="px-4 py-3 text-right">{shares:,}</td>
          <td class="px-4 py-3 text-right text-slate-400">{invest:,}</td>
          <td class="px-4 py-3 text-right text-orange-400">{stop:,.0f}</td>
          <td class="px-4 py-3 text-right text-slate-400">{days}日目</td>
        </tr>"""

    # ── pending行 ─────────────────────────────────────────────────────────────
    pend_rows = ""
    for p in pending:
        pend_rows += f"""
        <tr class="hover:bg-slate-750 transition-colors">
          <td class="px-4 py-3 font-mono font-bold text-yellow-400">{p['ticker']}</td>
          <td class="px-4 py-3 text-slate-300">{p['sector']}</td>
          <td class="px-4 py-3 text-right">{p.get('signal_close', 0):,.0f}</td>
          <td class="px-4 py-3 text-right text-emerald-400">+{p.get('gap_pct', 0):.1f}%</td>
          <td class="px-4 py-3 text-right text-slate-400">{p.get('corr', 0):.2f}</td>
          <td class="px-4 py-3 text-slate-400">{p.get('classification', '')}</td>
        </tr>"""

    # ── 決済トレード行（全件） ─────────────────────────────────────────────────
    trade_rows = ""
    for t in reversed(trades):
        pnl_val  = t.get("pnl_jpy", 0)
        pnl_col  = "#22c55e" if pnl_val >= 0 else "#ef4444"
        sign     = "+" if pnl_val >= 0 else ""
        reason_map = {"target": "利確", "stop": "損切", "time": "時間"}
        reason   = reason_map.get(t.get("exit_reason", ""), t.get("exit_reason", ""))
        key      = f"trade_{t['ticker']}_{t['exit_date']}"
        clickable = "cursor-pointer hover:text-cyan-300 underline" if charts.get(key) else ""
        onclick   = f'onclick="showChart(\'{key}\')"' if charts.get(key) else ""

        trade_rows += f"""
        <tr class="hover:bg-slate-750 transition-colors">
          <td class="px-4 py-3 font-mono text-cyan-400 {clickable}" {onclick}>{t.get('ticker','')}</td>
          <td class="px-4 py-3 text-slate-400">{t.get('entry_date','')}</td>
          <td class="px-4 py-3 text-slate-400">{t.get('exit_date','')}</td>
          <td class="px-4 py-3 text-right">{t.get('entry_price',0):,.0f}</td>
          <td class="px-4 py-3 text-right">{t.get('exit_price',0):,.0f}</td>
          <td class="px-4 py-3 text-right font-bold" style="color:{pnl_col}">{sign}{pnl_val:,.0f}</td>
          <td class="px-4 py-3 text-right" style="color:{pnl_col}">{t.get('return_pct',0):+.2f}%</td>
          <td class="px-4 py-3 text-slate-400">{reason}</td>
          <td class="px-4 py-3 text-right text-slate-400">{t.get('days_held',0)}日</td>
        </tr>"""

    # ── セクターパフォーマンステーブル行 ─────────────────────────────────────
    sector_rows = ""
    for r in sector_perf:
        def _col(v):
            if pd.isna(v): return "#64748b"
            return "#22c55e" if v >= 0 else "#ef4444"
        def _fmt(v):
            if pd.isna(v): return "—"
            return f"{v:+.1f}%"
        rank_icon = "▲" if r["ret20"] > 2 else ("▼" if r["ret20"] < -2 else "—")
        rank_col  = "#22c55e" if r["ret20"] > 2 else ("#ef4444" if r["ret20"] < -2 else "#64748b")
        sector_rows += f"""
        <tr class="hover:bg-slate-750 transition-colors">
          <td class="px-4 py-2.5 font-semibold" style="color:{r['color']}">{r['name']}</td>
          <td class="px-4 py-2.5 text-right font-bold" style="color:{_col(r['ret5'])}">{_fmt(r['ret5'])}</td>
          <td class="px-4 py-2.5 text-right font-bold" style="color:{_col(r['ret20'])}">{_fmt(r['ret20'])}</td>
          <td class="px-4 py-2.5 text-right" style="color:{_col(r['ret60'])}">{_fmt(r['ret60'])}</td>
          <td class="px-4 py-2.5 text-center font-bold" style="color:{rank_col}">{rank_icon}</td>
        </tr>"""

    no_sector_rows = '<tr><td colspan="5" class="px-4 py-6 text-center text-slate-500">データなし</td></tr>' if not sector_rows else sector_rows

    no_positions = f'<tr><td colspan="9" class="px-4 py-6 text-center text-slate-500">保有なし</td></tr>' if not pos_rows else pos_rows
    no_pending   = f'<tr><td colspan="6" class="px-4 py-6 text-center text-slate-500">なし</td></tr>' if not pend_rows else pend_rows
    no_trades    = f'<tr><td colspan="9" class="px-4 py-6 text-center text-slate-500">決済トレードなし</td></tr>' if not trade_rows else trade_rows

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M JST")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FxCompany デモ口座</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>
    body {{ background: #0f172a; color: #e2e8f0; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; }}
    .table-header {{ background: #0f172a; }}
    tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
    #pw-overlay {{ position:fixed; inset:0; background:#0f172a; display:flex; align-items:center; justify-content:center; z-index:9999; }}
    #pw-box {{ background:#1e293b; border:1px solid #334155; border-radius:16px; padding:40px; width:320px; text-align:center; }}
    #pw-input {{ background:#0f172a; border:1px solid #475569; border-radius:8px; color:#fff; font-size:20px; text-align:center; width:100%; padding:12px; margin:16px 0; letter-spacing:6px; outline:none; }}
    #pw-input:focus {{ border-color:#22d3ee; }}
    #pw-btn {{ background:#22d3ee; color:#0f172a; font-weight:bold; border:none; border-radius:8px; width:100%; padding:12px; cursor:pointer; font-size:15px; }}
    #pw-btn:hover {{ background:#06b6d4; }}
    #pw-err {{ color:#f87171; font-size:13px; margin-top:8px; min-height:18px; }}
    @keyframes shake {{ 0%,100%{{transform:translateX(0)}} 20%,60%{{transform:translateX(-8px)}} 40%,80%{{transform:translateX(8px)}} }}
    .shake {{ animation: shake 0.4s ease; }}
    #chart-modal {{ position:fixed; inset:0; background:rgba(0,0,0,0.85); display:none; align-items:center; justify-content:center; z-index:8888; }}
    #chart-modal.open {{ display:flex; }}
    #chart-box {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:20px; max-width:920px; width:95%; position:relative; }}
    #chart-close {{ position:absolute; top:12px; right:12px; background:#334155; border:none; color:#e2e8f0; padding:5px 12px; border-radius:6px; cursor:pointer; font-size:13px; }}
    #chart-close:hover {{ background:#475569; }}
    #chart-img {{ width:100%; border-radius:8px; margin-top:8px; display:block; }}
    .ticker-link {{ cursor:pointer; text-decoration:underline; text-underline-offset:3px; }}
    .ticker-link:hover {{ opacity:0.8; }}
  </style>
</head>
<body class="min-h-screen p-4 md:p-8">

  <!-- パスワード画面 -->
  <div id="pw-overlay">
    <div id="pw-box">
      <div style="font-size:32px;margin-bottom:8px;">🔒</div>
      <div style="color:#e2e8f0;font-weight:bold;font-size:18px;">FxCompany デモ口座</div>
      <div style="color:#64748b;font-size:13px;margin-top:4px;">パスワードを入力してください</div>
      <input id="pw-input" type="password" placeholder="●●●●" maxlength="32" autofocus />
      <button id="pw-btn" onclick="checkPw()">ログイン</button>
      <div id="pw-err"></div>
    </div>
  </div>

  <!-- チャートモーダル -->
  <div id="chart-modal" onclick="if(event.target===this)closeChart()">
    <div id="chart-box">
      <button id="chart-close" onclick="closeChart()">✕ 閉じる</button>
      <img id="chart-img" src="" alt="チャート" />
    </div>
  </div>

  <!-- Header -->
  <div class="mb-8">
    <div class="flex items-center justify-between flex-wrap gap-4">
      <div>
        <h1 class="text-2xl font-bold text-white">FxCompany <span class="text-cyan-400">デモ口座</span></h1>
        <p class="text-slate-400 text-sm mt-1">セクター追いつき戦略 v2-f｜自動運用ダッシュボード</p>
      </div>
      <div class="text-right">
        <div class="text-slate-400 text-xs">最終データ更新</div>
        <div class="text-white font-mono text-sm">{last_run}</div>
        <div class="text-slate-500 text-xs mt-1">生成: {generated_at}</div>
      </div>
    </div>
  </div>

  <!-- Summary cards -->
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
    <div class="card p-5">
      <div class="text-slate-400 text-xs mb-1">資産評価額</div>
      <div class="text-white text-xl font-bold">{total_equity:,.0f}<span class="text-sm text-slate-400">円</span></div>
      <div class="text-sm mt-1" style="color:{ret_color}">{ret_sign}{ret_pct:.2f}% 初期比</div>
    </div>
    <div class="card p-5">
      <div class="text-slate-400 text-xs mb-1">含み損益</div>
      <div class="text-xl font-bold" style="color:{'#22c55e' if unrealized >= 0 else '#ef4444'}">
        {'+'if unrealized>=0 else ''}{unrealized:,.0f}<span class="text-sm text-slate-400">円</span>
      </div>
      <div class="text-slate-400 text-xs mt-1">実現: {'+' if realized_pnl>=0 else ''}{realized_pnl:,.0f}円</div>
    </div>
    <div class="card p-5">
      <div class="text-slate-400 text-xs mb-1">最大DD</div>
      <div class="text-xl font-bold {'text-emerald-400' if max_dd < 10 else 'text-yellow-400' if max_dd < 20 else 'text-red-400'}">{max_dd:.1f}%</div>
      <div class="text-slate-400 text-xs mt-1">上限: 25%（本番停止ライン）</div>
    </div>
    <div class="card p-5">
      <div class="text-slate-400 text-xs mb-1">累計トレード</div>
      <div class="text-white text-xl font-bold">{trade_count}<span class="text-sm text-slate-400">件</span></div>
      <div class="text-slate-400 text-xs mt-1">保有: {len(positions)}件 / 候補: {len(pending)}件</div>
    </div>
  </div>

  <!-- Charts -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
    <div class="card p-5 md:col-span-2">
      <h2 class="text-white font-semibold mb-4">口座額推移（万円）</h2>
      <canvas id="equityChart" height="120"></canvas>
    </div>
    <div class="card p-5">
      <h2 class="text-white font-semibold mb-4">ドローダウン（%）</h2>
      <canvas id="ddChart" height="120"></canvas>
    </div>
  </div>

  <!-- Sector Index -->
  <div class="card mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-slate-700 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-violet-400"></span>
      <h2 class="text-white font-semibold">セクター指数推移（等加重合成・直近60日）</h2>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-0">
      <div class="md:col-span-2 p-4">
        {'<img src="data:image/png;base64,' + sector_chart_b64 + '" class="w-full rounded-lg" />' if sector_chart_b64 else '<div class="text-slate-500 text-sm p-4">チャートなし（demo_signal.py を実行すると表示されます）</div>'}
      </div>
      <div class="p-4 border-l border-slate-700">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-slate-400 text-xs border-b border-slate-700">
              <th class="pb-2 text-left">業種</th>
              <th class="pb-2 text-right">5日</th>
              <th class="pb-2 text-right">20日</th>
              <th class="pb-2 text-right">60日</th>
              <th class="pb-2 text-center">↑↓</th>
            </tr>
          </thead>
          <tbody>{no_sector_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Positions -->
  <div class="card mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-slate-700 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
      <h2 class="text-white font-semibold">保有ポジション（{len(positions)}件）</h2>
      <span class="text-slate-500 text-xs ml-2">銘柄をクリックするとチャートを表示</span>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="table-header">
          <tr class="text-slate-400 text-xs">
            <th class="px-4 py-3 text-left">銘柄</th>
            <th class="px-4 py-3 text-left">業種</th>
            <th class="px-4 py-3 text-right">取得値</th>
            <th class="px-4 py-3 text-right">現在値</th>
            <th class="px-4 py-3 text-right">含み損益</th>
            <th class="px-4 py-3 text-right">保有株数</th>
            <th class="px-4 py-3 text-right">投資額</th>
            <th class="px-4 py-3 text-right">ストップ</th>
            <th class="px-4 py-3 text-right">保有日数</th>
          </tr>
        </thead>
        <tbody>{no_positions}</tbody>
      </table>
    </div>
  </div>

  <!-- Divergence Chart -->
  {'<div class="card mb-6 overflow-hidden"><div class="px-5 py-4 border-b border-slate-700 flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-yellow-400"></span><h2 class="text-white font-semibold">セクター指数 vs 保有・候補銘柄（乖離）</h2><span class="text-slate-500 text-xs ml-2">破線=個別株、実線=セクター指数、末尾の数値は乖離</span></div><div class="p-4"><img src="data:image/png;base64,' + div_chart_b64 + '" class="w-full rounded-lg" /></div></div>' if div_chart_b64 else ''}

  <!-- Pending -->
  <div class="card mb-6 overflow-hidden">
    <div class="px-5 py-4 border-b border-slate-700 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-yellow-400"></span>
      <h2 class="text-white font-semibold">明日 寄り候補（{len(pending)}件）</h2>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="table-header">
          <tr class="text-slate-400 text-xs">
            <th class="px-4 py-3 text-left">銘柄</th>
            <th class="px-4 py-3 text-left">業種</th>
            <th class="px-4 py-3 text-right">引け値</th>
            <th class="px-4 py-3 text-right">乖離</th>
            <th class="px-4 py-3 text-right">相関</th>
            <th class="px-4 py-3 text-left">分類</th>
          </tr>
        </thead>
        <tbody>{no_pending}</tbody>
      </table>
    </div>
  </div>

  <!-- Trades（全件・スクロール） -->
  <div class="card mb-8 overflow-hidden">
    <div class="px-5 py-4 border-b border-slate-700 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
      <h2 class="text-white font-semibold">決済トレード履歴（全{len(trades)}件）</h2>
      <span class="text-slate-500 text-xs ml-2">銘柄をクリックするとチャートを表示</span>
    </div>
    <div class="overflow-x-auto" style="max-height:480px; overflow-y:auto;">
      <table class="w-full text-sm">
        <thead class="table-header" style="position:sticky;top:0;z-index:1;">
          <tr class="text-slate-400 text-xs">
            <th class="px-4 py-3 text-left">銘柄</th>
            <th class="px-4 py-3 text-left">エントリー</th>
            <th class="px-4 py-3 text-left">決済日</th>
            <th class="px-4 py-3 text-right">取得値</th>
            <th class="px-4 py-3 text-right">決済値</th>
            <th class="px-4 py-3 text-right">損益</th>
            <th class="px-4 py-3 text-right">%</th>
            <th class="px-4 py-3 text-left">理由</th>
            <th class="px-4 py-3 text-right">日数</th>
          </tr>
        </thead>
        <tbody>{no_trades}</tbody>
      </table>
    </div>
  </div>

  <!-- Footer -->
  <div class="text-center text-slate-600 text-xs pb-4">
    FxCompany 調査部門（AI孫正義）｜セクター追いつき戦略 v2-f デモ運用
  </div>

  <script>
    // パスワード認証
    const PW_HASH = "{pw_hash}";
    async function sha256(msg) {{
      const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(msg));
      return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,"0")).join("");
    }}
    async function checkPw() {{
      const val = document.getElementById("pw-input").value;
      const hash = await sha256(val);
      if (hash === PW_HASH) {{
        sessionStorage.setItem("fx_auth", "1");
        document.getElementById("pw-overlay").style.display = "none";
      }} else {{
        const box = document.getElementById("pw-box");
        document.getElementById("pw-err").textContent = "パスワードが違います";
        box.classList.remove("shake"); void box.offsetWidth; box.classList.add("shake");
        document.getElementById("pw-input").value = "";
      }}
    }}
    document.getElementById("pw-input").addEventListener("keydown", e => {{ if(e.key==="Enter") checkPw(); }});
    if (sessionStorage.getItem("fx_auth") === "1") {{
      document.getElementById("pw-overlay").style.display = "none";
    }}

    // チャートモーダル
    const CHARTS = {charts_json};
    function showChart(key) {{
      const data = CHARTS[key];
      if (!data) return;
      document.getElementById("chart-img").src = "data:image/png;base64," + data;
      document.getElementById("chart-modal").classList.add("open");
    }}
    function closeChart() {{
      document.getElementById("chart-modal").classList.remove("open");
      document.getElementById("chart-img").src = "";
    }}
    document.addEventListener("keydown", e => {{ if(e.key === "Escape") closeChart(); }});

    // 口座額チャート
    const DATES  = {chart_dates};
    const EQUITY = {chart_equity};
    const DD     = {chart_dd};

    new Chart(document.getElementById('equityChart'), {{
      type: 'line',
      data: {{
        labels: DATES,
        datasets: [{{
          label: '評価額（万円）',
          data: EQUITY,
          borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.08)',
          borderWidth: 2, fill: true, tension: 0.3,
          pointRadius: EQUITY.length > 20 ? 0 : 3,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 8 }}, grid: {{ color: '#1e293b' }} }},
          y: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e293b' }} }}
        }}
      }}
    }});

    new Chart(document.getElementById('ddChart'), {{
      type: 'line',
      data: {{
        labels: DATES,
        datasets: [{{
          label: 'DD（%）',
          data: DD,
          borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.1)',
          borderWidth: 1.5, fill: true, tension: 0.3, pointRadius: 0,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 6 }}, grid: {{ color: '#1e293b' }} }},
          y: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e293b' }}, max: 0 }}
        }}
      }}
    }});
  </script>
</body>
</html>"""


def main():
    print("ダッシュボード生成中...")
    state, pnl, trades = load_data()
    html = build_html(state, pnl, trades)
    out  = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"生成完了: {out}")


if __name__ == "__main__":
    main()
