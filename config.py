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
RSI_OVERSOLD       = 20      # 1H RSI must drop below this to activate setup
RSI_SETUP_EXIT     = 30      # (live bot only)
SETUP_WINDOW_BARS  = 6       # H1 bars to watch for inside bar after RSI trigger
SETUP_EXPIRY_BARS  = 3       # (live bot only)

# ── SWING DETECTION (5min) ──
SWING_LOOKBACK     = 3       # Candles on each side to confirm a swing high/low

# ── REWARD:RISK ──
MIN_RR             = 3.0     # Minimum RR to take the trade
TARGET_RR          = 5.0     # Primary TP target

# ── EXIT MANAGEMENT ──
USE_TRAILING_SL    = True    # True = trail SL on M5 swing lows; False = fixed SL + TP only

# ── CONSOLIDATION RECTANGLE ──
RECT_MIN_CANDLES   = 5       # Min M5 candles to form a valid rectangle
RECT_MAX_RANGE_PCT = 0.001   # Max range as % of price (0.1%)

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
