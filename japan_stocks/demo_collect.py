# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 デモ環境用 日次データ収集
平日 16:00 に自動実行 → CANDIDATE_SECTORS 全銘柄のキャッシュを最新に更新

実行: python japan_stocks/demo_collect.py
登録: python japan_stocks/setup_scheduler.py demo
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
import data as dt
from jquants import JQuantsClient
from run_backtest import CANDIDATE_SECTORS

LOG_DIR  = Path(__file__).parent / "results" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "demo_collect.log"

DATA_START      = "2021-01-01"   # 十分な遡及期間（252日SMA等に使用）
MAX_STOCKS      = 20             # 業種あたり最大銘柄数
MIN_STOCKS      = 5              # 業種あたり最低銘柄数
WORKERS         = 20             # 並列取得スレッド数


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_candidate_tickers() -> dict[str, list[str]]:
    """CANDIDATE_SECTORSの銘柄コードをJ-Quantsから取得"""
    client = JQuantsClient()
    master = client.get_stock_list()
    prime  = master[master["MktNm"].str.contains("プライム", na=False)].copy()
    prime["Code"] = prime["Code"].astype(str).str.zfill(4)

    def _to_yf(code: str) -> str:
        c = str(code).zfill(5)
        return (c[:4] if c.endswith("0") else c) + ".T"

    result: dict[str, list[str]] = {}
    for (_, s33_name), group in prime.groupby(["S33", "S33Nm"]):
        if s33_name not in CANDIDATE_SECTORS:
            continue
        codes   = sorted(group["Code"].tolist())[:MAX_STOCKS]
        tickers = [_to_yf(c) for c in codes]
        result[s33_name] = tickers

    return result


def fetch_one(ticker: str) -> tuple[str, bool, str]:
    """1銘柄を差分更新。戻り値: (ticker, 成功, 最新日付)"""
    try:
        df = dt.fetch(ticker, start=DATA_START)
        if len(df) < 60:
            return ticker, False, ""
        latest = df.index[-1].strftime("%Y-%m-%d")
        return ticker, True, latest
    except Exception as e:
        return ticker, False, str(e)[:40]


def main():
    today    = datetime.today().strftime("%Y-%m-%d")
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _log("=" * 55)
    _log(f"デモ環境 日次データ収集 開始: {run_time}")
    _log("=" * 55)

    # 週末・祝日チェック（土日はスキップ）
    if datetime.today().weekday() >= 5:
        _log("本日は土日のためスキップ")
        return

    # 銘柄リスト取得
    _log("J-Quants から銘柄マスター取得中...")
    try:
        sector_tickers = get_candidate_tickers()
    except Exception as e:
        _log(f"ERROR: 銘柄取得失敗 → {e}")
        sys.exit(1)

    all_tickers: list[str] = []
    for sector, tickers in sector_tickers.items():
        _log(f"  {sector}: {len(tickers)}銘柄")
        all_tickers.extend(tickers)
    all_tickers = list(set(all_tickers))
    _log(f"  合計: {len(all_tickers)}銘柄")

    # 並列で差分取得
    _log(f"\n株価データ更新中（{WORKERS}並列）...")
    ok_count   = 0
    ng_count   = 0
    latest_dates: list[str] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_one, t): t for t in all_tickers}
        done = 0
        for f in as_completed(futures):
            ticker, success, info = f.result()
            done += 1
            if success:
                ok_count += 1
                latest_dates.append(info)
            else:
                ng_count += 1
            if done % 30 == 0 or done == len(all_tickers):
                print(f"  {done}/{len(all_tickers)} 完了（成功:{ok_count} 失敗:{ng_count}）",
                      end="\r")

    print()

    # 結果サマリー
    newest = max(latest_dates) if latest_dates else "不明"
    _log(f"\n── 完了サマリー ──────────────────────────")
    _log(f"  成功: {ok_count}銘柄 / 失敗: {ng_count}銘柄")
    _log(f"  キャッシュ最新日: {newest}")

    # 業種別件数確認
    _log(f"\n── 業種別内訳 ────────────────────────────")
    for sector, tickers in sorted(sector_tickers.items()):
        valid = 0
        for t in tickers:
            try:
                df = dt.fetch(t, start=DATA_START)
                if len(df) >= 60:
                    valid += 1
            except Exception:
                pass
        status = "✓" if valid >= MIN_STOCKS else "✗ 不足"
        _log(f"  {sector:<14} {valid}/{len(tickers)}銘柄  {status}")

    _log(f"\nデータ収集完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log("=" * 55 + "\n")


if __name__ == "__main__":
    main()
