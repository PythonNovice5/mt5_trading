"""
Run the backtest across all pairs in config.SYMBOLS and produce one combined report.

Usage:
    python backtest_all.py            # H1/M5, 1 year (defaults)
    python backtest_all.py H1 M5 1
"""

import sys
from config import SYMBOLS
from backtest import load_csv, run_backtest, compute_stats


def main():
    setup_tf = sys.argv[1] if len(sys.argv) > 1 else "H1"
    entry_tf = sys.argv[2] if len(sys.argv) > 2 else "M5"
    years    = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    all_trades = []
    print(f"\nRunning backtest on {len(SYMBOLS)} pairs ({setup_tf}/{entry_tf}, {years}y)\n")

    for symbol in SYMBOLS:
        h1 = load_csv(symbol, setup_tf, years)
        m5 = load_csv(symbol, entry_tf, years)
        if h1 is None or m5 is None:
            print(f"  {symbol}: data missing — skipped\n")
            continue

        trades = run_backtest(symbol, h1, m5)
        s      = compute_stats(trades)
        all_trades.extend(trades)

        if s:
            print(f"  {symbol:8s} | trades {s['total_trades']:3d} | WR {s['win_rate']:5.1f}% | "
                  f"PF {s['profit_factor']:5.2f} | P&L ${s['total_pnl_usd']:8.2f}")
        else:
            print(f"  {symbol:8s} | no trades")

    print("\n" + "=" * 60)
    all_trades.sort(key=lambda t: t["entry_time"])   # chronological for equity curve/DD
    stats = compute_stats(all_trades)
    if not stats:
        print("No trades across any pair.")
        return

    print(f"COMBINED ({len(SYMBOLS)} pairs)")
    print(f"Total Trades    : {stats['total_trades']}")
    print(f"Wins / Losses   : {stats['wins']} / {stats['losses']}")
    print(f"Win Rate        : {stats['win_rate']}%")
    print(f"Total P&L       : ${stats['total_pnl_usd']}")
    print(f"Profit Factor   : {stats['profit_factor']}")
    print(f"Max Drawdown    : ${stats['max_drawdown_usd']}")
    print(f"Avg RR Achieved : {stats['avg_rr_achieved']}")
    print(f"Max Consec Loss : {stats['max_consec_losses']}")

    print(f"\nGenerating combined HTML report...")
    from report import generate_report
    generate_report(stats, "ALL", setup_tf, entry_tf, years)


if __name__ == "__main__":
    main()
