"""
Opening-Range Failed-Breakout Reversal — NDX100.

Per day (broker time):
  1. First 15-min candle (US open) = opening range [range_high, range_low].
  2. The very next 15-min candle must break ONE side of that range:
       - breaks high only  → SHORT bias
       - breaks low only   → LONG bias
       - breaks both/neither → skip the day
  3. Entry (reversal): after the break, enter when the OPPOSITE side is breached:
       - SHORT: enter at range_low  when price trades below range_low
       - LONG : enter at range_high when price trades above range_high
  4. SL = the first-broken side (range_high for SHORT, range_low for LONG).
  5. Exit: at ORB_EXIT_TIME (5 min before US close), or SL, whichever first.

Usage:
    python backtest_orb.py            # NDX100 M5 1y
    python backtest_orb.py NDX100 1
"""

import sys
import pandas as pd

from config import US_OPEN_TIME, ORB_EXIT_TIME, ORB_RANGE_MINUTES, FIXED_RISK_USD
from backtest import load_csv, compute_stats


def _t(hhmm: str) -> pd.Timedelta:
    h, m = hhmm.split(":")
    return pd.Timedelta(hours=int(h), minutes=int(m))


def run_orb(symbol: str, m5: pd.DataFrame) -> list[dict]:
    m5 = m5.copy()
    m5["date"] = m5["time"].dt.normalize()

    open_off  = _t(US_OPEN_TIME)
    rng_len   = pd.Timedelta(minutes=ORB_RANGE_MINUTES)
    exit_off  = _t(ORB_EXIT_TIME)

    trades = []

    for day, day_df in m5.groupby("date"):
        day_df = day_df.sort_values("time")
        open_dt   = day + open_off
        c1_end    = open_dt + rng_len            # first candle window end
        c2_end    = c1_end  + rng_len            # second candle window end
        exit_dt   = day + exit_off

        c1 = day_df[(day_df["time"] >= open_dt) & (day_df["time"] < c1_end)]
        c2 = day_df[(day_df["time"] >= c1_end)  & (day_df["time"] < c2_end)]
        if len(c1) < 3 or len(c2) < 3:
            continue  # incomplete session data

        range_high = c1["high"].max()
        range_low  = c1["low"].min()

        broke_high = c2["high"].max() > range_high
        broke_low  = c2["low"].min()  < range_low

        if broke_high == broke_low:
            continue  # both or neither → skip

        direction = "SHORT" if broke_high else "LONG"
        sl_price  = range_high if direction == "SHORT" else range_low
        sl_dist   = range_high - range_low
        if sl_dist <= 0:
            continue

        # ── Look for reversal entry from after the 2nd candle to exit time ──
        monitor = day_df[(day_df["time"] >= c2_end) & (day_df["time"] <= exit_dt)]
        entry_price = entry_time = None
        for _, row in monitor.iterrows():
            if direction == "SHORT" and row["low"] <= range_low:
                entry_price, entry_time = range_low, row["time"]
                break
            if direction == "LONG" and row["high"] >= range_high:
                entry_price, entry_time = range_high, row["time"]
                break

        if entry_price is None:
            continue  # opposite side never breached → no trade

        # ── Simulate: SL hit or time-based exit at ORB_EXIT_TIME ──
        # Include the entry candle: a single wide bar can breach entry AND SL.
        fwd = day_df[(day_df["time"] >= entry_time) & (day_df["time"] <= exit_dt)]
        result = "EOD"
        exit_price = None
        exit_time  = None

        for _, row in fwd.iterrows():
            if direction == "SHORT" and row["high"] >= sl_price:
                result, exit_price, exit_time = "SL", sl_price, row["time"]
                break
            if direction == "LONG" and row["low"] <= sl_price:
                result, exit_price, exit_time = "SL", sl_price, row["time"]
                break

        if result == "EOD":
            if len(fwd) == 0:
                continue
            last = fwd.iloc[-1]
            exit_price, exit_time = last["close"], last["time"]

        if direction == "SHORT":
            rr_achieved = (entry_price - exit_price) / sl_dist
        else:
            rr_achieved = (exit_price - entry_price) / sl_dist

        pnl_usd = round(FIXED_RISK_USD * rr_achieved, 2)
        result  = "SL" if result == "SL" else ("EOD+" if pnl_usd > 0 else "EOD-")

        trades.append({
            "symbol":        symbol,
            "entry_time":    entry_time,
            "exit_time":     exit_time,
            "entry_price":   round(entry_price, 2),
            "sl_price":      round(sl_price, 2),
            "tp_price":      direction,                 # reuse column to show direction
            "exit_price":    round(exit_price, 2),
            "sl_pips":       round(sl_dist, 1),         # index points
            "rr_planned":    "-",
            "rr_achieved":   round(rr_achieved, 2),
            "result":        result,
            "pnl_usd":       pnl_usd,
            "duration_mins": int((exit_time - entry_time).total_seconds() / 60),
            "h1_rsi":        direction,
            "mother_high":   round(range_high, 2),
            "mother_low":    round(range_low, 2),
        })

    return trades


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NDX100"
    years  = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    print(f"\nLoading {symbol} M5 data...")
    m5 = load_csv(symbol, "M5", years)
    if m5 is None:
        sys.exit(1)

    print(f"M5 candles: {len(m5)}")
    print(f"Running opening-range reversal backtest...\n")

    trades = run_orb(symbol, m5)
    stats  = compute_stats(trades)

    if not stats:
        print("No trades found.")
        sys.exit(0)

    longs  = sum(1 for t in trades if t["h1_rsi"] == "LONG")
    shorts = len(trades) - longs

    print(f"Total Trades    : {stats['total_trades']}  (LONG {longs} / SHORT {shorts})")
    print(f"Wins / Losses   : {stats['wins']} / {stats['losses']}")
    print(f"Win Rate        : {stats['win_rate']}%")
    print(f"Total P&L       : ${stats['total_pnl_usd']}")
    print(f"Profit Factor   : {stats['profit_factor']}")
    print(f"Max Drawdown    : ${stats['max_drawdown_usd']}")
    print(f"Avg RR Achieved : {stats['avg_rr_achieved']}")
    print(f"Max Consec Loss : {stats['max_consec_losses']}")
    print(f"\nGenerating HTML report...")

    from report import generate_report
    generate_report(stats, symbol, "ORB", "M5", years)
