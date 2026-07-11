"""
Boot orchestrator for the ORB live bot (runs on Windows startup via Task Scheduler).

Sequence, with an email at each step:
  1. Machine started
  2. Launch + connect MT5 terminal   -> verify -> email
  3. Launch bot_orb.py (auto-shutdown mode) -> verify alive -> email

The bot itself sends the 4th email (shutdown) when the trading day is done.

Run:
    python launch_orb.py            # NDX100
    python launch_orb.py NDX100
"""

import sys
import os
import time
import logging
import subprocess

import MetaTrader5 as mt5

from config import MT5_TERMINAL_PATH
from notify import notify

# Reuse the same log file/format as the bot
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("orb")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    _fh = logging.FileHandler("logs/orb_bot.log", encoding="utf-8"); _fh.setFormatter(_fmt); logger.addHandler(_fh)
    _sh = logging.StreamHandler();                                    _sh.setFormatter(_fmt); logger.addHandler(_sh)

def log(msg): logger.info(msg)


def launch_mt5() -> bool:
    """Launch the MT5 terminal and confirm a live connection."""
    if not os.path.exists(MT5_TERMINAL_PATH):
        log(f"[FAIL] MT5 path not found: {MT5_TERMINAL_PATH}")
        notify("ORB: MT5 launch FAILED", f"terminal not found at {MT5_TERMINAL_PATH}")
        return False

    # mt5.initialize(path=...) launches the terminal if it isn't running, then connects
    for attempt in range(1, 6):
        if mt5.initialize(path=MT5_TERMINAL_PATH):
            acct = mt5.account_info()
            mt5.shutdown()  # release our handle; the bot opens its own
            info = f"account {acct.login} | balance ${acct.balance:,.2f}" if acct else "connected"
            log(f"[OK] MT5 launched & connected ({info})")
            notify("ORB: MT5 launched", f"MT5 up and connected.\n{info}")
            return True
        log(f"  MT5 connect attempt {attempt}/5 failed: {mt5.last_error()}")
        time.sleep(10)

    log("[FAIL] MT5 could not connect after 5 attempts")
    notify("ORB: MT5 launch FAILED", f"could not connect after 5 attempts: {mt5.last_error()}")
    return False


def launch_bot(symbol: str) -> bool:
    """Start the trading bot in auto-shutdown mode as a background process."""
    try:
        proc = subprocess.Popen(
            [sys.executable, "bot_orb.py", symbol, "--shutdown"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
    except Exception as e:
        log(f"[FAIL] could not start bot: {e}")
        notify("ORB: bot launch FAILED", f"could not start bot_orb.py: {e}")
        return False

    time.sleep(8)  # give it a moment to boot / crash
    if proc.poll() is not None:
        log(f"[FAIL] bot exited immediately (code {proc.returncode})")
        notify("ORB: bot launch FAILED", f"bot_orb.py exited immediately (code {proc.returncode})")
        return False

    log(f"[OK] bot_orb.py running (pid {proc.pid})")
    notify("ORB: bot launched", f"bot_orb.py started for {symbol} (pid {proc.pid}, auto-shutdown on).")
    return True


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NDX100"

    log("=" * 55)
    log(f"  ORB boot orchestrator - {symbol}")
    log("=" * 55)
    notify("ORB: machine started", f"AWS server booted; starting ORB stack for {symbol}.")

    if not launch_mt5():
        log("Aborting — MT5 not available.")
        return
    if not launch_bot(symbol):
        log("Aborting — bot did not start.")
        return

    log("Boot sequence complete. Bot is now trading the session.")


if __name__ == "__main__":
    main()
