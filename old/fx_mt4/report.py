"""
fx_mt4/report.py  ─ デモトレード損益レポート生成

出力:
  FxDemo/trades/trades.csv      → トレード履歴（EAが書き出し）
  FxDemo/reports/report_YYYYMMDD.md  → 日次レポート（Python生成）
  FxDemo/reports/pnl_history.csv     → 損益推移（累積）

実行: python -m fx_mt4.report
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from datetime import datetime, date
from fx_mt4.config import MT4_FILES, INITIAL_CAPITAL, LOT_SIZE

TRADES_CSV  = MT4_FILES / "trades" / "trades.csv"
REPORTS_DIR = MT4_FILES / "reports"
PNL_CSV     = REPORTS_DIR / "pnl_history.csv"
STATUS_FILE = MT4_FILES / "status" / "status.json"

PIP_VAL_JPY = 667   # 10倍レバ 6.7万通貨 1pip=667円（参考）


def load_trades() -> pd.DataFrame:
    if not TRADES_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRADES_CSV, parse_dates=["close_time", "open_time"])
    return df.sort_values("close_time").reset_index(drop=True)


def load_status() -> dict:
    import json
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except:
        return {}


def calc_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    p   = df["profit"].values
    pip = df["pips"].values
    w   = p[p > 0]; l = p[p <= 0]
    n   = len(p)
    wr  = len(w) / n * 100
    pf  = w.sum() / abs(l.sum()) if len(l) > 0 and l.sum() != 0 else 0
    eq  = np.cumsum(p)
    pk  = np.maximum.accumulate(np.maximum(eq, 0))
    mdd = (eq - pk).min()
    return dict(
        n=n, wr=wr, pf=pf,
        total_profit=p.sum(),
        avg_profit=p.mean(),
        avg_win=w.mean()  if len(w) else 0,
        avg_loss=l.mean() if len(l) else 0,
        avg_pips=pip.mean(),
        total_pips=pip.sum(),
        max_dd=mdd,
        avg_hold=df["hold_hours"].mean(),
    )


def build_report(df: pd.DataFrame, status: dict) -> str:
    today = date.today()
    lines = []
    L = lines.append

    L(f"# FxDemo デモトレード損益レポート")
    L(f"  作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L(f"  戦略: USDJPY 30分足 レンジブレイク")
    L(f"  初期資金: {INITIAL_CAPITAL:,}円  ロット: {LOT_SIZE}")
    L("")

    # 現在のポジション
    pos_list = status.get("positions", [])
    bal  = status.get("balance", 0)
    eq   = status.get("equity", 0)
    L("## 現在の状況")
    L(f"  残高    : {bal:,.0f}円")
    L(f"  有効証拠金: {eq:,.0f}円")
    if pos_list:
        pos = pos_list[0]
        unreal = pos.get("profit", 0)
        L(f"  保有中  : {pos.get('type')} {pos.get('open_price')}  含み益: {unreal:+,.0f}円")
    else:
        L(f"  ポジション: なし")
    L("")

    if df.empty:
        L("## トレード履歴")
        L("  まだ決済済みトレードはありません。")
        return "\n".join(lines)

    # 全期間
    m = calc_metrics(df)
    L("## 全期間 集計")
    L(f"  トレード数  : {m['n']}件")
    L(f"  勝率        : {m['wr']:.1f}%")
    L(f"  PF          : {m['pf']:.2f}")
    L(f"  総損益      : {m['total_profit']:+,.0f}円")
    L(f"  総pips      : {m['total_pips']:+.1f}pips")
    L(f"  平均勝ち    : {m['avg_win']:+,.0f}円")
    L(f"  平均負け    : {m['avg_loss']:+,.0f}円")
    L(f"  最大DD      : {m['max_dd']:+,.0f}円")
    L(f"  平均保有    : {m['avg_hold']:.1f}時間")
    L("")

    # 週次
    df2 = df.copy()
    df2["week"] = df2["close_time"].dt.to_period("W")
    weekly = df2.groupby("week").agg(
        n=("profit","count"),
        profit=("profit","sum"),
        pips=("pips","sum"),
        wr=("profit", lambda x: (x>0).mean()*100)
    )
    L("## 週次損益")
    L(f"  {'週':^12} | {'件数':>4} | {'勝率':>6} | {'損益(円)':>10} | {'pips':>8}")
    L("  " + "-"*50)
    for wk, row in weekly.iterrows():
        L(f"  {str(wk):^12} | {int(row.n):>4} | {row.wr:>6.1f}% | {row.profit:>+10,.0f} | {row.pips:>+8.1f}")
    L("")

    # 月次
    df2["month"] = df2["close_time"].dt.to_period("M")
    monthly = df2.groupby("month").agg(
        n=("profit","count"),
        profit=("profit","sum"),
        pips=("pips","sum"),
    )
    L("## 月次損益")
    for mo, row in monthly.iterrows():
        bar = "#" * min(int(abs(row.profit)/1000), 20)
        sign = "+" if row.profit >= 0 else "-"
        L(f"  {mo}  {sign}{abs(row.profit):>8,.0f}円  {bar}")
    L("")

    # 直近10件
    L("## 直近10件のトレード")
    L(f"  {'決済日時':^18} | {'種別':>4} | {'pips':>7} | {'損益(円)':>10} | {'保有':>6}")
    L("  " + "-"*58)
    for _, row in df.tail(10).iterrows():
        dt = row["close_time"].strftime("%m/%d %H:%M") if pd.notna(row["close_time"]) else "-"
        L(f"  {dt:^18} | {row['type']:>4} | {row['pips']:>+7.1f} | {row['profit']:>+10,.0f} | {row['hold_hours']:>5.1f}h")
    L("")

    # 累積損益
    df2["cumulative"] = df2["profit"].cumsum()
    L("## 累積損益推移（直近20件）")
    for _, row in df.tail(20).iterrows():
        idx = df.index[df["close_time"] == row["close_time"]].tolist()
        cum = df["profit"].iloc[:idx[0]+1].sum() if idx else 0
        bar_len = int(abs(cum) / 1000)
        bar = ("+" if cum >= 0 else "-") * min(bar_len, 25)
        L(f"  {row['close_time'].strftime('%m/%d'):^6}  {cum:>+9,.0f}円  {bar}")

    return "\n".join(lines)


def save_pnl_history(df: pd.DataFrame):
    """損益推移CSVを更新"""
    if df.empty:
        return
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    df2 = df[["close_time","type","pips","profit"]].copy()
    df2["cumulative_profit"] = df2["profit"].cumsum()
    df2["cumulative_pips"]   = df2["pips"].cumsum()
    df2.to_csv(PNL_CSV, index=False, encoding="utf-8-sig")
    print(f"  損益推移CSV保存: {PNL_CSV}")


def main():
    print("=" * 50)
    print("  FxDemo レポート生成")
    print("=" * 50)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    df     = load_trades()
    status = load_status()

    print(f"  トレード件数: {len(df)}件")
    if not df.empty:
        print(f"  期間: {df['close_time'].min()} 〜 {df['close_time'].max()}")
        print(f"  総損益: {df['profit'].sum():+,.0f}円")

    report = build_report(df, status)

    # レポート保存
    out = REPORTS_DIR / f"report_{date.today():%Y%m%d}.md"
    out.write_text(report, encoding="utf-8")
    print(f"\n  レポート保存: {out}")

    # 損益推移CSV
    save_pnl_history(df)

    print("\n" + report)
    print("=" * 50)


if __name__ == "__main__":
    main()
