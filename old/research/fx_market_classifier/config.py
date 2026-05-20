"""
FX Market State Classifier — Configuration
Research-grade starting parameters. Tune via IS/OOS validation before live use.
"""

PAIRS = [
    "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CHFJPY",
    "GBPUSD", "AUDUSD", "NZDUSD", "EURGBP", "EURAUD", "AUDNZD",
]

# (base_currency, quote_currency) for each pair
PAIR_CURRENCIES: dict[str, tuple[str, str]] = {
    "USDJPY": ("USD", "JPY"),
    "EURJPY": ("EUR", "JPY"),
    "GBPJPY": ("GBP", "JPY"),
    "AUDJPY": ("AUD", "JPY"),
    "NZDJPY": ("NZD", "JPY"),
    "CHFJPY": ("CHF", "JPY"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"),
    "EURGBP": ("EUR", "GBP"),
    "EURAUD": ("EUR", "AUD"),
    "AUDNZD": ("AUD", "NZD"),
}

CURRENCIES = ["USD", "JPY", "EUR", "GBP", "AUD", "NZD", "CHF"]

# Feature parameters
ACF_WINDOW = 100       # bars for rolling ACF
BB_WINDOW = 20         # bars for Bollinger Bands
ATR_WINDOW = 14        # bars for ATR

# Classification thresholds (research starting points — subject to IS validation)
STRENGTH_DIFF_THRESHOLD = 0.0008   # |base_strength − quote_strength|; ~0.08% log-return diff
ACF_TREND_MIN = 0.05               # ACF(lag=1) above this → serial correlation = trend candidate
ACF_REVERSION_MAX = -0.05          # ACF(lag=1) below this → anti-serial = reversion candidate

# Backtest defaults
BB_TREND_SIGMA = 1.0       # entry sigma for trend breakout
BB_REVERSION_SIGMA = 3.0   # entry sigma for mean-reversion touch
SPREAD_PCT = 0.02          # one-way cost in % (spread equivalent)
