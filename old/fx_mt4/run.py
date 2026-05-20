"""
fx_mt4/run.py  ─ メインランナー
Windows タスクスケジューラで30分ごとに実行する

実行: python -m fx_mt4.run
"""
import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from fx_mt4.engine import (
    log, load_all_pairs,
    generate_signal, get_position, has_position,
    should_exit, write_signal, write_close_signal,
    signal_pending, get_status,
)
from fx_mt4.config import READY_FLAG
from fx_mt4.dashboard import main as update_dashboard


def main():
    log("=" * 50)
    log("FxDemo ランナー起動")

    # MT4からのデータ準備確認
    if not READY_FLAG.exists():
        log("data_ready.txt がない → MT4 EA が未起動の可能性")
        log("処理スキップ（EAを起動してください）")
        return

    # データ読み込み
    dfs = load_all_pairs()
    if not dfs:
        log("ERROR: データなし → 終了")
        return

    # 未処理シグナルが残っていれば待機
    if signal_pending():
        log("未処理シグナルあり → 今回はスキップ（EAの処理待ち）")
        return

    # ── ポジションあり → エグジット判定 ──────────────────────────────────────
    if has_position():
        pos = get_position()
        log(f"保有中: {pos.get('type')} {pos.get('open_price')} "
            f"含み益{pos.get('profit',0):.0f}")

        if should_exit(dfs, pos):
            write_close_signal()
            log("→ クローズシグナル発行")
        else:
            log("→ 保有継続")
        return

    # ── ポジションなし → エントリーシグナル判定 ───────────────────────────────
    sig = generate_signal(dfs)

    if sig["action"] in ("BUY", "SELL"):
        write_signal(sig)
        log(f"→ エントリーシグナル発行: {sig['action']}")
    else:
        log("→ シグナルなし")

    # ダッシュボード更新 & Git push
    try:
        update_dashboard()
        _git_push()
    except Exception as e:
        log(f"ダッシュボード更新エラー: {e}")

    log("処理完了")
    log("=" * 50)


def _git_push():
    import subprocess
    root = Path(__file__).parent.parent
    result = subprocess.run(
        ["git", "add", "docs/fx_demo/index.html"],
        cwd=root, capture_output=True, text=True
    )
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=root, capture_output=True
    )
    if result.returncode == 0:
        return  # 変更なし
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    subprocess.run(
        ["git", "commit", "-m", f"fx_demo: {ts} 自動更新 [skip ci]"],
        cwd=root, capture_output=True, text=True
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=root, capture_output=True, text=True
    )
    log("GitHub Pages 更新完了")


if __name__ == "__main__":
    main()
