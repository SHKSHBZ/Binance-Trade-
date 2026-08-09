import requests
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION ---
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
TIMEFRAME = "1h"
LIMIT = 200 # Need enough data for 50 EMA

STARTING_CAPITAL = 200.0
RISK_PER_TRADE_PCT = 0.015 # 1.5% Risk to prevent drawdowns
LEVERAGE = 10

# Paper trading state
paper_balance = STARTING_CAPITAL
active_trades = []
active_fvgs = {sym: [] for sym in SYMBOLS}

def get_klines(symbol):
    """Fetches recent OHLCV data from Binance Public API."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={TIMEFRAME}&limit={LIMIT}"
    response = requests.get(url)
    data = response.json()
    
    # Format: [Open time, Open, High, Low, Close, Volume, Close time, ...]
    df = pd.DataFrame(data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    
    # Convert string to float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
        
    return df

def process_symbol(symbol):
    """Scans a symbol for FVGs and checks for trade entries."""
    global paper_balance, active_trades
    
    try:
        df = get_klines(symbol)
    except Exception as e:
        print(f"[{symbol}] Error fetching data: {e}")
        return
        
    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    
    current_price = closes[-1]
    
    # Calculate 4H equivalent EMA-50 on 1H data (EMA-200 on 1H is roughly EMA-50 on 4H)
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    current_ema = df['ema200'].values[-1]
    
    # Update existing trades
    for trade in list(active_trades):
        if trade['symbol'] == symbol:
            if trade['dir'] == 'LONG':
                if lows[-1] <= trade['stop']:
                    print(f"❌ [STOP OUT] {symbol} LONG. Loss: -${trade['risk']:.2f}")
                    paper_balance -= trade['risk']
                    active_trades.remove(trade)
                elif highs[-1] >= trade['target']:
                    profit = trade['risk'] * 1.5
                    print(f"✅ [TAKE PROFIT] {symbol} LONG. Profit: +${profit:.2f}")
                    paper_balance += profit
                    active_trades.remove(trade)
            elif trade['dir'] == 'SHORT':
                if highs[-1] >= trade['stop']:
                    print(f"❌ [STOP OUT] {symbol} SHORT. Loss: -${trade['risk']:.2f}")
                    paper_balance -= trade['risk']
                    active_trades.remove(trade)
                elif lows[-1] <= trade['target']:
                    profit = trade['risk'] * 1.5
                    print(f"✅ [TAKE PROFIT] {symbol} SHORT. Profit: +${profit:.2f}")
                    paper_balance += profit
                    active_trades.remove(trade)
    
    # Clean up expired FVGs
    active_fvgs[symbol] = [f for f in active_fvgs[symbol] if not f['mitigated']]

    # We look at the most recently COMPLETED 3-candle sequence (indices -4, -3, -2)
    # because index -1 is the currently forming candle that hasn't closed yet.
    if len(closes) > 4:
        # Bullish FVG
        if lows[-2] > highs[-4] and closes[-3] > opens[-3]:
            gap_bottom = highs[-4]
            gap_top = lows[-2]
            ob_stop = min(lows[-4], lows[-3], lows[-2]) - (current_price * 0.001) # Small buffer
            target = highs[-2] + abs(highs[-2] - ob_stop) * 1.5
            
            # Ensure it's not already logged
            if not any(f['top'] == gap_top for f in active_fvgs[symbol]):
                print(f"🔍 [{symbol}] New BULLISH FVG Detected between {gap_bottom:.2f} and {gap_top:.2f}")
                active_fvgs[symbol].append({
                    'dir': 'LONG', 'top': gap_top, 'bottom': gap_bottom,
                    'ob_stop': ob_stop, 'target': target, 'mitigated': False
                })
                
        # Bearish FVG
        elif highs[-2] < lows[-4] and closes[-3] < opens[-3]:
            gap_bottom = highs[-2]
            gap_top = lows[-4]
            ob_stop = max(highs[-4], highs[-3], highs[-2]) + (current_price * 0.001)
            target = lows[-2] - abs(ob_stop - lows[-2]) * 1.5
            
            if not any(f['bottom'] == gap_bottom for f in active_fvgs[symbol]):
                print(f"🔍 [{symbol}] New BEARISH FVG Detected between {gap_bottom:.2f} and {gap_top:.2f}")
                active_fvgs[symbol].append({
                    'dir': 'SHORT', 'top': gap_top, 'bottom': gap_bottom,
                    'ob_stop': ob_stop, 'target': target, 'mitigated': False
                })

    # Check for Entries (Mitigation of existing FVGs)
    for fvg in active_fvgs[symbol]:
        if fvg['mitigated']: continue
        
        # Trend check
        trend = "LONG" if current_price > current_ema else "SHORT"
        
        if fvg['dir'] == 'LONG' and trend == 'LONG':
            # Price touches the top of the gap
            if lows[-1] <= fvg['top'] and current_price >= fvg['ob_stop']:
                print(f"🚀 [ENTRY] BUY {symbol} @ {current_price:.2f} | Stop: {fvg['ob_stop']:.2f} | Target: {fvg['target']:.2f}")
                fvg['mitigated'] = True
                active_trades.append({
                    'symbol': symbol, 'dir': 'LONG', 'entry': current_price,
                    'stop': fvg['ob_stop'], 'target': fvg['target'],
                    'risk': paper_balance * RISK_PER_TRADE_PCT
                })
                
        elif fvg['dir'] == 'SHORT' and trend == 'SHORT':
            # Price touches the bottom of the gap
            if highs[-1] >= fvg['bottom'] and current_price <= fvg['ob_stop']:
                print(f"🚀 [ENTRY] SELL {symbol} @ {current_price:.2f} | Stop: {fvg['ob_stop']:.2f} | Target: {fvg['target']:.2f}")
                fvg['mitigated'] = True
                active_trades.append({
                    'symbol': symbol, 'dir': 'SHORT', 'entry': current_price,
                    'stop': fvg['ob_stop'], 'target': fvg['target'],
                    'risk': paper_balance * RISK_PER_TRADE_PCT
                })

def run_bot():
    print(f"🤖 Binance FVG SMC Bot Started in PAPER TRADING Mode.")
    print(f"💰 Starting Balance: ${STARTING_CAPITAL}")
    print(f"📈 Monitoring: {', '.join(SYMBOLS)}\n")
    
    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n--- Scanning Market ({current_time}) --- | Balance: ${paper_balance:.2f} | Active Trades: {len(active_trades)}")
        
        for symbol in SYMBOLS:
            process_symbol(symbol)
            
        print("Sleeping for 60 seconds...")
        time.sleep(60) # Scan every minute for the 1H candle crossing a gap

if __name__ == "__main__":
    run_bot()
