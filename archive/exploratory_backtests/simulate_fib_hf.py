"""
Fibonacci Retracement Backtest Strategy (High Frequency)
========================================================
Key Fixes to generate MORE TRADES:
1. Switched swing detection from 4H to 1H timeframe.
2. Reduced swing lookback to 12 hours (finds many more swings).
3. EMA trend filter moved to 1H EMA-100.
4. Entering at 0.5 Fibonacci level (gets hit more often than 0.618).
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up
DATA_FILE = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

# HIGH FREQUENCY SETTINGS
SWING_LOOKBACK_1H = 12    # Highest/lowest in 12 hours
EMA_PERIOD_1H = 100       # Trend filter
ENTRY_LEVEL = 0.5         # 0.5 gets hit much more often than 0.618
STOP_LEVEL = 1.0          # Stop loss beyond the swing extreme
TARGET_LEVEL = 0.0        # Target the original swing extreme
FORWARD_BARS = 100        # Hold for max ~4 days

def detect_swings(highs, lows, lb):
    sl, sh = [], []
    for i in range(lb, len(lows) - lb):
        wl = lows[i - lb:i + lb + 1]
        wh = highs[i - lb:i + lb + 1]
        if lows[i] == wl.min() and list(wl).count(lows[i]) == 1:
            sl.append(i)
        if highs[i] == wh.max() and list(wh).count(highs[i]) == 1:
            sh.append(i)
    return sl, sh

def simulate_fibonacci():
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    lows = df['low'].values
    highs = df['high'].values
    closes = df['close'].values
    opens = df['open'].values
    times = df.index

    # Swing detection on 1H directly!
    sl_idxs, sh_idxs = detect_swings(highs, lows, SWING_LOOKBACK_1H)
    
    ema = df['close'].ewm(span=EMA_PERIOD_1H, adjust=False).mean().values
    
    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []
    
    last_trade_bar = 0

    for bar in range(50, len(closes)):
        if bar - last_trade_bar < 6: continue # Only 6h cooldown for more trades
        
        # Find the most recent swings before current bar
        recent_sls = [i for i in sl_idxs if i < bar]
        recent_shs = [i for i in sh_idxs if i < bar]
        
        if not recent_sls or not recent_shs: continue
        
        last_sl_idx = recent_sls[-1]
        last_sh_idx = recent_shs[-1]
        
        ev = ema[bar]
        direction = None
        
        # Determine the leg direction based on which swing happened last
        if last_sl_idx > last_sh_idx:
            # Last swing was a LOW. Price fell from HIGH to LOW. Bear leg.
            # Look for a SHORT on the bounce.
            leg_high = highs[last_sh_idx]
            leg_low = lows[last_sl_idx]
            
            # Trend Filter: Only short if price is below EMA
            if closes[bar] < ev:
                entry_price = leg_low + (leg_high - leg_low) * ENTRY_LEVEL
                stop_price = leg_low + (leg_high - leg_low) * STOP_LEVEL 
                target_price = leg_low - (leg_high - leg_low) * 0.272
                
                if highs[bar] >= entry_price and closes[bar] < entry_price:
                    direction = "SHORT"
            
        else:
            # Last swing was a HIGH. Price rose from LOW to HIGH. Bull leg.
            # Look for a LONG on the pullback.
            leg_low = lows[last_sl_idx]
            leg_high = highs[last_sh_idx]
            
            # Trend Filter: Only long if price is above EMA
            if closes[bar] > ev:
                entry_price = leg_high - (leg_high - leg_low) * ENTRY_LEVEL
                stop_price = leg_high - (leg_high - leg_low) * STOP_LEVEL
                target_price = leg_high + (leg_high - leg_low) * 0.272
                
                if lows[bar] <= entry_price and closes[bar] > entry_price:
                    direction = "LONG"
                
        if not direction: continue
        
        exec_price = closes[bar]
        
        if direction == "SHORT" and stop_price <= exec_price: continue
        if direction == "LONG" and stop_price >= exec_price: continue
        
        stop_dist = abs(exec_price - stop_price)
        target_dist = abs(target_price - exec_price)
        if stop_dist == 0: continue
        
        # Reduced R:R requirement to allow more trades
        if (target_dist / stop_dist) < 0.8: continue
        
        risk_amt = capital * RISK_PER_TRADE_PCT
        pos_usd = min((risk_amt / stop_dist) * exec_price, capital * LEVERAGE)
        qty = pos_usd / exec_price
        
        exit_p = exit_r = None
        end = min(bar + FORWARD_BARS, len(closes))
        
        for j in range(bar + 1, end):
            if direction == "SHORT":
                if highs[j] >= stop_price:
                    exit_p, exit_r = stop_price, "STOP"
                    break
                if lows[j] <= target_price:
                    exit_p, exit_r = target_price, "TARGET"
                    break
            else:
                if lows[j] <= stop_price:
                    exit_p, exit_r = stop_price, "STOP"
                    break
                if highs[j] >= target_price:
                    exit_p, exit_r = target_price, "TARGET"
                    break
                    
        if exit_p is None:
            exit_p, exit_r = closes[end-1], "TIME"
            
        if direction == "LONG": pnl = qty * (exit_p - exec_price)
        else: pnl = qty * (exec_price - exit_p)
        
        comm = qty * exec_price * COMMISSION_PCT + qty * exit_p * COMMISSION_PCT
        net = pnl - comm
        
        capital += net
        if capital <= 0: capital = 0
        if capital > peak: peak = capital
        dd = (peak - capital) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
        
        trades.append({
            'dir': direction,
            'time': times[bar],
            'entry': exec_price,
            'stop': stop_price,
            'target': target_price,
            'pnl': net,
            'bal': capital,
            'exit_r': exit_r
        })
        
        last_trade_bar = bar
        if capital <= 0: break
        
    return trades, capital, max_dd

if __name__ == "__main__":
    print("Running High Frequency Fibonacci Retracement Strategy...")
    trades, final, mdd = simulate_fibonacci()
    wins = len([t for t in trades if t['pnl'] > 0])
    
    print("\nTRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")
    
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Max DD: {mdd:.1f}%")
