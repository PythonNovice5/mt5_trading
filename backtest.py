"""
Backtester for the RSI Higher-High/Low strategy.
Uses CSV data downloaded via download_data_claud.py.

Usage:
    python backtest.py                        # uses defaults in config
    python backtest.py EURUSD H1 M5 1        # symbol, setup_tf, entry_tf, years
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import timedelta

from config import (
    RSI_PERIOD, RSI_OVERSOLD, SETUP_EXPIRY_BARS,
    SWING_LOOKBACK, MIN_RR, TARGET_RR,
    FIXED_RISK_USD, MAX_OPEN_TRADES,
)
from indicators import calculate_rsi, get_swing_high_levels, get_swing_low_levels


# ── DATA LOADING ──────────────────────────────────────────────────────────────

def load_csv(symbol: str, timeframe: str, years: int) -> pd.DataFrame | None:
    path = f"data/{symbol}_{timeframe.upper()}_{years}y.csv"
    if not os.path.exists(path):
        print(f"File not found: {path}")
        print("Run: python download_data_claud.py {symbol} {timeframe} {years}")
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
    Simulate the strategy on historical data.
    Returns list of trade dicts.
    """
    h1 = h1.copy().reset_index(drop=True)
    m5 = m5.copy().reset_index(drop=True)

    h1["rsi"] = calculate_rsi(h1["close"], RSI_PERIOD)

    trades   = []
    open_trades_count = 0
    active_setups: dict[str, dict] = {}  # keyed by symbol (single symbol here)

    # Pre-compute swing highs/lows on m5 once — iterate by index
    # We'll do a rolling window approach per signal instead

    for h1_idx in range(RSI_PERIOD + SWING_LOOKBACK + 1, len(h1)):
        h1_candle = h1.iloc[h1_idx]
        rsi_val   = h1_candle["rsi"]

        # ── 1H SETUP CHECK ──
        if pd.notna(rsi_val) and rsi_val < RSI_OVERSOLD:
            # New setup or update existing (each H1 candle with RSI < 25 resets the key low)
            if symbol not in active_setups:
                print(f"[RSI SETUP] {symbol} | {h1_candle['time']} | RSI = {round(rsi_val, 2)}")
            active_setups[symbol] = {
                "setup_bar":   h1_idx,
                "setup_time":  h1_candle["time"],
                "key_low":     h1_candle["low"],   # fixed key low = low of RSI candle
                "h1_open":     h1_candle["time"],
                "h1_close":    h1_candle["time"] + pd.Timedelta(hours=1),
                "rsi":         round(rsi_val, 2),
            }
        elif symbol in active_setups:
            setup = active_setups[symbol]

            # ── ENTRY WINDOW: only the 1 hour AFTER the RSI candle closes ──
            entry_window_start = setup["h1_close"]
            entry_window_end   = setup["h1_close"] + pd.Timedelta(hours=1)
            key_low            = setup["key_low"]

            # Only scan during the entry window
            if not (entry_window_start <= h1_candle["time"] < entry_window_end):
                # Outside entry window — expire setup
                active_setups.pop(symbol, None)
                continue

            if open_trades_count >= MAX_OPEN_TRADES:
                continue

            # ── 5MIN ENTRY SCAN ──
            m5_slice = m5[
                (m5["time"] >= entry_window_start) &
                (m5["time"] < entry_window_end)
            ].reset_index(drop=True)

            if len(m5_slice) < 3:
                continue

            # Invalidate if price breaks below key low
            if m5_slice["low"].min() < key_low:
                print(f"  → [{setup['setup_time']}] Key low {key_low} breached — reset")
                active_setups.pop(symbol, None)
                continue

            # Find SH1 = last swing high on M5 BEFORE the key low (look back up to 12 hours)
            key_low_time   = setup["setup_time"]  # H1 RSI candle open time = when key low formed
            m5_before_low  = m5[m5["time"] <= key_low_time].tail(144).reset_index(drop=True)  # last 12h of M5
            swing_highs    = get_swing_high_levels(m5_before_low)

            if not swing_highs:
                print(f"  → [{setup['setup_time']}] No SH1 found on M5 before key low")
                continue

            sh1_price = swing_highs[-1]["price"]
            print(f"  → M5 SH1: {sh1_price} at {swing_highs[-1]['time']} | Key low: {key_low}")

            # Find first M5 candle that closes above SH1
            entry_candle = None
            for _, candle in m5_slice.iterrows():
                if candle["time"] > swing_highs[-1]["time"] and candle["close"] > sh1_price:
                    entry_candle = candle
                    break

            if entry_candle is None:
                print(f"  → [{setup['setup_time']}] No M5 candle closed above SH1 {sh1_price}")
                continue

            entry_price = entry_candle["close"]
            sl_price    = entry_candle["low"] - pip_size(symbol)
            sl_distance = entry_price - sl_price

            if sl_distance <= 0:
                continue

            tp_1_5 = entry_price + sl_distance * TARGET_RR

            # Next swing high above SH1 on M5 for TP
            above_sh1  = [
                sh for sh in get_swing_high_levels(m5_slice)
                if sh["price"] > sh1_price and sh["price"] > entry_price
            ]
            next_sh_tp = above_sh1[0]["price"] if above_sh1 else None

            tp_price = max(tp_1_5, next_sh_tp) if next_sh_tp else tp_1_5
            rr       = (tp_price - entry_price) / sl_distance

            if rr < MIN_RR:
                print(f"  → [{setup['setup_time']}] RR {round(rr,2)} below minimum {MIN_RR}")
                continue

            # ── SIMULATE TRADE OUTCOME ──
            entry_time = entry_candle["time"]
            m5_forward = m5[m5["time"] > entry_time].reset_index(drop=True)

            result     = "OPEN"
            exit_price = None
            exit_time  = None
            pnl_usd    = None

            for _, row in m5_forward.iterrows():
                if row["low"] <= sl_price:
                    result     = "SL"
                    exit_price = sl_price
                    exit_time  = row["time"]
                    pnl_usd    = -FIXED_RISK_USD
                    break
                if row["high"] >= tp_price:
                    result     = "TP"
                    exit_price = tp_price
                    exit_time  = row["time"]
                    pnl_usd    = round(FIXED_RISK_USD * rr, 2)
                    break

            if result == "OPEN":
                continue

            duration_mins = int((exit_time - entry_time).total_seconds() / 60) if exit_time else None
            active_setups.pop(symbol, None)

            trades.append({
                "symbol":        symbol,
                "entry_time":    entry_time,
                "exit_time":     exit_time,
                "entry_price":   round(entry_price, 5),
                "sl_price":      round(sl_price, 5),
                "tp_price":      round(tp_price, 5),
                "exit_price":    round(exit_price, 5),
                "sl_pips":       pips(sl_distance, symbol),
                "rr_planned":    round(rr, 2),
                "rr_achieved":   round((exit_price - entry_price) / sl_distance, 2) if exit_price else None,
                "result":        result,
                "pnl_usd":       pnl_usd,
                "duration_mins": duration_mins,
                "rsi_at_setup":  setup["rsi"],
                "sh1_price":     sh1_price,
            })

    return trades


