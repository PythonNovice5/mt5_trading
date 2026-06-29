"""
Main bot loop.
Scans all pairs every 60s for 1H setups and 5min entry signals.
Reuses MT5 connection logic from execution_bot.py.
"""

import time
import logging
import os
from datetime import datetime

import MetaTrader5 as mt5

from config import (
    SYMBOLS, LOOP_INTERVAL_SEC, MAX_OPEN_TRADES,
    LOG_DIR, TRADE_LOG_FILE, SIGNAL_LOG_FILE,
    SETUP_EXPIRY_BARS, H1_CANDLES,
)
from execution_bot import connect, disconnect, get_account_info
from strategy import (
    check_1h_setup, check_entry_signal,
    is_spread_ok, calculate_lot_size, get_candles,
)


# ── LOGGER SETUP ──────────────────────────────────────────────────────────────

os.makedirs(LOG_DIR, exist_ok=True)

def _make_logger(name: str, filepath: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(filepath)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(sh)
    return logger

trade_log  = _make_logger("trade",  TRADE_LOG_FILE)
signal_log = _make_logger("signal", SIGNAL_LOG_FILE)


# ── TRADE EXECUTION ───────────────────────────────────────────────────────────

def count_open_trades(magic: int = 20250321) -> int:
    positions = mt5.positions_get()
    if not positions:
        return 0
    return sum(1 for p in positions if p.magic == magic)


def place_trade(signal: dict) -> bool:
    symbol     = signal["symbol"]
    entry      = signal["entry_price"]
    sl         = signal["sl_price"]
    tp         = signal["tp_price"]
    sl_dist    = signal["sl_distance"]

    lot = calculate_lot_size(symbol, sl_dist)
    if lot == 0:
        signal_log.warning(f"{symbol} | lot size = 0, skipping")
        return False

    if not mt5.symbol_select(symbol, True):
        signal_log.warning(f"{symbol} | could not select symbol")
        return False

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         mt5.ORDER_TYPE_BUY,
        "price":        tick.ask,
        "sl":           sl,
        "tp":           tp,
        "deviation":    20,
        "magic":        20250321,
        "comment":      "RSI-HHL Bot",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        trade_log.info(
            f"TRADE PLACED | {symbol} | BUY | "
            f"Entry={result.price} SL={sl} TP={tp} "
            f"Lot={lot} RR={signal['rr']} Ticket=#{result.order}"
        )
        return True
    else:
        trade_log.error(
            f"TRADE FAILED | {symbol} | retcode={result.retcode} | {result.comment}"
        )
        return False


# ── SETUP STATE MANAGER ───────────────────────────────────────────────────────

class SetupState:
    """Tracks active 1H setups per symbol and expires them after N bars."""

    def __init__(self):
        self._setups: dict[str, dict] = {}
        self._last_h1_bar: dict[str, int] = {}

    def update(self, symbol: str, current_bar_count: int) -> dict | None:
        """
        Check for new 1H setup. Expire stale ones.
        Returns active setup for symbol or None.
        """
        setup = self._setups.get(symbol)

        # Expire check
        if setup:
            bars_elapsed = current_bar_count - setup["h1_bar_at_setup"]
            if bars_elapsed > SETUP_EXPIRY_BARS:
                signal_log.info(f"{symbol} | Setup EXPIRED after {bars_elapsed} bars")
                del self._setups[symbol]
                setup = None

        # Only scan for new setup if no active one
        if setup is None:
            new_setup = check_1h_setup(symbol)
            if new_setup:
                self._setups[symbol] = new_setup
                signal_log.info(
                    f"{symbol} | NEW SETUP | RSI={new_setup['rsi_at_setup']} "
                    f"Low={new_setup['low_price']} SH1={new_setup['sh1_price']}"
                )
                return new_setup
            return None

        return setup

    def clear(self, symbol: str):
        self._setups.pop(symbol, None)


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def run():
    print("\n" + "=" * 55)
    print("  RSI Higher-High/Low Strategy Bot")
    print("=" * 55)

    if not connect():
        return

    state = SetupState()
    traded_signals: set[str] = set()  # prevent duplicate trades on same signal candle

    print(f"\nScanning {len(SYMBOLS)} pairs every {LOOP_INTERVAL_SEC}s...\n")

    while True:
        try:
            loop_start = datetime.now()

            open_trades = count_open_trades()
            if open_trades >= MAX_OPEN_TRADES:
                signal_log.info(f"Max trades reached ({open_trades}/{MAX_OPEN_TRADES}), skipping scan")
                time.sleep(LOOP_INTERVAL_SEC)
                continue

            for symbol in SYMBOLS:
                # Get current 1H bar count for expiry tracking
                h1_df = get_candles(symbol, "H1", H1_CANDLES)
                if h1_df is None:
                    continue
                current_bar = len(h1_df) - 1

                setup = state.update(symbol, current_bar)
                if setup is None:
                    continue

                # Check spread
                if not is_spread_ok(symbol):
                    signal_log.info(f"{symbol} | Spread too high, skipping entry check")
                    continue

                # Check for entry signal
                entry = check_entry_signal(symbol, setup)
                if entry is None:
                    continue

                # Deduplicate — don't trade same signal candle twice
                signal_key = f"{symbol}_{entry['signal_time']}"
                if signal_key in traded_signals:
                    continue

                signal_log.info(
                    f"{symbol} | ENTRY SIGNAL | "
                    f"Entry={entry['entry_price']} SL={entry['sl_price']} "
                    f"TP={entry['tp_price']} RR={entry['rr']}"
                )

                # Re-check open trades before placing
                if count_open_trades() >= MAX_OPEN_TRADES:
                    signal_log.info(f"{symbol} | Signal valid but max trades reached")
                    continue

                success = place_trade(entry)
                if success:
                    traded_signals.add(signal_key)
                    state.clear(symbol)  # Setup consumed — reset for this pair

            elapsed = (datetime.now() - loop_start).total_seconds()
            sleep_for = max(0, LOOP_INTERVAL_SEC - elapsed)
            time.sleep(sleep_for)

        except KeyboardInterrupt:
            print("\n\nStopping bot...")
            break
        except Exception as e:
            trade_log.error(f"Loop error: {e}", exc_info=True)
            time.sleep(LOOP_INTERVAL_SEC)

    disconnect()
    print("Bot stopped.")


if __name__ == "__main__":
    run()
