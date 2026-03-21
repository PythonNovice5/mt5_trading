"""
FundingPips MT5 Trade Execution Bot
------------------------------------
- Designed for Indices (US30, NAS100, etc.)
- Risk: 0.25% of account balance per trade
- Semi-automated: You provide entry/SL/TP, bot handles execution & lot sizing
- Includes FundingPips drawdown protection
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIGURATION — Edit these values
# ──────────────────────────────────────────────

RISK_PERCENT = 0.25          # Risk per trade (% of balance)
MAX_DAILY_LOSS_PERCENT = 4.0 # FundingPips daily drawdown limit (%)
MAX_TOTAL_LOSS_PERCENT = 8.0 # FundingPips max total drawdown limit (%)

# ──────────────────────────────────────────────
# CONNECT TO MT5
# ──────────────────────────────────────────────

def connect():
    """Initialize and connect to MT5 terminal."""
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return False
    account = mt5.account_info()
    print(f"✅ Connected to MT5")
    print(f"   Account  : {account.login}")
    print(f"   Balance  : ${account.balance:,.2f}")
    print(f"   Equity   : ${account.equity:,.2f}")
    print(f"   Server   : {account.server}")
    return True


def disconnect():
    """Shutdown MT5 connection."""
    mt5.shutdown()
    print("🔌 Disconnected from MT5.")


# ──────────────────────────────────────────────
# ACCOUNT & RISK INFO
# ──────────────────────────────────────────────

def get_account_info():
    """Return current account balance and equity."""
    info = mt5.account_info()
    return {
        "balance": info.balance,
        "equity": info.equity,
        "profit": info.profit,
        "margin_free": info.margin_free,
    }


def check_drawdown_limits(initial_balance: float) -> dict:
    """
    Check if FundingPips drawdown limits are breached.
    Returns a dict with status and details.
    """
    info = get_account_info()
    balance = info["balance"]
    equity = info["equity"]

    daily_loss_pct = ((initial_balance - equity) / initial_balance) * 100
    total_loss_pct = ((initial_balance - balance) / initial_balance) * 100

    daily_ok = daily_loss_pct < MAX_DAILY_LOSS_PERCENT
    total_ok = total_loss_pct < MAX_TOTAL_LOSS_PERCENT

    print(f"\n📊 Drawdown Check:")
    print(f"   Daily Loss  : {daily_loss_pct:.2f}% (limit: {MAX_DAILY_LOSS_PERCENT}%) {'✅' if daily_ok else '🚫'}")
    print(f"   Total Loss  : {total_loss_pct:.2f}% (limit: {MAX_TOTAL_LOSS_PERCENT}%) {'✅' if total_ok else '🚫'}")

    return {
        "daily_ok": daily_ok,
        "total_ok": total_ok,
        "safe_to_trade": daily_ok and total_ok,
        "daily_loss_pct": daily_loss_pct,
        "total_loss_pct": total_loss_pct,
    }


# ──────────────────────────────────────────────
# LOT SIZE CALCULATOR
# ──────────────────────────────────────────────

def calculate_lot_size(symbol: str, sl_points: float) -> float:
    """
    Calculate lot size based on:
    - 0.25% of account balance as risk amount
    - SL distance in points
    """
    account = get_account_info()
    balance = account["balance"]
    risk_amount = balance * (RISK_PERCENT / 100)

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"❌ Symbol {symbol} not found.")
        return 0.0

    # Point value per lot
    point = symbol_info.point
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    value_per_point = tick_value / tick_size * point

    if value_per_point == 0 or sl_points == 0:
        print("❌ Cannot calculate lot size — invalid tick value or SL.")
        return 0.0

    lot_size = risk_amount / (sl_points * value_per_point)

    # Normalize to broker's allowed step
    lot_step = symbol_info.volume_step
    lot_size = round(lot_size / lot_step) * lot_step
    lot_size = max(symbol_info.volume_min, min(lot_size, symbol_info.volume_max))

    print(f"\n💰 Risk Calculation:")
    print(f"   Balance     : ${balance:,.2f}")
    print(f"   Risk Amount : ${risk_amount:.2f} ({RISK_PERCENT}%)")
    print(f"   SL Distance : {sl_points:.1f} points")
    print(f"   Lot Size    : {lot_size}")

    return lot_size


# ──────────────────────────────────────────────
# TRADE EXECUTION
# ──────────────────────────────────────────────

def place_trade(symbol: str, direction: str, sl_price: float, tp_price: float, comment: str = "FP Bot"):
    """
    Place a trade on the given symbol.

    Args:
        symbol    : e.g. "US30", "NAS100"
        direction : "buy" or "sell"
        sl_price  : Stop Loss price level
        tp_price  : Take Profit price level
        comment   : Trade comment (shown in MT5)
    """
    print(f"\n{'='*50}")
    print(f"🤖 Placing {direction.upper()} on {symbol}")
    print(f"{'='*50}")

    # Ensure symbol is available
    if not mt5.symbol_select(symbol, True):
        print(f"❌ Could not select symbol: {symbol}")
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"❌ Could not get tick data for {symbol}")
        return None

    # Determine order type and entry price
    if direction.lower() == "buy":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    elif direction.lower() == "sell":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        print("❌ Direction must be 'buy' or 'sell'")
        return None

    # Calculate SL distance and lot size
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point
    sl_points = abs(price - sl_price) / point

    lot = calculate_lot_size(symbol, sl_points)
    if lot == 0:
        print("❌ Lot size is 0 — trade aborted.")
        return None

    # Build trade request
    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    lot,
        "type":      order_type,
        "price":     price,
        "sl":        sl_price,
        "tp":        tp_price,
        "deviation": 20,
        "magic":     20250320,
        "comment":   comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(f"\n📋 Trade Summary:")
    print(f"   Symbol    : {symbol}")
    print(f"   Direction : {direction.upper()}")
    print(f"   Entry     : {price}")
    print(f"   SL        : {sl_price}")
    print(f"   TP        : {tp_price}")
    print(f"   Lot Size  : {lot}")

    # Confirm before sending
    confirm = input("\n⚡ Confirm trade? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("🚫 Trade cancelled by user.")
        return None

    # Send order
    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"\n✅ Trade placed successfully!")
        print(f"   Ticket  : #{result.order}")
        print(f"   Volume  : {result.volume}")
        print(f"   Price   : {result.price}")
    else:
        print(f"\n❌ Trade failed! Error code: {result.retcode}")
        print(f"   Comment : {result.comment}")

    return result


# ──────────────────────────────────────────────
# CLOSE ALL TRADES
# ──────────────────────────────────────────────

def close_all_trades():
    """Close all open positions."""
    positions = mt5.positions_get()
    if not positions:
        print("ℹ️  No open positions to close.")
        return

    print(f"\n🔴 Closing {len(positions)} open position(s)...")

    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        volume = pos.volume

        tick = mt5.symbol_info_tick(symbol)

        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        close_request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    symbol,
            "volume":    volume,
            "type":      order_type,
            "position":  ticket,
            "price":     price,
            "deviation": 20,
            "magic":     20250320,
            "comment":   "Bot close all",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(close_request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"   ✅ Closed #{ticket} ({symbol})")
        else:
            print(f"   ❌ Failed to close #{ticket} — Error: {result.retcode}")


# ──────────────────────────────────────────────
# VIEW OPEN POSITIONS
# ──────────────────────────────────────────────

def show_open_positions():
    """Display all currently open positions."""
    positions = mt5.positions_get()
    if not positions:
        print("ℹ️  No open positions.")
        return

    print(f"\n📂 Open Positions ({len(positions)}):")
    print(f"{'─'*65}")
    print(f"{'Ticket':<10} {'Symbol':<10} {'Type':<6} {'Lots':<6} {'Entry':<10} {'SL':<10} {'TP':<10} {'P&L'}")
    print(f"{'─'*65}")

    for pos in positions:
        direction = "BUY" if pos.type == 0 else "SELL"
        print(f"{pos.ticket:<10} {pos.symbol:<10} {direction:<6} {pos.volume:<6} "
              f"{pos.price_open:<10.2f} {pos.sl:<10.2f} {pos.tp:<10.2f} ${pos.profit:.2f}")


# ──────────────────────────────────────────────
# MAIN MENU
# ──────────────────────────────────────────────

def main():
    print("\n" + "="*50)
    print("  FundingPips MT5 Bot — Indices Day Trader")
    print("="*50)

    if not connect():
        return

    # Store starting balance for drawdown tracking
    initial_balance = get_account_info()["balance"]
    print(f"\n📌 Session start balance: ${initial_balance:,.2f}")

    while True:
        print("\n" + "─"*40)
        print("MENU:")
        print("  1. Place a Trade")
        print("  2. View Open Positions")
        print("  3. Close All Trades")
        print("  4. Check Drawdown Limits")
        print("  5. Exit")
        print("─"*40)

        choice = input("Select option (1-5): ").strip()

        if choice == "1":
            # Check drawdown before trading
            dd = check_drawdown_limits(initial_balance)
            if not dd["safe_to_trade"]:
                print("🚫 Trading blocked — Drawdown limit reached. Protect your account!")
                continue

            symbol    = input("Symbol (e.g. US30, NAS100): ").strip().upper()
            direction = input("Direction (buy/sell): ").strip().lower()
            sl_price  = float(input("Stop Loss price: "))
            tp_price  = float(input("Take Profit price: "))
            comment   = input("Comment (press Enter to skip): ").strip() or "FP Bot"

            place_trade(symbol, direction, sl_price, tp_price, comment)

        elif choice == "2":
            show_open_positions()

        elif choice == "3":
            confirm = input("Close ALL open trades? (yes/no): ").strip().lower()
            if confirm == "yes":
                close_all_trades()

        elif choice == "4":
            check_drawdown_limits(initial_balance)

        elif choice == "5":
            disconnect()
            print("👋 Goodbye! Trade safe.")
            break

        else:
            print("❌ Invalid option. Try again.")


if __name__ == "__main__":
    main()