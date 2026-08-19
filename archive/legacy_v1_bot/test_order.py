import os
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException

load_dotenv()
API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_SECRET_KEY")

try:
    print("Connecting to Binance Futures Testnet...")
    client = Client(API_KEY, API_SECRET, testnet=True)
    
    # Verify Balance
    balance_info = client.futures_account_balance()
    usdt_balance = float([b['balance'] for b in balance_info if b['asset'] == 'USDT'][0])
    print(f"✅ Connection Successful! Current Balance: ${usdt_balance:.2f} USDT")

    # Set leverage to 1x for safety on the test order
    symbol = "BTCUSDT"
    # Place a tiny Market Buy Order (0.01 BTC)
    qty = 0.01 
    print(f"\nPlacing Market BUY Order for {qty} {symbol}...")
    
    order = client.futures_create_order(
        symbol=symbol,
        side='BUY',
        type='MARKET',
        quantity=qty
    )
    
    print("\n✅ Order Executed Successfully!")
    print(f"Order ID: {order['orderId']}")
    print(f"Status: {order['status']}")
    print(f"Executed Qty: {order['executedQty']}")
    
except BinanceAPIException as e:
    print(f"\n❌ Binance API Error: {e}")
except Exception as e:
    print(f"\n❌ Unexpected Error: {e}")
