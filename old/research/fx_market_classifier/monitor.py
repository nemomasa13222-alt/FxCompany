"""
Real-time FX Market State Monitor
----------------------------------
5分足の最新バーに基づき、通貨強弱・ACF・推奨戦略をターミナルに表示。
デフォルトは300秒ごとに自動更新（5分バー確定に合わせる）。

Usage:
    python -m fx_market_classifier.monitor            # 300秒ごと自動更新
    python -m fx_market_classifier.monitor --once     # 1回だけ表示して終了
    python -m fx_market_classifier.monitor --interval 60  # 60秒ごと更新
"""
from __future__ import annotations

import argparse
import math
import time
from datetime import datetime, timezone

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .classifier import MarketClassifier, MarketState
from .config import (
    ACF_REVERSION_MAX,
    ACF_TREND_MIN,
    PAIR_CURRENCIES,
    STRENGTH_DIFF_THRESHOLD,
)
from .data_fetcher import fetch_ohlcv

# ASCII-safe console（Windows cp932環境対応）
console = Console(legacy_windows=False, highlight=False)

# ── スタイル定義（ASCII記号のみ使用） ────────────────────────────────────────

_STATE_STYLE = {
    MarketState.TREND:          "bold bright_blue",
    MarketState.MEAN_REVERSION: "bold bright_yellow",
    MarketState.NO_TRADE:       "dim white",
}
_STATE_LABEL = {
    MarketState.TREND:          "[TREND]",
    MarketState.MEAN_REVERSION: "[MEAN_REV]",
    MarketState.NO_TRADE:       "[  ---  ]",
}


# ── 棒グラフ（ASCII） ─────────────────────────────────────────────────────────

def _bar(value: float, scale: float, width: int = 12) -> Text:
    """符号付き棒グラフ（#=正 / -=負）"""
    if scale == 0:
        return Text(" " * width)
    ratio = max(-1.0, min(1.0, value / scale))
    filled = int(abs(ratio) * width)
    char = "#" if ratio >= 0 else "-"
    bar_str = char * filled + " " * (width - filled)
    return Text(bar_str, style="green" if value >= 0 else "red")


# ── 通貨強弱テーブル ──────────────────────────────────────────────────────────

def build_strength_table(clf: MarketClassifier) -> Table:
    latest = clf.strength.iloc[-1].sort_values(ascending=False)
    scale  = max(abs(latest.values)) if len(latest) > 0 else 1e-4

    tbl = Table(
        title="[bold white]通貨強弱ランキング[/bold white]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
        expand=False,
    )
    tbl.add_column("順位", justify="right", style="dim", width=5)
    tbl.add_column("通貨", justify="center", width=8)
    tbl.add_column("強弱値", justify="right", width=12)
    tbl.add_column("", justify="left", width=15)  # bar

    for rank, (ccy, val) in enumerate(latest.items(), 1):
        style = "green" if val >= 0 else "red"
        tbl.add_row(
            str(rank),
            Text(ccy, style=f"bold {style}"),
            Text(f"{val:+.6f}", style=style),
            _bar(val, scale),
        )
    return tbl


# ── ペア分類テーブル ──────────────────────────────────────────────────────────

def _acf_tag(acf: float) -> str:
    if math.isnan(acf):
        return "  N/A  "
    if acf >= ACF_TREND_MIN:
        return f"{acf:+.3f} (+)"   # トレンド方向
    if acf <= ACF_REVERSION_MAX:
        return f"{acf:+.3f} (-)"   # 平均回帰方向
    return f"{acf:+.3f} ( )"      # 中立


def _direction_text(state: MarketState, diff: float) -> Text:
    if state == MarketState.TREND:
        if diff > 0:
            return Text("Long  > 順張り Buy  ", style="bold green")
        else:
            return Text("Short > 順張り Sell ", style="bold red")
    if state == MarketState.MEAN_REVERSION:
        return Text("Fade  > 逆張りエントリ", style="bold bright_yellow")
    return Text("---   > 待機", style="dim")


