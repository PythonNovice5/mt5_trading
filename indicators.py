"""
Technical indicator calculations.
No external TA libraries — pure pandas/numpy only.
"""

import numpy as np
import pandas as pd
from config import SWING_LOOKBACK


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI — matches TradingView/MT5 standard calculation."""
    delta = closes.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)

    avg_gain = np.zeros(len(closes))
    avg_loss = np.zeros(len(closes))

    # First value: simple average
    avg_gain[period] = gain.iloc[1:period + 1].mean()
    avg_loss[period] = loss.iloc[1:period + 1].mean()

    # Wilder's smoothing for remaining values
    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss.iloc[i]) / period

    avg_gain = pd.Series(avg_gain, index=closes.index)
    avg_loss = pd.Series(avg_loss, index=closes.index)

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi.iloc[:period] = np.nan
    return rsi


def find_swing_highs(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> pd.Series:
    """
    Returns a boolean Series — True where a confirmed swing high exists.
    A swing high at index i: high[i] > all highs within [i-lookback, i+lookback].
    """
    highs = df["high"]
    is_swing = pd.Series(False, index=df.index)

    for i in range(lookback, len(df) - lookback):
        window = highs.iloc[i - lookback: i + lookback + 1]
        if highs.iloc[i] == window.max() and list(window).count(highs.iloc[i]) == 1:
            is_swing.iloc[i] = True

    return is_swing


def find_swing_lows(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> pd.Series:
    """
    Returns a boolean Series — True where a confirmed swing low exists.
    A swing low at index i: low[i] < all lows within [i-lookback, i+lookback].
    """
    lows = df["low"]
    is_swing = pd.Series(False, index=df.index)

    for i in range(lookback, len(df) - lookback):
        window = lows.iloc[i - lookback: i + lookback + 1]
        if lows.iloc[i] == window.min() and list(window).count(lows.iloc[i]) == 1:
            is_swing.iloc[i] = True

    return is_swing


def get_swing_high_levels(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> list[dict]:
    """Returns list of confirmed swing highs as {index, time, price}."""
    mask = find_swing_highs(df, lookback)
    results = []
    for i in df.index[mask]:
        results.append({
            "index": i,
            "time":  df.loc[i, "time"],
            "price": df.loc[i, "high"],
        })
    return results


def get_swing_low_levels(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> list[dict]:
    """Returns list of confirmed swing lows as {index, time, price}."""
    mask = find_swing_lows(df, lookback)
    results = []
    for i in df.index[mask]:
        results.append({
            "index": i,
            "time":  df.loc[i, "time"],
            "price": df.loc[i, "low"],
        })
    return results
