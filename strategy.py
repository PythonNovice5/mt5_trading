"""
Strategy logic:
  - 1H setup: RSI(14) < 25 → record swing high (SH1) before the low + the low itself
  - 5min entry: higher low formed → 5min candle closes above SH1 → trade
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

from config import (
    RSI_PERIOD, RSI_OVERSOLD, SETUP_EXPIRY_BARS,
    H1_CANDLES, M5_CANDLES, MIN_RR, TARGET_RR,
    MAX_SPREAD_PIPS, FIXED_RISK_USD,
)
from indicators import calculate_rsi, get_swing_high_levels, get_swing_low_levels


# ── MT5 DATA FETCH ─────────────────────────────────────────────────────────────

TF_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}


def get_candles(symbol: str, timeframe: str, n: int) -> pd.DataFrame | None:
    """Fetch last N closed candles for symbol/timeframe. Returns DataFrame or None."""
    tf = TF_MAP.get(timeframe.upper())
    if tf is None:
        return None

    # Fetch n+1 so we can drop the currently forming candle
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n + 1)
    if rates is None or len(rates) < 2:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"tick_volume": "volume"})
    df = df[["time", "open", "high", "low", "close", "volume"]]

    # Drop last row (currently forming candle)
    return df.iloc[:-1].reset_index(drop=True)


# ── SPREAD CHECK ───────────────────────────────────────────────────────────────

def get_spread_pips(symbol: str) -> float:
    """Return current spread in pips."""
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return 999.0

    spread_points = tick.ask - tick.bid
    # For JPY pairs 1 pip = 0.01, others = 0.0001
    pip_size = 0.01 if "JPY" in symbol else 0.0001
    return round(spread_points / pip_size, 1)


# ── 1H SETUP DETECTION ────────────────────────────────────────────────────────

def check_1h_setup(symbol: str) -> dict | None:
    """
    Scan 1H chart for RSI < RSI_OVERSOLD on the last closed candle.
    If triggered, find the last swing high (SH1) BEFORE the low candle.

    Returns setup dict or None.
    """
    df = get_candles(symbol, "H1", H1_CANDLES)
    if df is None or len(df) < RSI_PERIOD + 5:
        return None

    df["rsi"] = calculate_rsi(df["close"], RSI_PERIOD)

    # Check last closed candle
    last = df.iloc[-1]
    if pd.isna(last["rsi"]) or last["rsi"] >= RSI_OVERSOLD:
        return None

    low_candle_idx = len(df) - 1
    low_price      = last["low"]
    low_time       = last["time"]

    # Find last swing high BEFORE this low candle
    swing_highs = get_swing_high_levels(df)
    # Filter only those before the low candle
    prior_highs = [sh for sh in swing_highs if sh["index"] < low_candle_idx]

    if not prior_highs:
        return None

    # Most recent swing high before the low = SH1
    sh1 = prior_highs[-1]

    return {
        "symbol":          symbol,
        "setup_time":      low_time,
        "low_price":       low_price,
        "sh1_price":       sh1["price"],
        "sh1_time":        sh1["time"],
        "expiry_bar":      low_candle_idx + SETUP_EXPIRY_BARS,
        "h1_bar_at_setup": low_candle_idx,
        "rsi_at_setup":    round(last["rsi"], 2),
    }


# ── 5MIN ENTRY DETECTION ──────────────────────────────────────────────────────

def check_entry_signal(symbol: str, setup: dict) -> dict | None:
    """
    On 5min chart:
    1. Find the absolute low (lowest low after setup time)
    2. Confirm a higher swing low has formed after that
    3. Check if last closed candle closes ABOVE SH1

    Returns entry dict or None.
    """
    df = get_candles(symbol, "M5", M5_CANDLES)
    if df is None or len(df) < 20:
        return None

    sh1_price = setup["sh1_price"]
    setup_time = setup["setup_time"]

    # Only look at candles from setup time onward
    df_after = df[df["time"] >= setup_time].reset_index(drop=True)
    if len(df_after) < 10:
        return None

    # Step 1: Find absolute low after setup
    abs_low_idx   = df_after["low"].idxmin()
    abs_low_price = df_after.loc[abs_low_idx, "low"]

    # Step 2: Find swing lows after the absolute low
    df_post_low = df_after.iloc[abs_low_idx:].reset_index(drop=True)
    swing_lows  = get_swing_low_levels(df_post_low)

    # Need at least 2 swing lows to confirm higher low
    if len(swing_lows) < 2:
        return None

    last_sl  = swing_lows[-1]
    prev_sl  = swing_lows[-2]

    # Confirm higher low: last swing low > previous swing low
    if last_sl["price"] <= prev_sl["price"]:
        return None

    # Step 3: Last closed candle closes above SH1
    last_candle = df.iloc[-1]
    if last_candle["close"] <= sh1_price:
        return None

    # We have a valid entry signal
    entry_price = last_candle["close"]
    sl_price    = last_candle["low"] - _pip_buffer(symbol)

    sl_distance = entry_price - sl_price
    if sl_distance <= 0:
        return None

    tp_1_3 = entry_price + (sl_distance * MIN_RR)
    tp_1_5 = entry_price + (sl_distance * TARGET_RR)

    # Find next swing high above SH1 on 5min for TP target
    swing_highs  = get_swing_high_levels(df)
    above_sh1    = [sh for sh in swing_highs if sh["price"] > sh1_price and sh["price"] > entry_price]
    next_sh_tp   = above_sh1[0]["price"] if above_sh1 else None

    # TP = furthest of 1:5 or next swing high, minimum 1:3
    if next_sh_tp and next_sh_tp > tp_1_5:
        tp_price = next_sh_tp
    else:
        tp_price = tp_1_5

    # RR check — must be at least 1:3
    achieved_rr = (tp_price - entry_price) / sl_distance
    if achieved_rr < MIN_RR:
        return None

    return {
        "symbol":      symbol,
        "entry_price": round(entry_price, 5),
        "sl_price":    round(sl_price, 5),
        "tp_price":    round(tp_price, 5),
        "sl_distance": round(sl_distance, 5),
        "rr":          round(achieved_rr, 2),
        "signal_time": last_candle["time"],
        "sh1_price":   sh1_price,
    }


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _pip_buffer(symbol: str) -> float:
    """1 pip buffer below SL candle low."""
    return 0.01 if "JPY" in symbol else 0.0001


def is_spread_ok(symbol: str) -> bool:
    return get_spread_pips(symbol) <= MAX_SPREAD_PIPS


def calculate_lot_size(symbol: str, sl_distance: float) -> float:
    """
    Lot size based on fixed risk in USD.
    Reuses tick value from MT5 symbol info.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0

    tick_value = info.trade_tick_value
    tick_size  = info.trade_tick_size
    point      = info.point

    value_per_point = tick_value / tick_size * point
    if value_per_point == 0:
        return 0.0

    sl_points = sl_distance / point
    lot       = FIXED_RISK_USD / (sl_points * value_per_point)

    lot = round(lot / info.volume_step) * info.volume_step
    lot = max(info.volume_min, min(lot, info.volume_max))
    return round(lot, 2)
