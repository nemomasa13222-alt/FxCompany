# -*- coding: utf-8 -*-
"""
日次引き継ぎ書 自動生成スクリプト
毎日 23:50 にタスクスケジューラから実行

処理:
  1. 当日のFX・株デモ実績を読み込む
  2. 前日の引き継ぎ書を参照
  3. 今日の引き継ぎ書（YYYY-MM-DD.md）を生成
  4. git commit & push
"""
import sys, json, subprocess
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd

REPO      = Path(__file__).parent.parent
HANDOVER  = Path(__file__).parent
TODAY     = date.today()
TODAY_STR = TODAY.strftime("%Y-%m-%d")
OUT_FILE  = HANDOVER / f"{TODAY_STR}.md"

# ── 既に今日分が存在したらスキップ ────────────────────────────────
if OUT_FILE.exists():
    print(f"本日分 ({TODAY_STR}) は既に存在します。スキップ。")
    sys.exit(0)

# ── FX MT4 データ読み込み ──────────────────────────────────────────
fx_trades_file = REPO / "fx_mt4" / "trades" / "trades.csv"
fx_status_file = REPO / "fx_mt4" / "trades" / "trades.csv"  # MT4 Files は別パス

MT4_TRADES = Path(
    r"C:\Users\MAI\AppData\Roaming\MetaQuotes\Terminal"
    r"\082F53F5881F3D6022DF806C3D307B50\MQL4\Files\FxDemo\trades\trades.csv"
)

def load_fx():
    f = MT4_TRADES if MT4_TRADES.exists() else fx_trades_file
    if not f.exists():
        return pd.DataFrame(), {}
    df = pd.read_csv(f, dtype=str)
    for col in ["profit_yen", "pips", "lots"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["open_time", "close_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # 今日決済分
    today_df = df[df["close_time"].dt.date == TODAY] if "close_time" in df.columns else pd.DataFrame()

    pnl = df["profit_yen"].dropna() if "profit_yen" in df.columns else pd.Series(dtype=float)
    wins = int((pnl > 0).sum()) if len(pnl) else 0
    n    = len(pnl)
    cum_pnl = int(pnl.sum()) if len(pnl) else 0
    balance = 1_000_000 + cum_pnl

    return today_df, {
        "n_total":  n,
        "n_wins":   wins,
        "win_rate": round(wins / n * 100, 1) if n > 0 else 0,
        "cum_pnl":  cum_pnl,
        "balance":  balance,
    }

# ── 株デモ データ読み込み ──────────────────────────────────────────
def load_stock():
    state_file  = REPO / "japan_stocks" / "results" / "demo" / "state.json"
    trades_file = REPO / "japan_stocks" / "results" / "demo" / "trades.csv"

    state = {}
    if state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

    trades_today = pd.DataFrame()
    if trades_file.exists():
        df = pd.read_csv(trades_file, encoding="utf-8")
        df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
        trades_today = df[df["exit_date"].dt.date == TODAY]

    cap    = state.get("capital", 1_000_000)
    peak   = state.get("peak_capital", 1_000_000)
    real   = state.get("total_realized_pnl", 0)
    n_pos  = len(state.get("positions", []))
    n_pend = len(state.get("pending", []))

    return trades_today, {
        "capital":     int(cap),
        "realized":    int(real),
        "n_positions": n_pos,
        "n_pending":   n_pend,
        "return_pct":  round((cap - 1_000_000) / 1_000_000 * 100, 2),
        "last_run":    state.get("last_run", "不明"),
    }

# ── 前日の引き継ぎ書を読む ─────────────────────────────────────────
def load_prev_handover():
    for i in range(1, 8):
        prev_date = TODAY - timedelta(days=i)
        prev_file = HANDOVER / f"{prev_date.strftime('%Y-%m-%d')}.md"
        if prev_file.exists():
            return prev_date.strftime("%Y-%m-%d"), prev_file.read_text(encoding="utf-8")
    return None, None

# ── 引き継ぎ書生成 ────────────────────────────────────────────────
fx_today, fx_stats     = load_fx()
st_today, stock_stats  = load_stock()
prev_date, prev_text   = load_prev_handover()

# 今日のトレード内容
def fmt_trades(df, pnl_col="profit_yen", type_col="type"):
    if df.empty:
        return "- なし"
    lines = []
    for _, r in df.iterrows():
        pnl = r.get(pnl_col, 0) or 0
        sign = "+" if pnl >= 0 else ""
        t = r.get(type_col, "")
        lines.append(f"- {t}  {sign}{int(pnl):,}円")
    return "\n".join(lines)

fx_today_str  = fmt_trades(fx_today,  pnl_col="profit_yen", type_col="type")
st_today_str  = fmt_trades(st_today,  pnl_col="pnl_jpy",    type_col="exit_reason")

nothing_fx    = fx_today.empty
nothing_stock = st_today.empty
nothing_today = nothing_fx and nothing_stock

content = f"""# 引き継ぎ書  {TODAY_STR}

{'> 📋 本日は特段の動きなし。前日分（' + prev_date + '）の内容が継続' if nothing_today else ''}

---

## 今日の動き

### FX MT4 デモ（USDJPY 30分 レンジブレイク）
{fx_today_str}

### 株デモ（セクター追いつき戦略）
{st_today_str}

---

## 稼働中システム

| システム | 状態 | 備考 |
|---------|------|------|
| 株デモ GitHub Actions | ✅ 稼働中（平日 JST 20:00） | demo_automation.yml |
| FX MT4 EA v2.00 | ✅ 稼働中（要 MT4 確認） | XMTrading Demo #37147509 |
| FX push_trades タスク | ✅ 稼働中（30分ごと） | FxDemo_MT4_Push |
| GitHub Pages | ✅ 稼働中 | nemomasa13222-alt.github.io/FxCompany/ |

---

## 重要な数字（最新）

### FX MT4 デモ
- 残高: **{fx_stats['balance']:,}円** / 累積損益: {fx_stats['cum_pnl']:+,}円
- 件数: {fx_stats['n_total']}件 / 勝率: {fx_stats['win_rate']}%

### 株デモ
- 資産: **{stock_stats['capital']:,}円**（{stock_stats['return_pct']:+.2f}%）/ 実現損益: {stock_stats['realized']:+,}円
- 保有: {stock_stats['n_positions']}件 / pending: {stock_stats['n_pending']}件
- 最終実行: {stock_stats['last_run']}

---

## 未解決・継続タスク

- [ ] MT4 Strategy Tester でバックテスト実施（優先度: 中）
- [ ] cache/ フォルダ（20GB）整理（優先度: 低）

---

## 前日からの引き継ぎ

前日分: `{prev_date or 'なし'}` を参照

---
*自動生成: make_handover.py  {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

OUT_FILE.write_text(content, encoding="utf-8")
print(f"引き継ぎ書作成: {OUT_FILE}")

# ── git push ──────────────────────────────────────────────────────
try:
    subprocess.run(["git", "add", str(OUT_FILE)], cwd=REPO, check=True)
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=REPO)
    if diff.returncode != 0:
        subprocess.run(["git", "commit", "-m",
                        f"handover: {TODAY_STR} 日次引き継ぎ書 [skip ci]"],
                       cwd=REPO, check=True)
        subprocess.run(["git", "pull", "--rebase"], cwd=REPO)
        subprocess.run(["git", "push"], cwd=REPO, check=True)
        print("push 完了")
except subprocess.CalledProcessError as e:
    print(f"git エラー: {e}")
