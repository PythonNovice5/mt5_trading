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
USE_TRAILING_SL    = True    # True = trail SL up to each completed M5 candle low; False = fixed SL + TP only
TRAIL_ACTIVATE_RR  = 1.0     # Start trailing only after price reaches this R multiple (0 = trail from entry)
MIN_SL_PIPS        = 5.0     # Minimum SL distance; widen SL to this if marked candle is smaller

# ── CONSOLIDATION RECTANGLE ──
RECT_MIN_CANDLES   = 5       # Min M5 candles to form a valid rectangle
RECT_MAX_RANGE_PCT = 0.001   # Max range as % of price (0.1%)

# ── OPENING RANGE REVERSAL (NDX100) ──
US_OPEN_TIME       = "16:30"  # Broker-time of US cash open (9:30 ET). Volume-confirmed.
ORB_EXIT_TIME      = "22:55"  # Exit 5 min before US close (23:00 broker time)
ORB_RANGE_MINUTES  = 15       # Length of the opening-range candle

# ── DEPLOY / AUTO-START (AWS Windows server) ──
MT5_TERMINAL_PATH  = r"C:\Program Files\FundingPips MT5\terminal64.exe"  # adjust to your install

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
