"""
Backtester — RSI Fixed-Target Reversal (EURGBP).

Simple version:
  - H1 RSI(14) < 10 → BUY immediately, SL 50 points, TP 300 points (1:6)
  - H1 RSI(14) > 90 → SELL immediately, SL 50 points, TP 300 points
  - 1 point = 0.00001 (5-digit); SL = 5 pips, TP = 30 pips
  - One trade per extreme episode (re-arms once RSI leaves the zone)

Usage:
    python backtest_rsi_fixed.py                 # EURGBP 3y
    python backtest_rsi_fixed.py EURGBP 3
"""

import sys
import pandas as pd

from config import (
    RSI_FIX_PERIOD, RSI_FIX_OB, RSI_FIX_OS,
    RSI_FIX_SL_POINTS, RSI_FIX_TP_POINTS, FIXED_RISK_USD,
)
from indicators import calculate_rsi
from backtest import load_csv, compute_stats


def point_size(symbol: str) -> float:
    """Smallest price increment (5-digit FX = 0.00001, 3-digit JPY = 0.001)."""
    return 0.001 if "JPY" in symbol else 0.00001


def run_rsi_fixed(symbol: str, h1: pd.DataFrame, m5: pd.DataFrame) -> list[dict]:
    h1 = h1.copy().reset_index(drop=True)
    m5 = m5.copy().reset_index(drop=True)
    h1["rsi"] = calculate_rsi(h1["close"], RSI_FIX_PERIOD)

    h1r = h1[["time", "rsi"]].copy()
    h1r["time"] = h1r["time"] + pd.Timedelta(hours=1)   # H1 close time
    h1r = h1r.rename(columns={"rsi": "h1_rsi"})
    m5 = pd.merge_asof(m5.sort_values("time"), h1r.sort_values("time"),
                       on="time", direction="backward").reset_index(drop=True)

    pt      = point_size(symbol)
    sl_dist = RSI_FIX_SL_POINTS * pt
    tp_dist = RSI_FIX_TP_POINTS * pt
    rr      = RSI_FIX_TP_POINTS / RSI_FIX_SL_POINTS

    trades           = []
    trade_open_until = None
    traded_os = traded_ob = False   # one trade per episode

    for i in range(len(m5)):
        c = m5.iloc[i]
        r = c["h1_rsi"]
        if pd.isna(r):
            continue
        if trade_open_until is not None:
            if c["time"] <= trade_open_until:
                continue
            trade_open_until = None

        direction = None
        if r < RSI_FIX_OS:
            if not traded_os:
                direction, traded_os = "LONG", True
        else:
            traded_os = False
        if r > RSI_FIX_OB:
            if not traded_ob:
                direction, traded_ob = "SHORT", True
        else:
            traded_ob = False

        if direction is None:
            continue

        entry_price = c["close"]
        if direction == "LONG":
            sl_price, tp_price = entry_price - sl_dist, entry_price + tp_dist
        else:
            sl_price, tp_price = entry_price + sl_dist, entry_price - tp_dist

        # Walk forward (from next candle) until SL or TP
        result = "OPEN"; exit_price = exit_time = None
        for j in range(i + 1, len(m5)):
            row = m5.iloc[j]
            if direction == "LONG":
                if row["low"] <= sl_price:
                    result, exit_price, exit_time = "SL", sl_price, row["time"]; break
                if row["high"] >= tp_price:
                    result, exit_price, exit_time = "TP", tp_price, row["time"]; break
            else:
                if row["high"] >= sl_price:
                    result, exit_price, exit_time = "SL", sl_price, row["time"]; break
                if row["low"] <= tp_price:
                    result, exit_price, exit_time = "TP", tp_price, row["time"]; break

        if result == "OPEN":
            continue

        trade_open_until = exit_time
        rr_achieved = rr if result == "TP" else -1.0
        pnl_usd     = round(FIXED_RISK_USD * rr_achieved, 2)

        trades.append({
            "symbol":        symbol,
            "entry_time":    c["time"],
            "exit_time":     exit_time,
            "entry_price":   round(entry_price, 5),
            "sl_price":      round(sl_price, 5),
            "tp_price":      round(tp_price, 5),
            "exit_price":    round(exit_price, 5),
            "sl_pips":       RSI_FIX_SL_POINTS,
            "rr_planned":    round(rr, 1),
            "rr_achieved":   round(rr_achieved, 2),
            "result":        result,
            "pnl_usd":       pnl_usd,
            "duration_mins": int((exit_time - c["time"]).total_seconds() / 60),
            "h1_rsi":        round(float(r), 1),
            "mother_high":   direction,
            "mother_low":    "",
        })

    return trades


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURGBP"
    years  = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    print(f"\nLoading {symbol} H1 + M5 ({years}y)...")
    h1 = load_csv(symbol, "H1", years)
    m5 = load_csv(symbol, "M5", years)
    if h1 is None or m5 is None:
        sys.exit(1)

    print(f"H1 {len(h1)} | M5 {len(m5)} candles")
    print(f"Data span : {m5['time'].min()} -> {m5['time'].max()}")
    print(f"Rule: RSI(14) <{RSI_FIX_OS} buy / >{RSI_FIX_OB} sell | "
          f"SL {RSI_FIX_SL_POINTS}pts TP {RSI_FIX_TP_POINTS}pts\n")

    trades = run_rsi_fixed(symbol, h1, m5)
    stats  = compute_stats(trades)
    if not stats:
        print("No trades found (RSI-14 rarely reaches 10/90 on EURGBP).")
        sys.exit(0)

    tdf = pd.DataFrame(trades)
    tdf["year"] = pd.to_datetime(tdf["entry_time"]).dt.year
    print("Per-year:")
    for yr, g in tdf.groupby("year"):
        w  = (g.pnl_usd > 0).sum()
        pf = g[g.pnl_usd > 0].pnl_usd.sum() / abs(g[g.pnl_usd <= 0].pnl_usd.sum()) if (g.pnl_usd <= 0).any() else float("inf")
        print(f"  {yr} | trades {len(g):3d} | WR {round(w/len(g)*100,1):5}% | PF {round(pf,2):5} | P&L ${round(g.pnl_usd.sum(),2):8}")

    print(f"\nTotal Trades    : {stats['total_trades']}")
    print(f"Wins / Losses   : {stats['wins']} / {stats['losses']}")
    print(f"Win Rate        : {stats['win_rate']}%")
    print(f"Total P&L       : ${stats['total_pnl_usd']}")
    print(f"Profit Factor   : {stats['profit_factor']}")
    print(f"Max Drawdown    : ${stats['max_drawdown_usd']}")
    print(f"Avg RR Achieved : {stats['avg_rr_achieved']}")
    print(f"\nGenerating HTML report...")

    from report import generate_report
    generate_report(stats, symbol, "RSIfix", "M5", years)
