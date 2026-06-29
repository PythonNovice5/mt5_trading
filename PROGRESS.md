# MT5 Trading Bot — Project Progress

## What This Project Is

A **semi-automated + algorithmic trading bot** for prop-firm accounts (FundingPips) using MetaTrader 5 (MT5) + Python.
Target instruments: Major Forex pairs (EURUSD, GBPUSD, AUDUSD, USDCAD, USDCHF, USDJPY, AUDCAD).

---

## Project Structure

| File | Purpose |
|------|---------|
| `config.py` | All settings in one place — pairs, risk, RSI, swing lookback, RR targets |
| `indicators.py` | RSI(14), swing high/low detection (3 candles each side) |
| `strategy.py` | 1H setup scanner + 5min entry signal detector |
| `bot.py` | Main 24/7 loop — scans every 60s, places trades, logs everything |
| `backtest.py` | Backtester using downloaded CSVs — simulates full strategy |
| `report.py` | Generates HTML report from backtest results |
| `execution_bot.py` | Original bot — reused: `connect`, `disconnect`, `get_account_info` |
| `download_data_claud.py` | Downloads OHLCV data from MT5 to CSV (reused for backtest) |
| `download_data.py` | Original basic downloader |

---

## Strategy Logic

**Setup (1H):**
- Scan 7 forex pairs every new 1H candle
- RSI(14) < 25 → record the LOW and the last swing high before it (SH1)
- Setup active for next 3 hourly candles, then expires

**Entry (5min):**
- After setup: find absolute low on 5min
- Confirm higher swing low forms (current > previous)
- 5min candle closes ABOVE SH1 → entry signal
- Entry = close of that candle
- SL = low of entry candle − 1 pip buffer
- TP = 1:5 RR or next swing high on 5min (whichever is further, minimum 1:3)

**Risk:**
- Fixed $12.50 per trade (0.25% of $5000 — adjustable in `config.py`)
- Max 3 open trades simultaneously
- Skip if spread > 20 pips
- BUY only (long-only mean reversion)

---

## What's Built (Done)

- [x] `config.py` — central config
- [x] `indicators.py` — RSI, swing high/low (3 candles each side)
- [x] `strategy.py` — 1H setup + 5min entry logic with RR validation
- [x] `bot.py` — main loop, trade execution, file logger, setup state manager, dedup guard
- [x] `backtest.py` — full walk-forward backtest on CSV data
- [x] `report.py` — HTML report with equity curve, trade log, per-symbol breakdown
- [x] MT5 connection (reused from `execution_bot.py`)
- [x] Historical data download (reused from `download_data_claud.py`)

---

## What's NOT Built Yet

- [ ] Trailing stop
- [ ] Partial close / scale-out
- [ ] Telegram / email alerts
- [ ] Multi-symbol backtest in one run
- [ ] Daily drawdown reset logic in live bot

---

## Key Config (`config.py`)

```python
FIXED_RISK_USD    = 12.50   # $ risk per trade
MAX_OPEN_TRADES   = 3
MAX_SPREAD_PIPS   = 20
RSI_OVERSOLD      = 25
SETUP_EXPIRY_BARS = 3
SWING_LOOKBACK    = 3       # candles each side for swing detection
MIN_RR            = 3.0
TARGET_RR         = 5.0
```

---

## How to Run

```bash
# Live bot (MT5 must be open and logged in)
python bot.py

# Download data for backtest
python download_data_claud.py EURUSD H1 1
python download_data_claud.py EURUSD M5 1

# Run backtest + generate HTML report
python backtest.py EURUSD H1 M5 1
```

Reports saved to `reports/`, logs to `logs/`.
