"""
Backtester — RSI mean-reversion with inside bar entry.

Strategy:
  1. H1 RSI < 20  → activate setup (switch to M5)
  2. M5: look for inside bar (candle B fully inside candle A)
  3. First M5 candle that closes above candle A's high  → entry
     SL = candle A's low  |  TP = 1:5 RR  |  trail SL on M5 swing lows
  4. Abandon if H1 RSI rises back above 30

Usage:
    python backtest.py EURUSD H1 M5 1
"""

import sys
import os
import pandas as pd
import numpy as np

from config import (
    RSI_PERIOD, RSI_OVERSOLD, SETUP_WINDOW_BARS,
    SWING_LOOKBACK, TARGET_RR, FIXED_RISK_USD, USE_TRAILING_SL,
    TRAIL_ACTIVATE_RR, MIN_SL_PIPS,
)
from indicators import calculate_rsi


# ── DATA LOADING ──────────────────────────────────────────────────────────────

def load_csv(symbol: str, timeframe: str, years: int) -> pd.DataFrame | None:
    path = f"data/{symbol}_{timeframe.upper()}_{years}y.csv"
    if not os.path.exists(path):
        print(f"File not found: {path}")
        print(f"Run: python download_data_claud.py {symbol} {timeframe} {years}")
        return None
    df = pd.read_csv(path, parse_dates=["datetime"])
    df = df.rename(columns={"datetime": "time"})
    return df.reset_index(drop=True)


# ── PIP UTILS ─────────────────────────────────────────────────────────────────

def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol else 0.0001

def pips(distance: float, symbol: str) -> float:
    return round(distance / pip_size(symbol), 1)


# ── BACKTEST ENGINE ───────────────────────────────────────────────────────────

