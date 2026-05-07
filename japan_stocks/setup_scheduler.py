# -*- coding: utf-8 -*-
"""
Windowsタスクスケジューラ 設定スクリプト

タスク一覧:
  screening  平日 16:00  run_daily.py      ミネルヴィニスクリーニング
  demo       平日 16:00  demo_collect.py   デモ環境用データ収集（セクター追いつき）

実行例:
  python japan_stocks/setup_scheduler.py              # screening タスク登録
  python japan_stocks/setup_scheduler.py demo         # demo タスク登録
  python japan_stocks/setup_scheduler.py status       # 全タスク状態確認
  python japan_stocks/setup_scheduler.py remove       # screening タスク削除
  python japan_stocks/setup_scheduler.py remove demo  # demo タスク削除
"""

import subprocess
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PYTHON   = sys.executable
WORK_DIR = Path(__file__).parent.parent
LOG_DIR  = Path(__file__).parent / "results" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── タスク定義 ────────────────────────────────────────────────────────────────
TASKS = {
    "screening": {
        "task_name":  "FxCompany_DailyScreening",
        "script":     Path(__file__).parent / "run_daily.py",
        "bat":        Path(__file__).parent / "_run_daily.bat",
        "log":        LOG_DIR / "daily_screening.log",
        "time":       "16:00",
        "label":      "ミネルヴィニ スクリーニング",
    },
    "demo": {
        "task_name":  "FxCompany_DemoCollect",
        "script":     Path(__file__).parent / "demo_collect.py",
        "bat":        Path(__file__).parent / "_run_demo_collect.bat",
        "log":        LOG_DIR / "demo_collect.log",
        "time":       "16:00",
        "label":      "デモ環境 データ収集（セクター追いつき）",
    },
    "demo_signal": {
        "task_name":  "FxCompany_DemoSignal",
        "script":     Path(__file__).parent / "demo_signal.py",
        "bat":        Path(__file__).parent / "_run_demo_signal.bat",
        "log":        LOG_DIR / "demo_signal.log",
        "time":       "16:10",
        "label":      "デモ環境 シグナル生成・架空執行（セクター追いつき）",
    },
}


def _make_bat(cfg: dict):
    """ラップバッチファイルを生成"""
    content = (
        f'@echo off\n'
        f'chcp 65001 > nul\n'
        f'set PYTHONIOENCODING=utf-8\n'
        f'cd /d "{WORK_DIR}"\n'
        f'echo [%%date%% %%time%%] 開始 >> "{cfg["log"]}"\n'
        f'"{PYTHON}" "{cfg["script"]}" >> "{cfg["log"]}" 2>&1\n'
        f'echo [%%date%% %%time%%] 完了 >> "{cfg["log"]}"\n'
    )
    cfg["bat"].write_text(content, encoding="utf-8")
    print(f"  バッチ作成: {cfg['bat'].name}")


def register(task_key: str = "screening"):
    cfg = TASKS[task_key]
    _make_bat(cfg)

    cmd = [
        "schtasks", "/create",
        "/tn",  cfg["task_name"],
        "/tr",  str(cfg["bat"]),
        "/sc",  "WEEKLY",
        "/d",   "MON,TUE,WED,THU,FRI",
        "/st",  cfg["time"],
        "/f",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    if result.returncode == 0:
        print(f"\n✓ タスク登録完了: {cfg['task_name']}")
        print(f"  内容      : {cfg['label']}")
        print(f"  スケジュール: 平日（月〜金） {cfg['time']}")
        print(f"  スクリプト: {cfg['script']}")
        print(f"  ログ      : {cfg['log']}")
    else:
        print(f"\n✗ タスク登録失敗:")
        print(result.stderr)
        print("\n手動登録の手順:")
        print("  1. タスクスケジューラを開く（検索: 'タスクスケジューラ'）")
        print("  2. 「基本タスクの作成」をクリック")
        print(f"  3. 名前: {cfg['task_name']}")
        print(f"  4. トリガー: 毎週 月〜金 {cfg['time']}")
        print(f"  5. 操作: プログラムの開始 → {cfg['bat']}")


def remove(task_key: str = "screening"):
    cfg = TASKS[task_key]
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", cfg["task_name"], "/f"],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode == 0:
        print(f"✓ タスク削除完了: {cfg['task_name']}")
    else:
        print(f"✗ タスク削除失敗: {result.stderr}")


def status():
    for key, cfg in TASKS.items():
        print(f"\n── {key}: {cfg['label']} ──")
        result = subprocess.run(
            ["schtasks", "/query", "/tn", cfg["task_name"], "/fo", "LIST"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"  未登録")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        register("screening")
    elif args[0] in TASKS:
        register(args[0])
    elif args[0] == "status":
        status()
    elif args[0] == "remove":
        key = args[1] if len(args) > 1 else "screening"
        remove(key)
    elif args[0] == "all":
        for key in TASKS:
            register(key)
    else:
        print(f"不明なコマンド: {args[0]}")
        print(f"使い方: python setup_scheduler.py [{'|'.join(TASKS)}|all|status|remove [key]]")
