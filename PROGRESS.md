# MT5 Trading Bot — Project Progress

## What This Project Is

An **automated algorithmic trading bot** running live on a FundingPips MT5 account
($5,000). The active strategy is an **Opening-Range Failed-Breakout Reversal on
NDX100**, fully self-deploying on an AWS Windows server (starts itself, trades one
session, emails at each step, and powers itself off).

> An earlier RSI mean-reversion strategy (Forex, long-only) was built first and
> shelved — those files are kept but are **legacy** (see bottom).

---

## Active Strategy — ORB Reversal (NDX100)

Per day, all in **broker time** (US open = 16:30 broker = 9:30 ET, DST-aligned):

1. **Opening range** = first 15-min candle after the open (16:30–16:45).
2. **Break candle** = the next 15-min candle (16:45–17:00) must break **one** side:
   - breaks the **high** only → **SHORT** bias
   - breaks the **low** only → **LONG** bias
   - breaks **both / neither** → skip the day
3. **Entry (reversal)** on the *opposite* side breaching:
   - SHORT: sell when price trades below the range low
   - LONG: buy when price trades above the range high
4. **SL** = the range **midpoint** (half-range stop). No fixed TP.
5. **Exit** = force-flat at **22:55** broker (5 min before US close) or SL, whichever first.
6. **One trade per day**, both directions.

### Backtest (NDX100 M15, ~4.5 years, 2022–2026)
| Metric | Value |
|---|---|
| Profit factor | **1.51** |
| Total P&L | ~+$1,948 (at $12.50/R) |
| Win rate | 30.5% (low-WR / high-R by design) |
| Max drawdown | $170 |
| Consistency | all 5 years net positive (2022 ~breakeven) |

Half-range SL (vs full range) roughly 2.5×'d total P&L and made every year green.

---

## Second Strategy — RSI Extreme Reversal (EURGBP) — *backtest stage*

A high-R fade of RSI extremes on EUR/GBP (not yet deployed; in backtest).

1. **H1 RSI(14) > 80** → arm SHORT (stays armed while RSI stays above 80).
   **H1 RSI(14) < 20** → arm LONG (while below 20).
2. **Entry:** first **red** M5 candle → sell at its close (SHORT);
   first **green** M5 candle → buy at its close (LONG).
3. **SL** = the trigger candle's extreme (high for short / low for long),
   floored at **10 pips** (`RSI_REV_MIN_SL_PIPS`) so tiny candles don't give noise stops.
4. **TP** = **1:5** RR. Re-entry allowed while still in the zone (one trade at a time).

Fully deterministic (RSI value + candle colour + close), low-WR/high-R by design.
Backtester: `backtest_rsi.py`. Config block: `RSI_REV_*` in `config.py`.

```bash
python download_data_claud.py EURGBP H1 3
python download_data_claud.py EURGBP M5 3
python backtest_rsi.py EURGBP 3
```

---

## Live Config (`config.py`)
```python
US_OPEN_TIME      = "16:30"   # broker time of 9:30 ET (volume-confirmed, DST-aligned)
ORB_EXIT_TIME     = "22:55"   # 5 min before US close
ORB_RANGE_MINUTES = 15
MT5_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
# risk lives in execution_bot.py:
RISK_PERCENT           = 0.02  # SURVIVAL MODE → floors at 0.01 lot (~$16-30/trade)
MAX_DAILY_LOSS_PERCENT = 5.0   # kill-switch
```
Risk is **% of live balance**, auto-sized to each trade's stop distance.
Currently in **survival mode** (0.02% → minimum lot) to protect a thin drawdown
buffer; raise `RISK_PERCENT` in `execution_bot.py` when appropriate (e.g. 0.8 = 0.8%).

---

## Deployment / Automation (AWS)

Fully hands-off daily loop:
```
EventBridge Scheduler (9:00 AM America/New_York, Mon–Fri)
  → starts EC2 instance                              [email: machine started]
    → Windows auto-logon → Startup runs run_orb.bat
      → launch_orb.py launches + verifies MT5         [email: MT5 launched]
        → runs bot_orb.py in-process (auto-shutdown)  [email: bot launched]
          → bot trades the session
            → powers off when day resolves            [email: shutting down]
```
- **Emails** via AWS SNS (topic `orb-bot-alerts` → egarg0587@gmail.com).
- **Shutdown** is event-driven: skip-day (17:00), SL hit, or 22:55 EOD; plus a
  **21:45 UTC wall-clock backstop** for market holidays / dead sessions.
- **DST**: broker clock tracks NY (open stays 16:30 year-round → bot is auto-correct);
  EventBridge uses `America/New_York` timezone so the start also tracks DST.
- **Restart-safe**: reconciles an open position; a state flag
  (`logs/orb_last_trade.txt`) blocks a second trade the same day.
- Full setup steps in **`AUTOSTART.md`**.

---

## Project Structure

| File | Purpose |
|------|---------|
| `config.py` | Central settings (ORB times, MT5 path, risk, legacy RSI params) |
| `backtest_orb.py` | ORB backtester (any timeframe; per-year breakdown) |
| `backtest_rsi.py` | RSI extreme-reversal backtester (EURGBP; per-year breakdown) |
| `bot_orb.py` | **Live ORB bot** — daily state machine, half-range SL, auto-shutdown |
| `launch_orb.py` | Boot orchestrator — launches MT5 + bot, emails each step |
| `run_orb.bat` | Startup-folder launcher (venv + `launch_orb.py`) |
| `notify.py` | AWS SNS email helper |
| `execution_bot.py` | Reused: `connect`, `calculate_lot_size`, risk/drawdown constants |
| `report.py` | HTML backtest report (equity curve, trade log) |
| `download_data_claud.py` | MT5 → CSV data downloader |
| `AUTOSTART.md` | Full AWS + Windows deployment guide |

---

## How to Run / Monitor

```bash
# ORB backtest (server, data downloaded first)
python download_data_claud.py NDX100 M15 5
python backtest_orb.py NDX100 5 M15

# RSI reversal backtest (EURGBP)
python download_data_claud.py EURGBP H1 3
python download_data_claud.py EURGBP M5 3
python backtest_rsi.py EURGBP 3

# Live bot — manual (no auto-shutdown)
python bot_orb.py NDX100

# Live bot — full boot flow (emails + auto-shutdown; what Startup runs)
python launch_orb.py NDX100

# Watch live
tail -f logs/orb_bot.log
```

Deployed live on AWS as of **July 2026** — first automated session Mon 13 Jul 2026.

---

## Legacy (RSI mean-reversion, Forex) — shelved
`indicators.py`, `strategy.py`, `bot.py`, `backtest.py` implement the original
long-only RSI(14) < setup on 7 Forex pairs. Kept for reference; not deployed.