def build_pair_table(clf: MarketClassifier) -> Table:
    current    = clf.current_state()
    latest_str = clf.strength.iloc[-1]

    tbl = Table(
        title="[bold white]ペア分類 -- 現在の推奨戦略[/bold white]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    tbl.add_column("ペア",       width=9,  justify="center")
    tbl.add_column("強弱差",     width=13, justify="right")
    tbl.add_column("ACF(lag1)", width=14, justify="right")
    tbl.add_column("状態",       width=12, justify="center")
    tbl.add_column("推奨アクション",        width=24, justify="left")

    # 状態順にソート: TREND → MEAN_REV → NO_TRADE
    _order = {MarketState.TREND: 0, MarketState.MEAN_REVERSION: 1, MarketState.NO_TRADE: 2}
    sorted_pairs = sorted(current.keys(), key=lambda p: (_order.get(current[p], 9), p))

    for pair in sorted_pairs:
        state      = current[pair]
        base_ccy, quote_ccy = PAIR_CURRENCIES[pair]

        base_s  = float(latest_str.get(base_ccy,  0.0))
        quote_s = float(latest_str.get(quote_ccy, 0.0))
        diff    = base_s - quote_s

        acf_val = float(clf.acf[pair].iloc[-1]) if not clf.acf[pair].empty else float("nan")

        style      = _STATE_STYLE.get(state, "dim")
        state_text = Text(_STATE_LABEL.get(state, "?"), style=style)

        diff_label = f"{base_ccy}>{quote_ccy}" if diff > 0 else f"{quote_ccy}>{base_ccy}"
        diff_style = "green" if diff > 0 else "red"

        acf_str   = _acf_tag(acf_val)
        acf_style = (
            "bright_blue"   if (not math.isnan(acf_val) and acf_val > 0)
            else "bright_yellow" if (not math.isnan(acf_val) and acf_val < 0)
            else "dim"
        )

        tbl.add_row(
            Text(pair, style="bold white"),
            Text(f"{diff:+.5f} {diff_label}", style=diff_style),
            Text(acf_str, style=acf_style),
            state_text,
            _direction_text(state, diff),
        )

    return tbl


# ── 判定基準パネル ────────────────────────────────────────────────────────────

def build_legend() -> Panel:
    body = (
        f"[bold white]判定ルール[/bold white]\n"
        f"  [bright_blue][TREND]   [/bright_blue]"
        f"| |強弱差| >= {STRENGTH_DIFF_THRESHOLD:.4f}  AND  ACF >= {ACF_TREND_MIN:+.2f}  => 順張り\n"
        f"  [bright_yellow][MEAN_REV][/bright_yellow]"
        f"| |強弱差| >= {STRENGTH_DIFF_THRESHOLD:.4f}  AND  ACF <= {ACF_REVERSION_MAX:+.2f}  => 逆張り\n"
        f"  [dim][  ---  ] [/dim]"
        f"| |強弱差| <  {STRENGTH_DIFF_THRESHOLD:.4f} or ACF中立          => 待機\n\n"
        f"  [dim]強弱値 = 各通貨が絡む全ペアの対数リターン符号付き平均\n"
        f"  ACF    = 直近100本の log-return 1階自己相関係数\n"
        f"  (+) = ACF正 = 系列相関あり（トレンド性）\n"
        f"  (-) = ACF負 = 反転傾向（平均回帰性）[/dim]"
    )
    return Panel(body, box=box.ASCII, expand=True, border_style="dim white")


# ── サマリー ──────────────────────────────────────────────────────────────────

def build_summary(current: dict) -> str:
    t = sum(1 for v in current.values() if v == MarketState.TREND)
    m = sum(1 for v in current.values() if v == MarketState.MEAN_REVERSION)
    n = sum(1 for v in current.values() if v == MarketState.NO_TRADE)
    return (
        f"  [bold bright_blue][TREND] {t}ペア[/]   "
        f"[bold bright_yellow][MEAN_REV] {m}ペア[/]   "
        f"[dim][---] {n}ペア[/]"
    )


# ── 画面描画 ──────────────────────────────────────────────────────────────────

def snapshot(clf: MarketClassifier, next_refresh_sec: int | None = None) -> None:
    console.clear()

    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S  UTC")
    next_str = f"  -- 次の更新まで {next_refresh_sec}秒" if next_refresh_sec else ""

    console.rule(
        f"[bold white]FX Market State Monitor[/bold white]  "
        f"[dim]{now_str}{next_str}[/dim]",
        characters="=",
    )
    console.print()

    console.print(
        Columns(
            [build_strength_table(clf), build_legend()],
            equal=False,
            expand=True,
        )
    )
    console.print()

    console.print(build_pair_table(clf))
    console.print()

    current = clf.current_state()
    console.print(build_summary(current))
    console.print()


# ── データ取得 + 分類 ──────────────────────────────────────────────────────────

def fetch_and_classify(lookback_days: int = 7) -> MarketClassifier:
    price_data = fetch_ohlcv(lookback_days=lookback_days)
    if not price_data:
        raise RuntimeError("データ取得失敗。ネット接続を確認してください。")
    return MarketClassifier(price_data)


# ── エントリーポイント ─────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="FX Market State Monitor (real-time)")
    parser.add_argument("--interval", type=int, default=300,
                        help="更新間隔（秒）。デフォルト300秒（5分バー）")
    parser.add_argument("--once", action="store_true",
                        help="1回だけ表示して終了")
    parser.add_argument("--lookback", type=int, default=7,
                        help="データ取得日数。デフォルト7日")
    args = parser.parse_args(argv)

    console.print("[dim]データ取得中...[/dim]")
    clf = fetch_and_classify(args.lookback)
    snapshot(clf, next_refresh_sec=None if args.once else args.interval)

    if args.once:
        return

    try:
        while True:
            for remaining in range(args.interval, 0, -1):
                time.sleep(1)
                if remaining % 60 == 0 or remaining <= 10:
                    console.print(
                        f"\r[dim]  次の更新まで {remaining}秒...[/dim]",
                        end="",
                    )

            console.print("\n[dim]データ更新中...[/dim]")
            clf = fetch_and_classify(args.lookback)
            snapshot(clf, next_refresh_sec=args.interval)

    except KeyboardInterrupt:
        console.print("\n[dim]モニター終了[/dim]")


if __name__ == "__main__":
    main()
