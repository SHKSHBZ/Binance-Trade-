import os
from dotenv import load_dotenv
from binance.client import Client
import json

load_dotenv()
API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_SECRET_KEY")

client = Client(API_KEY, API_SECRET, testnet=True)

print("Checking Order 28530518414...")
try:
    order = client.futures_get_order(symbol="BTCUSDT", orderId=28530518414)
    print(f"Status: {order['status']}")
    print(f"Executed Qty: {order['executedQty']}")
except Exception as e:
    print(f"Error fetching order: {e}")

print("\nChecking Open Positions...")
try:
    positions = client.futures_position_information()
    open_positions = [p for p in positions if float(p['positionAmt']) != 0]
    if open_positions:
        for p in open_positions:
            print(f"Symbol: {p['symbol']} | Amt: {p['positionAmt']} | Unrealized PnL: {p['unRealizedProfit']}")
    else:
        print("No open positions found.")
except Exception as e:
    print(f"Error fetching positions: {e}")
