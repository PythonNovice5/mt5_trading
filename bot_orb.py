"""
Live bot - Opening-Range Failed-Breakout Reversal (NDX100).

Daily flow (broker time), mirrors backtest_orb.py:
  1. First 15-min candle after US open (16:30) = opening range.
  2. 2nd 15-min candle (16:45) must break ONE side:
       high only  -> SHORT bias   |   low only -> LONG bias
       both/neither -> skip the day
  3. Enter (market) when the OPPOSITE side is breached:
       SHORT: sell when price <= range_low
       LONG : buy  when price >= range_high
  4. SL = midpoint of the range (half-range stop). No TP.
  5. Exit: flat at ORB_EXIT_TIME (22:55) or SL - one trade per day.

Run on the Windows server with MT5 open & logged in:
    python bot_orb.py            # NDX100
    python bot_orb.py NDX100
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5
import pandas as pd

from config import US_OPEN_TIME, ORB_EXIT_TIME, ORB_RANGE_MINUTES
from execution_bot import (
    connect, disconnect, calculate_lot_size, get_account_info,
    MAX_DAILY_LOSS_PERCENT,
)

MAGIC     = 26073
POLL_SEC  = 1

# ── LOGGER (console + logs/orb_bot.log) ──
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("orb")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    _fh = logging.FileHandler("logs/orb_bot.log", encoding="utf-8"); _fh.setFormatter(_fmt); logger.addHandler(_fh)
    _sh = logging.StreamHandler();                 _sh.setFormatter(_fmt); logger.addHandler(_sh)

def log(msg: str):
    logger.info(msg)


def is_market_open(symbol: str) -> bool:
    """Detect a live market by checking that quotes are actively updating."""
    info = mt5.symbol_info(symbol)
    if info is None or info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        return False
    t1 = mt5.symbol_info_tick(symbol)
    time.sleep(2)
    t2 = mt5.symbol_info_tick(symbol)
    if t1 is None or t2 is None:
        return False
    return t2.time_msc != t1.time_msc   # quote advanced -> market is live


def _t(hhmm: str) -> timedelta:
    h, m = hhmm.split(":")
    return timedelta(hours=int(h), minutes=int(m))


def broker_now(symbol: str) -> datetime | None:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return datetime.fromtimestamp(tick.time, tz=timezone.utc).replace(tzinfo=None)  # broker wall time


def get_m15_bar(symbol: str, bar_open: datetime):
    """Return the completed M15 bar whose open == bar_open, or None."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 200)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    row = df[df["time"] == pd.Timestamp(bar_open)]
    return None if row.empty else row.iloc[0]


def orb_position(symbol: str):
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return None
    for p in positions:
        if p.magic == MAGIC:
            return p
    return None


STATE_FILE = "logs/orb_last_trade.txt"

def mark_traded(day) -> None:
    """Persist the date we last entered a trade (survives restart)."""
    with open(STATE_FILE, "w") as f:
        f.write(str(day))

def already_traded(day) -> bool:
    """True if our own flag says we already traded on this date."""
    try:
        with open(STATE_FILE) as f:
            return f.read().strip() == str(day)
    except FileNotFoundError:
        return False


def place_market(symbol: str, direction: str, sl_price: float) -> bool:
    if not mt5.symbol_select(symbol, True):
        log(f"  ! could not select {symbol}")
        return False
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None:
        return False

    if direction == "SHORT":
        order_type, price = mt5.ORDER_TYPE_SELL, tick.bid
    else:
        order_type, price = mt5.ORDER_TYPE_BUY, tick.ask

    sl_points = abs(price - sl_price) / info.point
    lot = calculate_lot_size(symbol, sl_points)
    if lot == 0:
        log("  ! lot size 0 - skipping")
        return False

    base = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    lot,
        "type":      order_type,
        "price":     price,
        "sl":        sl_price,
        "tp":        0.0,            # no TP - time-based exit
        "deviation": 20,
        "magic":     MAGIC,
        "comment":   "ORB reversal",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    # Try filling modes in order - brokers differ (IOC / FOK / RETURN)
    for fill in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        r = mt5.order_send({**base, "type_filling": fill})
        if r is None:
            continue
        if r.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"  [OK] {direction} filled @ {r.price} | SL {sl_price} | lot {lot} | #{r.order}")
            return True
        if r.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
            log(f"  [FAIL] order failed retcode={r.retcode} {r.comment}")
            return False
    log(f"  [FAIL] order failed - no supported filling mode")
    return False


def close_orb(symbol: str):
    pos = orb_position(symbol)
    if pos is None:
        return
    tick = mt5.symbol_info_tick(symbol)
    if pos.type == mt5.ORDER_TYPE_BUY:
        otype, price = mt5.ORDER_TYPE_SELL, tick.bid
    else:
        otype, price = mt5.ORDER_TYPE_BUY, tick.ask
    r = mt5.order_send({
        "action":   mt5.TRADE_ACTION_DEAL,
        "symbol":   symbol,
        "volume":   pos.volume,
        "type":     otype,
        "position": pos.ticket,
        "price":    price,
        "deviation":20,
        "magic":    MAGIC,
        "comment":  "ORB EOD exit",
        "type_filling": mt5.ORDER_FILLING_IOC,
    })
    log(f"  [EOD] EOD close #{pos.ticket} @ {price} | P&L ${pos.profit:.2f} | retcode {r.retcode}")


