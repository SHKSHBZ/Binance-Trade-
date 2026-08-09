import os
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
import json

# --- LOAD SECRETS ---
load_dotenv()
API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_SECRET_KEY")

if not API_KEY or not API_SECRET:
    print("❌ ERROR: Could not find API keys in .env file!")
    exit(1)

# --- CONFIGURATION ---
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
TIMEFRAME = Client.KLINE_INTERVAL_1HOUR
LIMIT = 200 
RISK_PER_TRADE_PCT = 0.015 
LEVERAGE = 10
STATE_FILE = "state.json"

try:
    client = Client(API_KEY, API_SECRET, testnet=True)
    is_futures = True
    try:
        balance_info = client.futures_account_balance()
        account_balance = float([b['balance'] for b in balance_info if b['asset'] == 'USDT'][0])
    except Exception as e:
        is_futures = False
        balance_info = client.get_asset_balance(asset='USDT')
        account_balance = float(balance_info['free']) if balance_info else 0.0
except Exception as e:
    print(f"❌ Connection Error: {e}")
    exit(1)

active_fvgs = {sym: [] for sym in SYMBOLS}
recent_logs = []

def log_msg(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    recent_logs.insert(0, full_msg)
    if len(recent_logs) > 50:
        recent_logs.pop()

def save_state():
    state = {
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "balance": account_balance,
        "is_futures": is_futures,
        "fvgs": active_fvgs,
        "logs": recent_logs
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def get_market_data(symbol):
    if is_futures:
        klines = client.futures_klines(symbol=symbol, interval=TIMEFRAME, limit=LIMIT)
    else:
        klines = client.get_klines(symbol=symbol, interval=TIMEFRAME, limit=LIMIT)
        
    df = pd.DataFrame(klines, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    return df

def scan_for_trades():
    global account_balance
    log_msg(f"Scanning {len(SYMBOLS)} pairs...")

    # Fetch all open positions to enforce 1-trade limit
    open_positions = {}
    try:
        if is_futures:
            positions = client.futures_position_information()
            for p in positions:
                amt = float(p['positionAmt'])
                if amt > 0:
                    open_positions[p['symbol']] = 'LONG'
                elif amt < 0:
                    open_positions[p['symbol']] = 'SHORT'
    except Exception as e:
        log_msg(f"Error fetching positions: {e}")

    for symbol in SYMBOLS:
        try:
            df = get_market_data(symbol)
        except Exception as e:
            log_msg(f"[{symbol}] Error fetching data: {e}")
            continue

        closes = df['close'].values
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        current_price = closes[-1]
        
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        current_ema = df['ema200'].values[-1]
        
        # Detect FVGs
        if len(closes) > 4:
            if lows[-2] > highs[-4] and closes[-3] > opens[-3]:
                gap_bottom, gap_top = highs[-4], lows[-2]
                ob_stop = min(lows[-4], lows[-3], lows[-2]) - (current_price * 0.001)
                target = highs[-2] + abs(highs[-2] - ob_stop) * 1.5
                if not any(f['top'] == gap_top for f in active_fvgs[symbol]):
                    log_msg(f"🔍 [{symbol}] BULL FVG: {gap_bottom:.2f} -> {gap_top:.2f}")
                    active_fvgs[symbol].append({
                        'dir': 'LONG', 'top': gap_top, 'bottom': gap_bottom,
                        'ob_stop': ob_stop, 'target': target, 'mitigated': False,
                        'detected_at': datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
            elif highs[-2] < lows[-4] and closes[-3] < opens[-3]:
                gap_bottom, gap_top = highs[-2], lows[-4]
                ob_stop = max(highs[-4], highs[-3], highs[-2]) + (current_price * 0.001)
                target = lows[-2] - abs(ob_stop - lows[-2]) * 1.5
                if not any(f['bottom'] == gap_bottom for f in active_fvgs[symbol]):
                    log_msg(f"🔍 [{symbol}] BEAR FVG: {gap_bottom:.2f} -> {gap_top:.2f}")
                    active_fvgs[symbol].append({
                        'dir': 'SHORT', 'top': gap_top, 'bottom': gap_bottom,
                        'ob_stop': ob_stop, 'target': target, 'mitigated': False,
                        'detected_at': datetime.now().strftime("%Y-%m-%d %H:%M")
                    })

        # Check Entries & Passive Mitigation
        for fvg in active_fvgs[symbol]:
            if fvg['mitigated']: continue
            
            # 1. Passive Mitigation (Did price touch the FVG?)
            touched_long = (fvg['dir'] == 'LONG' and lows[-1] <= fvg['top'])
            touched_short = (fvg['dir'] == 'SHORT' and highs[-1] >= fvg['bottom'])
            
            if touched_long or touched_short:
                # Instantly clear it off the radar because market touched it
                fvg['mitigated'] = True
                
                # 2. Execution Phase
                trend = "LONG" if current_price > current_ema else "SHORT"
                
                # The Sniper Limit: Abort execution if we are already in a trade
                if symbol in open_positions:
                    current_pos_dir = open_positions[symbol]
                    if fvg['dir'] != current_pos_dir:
                        log_msg(f"🚨 [{symbol}] Opposing {fvg['dir']} signal detected! REVERSING POSITION...")
                        close_position(symbol, current_pos_dir)
                        del open_positions[symbol]
                    else:
                        log_msg(f"🛡️ [{symbol}] Blocked trade. 1-Trade Sniper Limit active.")
                        continue
                    
                # Check if price is still safe to enter (hasn't blown past stop loss in this 1min loop)
                if fvg['dir'] == 'LONG' and trend == 'LONG' and current_price >= fvg['ob_stop']:
                    execute_trade(symbol, 'BUY', current_price, fvg['ob_stop'], fvg['target'])
                    open_positions[symbol] = 'LONG'
                elif fvg['dir'] == 'SHORT' and trend == 'SHORT' and current_price <= fvg['ob_stop']:
                    execute_trade(symbol, 'SELL', current_price, fvg['ob_stop'], fvg['target'])
                    open_positions[symbol] = 'SHORT'

    # After full scan, fetch updated balance to save state
    try:
        balance_info = client.futures_account_balance()
        account_balance = float([b['balance'] for b in balance_info if b['asset'] == 'USDT'][0])
    except: pass
    save_state()

# Store precision info
symbol_precisions = {}
try:
    if is_futures:
        ex_info = client.futures_exchange_info()
    else:
        ex_info = client.get_exchange_info()
        
    for s in ex_info['symbols']:
        if s['symbol'] in SYMBOLS:
            symbol_precisions[s['symbol']] = s['quantityPrecision'] if is_futures else s['baseAssetPrecision']
except Exception as e:
    print(f"Error fetching precision: {e}")

def close_position(symbol, current_pos_dir):
    try:
        # Cancel all open orders (TP/SL)
        client.futures_cancel_all_open_orders(symbol=symbol)
        
        # Get exact position size
        positions = client.futures_position_information(symbol=symbol)
        amt = abs(float(positions[0]['positionAmt']))
        
        if amt > 0:
            # Market order to close
            side = 'SELL' if current_pos_dir == 'LONG' else 'BUY'
            client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=amt,
                reduceOnly=True
            )
            log_msg(f"🔪 [{symbol}] Successfully closed {current_pos_dir} position (Cut Losses).")
    except Exception as e:
        log_msg(f"❌ Error closing position for {symbol}: {e}")

def execute_trade(symbol, side, entry_price, stop_price, target_price):
    log_msg(f"🚀 [TRADE] {side} {symbol} @ {entry_price:.2f}")
    stop_dist = abs(entry_price - stop_price)
    risk_amt = account_balance * RISK_PER_TRADE_PCT
    pos_usd = min((risk_amt / stop_dist) * entry_price, account_balance * LEVERAGE)
    
    # Use exact precision for the symbol, default to 3 if unknown
    precision = symbol_precisions.get(symbol, 3)
    qty = round(pos_usd / entry_price, precision)
    
    try:
        if is_futures:
            client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)
            
            # 1. Place the Entry Order
            entry_order = client.futures_create_order(symbol=symbol, side=side, type='MARKET', quantity=qty)
            log_msg(f"✅ Entry Filled: {entry_order.get('orderId')}")
            
            # 2. Place the Stop Loss Order
            opposite_side = 'SELL' if side == 'BUY' else 'BUY'
            
            # Format prices to match tick size precision (usually 2 for USD-M pairs, but 1 or 2 is safe)
            # A simple round(price, 2) works for most USDT pairs, but to be robust we just round to 2.
            stop_price_formatted = round(stop_price, 2)
            target_price_formatted = round(target_price, 2)

            sl_order = client.futures_create_order(
                symbol=symbol,
                side=opposite_side,
                type='STOP_MARKET',
                stopPrice=stop_price_formatted,
                closePosition=True
            )
            log_msg(f"🛡️ Stop Loss Placed @ {stop_price_formatted}")
            
            # 3. Place the Take Profit Order
            tp_order = client.futures_create_order(
                symbol=symbol,
                side=opposite_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=target_price_formatted,
                closePosition=True
            )
            log_msg(f"🎯 Take Profit Placed @ {target_price_formatted}")
            
    except Exception as e:
        log_msg(f"❌ Execution Error: {e}")

if __name__ == "__main__":
    log_msg(f"Starting Bot. Balance: ${account_balance:.2f}")
    save_state()
    while True:
        scan_for_trades()
        time.sleep(60)
