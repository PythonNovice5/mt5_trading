"""
Central configuration for the MT5 strategy bot.
Edit values here — no need to touch any other file for basic tuning.
"""

# ── PAIRS TO SCAN ──
SYMBOLS = [
    "EURUSD",
    "GBPUSD",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "USDJPY",
    "AUDCAD",
]

# ── RISK ──
FIXED_RISK_USD     = 12.50   # Fixed risk per trade in USD
MAX_OPEN_TRADES    = 3       # Maximum simultaneous open positions

# ── SPREAD FILTER ──
MAX_SPREAD_PIPS    = 20      # Skip trade if spread exceeds this

# ── RSI SETUP (1H) ──
RSI_PERIOD         = 14
RSI_OVERSOLD       = 25      # 1H RSI must be below this to activate setup
SETUP_EXPIRY_BARS  = 3       # Setup expires after this many 1H candles

# ── SWING DETECTION (5min) ──
SWING_LOOKBACK     = 3       # Candles on each side to confirm a swing high/low

# ── REWARD:RISK ──
MIN_RR             = 3.0     # Minimum RR to take the trade
TARGET_RR          = 5.0     # Primary TP target

# ── TIMEFRAMES ──
SETUP_TF           = "H1"    # Timeframe for RSI setup scan
ENTRY_TF           = "M5"    # Timeframe for entry signal

# ── CANDLE HISTORY TO FETCH ──
H1_CANDLES         = 50      # How many 1H candles to fetch per scan
M5_CANDLES         = 200     # How many 5min candles to fetch per scan

# ── LOOP ──
LOOP_INTERVAL_SEC  = 60      # Main loop sleep interval in seconds

# ── LOGGING ──
LOG_DIR            = "logs"
TRADE_LOG_FILE     = "logs/trades.log"
SIGNAL_LOG_FILE    = "logs/signals.log"
