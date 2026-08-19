import json
import os
import subprocess
import time
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from binance.client import Client
import uvicorn

load_dotenv()
API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_SECRET_KEY")

try:
    client = Client(API_KEY, API_SECRET, testnet=True)
except Exception as e:
    print(f"Error connecting to Binance in Server: {e}")
    client = None

app = FastAPI(title="Binance SMC Control Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE_FILE = "state.json"
bot_process = None

# Simple Cache to avoid rate limits
cache = {
    "last_fetch": 0,
    "balance": 0.0,
    "unrealized_pnl": 0.0,
    "recent_trades": []
}

def fetch_binance_data():
    global cache
    now = time.time()
    if now - cache['last_fetch'] < 5:  # Cache for 5 seconds
        return cache
        
    if not client:
        return cache

    try:
        # Fetch Account & PNL
        account = client.futures_account()
        cache['balance'] = float(account['totalWalletBalance'])
        cache['unrealized_pnl'] = float(account['totalUnrealizedProfit'])
        
        # Fetch recent trades for monitored symbols (last 5 total)
        SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        all_trades = []
        for sym in SYMBOLS:
            trades = client.futures_account_trades(symbol=sym, limit=2)
            all_trades.extend(trades)
        
        # Sort by time descending and take top 5
        all_trades.sort(key=lambda x: x['time'], reverse=True)
        
        formatted_trades = []
        for t in all_trades[:5]:
            formatted_trades.append({
                "symbol": t['symbol'],
                "side": "BUY" if t['buyer'] else "SELL",
                "price": float(t['price']),
                "qty": float(t['qty']),
                "realizedPnl": float(t['realizedPnl']),
                "time": t['time']
            })
            
        cache['recent_trades'] = formatted_trades
        cache['last_fetch'] = now
    except Exception as e:
        print(f"Binance API Fetch Error: {e}")
        
    return cache

@app.get("/api/state")
def get_state():
    global bot_process
    binance_data = fetch_binance_data()
    
    bot_state = {
        "fvgs": {"BTCUSDT": [], "ETHUSDT": [], "SOLUSDT": [], "BNBUSDT": []},
        "logs": []
    }
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                bot_state['fvgs'] = saved.get('fvgs', bot_state['fvgs'])
                bot_state['logs'] = saved.get('logs', bot_state['logs'])
        except: pass
        
    is_running = bot_process is not None and bot_process.poll() is None
    
    return {
        "status": "RUNNING" if is_running else "STOPPED",
        "balance": binance_data['balance'],
        "unrealized_pnl": binance_data['unrealized_pnl'],
        "recent_trades": binance_data['recent_trades'],
        "fvgs": bot_state['fvgs'],
        "logs": bot_state['logs']
    }

@app.post("/api/start")
def start_bot():
    global bot_process
    if bot_process is None or bot_process.poll() is not None:
        # Start the bot subprocess
        bot_process = subprocess.Popen(["python", "binance_live_bot.py"])
        return {"status": "started"}
    return {"status": "already running"}

@app.post("/api/stop")
def stop_bot():
    global bot_process
    if bot_process is not None and bot_process.poll() is None:
        bot_process.terminate()
        bot_process.wait()
        bot_process = None
        return {"status": "stopped"}
    return {"status": "already stopped"}

os.makedirs("web", exist_ok=True)

@app.get("/")
def read_root():
    index_path = os.path.join("web", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Web dashboard not built yet."}

app.mount("/", StaticFiles(directory="web"), name="web")

if __name__ == "__main__":
    print("Starting Control Panel Server on http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
