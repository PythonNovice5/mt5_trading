"""
Backtester for the RSI mean-reversion strategy with consolidation rectangle entry.
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
    RSI_PERIOD, RSI_OVERSOLD, SWING_LOOKBACK, MIN_RR, TARGET_RR,
    FIXED_RISK_USD, MAX_OPEN_TRADES, RECT_MIN_CANDLES, RECT_MAX_RANGE_PCT,
)
from indicators import calculate_rsi, get_swing_low_levels


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


# ── CONSOLIDATION RECTANGLE DETECTION ────────────────────────────────────────

def find_consolidation_rect(m5_candles: pd.DataFrame, min_candles: int, max_range_pct: float) -> dict | None:
    """
    Find first consolidation rectangle in m5_candles.
    A rectangle is min_candles+ consecutive candles with high-low range <= max_range_pct.
    Extends the rectangle while adding more candles keeps range within limit.
    Returns {rect_high, rect_low, start_time, end_time, end_pos} or None.
    """
    n = len(m5_candles)
    if n < min_candles:
        return None

    for start in range(n - min_candles + 1):
        window = m5_candles.iloc[start:start + min_candles]
        rect_high = window["high"].max()
        rect_low  = window["low"].min()

        if rect_low <= 0:
            continue

        if (rect_high - rect_low) / rect_low > max_range_pct:
            continue

        # Extend rectangle while range stays tight
        end = start + min_candles
        while end < n:
            new_high = max(rect_high, m5_candles.iloc[end]["high"])
            new_low  = min(rect_low,  m5_candles.iloc[end]["low"])
            if (new_high - new_low) / new_low <= max_range_pct:
                rect_high = new_high
                rect_low  = new_low
                end += 1
            else:
                break

        return {
            "rect_high":  rect_high,
            "rect_low":   rect_low,
            "start_time": m5_candles.iloc[start]["time"],
            "end_time":   m5_candles.iloc[end - 1]["time"],
            "end_pos":    end - 1,
        }

    return None


# ── BACKTEST ENGINE ───────────────────────────────────────────────────────────

def run_backtest(symbol: str, h1: pd.DataFrame, m5: pd.DataFrame) -> list[dict]:
    """
    Walk H1 bars. On RSI < oversold, activate setup.
    Each subsequent H1 bar = one 1-hour observation window on M5.
    If M5 low breaks key_low → shift (max 7). If held → look for rect + entry.
    """
    h1 = h1.copy().reset_index(drop=True)
    m5 = m5.copy().reset_index(drop=True)
    h1["rsi"] = calculate_rsi(h1["close"], RSI_PERIOD)

    MAX_SHIFTS = 7
    trades       = []
    active_setup = None  # {key_low, rsi, shifts, setup_bar}

    for h1_idx in range(RSI_PERIOD + 1, len(h1)):
        h1_candle     = h1.iloc[h1_idx]
        rsi_val       = h1_candle["rsi"]
        h1_open_time  = h1_candle["time"]
        h1_close_time = h1_open_time + pd.Timedelta(hours=1)

        # ── RSI setup ──
        if pd.notna(rsi_val) and rsi_val < RSI_OVERSOLD:
            tag = "NEW" if active_setup is None else "UPD"
            print(f"[RSI {tag}] {symbol} | {h1_open_time} | RSI={round(rsi_val,2)} | Close={h1_candle['close']} | Low={h1_candle['low']}")
            if active_setup is None:
                active_setup = {
                    "key_low":   h1_candle["low"],
                    "rsi":       round(rsi_val, 2),
                    "shifts":    0,
                    "setup_bar": h1_idx,
                }

        if active_setup is None:
            continue

        # Skip the bar that created the setup — observe from the NEXT bar
        if h1_idx == active_setup["setup_bar"]:
            continue

        # ── Observe THIS H1 bar's M5 window only (12 candles) ──
        m5_this_bar = m5[
            (m5["time"] >= h1_open_time) &
            (m5["time"] <  h1_close_time)
        ].reset_index(drop=True)

        if len(m5_this_bar) == 0:
            continue

        # Key low broken → shift
        if m5_this_bar["low"].min() < active_setup["key_low"]:
            active_setup["shifts"] += 1
            active_setup["key_low"] = m5_this_bar["low"].min()
            print(f"  → Low broken — shift {active_setup['shifts']}/{MAX_SHIFTS} | new key_low={round(active_setup['key_low'], 5)}")
            if active_setup["shifts"] >= MAX_SHIFTS:
                print(f"  → Max shifts reached — abandon")
                active_setup = None
            continue

        # Low held — look for consolidation rectangle in this hour
        if len(m5_this_bar) < RECT_MIN_CANDLES:
            continue

        rect = find_consolidation_rect(m5_this_bar, RECT_MIN_CANDLES, RECT_MAX_RANGE_PCT)
        if rect is None:
            continue

        # First M5 candle closing above rect_high after rect ends
        m5_after_rect = m5_this_bar[m5_this_bar["time"] > rect["end_time"]].reset_index(drop=True)
        entry_candle = None
        for _, candle in m5_after_rect.iterrows():
            if candle["close"] > rect["rect_high"]:
                entry_candle = candle
                break

        if entry_candle is None:
            continue

        entry_price = entry_candle["close"]
        sl_price    = rect["rect_low"]
        sl_distance = entry_price - sl_price

        if sl_distance <= 0:
            active_setup = None
            continue

        tp_price = entry_price + sl_distance * TARGET_RR
        rr       = TARGET_RR

        if rr < MIN_RR:
            active_setup = None
            continue

        print(f"  → ENTRY | {entry_candle['time']} | Entry={round(entry_price,5)} SL={round(sl_price,5)} TP={round(tp_price,5)} Rect=[{round(rect['rect_low'],5)},{round(rect['rect_high'],5)}]")

        # ── Walk-forward trade simulation with trailing SL ──
        entry_time = entry_candle["time"]
        m5_forward = m5[m5["time"] > entry_time].reset_index(drop=True)

        result     = "OPEN"
        exit_price = None
        exit_time  = None
        current_sl = sl_price

        for fwd_idx, row in m5_forward.iterrows():
            if row["low"] <= current_sl:
                result     = "SL"
                exit_price = current_sl
                exit_time  = row["time"]
                break
            if row["high"] >= tp_price:
                result     = "TP"
                exit_price = tp_price
                exit_time  = row["time"]
                break
            # Trail SL to confirmed swing low (SWING_LOOKBACK candles each side)
            check_idx = fwd_idx - SWING_LOOKBACK
            if check_idx >= SWING_LOOKBACK:
                candidate_low = m5_forward.iloc[check_idx]["low"]
                left  = [m5_forward.iloc[j]["low"] for j in range(check_idx - SWING_LOOKBACK, check_idx)]
                right = [m5_forward.iloc[j]["low"] for j in range(check_idx + 1, check_idx + SWING_LOOKBACK + 1)]
                if all(candidate_low < l for l in left) and all(candidate_low < r for r in right):
                    if candidate_low > current_sl:
                        current_sl = candidate_low
                        print(f"    → Trail SL → {round(current_sl,5)} at {m5_forward.iloc[check_idx]['time']}")

        if result == "OPEN":
            active_setup = None
            continue

        duration_mins = int((exit_time - entry_time).total_seconds() / 60)
        pnl_usd       = round(FIXED_RISK_USD * rr, 2) if result == "TP" else -FIXED_RISK_USD

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
            "rr_achieved":   round((exit_price - entry_price) / sl_distance, 2),
            "result":        result,
            "pnl_usd":       pnl_usd,
            "duration_mins": duration_mins,
            "rsi_at_setup":  active_setup["rsi"],
            "rect_high":     round(rect["rect_high"], 5),
            "rect_low":      round(rect["rect_low"], 5),
        })

        active_setup = None

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

    equity = FIXED_RISK_USD * 400  # $5000 starting balance
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
