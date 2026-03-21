"""
MT5 Historical Data Downloader
--------------------------------
- Dynamic symbol, timeframe, and years via command line or direct call
- Supports all major timeframes
- Auto-creates data/ folder if missing
- Validates symbol and timeframe before downloading

Usage examples:
    python download_data.py                        # uses defaults below
    python download_data.py NDX100 H1 1            # symbol, timeframe, years
    python download_data.py US30 M15 2
    python download_data.py NDX100 D1 3
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import os
import sys


# ── DEFAULT PARAMETERS (change these or pass via command line) ──
SYMBOL    = "NDX100"
TIMEFRAME = "H4"
YEARS     = 1


# ── SUPPORTED TIMEFRAMES ──
TIMEFRAME_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
    "W1":  mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}


def download_data(symbol: str, timeframe: str, years: int) -> pd.DataFrame | None:
    """
    Download historical OHLCV data from MT5 and save to CSV.

    Args:
        symbol    : Trading symbol e.g. "NDX100", "US30"
        timeframe : Timeframe string e.g. "M15", "H1", "H4", "D1"
        years     : Number of years of history to download

    Returns:
        DataFrame if successful, None if failed
    """

    # Validate timeframe
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_MAP:
        print(f"❌ Invalid timeframe '{timeframe}'")
        print(f"   Supported: {', '.join(TIMEFRAME_MAP.keys())}")
        return None

    # Connect to MT5
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        print("   Make sure MT5 terminal is open and logged in.")
        return None

    print(f"\n📥 Downloading {symbol} | {timeframe} | {years} year(s)...")

    # Validate symbol
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"❌ Symbol '{symbol}' not found in MT5.")
        print("   Check the exact symbol name in your MT5 Market Watch.")
        mt5.shutdown()
        return None

    # Enable symbol if not visible
    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)

    # Calculate date range
    end_date   = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    # Download rates
    tf    = TIMEFRAME_MAP[timeframe]
    rates = mt5.copy_rates_range(symbol, tf, start_date, end_date)

    if rates is None or len(rates) == 0:
        print(f"❌ No data returned for {symbol} {timeframe}.")
        print(f"   Error: {mt5.last_error()}")
        mt5.shutdown()
        return None

    # Build DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = df.rename(columns={
        'time':       'datetime',
        'open':       'open',
        'high':       'high',
        'low':        'low',
        'close':      'close',
        'tick_volume':'volume',
    })
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
    df = df.sort_values('datetime').reset_index(drop=True)

    # Save to CSV
    os.makedirs("data", exist_ok=True)
    filename = f"data/{symbol}_{timeframe}_{years}y.csv"
    df.to_csv(filename, index=False)

    # Summary
    print(f"✅ Downloaded {len(df):,} candles")
    print(f"   From : {df['datetime'].iloc[0]}")
    print(f"   To   : {df['datetime'].iloc[-1]}")
    print(f"   Saved: {filename}")

    mt5.shutdown()
    return df


def load_data(symbol: str, timeframe: str, years: int) -> pd.DataFrame | None:
    """
    Load previously downloaded data from CSV.
    If file doesn't exist, downloads it first.

    Args:
        symbol    : Trading symbol
        timeframe : Timeframe string
        years     : Years of history

    Returns:
        DataFrame with OHLCV data
    """
    filename = f"data/{symbol}_{timeframe.upper()}_{years}y.csv"

    if os.path.exists(filename):
        print(f"📂 Loading existing data from {filename}...")
        df = pd.read_csv(filename, parse_dates=['datetime'])
        print(f"   Loaded {len(df):,} candles")
        return df
    else:
        print(f"⚠️  File not found: {filename}")
        print("   Downloading fresh data...")
        return download_data(symbol, timeframe, years)


if __name__ == "__main__":
    # Allow command line args: python download_data.py SYMBOL TIMEFRAME YEARS
    symbol    = sys.argv[1] if len(sys.argv) > 1 else SYMBOL
    timeframe = sys.argv[2] if len(sys.argv) > 2 else TIMEFRAME
    years     = int(sys.argv[3]) if len(sys.argv) > 3 else YEARS

    download_data(symbol, timeframe, years)