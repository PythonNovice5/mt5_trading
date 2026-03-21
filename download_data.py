import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta


# PARAMETERS
SYMBOL = "NDX100"
TIMEFRAME = "H4"
YEARS = 1


# MT5 TIMEFRAME MAP
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1
}


def download_data(symbol, timeframe, years):

    mt5.initialize()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    tf = TIMEFRAME_MAP[timeframe]

    rates = mt5.copy_rates_range(
        symbol,
        tf,
        start_date,
        end_date
    )

    df = pd.DataFrame(rates)

    df['time'] = pd.to_datetime(df['time'], unit='s')

    filename = f"data/{symbol}_{timeframe}_{years}y.csv"

    df.to_csv(filename, index=False)

    print(f"Downloaded {len(df)} candles")
    print(f"Saved to {filename}")

    mt5.shutdown()


if __name__ == "__main__":
    download_data(SYMBOL, TIMEFRAME, YEARS)