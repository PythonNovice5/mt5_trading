"""
Backtester — RSI Extreme Reversal (EURGBP).

Per the idea:
  - H1 RSI(14) > 80  → arm SHORT while it stays above 80
  - H1 RSI(14) < 20  → arm LONG  while it stays below 20
  - SHORT: first RED M5 candle → sell at its close, SL = its high, TP = 1:5
  - LONG : first GREEN M5 candle → buy at its close, SL = its low, TP = 1:5
  - Min stop floor (RSI_REV_MIN_SL_PIPS); widen SL if the candle is tinier
  - Re-entry allowed while still in the zone (one trade at a time)

Usage:
    python backtest_rsi.py                 # EURGBP H1 M5 3y
    python backtest_rsi.py EURGBP 3
"""

import sys
import pandas as pd

from config import (
    RSI_REV_PERIOD, RSI_REV_OB, RSI_REV_OS,
    RSI_REV_MIN_SL_PIPS, RSI_REV_TARGET_RR, RSI_REV_CONFIRM, FIXED_RISK_USD,
)
from indicators import calculate_rsi
from backtest import load_csv, compute_stats, pip_size, pips


def run_rsi(symbol: str, h1: pd.DataFrame, m5: pd.DataFrame) -> list[dict]:
    h1 = h1.copy().reset_index(drop=True)
    m5 = m5.copy().reset_index(drop=True)
    h1["rsi"] = calculate_rsi(h1["close"], RSI_REV_PERIOD)

    # Attach latest completed H1 RSI to each M5 candle (H1 close = open + 1h)
    h1r = h1[["time", "rsi"]].copy()
    h1r["time"] = h1r["time"] + pd.Timedelta(hours=1)
    h1r = h1r.rename(columns={"rsi": "h1_rsi"})
    m5 = pd.merge_asof(m5.sort_values("time"), h1r.sort_values("time"),
                       on="time", direction="backward").reset_index(drop=True)

    psize    = pip_size(symbol)
    min_dist = RSI_REV_MIN_SL_PIPS * psize
    rr       = RSI_REV_TARGET_RR

    trades           = []
    trade_open_until = None

    for i in range(len(m5)):
        c      = m5.iloc[i]
        h1_rsi = c["h1_rsi"]
        if pd.isna(h1_rsi):
            continue

        # Skip candles covered by an open simulated trade
        if trade_open_until is not None:
            if c["time"] <= trade_open_until:
                continue
            trade_open_until = None

        # Which zone are we in?
        if h1_rsi > RSI_REV_OB:
            direction = "SHORT"
        elif h1_rsi < RSI_REV_OS:
            direction = "LONG"
        else:
            continue  # not extreme → nothing armed

        # Need the trigger candle in the reversal direction
        is_red   = c["close"] < c["open"]
        is_green = c["close"] > c["open"]
        if direction == "SHORT" and not is_red:
            continue
        if direction == "LONG" and not is_green:
            continue

        # Confirmation: trigger candle must CLOSE beyond the previous candle's
        # extreme (a real break, not just a down/up tick) → higher-quality entries
        if RSI_REV_CONFIRM and i > 0:
            prev = m5.iloc[i - 1]
            if direction == "SHORT" and not (c["close"] < prev["low"]):
                continue
            if direction == "LONG" and not (c["close"] > prev["high"]):
                continue

        entry_price = c["close"]
        if direction == "SHORT":
            sl_price = c["high"]
            sl_dist  = max(sl_price - entry_price, min_dist)
            sl_price = entry_price + sl_dist
            tp_price = entry_price - sl_dist * rr
        else:
            sl_price = c["low"]
            sl_dist  = max(entry_price - sl_price, min_dist)
            sl_price = entry_price - sl_dist
            tp_price = entry_price + sl_dist * rr

        # ── Simulate forward (from next candle) until SL or TP ──
        result = "OPEN"; exit_price = exit_time = None
        for j in range(i + 1, len(m5)):
            row = m5.iloc[j]
            if direction == "SHORT":
                if row["high"] >= sl_price:
                    result, exit_price, exit_time = "SL", sl_price, row["time"]; break
                if row["low"] <= tp_price:
                    result, exit_price, exit_time = "TP", tp_price, row["time"]; break
            else:
                if row["low"] <= sl_price:
                    result, exit_price, exit_time = "SL", sl_price, row["time"]; break
                if row["high"] >= tp_price:
                    result, exit_price, exit_time = "TP", tp_price, row["time"]; break

        if result == "OPEN":
            continue

        trade_open_until = exit_time
        if direction == "SHORT":
            rr_achieved = (entry_price - exit_price) / sl_dist
        else:
            rr_achieved = (exit_price - entry_price) / sl_dist
        pnl_usd = round(FIXED_RISK_USD * rr_achieved, 2)

        trades.append({
            "symbol":        symbol,
            "entry_time":    c["time"],
            "exit_time":     exit_time,
            "entry_price":   round(entry_price, 5),
            "sl_price":      round(sl_price, 5),
            "tp_price":      round(tp_price, 5),
            "exit_price":    round(exit_price, 5),
            "sl_pips":       pips(sl_dist, symbol),
            "rr_planned":    rr,
            "rr_achieved":   round(rr_achieved, 2),
            "result":        result,
            "pnl_usd":       pnl_usd,
            "duration_mins": int((exit_time - c["time"]).total_seconds() / 60),
            "h1_rsi":        round(float(h1_rsi), 1),
            "mother_high":   round(c["high"], 5),
            "mother_low":    round(c["low"], 5),
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
    print("Running RSI extreme reversal backtest...\n")

    trades = run_rsi(symbol, h1, m5)
    stats  = compute_stats(trades)
    if not stats:
        print("No trades found.")
        sys.exit(0)

    tdf = pd.DataFrame(trades)
    tdf["year"] = pd.to_datetime(tdf["entry_time"]).dt.year
    longs = int((tdf["h1_rsi"] < RSI_REV_OS + 50).sum())  # informational only
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
    print(f"Max Consec Loss : {stats['max_consec_losses']}")
    print(f"\nGenerating HTML report...")

    from report import generate_report
    generate_report(stats, symbol, "RSIrev", "M5", years)
