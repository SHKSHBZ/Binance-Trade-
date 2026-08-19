"""
Fibonacci Retracement Backtest Strategy (Improved)
==================================================
Key Fixes:
1. Stop Loss set beyond the 1.0 (Swing Extreme) instead of 0.786.
2. Trend filter (EMA-50). Only take trades aligned with 4H trend.
3. Detailed reporting.
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up
DATA_FILE = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.08
COMMISSION_PCT = 0.0004
SWING_LOOKBACK_4H = 8
EMA_PERIOD_4H = 50

ENTRY_LEVEL = 0.618      # Trade the 0.618 retracement
STOP_LEVEL = 1.0       # Stop loss beyond the swing extreme (1.0)
TARGET_LEVEL = 0.0     # Target the original swing extreme

FORWARD_BARS = 300

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
    df_1h = pd.read_csv(fpath)
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], dayfirst=True, format='mixed')
    df_1h.set_index('timestamp', inplace=True)
    df_1h.sort_index(inplace=True)

    df_4h = df_1h.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    sl_idxs, sh_idxs = detect_swings(df_4h['high'].values, df_4h['low'].values, SWING_LOOKBACK_4H)
    
    sl_times = [df_4h.index[i] for i in sl_idxs]
    sh_times = [df_4h.index[i] for i in sh_idxs]
    
    ema = df_4h['close'].ewm(span=EMA_PERIOD_4H, adjust=False).mean()
    
    lows = df_1h['low'].values
    highs = df_1h['high'].values
    closes = df_1h['close'].values
    opens = df_1h['open'].values
    times = df_1h.index

    def get_ema(t):
        best = None
        for e in ema.index:
            if e <= t: best = e
            else: break
        return ema.get(best) if best is not None else None

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []
    
    last_trade_bar = 0

    for bar in range(100, len(closes)):
        if bar - last_trade_bar < 24: continue # 24h cooldown
        
        current_time = times[bar]
        
        recent_sls = [t for t in sl_times if t < current_time]
        recent_shs = [t for t in sh_times if t < current_time]
        
        if not recent_sls or not recent_shs: continue
        
        last_sl_time = recent_sls[-1]
        last_sh_time = recent_shs[-1]
        
        ev = get_ema(current_time)
        if ev is None: continue
        
        direction = None
        
        if last_sl_time > last_sh_time:
            # Most recent swing is a LOW. So price moved from HIGH down to LOW.
            # We look for a SHORT on the bounce.
            leg_high = df_4h.loc[last_sh_time]['high']
            leg_low = df_4h.loc[last_sl_time]['low']
            
            # Trend Filter: Only short if price is below EMA
            if closes[bar] < ev:
                entry_price = leg_low + (leg_high - leg_low) * ENTRY_LEVEL
                stop_price = leg_low + (leg_high - leg_low) * STOP_LEVEL # 1.0 (the swing high)
                target_price = leg_low - (leg_high - leg_low) * 0.272    # Extension
                
                # Check if we touch entry
                if highs[bar] >= entry_price and closes[bar] < entry_price:
                    direction = "SHORT"
            
        else:
            # Most recent swing is a HIGH. Price moved from LOW up to HIGH.
            # Look for a LONG on the pullback.
            leg_low = df_4h.loc[last_sl_time]['low']
            leg_high = df_4h.loc[last_sh_time]['high']
            
            # Trend Filter: Only long if price is above EMA
            if closes[bar] > ev:
                entry_price = leg_high - (leg_high - leg_low) * ENTRY_LEVEL
                stop_price = leg_high - (leg_high - leg_low) * STOP_LEVEL # 1.0 (the swing low)
                target_price = leg_high + (leg_high - leg_low) * 0.272    # Extension
                
                if lows[bar] <= entry_price and closes[bar] > entry_price:
                    direction = "LONG"
                
        if not direction: continue
        
        exec_price = closes[bar]
        
        if direction == "SHORT" and stop_price <= exec_price: continue
        if direction == "LONG" and stop_price >= exec_price: continue
        
        stop_dist = abs(exec_price - stop_price)
        target_dist = abs(target_price - exec_price)
        if stop_dist == 0: continue
        
        if (target_dist / stop_dist) < 1.0: continue
        
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
    print("Running Fibonacci Retracement Strategy...")
    trades, final, mdd = simulate_fibonacci()
    wins = len([t for t in trades if t['pnl'] > 0])
    
    print("\nTRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")
    
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Max DD: {mdd:.1f}%")