# ── SUMMARY STATS ─────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {}

    df = pd.DataFrame(trades)
    wins   = df[df["result"] == "TP"]
    losses = df[df["result"] == "SL"]

    total_pnl     = df["pnl_usd"].sum()
    gross_profit  = wins["pnl_usd"].sum() if len(wins) else 0
    gross_loss    = abs(losses["pnl_usd"].sum()) if len(losses) else 0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # Equity curve for max drawdown
    equity = FIXED_RISK_USD * 20  # approximate starting equity placeholder
    peak   = equity
    max_dd = 0.0
    for pnl in df["pnl_usd"]:
        equity += pnl
        peak    = max(peak, equity)
        dd      = peak - equity
        max_dd  = max(max_dd, dd)

    # Consecutive losses
    max_consec_loss = 0
    cur = 0
    for r in df["result"]:
        if r == "SL":
            cur += 1
            max_consec_loss = max(max_consec_loss, cur)
        else:
            cur = 0

    # Per-symbol breakdown
    by_symbol = df.groupby("symbol").agg(
        trades=("result", "count"),
        wins=("result", lambda x: (x == "TP").sum()),
        pnl=("pnl_usd", "sum"),
    ).round(2).to_dict("index")

    return {
        "total_trades":       len(df),
        "wins":               len(wins),
        "losses":             len(losses),
        "win_rate":           round(len(wins) / len(df) * 100, 1),
        "total_pnl_usd":      round(total_pnl, 2),
        "profit_factor":      profit_factor,
        "max_drawdown_usd":   round(max_dd, 2),
        "avg_rr_achieved":    round(df["rr_achieved"].mean(), 2),
        "avg_duration_mins":  round(df["duration_mins"].mean(), 1),
        "max_consec_losses":  max_consec_loss,
        "by_symbol":          by_symbol,
        "trades_df":          df,
    }


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    symbol    = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    setup_tf  = sys.argv[2] if len(sys.argv) > 2 else "H1"
    entry_tf  = sys.argv[3] if len(sys.argv) > 3 else "M5"
    years     = int(sys.argv[4]) if len(sys.argv) > 4 else 1

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

    print(f"Total Trades    : {stats['total_trades']}")
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
