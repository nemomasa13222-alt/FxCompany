# fx_mt4/config.py  ─ MT4デモ取引設定
from pathlib import Path

# ── MT4ファイルパス ──────────────────────────────────────────────────────────
# MT4の「データフォルダ」→ MQL4\Files\FxDemo\ を指す
# MT4メニュー: ファイル → データフォルダを開く → MQL4\Files\
# ここを環境に合わせて変更してください
MT4_FILES = Path(r"C:\Users\MAI\AppData\Roaming\MetaQuotes\Terminal\082F53F5881F3D6022DF806C3D307B50\MQL4\Files\FxDemo")

DATA_DIR   = MT4_FILES / "data"
SIGNAL_FILE= MT4_FILES / "signal" / "signal.json"
STATUS_FILE= MT4_FILES / "status" / "status.json"
READY_FLAG = MT4_FILES / "signal" / "data_ready.txt"
LOG_FILE   = MT4_FILES / "logs"   / "python.log"

# ── 戦略パラメータ（30分足ベスト）────────────────────────────────────────────
PAIR         = "USDJPY"
TIMEFRAME    = "30min"
RANGE_BARS   = 6      # レンジ判定バー数（6本=180分）
RANGE_PIPS   = 15     # レンジ幅上限（pips）
MIN_HOLD     = 3      # 最低保有バー数（3本=90分）
STRENGTH_WIN = 20     # 強弱スコアウィンドウ（20本=10時間）
PIP          = 0.01   # USDJPY 1pip

# ── 資金・ロット ──────────────────────────────────────────────────────────────
INITIAL_CAPITAL = 1_000_000  # デモ初期資金（円）
LOT_SIZE        = 0.1       # 固定ロット（1万通貨）
SPREAD_PIPS     = 0.2       # DMMFXスプレッド想定（記録用）

# ── コスト ────────────────────────────────────────────────────────────────────
ENTRY_COST_PIPS = 0.2   # エントリーコスト

# ── 12ペア（強弱計算用）─────────────────────────────────────────────────────
PAIRS = [
    "USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
    "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD",
]