def run_backtest(symbol: str, h1: pd.DataFrame, m5: pd.DataFrame) -> list[dict]:
    """
    State machine on M5 candles:
      INACTIVE → WATCHING : H1 RSI closes below RSI_OVERSOLD
      WATCHING → ARMED    : 3 consecutive higher highs on M5 (mark 3rd high + low)
      ARMED    → trade    : price breaks above marked high (intrabar)
      after exit          : back to WATCHING (keep scanning within window)
      window expires (6h) : back to INACTIVE
    """
    h1 = h1.copy().reset_index(drop=True)
    m5 = m5.copy().reset_index(drop=True)
    h1["rsi"] = calculate_rsi(h1["close"], RSI_PERIOD)

    # Attach latest completed H1 RSI to each M5 candle
    h1_rsi_df = h1[["time", "rsi"]].copy()
    h1_rsi_df["time"] = h1_rsi_df["time"] + pd.Timedelta(hours=1)  # H1 close time
    h1_rsi_df = h1_rsi_df.rename(columns={"rsi": "h1_rsi"})

    m5 = pd.merge_asof(
        m5.sort_values("time"),
        h1_rsi_df.sort_values("time"),
        on="time",
        direction="backward",
    ).reset_index(drop=True)

    trades           = []
    state            = "INACTIVE"   # INACTIVE | WATCHING | ARMED
    marked_high      = None         # high of 3rd (highest) higher-high candle
    marked_low       = None         # low of that same candle → SL
    setup_expiry     = None         # abandon setup after this time
    trade_open_until = None         # skip M5 candles during open trade

    def three_higher_highs(idx: int) -> bool:
        """True if m5[idx-2..idx] form 3 strictly higher highs."""
        if idx < 2:
            return False
        return (m5.iloc[idx - 2]["high"] < m5.iloc[idx - 1]["high"] < m5.iloc[idx]["high"])

    for i in range(1, len(m5)):
        candle  = m5.iloc[i]
        h1_rsi  = candle["h1_rsi"]

        if pd.isna(h1_rsi):
            continue

        # Skip candles covered by an open simulated trade
        if trade_open_until is not None:
            if candle["time"] <= trade_open_until:
                continue
            trade_open_until = None

        # Window expired → go idle
        if setup_expiry is not None and candle["time"] >= setup_expiry:
            if state != "INACTIVE":
                print(f"  → Window expired — abandon | {candle['time']}")
            state = "INACTIVE"
            marked_high = marked_low = setup_expiry = None
            continue

        # RSI closes below threshold → activate watch window
        if h1_rsi < RSI_OVERSOLD and state == "INACTIVE":
            expiry = candle["time"] + pd.Timedelta(hours=SETUP_WINDOW_BARS)
            print(f"[RSI ACTIVE] {symbol} | {candle['time']} | H1 RSI={round(h1_rsi, 2)} | Expires {expiry}")
            state        = "WATCHING"
            setup_expiry = expiry
            continue

        if state == "INACTIVE":
            continue

        # ── WATCHING: detect 3 consecutive higher highs ─────────────────────
        if state == "WATCHING":
            if three_higher_highs(i):
                marked_high = candle["high"]
                marked_low  = candle["low"]
                print(f"  → 3 higher highs | mark high={round(marked_high,5)} low(SL)={round(marked_low,5)} at {candle['time']}")
                state = "ARMED"
            continue

        # ── ARMED: enter on intrabar break above marked high ────────────────
        if state == "ARMED":
            if candle["high"] > marked_high:
                entry_price = marked_high
                # Widen SL to the minimum distance if the marked candle is too small
                min_dist    = MIN_SL_PIPS * pip_size(symbol)
                sl_distance = max(entry_price - marked_low, min_dist)
                sl_price    = entry_price - sl_distance

                if sl_distance <= 0:
                    state = "WATCHING"
                    marked_high = marked_low = None
                    continue

                tp_price   = entry_price + sl_distance * TARGET_RR
                rr         = TARGET_RR
                entry_time = candle["time"]
                saved_high = marked_high
                saved_low  = marked_low

                print(f"  → ENTRY | {entry_time} | Entry={round(entry_price,5)} SL={round(sl_price,5)} TP={round(tp_price,5)}")

                # Walk-forward simulation: trail SL up to each completed candle's low
                result      = "OPEN"
                exit_price  = None
                exit_time   = None
                current_sl  = sl_price
                trail_armed = (TRAIL_ACTIVATE_RR <= 0)   # arm immediately if threshold is 0
                trail_level = entry_price + sl_distance * TRAIL_ACTIVATE_RR

                for fwd_idx in range(i + 1, len(m5)):
                    row = m5.iloc[fwd_idx]
                    if row["low"] <= current_sl:
                        result = "SL"; exit_price = current_sl; exit_time = row["time"]; break
                    if row["high"] >= tp_price:
                        result = "TP"; exit_price = tp_price;   exit_time = row["time"]; break
                    # Arm trailing once price reaches the activation R-multiple
                    if not trail_armed and row["high"] >= trail_level:
                        trail_armed = True
                    # Trail: move SL up to this completed candle's low (only upward)
                    if USE_TRAILING_SL and trail_armed and row["low"] > current_sl:
                        current_sl = row["low"]

                if result == "OPEN":
                    state = "INACTIVE"
                    marked_high = marked_low = setup_expiry = None
                    continue

                trade_open_until = exit_time
                duration_mins    = int((exit_time - entry_time).total_seconds() / 60)
                rr_achieved      = (exit_price - entry_price) / sl_distance
                pnl_usd          = round(FIXED_RISK_USD * rr_achieved, 2)
                if result == "SL" and exit_price > entry_price:
                    result = "TS"   # trailing stop in profit

                trades.append({
                    "symbol":        symbol,
                    "entry_time":    entry_time,
                    "exit_time":     exit_time,
                    "entry_price":   round(entry_price, 5),
                    "sl_price":      round(sl_price, 5),
                    "tp_price":      round(tp_price, 5),
                    "exit_price":    round(exit_price, 5),
                    "sl_pips":       pips(sl_distance, symbol),
                    "rr_planned":    rr,
                    "rr_achieved":   round(rr_achieved, 2),
                    "result":        result,
                    "pnl_usd":       pnl_usd,
                    "duration_mins": duration_mins,
                    "h1_rsi":        round(h1_rsi, 2),
                    "mother_high":   round(saved_high, 5),
                    "mother_low":    round(saved_low, 5),
                })

                # Keep scanning for more trades within the same window
                state = "WATCHING"
                marked_high = marked_low = None
                continue

            # No break yet — re-arm if a fresh 3 higher highs forms
            if three_higher_highs(i):
                marked_high = candle["high"]
                marked_low  = candle["low"]
            continue

    return trades