def run(symbol: str):
    log("\n" + "=" * 55)
    log(f"  ORB Reversal Live Bot - {symbol}")
    log("=" * 55)
    if not connect():
        return

    market = is_market_open(symbol)
    log(f"Market is {'OPEN' if market else 'CLOSED'} for {symbol}.")
    if not market:
        log("Not a live session right now - waiting; will trade when it opens.")

    open_off = _t(US_OPEN_TIME)
    rng_len  = timedelta(minutes=ORB_RANGE_MINUTES)
    exit_off = _t(ORB_EXIT_TIME)

    day_state = {"date": None}

    def reset(d):
        day_state.clear()
        day_state.update({
            "date": d, "range": None, "direction": None,
            "entered": False, "skipped": False, "closed": False,
            "start_equity": get_account_info()["equity"],
        })

    log(f"Polling every {POLL_SEC}s. US open {US_OPEN_TIME}, exit {ORB_EXIT_TIME} (broker time).")

    last_hb_wall = 0.0
    last_tick_t  = None

    while True:
        try:
            now = broker_now(symbol)
            # "live" = quote advanced since last poll → market is actively trading
            live = now is not None and last_tick_t is not None and now != last_tick_t
            last_tick_t = now

            # Wall-clock heartbeat every 30 min (fires even when market is closed)
            if time.time() - last_hb_wall >= 1800:
                stt = day_state
                summary = (f"range={stt.get('range')} dir={stt.get('direction')} "
                           f"entered={stt.get('entered')} skipped={stt.get('skipped')}"
                           if stt.get("date") else "no active day")
                log(f"heartbeat | market={'OPEN' if live else 'CLOSED'} | broker_now={now} | {summary}")
                last_hb_wall = time.time()

            if not live:
                time.sleep(POLL_SEC); continue   # market not ticking → wait

            today   = datetime(now.year, now.month, now.day)
            open_dt = today + open_off
            c2_open = open_dt + rng_len
            c2_end  = c2_open + rng_len
            exit_dt = today + exit_off

            if day_state["date"] != today.date():
                reset(today.date())

            st = day_state

            # Reconcile after a restart (survives a kill/restart mid-day)
            if not st["entered"]:
                if orb_position(symbol) is not None:
                    st["entered"] = True
                    log(f"{now} | existing ORB position found - reconciled")
                elif already_traded(today.date()):
                    st["entered"] = True
                    st["closed"]  = True
                    log(f"{now} | already traded today (state flag) - no re-entry")

            # Daily loss kill-switch: halt (and flatten) if equity down too much
            if not st["skipped"] and st["start_equity"]:
                equity = get_account_info()["equity"]
                dd_pct = (st["start_equity"] - equity) / st["start_equity"] * 100
                if dd_pct >= MAX_DAILY_LOSS_PERCENT:
                    log(f"{now} | daily loss {dd_pct:.2f}% >= {MAX_DAILY_LOSS_PERCENT}% - HALT day")
                    close_orb(symbol)
                    st["skipped"] = True
                    st["closed"]  = True

            # 1) Build the opening range once the first candle has closed
            if st["range"] is None and now >= c2_open:
                bar = get_m15_bar(symbol, open_dt)
                if bar is not None:
                    st["range"] = (float(bar["high"]), float(bar["low"]))
                    log(f"{now} | range HIGH {st['range'][0]} LOW {st['range'][1]}")

            # 2) After 2nd candle closes, decide direction
            if st["range"] and st["direction"] is None and not st["skipped"] and now >= c2_end:
                bar2 = get_m15_bar(symbol, c2_open)
                if bar2 is not None:
                    rh, rl = st["range"]
                    broke_high = float(bar2["high"]) > rh
                    broke_low  = float(bar2["low"])  < rl
                    if broke_high == broke_low:
                        st["skipped"] = True
                        log(f"{now} | both/neither broken -> skip day")
                    else:
                        st["direction"] = "SHORT" if broke_high else "LONG"
                        mid       = round((rh + rl) / 2, 2)
                        entry_lvl = rl if broke_high else rh
                        log(f"{now} | {st['direction']} bias set | entry {entry_lvl} | SL {mid}")

            # 3) Wait for opposite-side breach -> enter (once, and only if flat)
            if (st["direction"] and not st["entered"] and not st["skipped"]
                    and c2_end <= now < exit_dt and orb_position(symbol) is None):
                rh, rl = st["range"]
                mid = (rh + rl) / 2
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    if st["direction"] == "SHORT" and tick.bid <= rl:
                        if place_market(symbol, "SHORT", mid):
                            st["entered"] = True
                            mark_traded(today.date())
                    elif st["direction"] == "LONG" and tick.ask >= rh:
                        if place_market(symbol, "LONG", mid):
                            st["entered"] = True
                            mark_traded(today.date())

            # 4) Flat at exit time
            if now >= exit_dt and not st["closed"]:
                close_orb(symbol)
                st["closed"] = True

            time.sleep(POLL_SEC)

        except KeyboardInterrupt:
            log("\nStopping bot...")
            break
        except Exception as e:
            log(f"loop error: {e}")
            time.sleep(POLL_SEC)

    disconnect()
    log("Bot stopped.")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NDX100"
    run(symbol)