# ── SUMMARY STATS ─────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {}

    df = pd.DataFrame(trades)
    wins   = df[df["pnl_usd"] > 0]
    losses = df[df["pnl_usd"] <= 0]

    total_pnl     = df["pnl_usd"].sum()
    gross_profit  = wins["pnl_usd"].sum() if len(wins) else 0
    gross_loss    = abs(losses["pnl_usd"].sum()) if len(losses) else 0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    equity = 5000.0
    peak   = equity
    max_dd = 0.0
    for pnl in df["pnl_usd"]:
        equity += pnl
        peak    = max(peak, equity)
        max_dd  = max(max_dd, peak - equity)

    max_consec_loss = cur = 0
    for r in df["result"]:
        if r == "SL":
            cur += 1
            max_consec_loss = max(max_consec_loss, cur)
        else:
            cur = 0

    by_symbol = df.groupby("symbol").agg(
        trades=("result", "count"),
        wins=("result", lambda x: (x == "TP").sum()),
        pnl=("pnl_usd", "sum"),
    ).round(2).to_dict("index")

    return {
        "total_trades":      len(df),
        "wins":              len(wins),
        "losses":            len(losses),
        "win_rate":          round(len(wins) / len(df) * 100, 1),
        "total_pnl_usd":     round(total_pnl, 2),
        "profit_factor":     profit_factor,
        "max_drawdown_usd":  round(max_dd, 2),
        "avg_rr_achieved":   round(df["rr_achieved"].mean(), 2),
        "avg_duration_mins": round(df["duration_mins"].mean(), 1),
        "max_consec_losses": max_consec_loss,
        "by_symbol":         by_symbol,
        "trades_df":         df,
    }


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    symbol   = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    setup_tf = sys.argv[2] if len(sys.argv) > 2 else "H1"
    entry_tf = sys.argv[3] if len(sys.argv) > 3 else "M5"
    years    = int(sys.argv[4]) if len(sys.argv) > 4 else 1

    print(f"\nLoading {symbol} data...")
    h1 = load_csv(symbol, setup_tf, years)
    m5 = load_csv(symbol, entry_tf, years)

    if h1 is None or m5 is None:
        sys.exit(1)

    print(f"H1 candles: {len(h1)} | M5 candles: {len(m5)}")
    print(f"Running backtest...\n")

    trades = run_backtest(symbol, h1, m5)
    stats  = compute_stats(trades)

    if not stats:
        print("No trades found.")
        sys.exit(0)

    print(f"\nTotal Trades    : {stats['total_trades']}")
    print(f"Wins / Losses   : {stats['wins']} / {stats['losses']}")
    print(f"Win Rate        : {stats['win_rate']}%")
    print(f"Total P&L       : ${stats['total_pnl_usd']}")
    print(f"Profit Factor   : {stats['profit_factor']}")
    print(f"Max Drawdown    : ${stats['max_drawdown_usd']}")
    print(f"Avg RR Achieved : {stats['avg_rr_achieved']}")
    print(f"Max Consec Loss : {stats['max_consec_losses']}")
    print(f"\nGenerating HTML report...")

    from report import generate_report
    generate_report(stats, symbol, setup_tf, entry_tf, years)
