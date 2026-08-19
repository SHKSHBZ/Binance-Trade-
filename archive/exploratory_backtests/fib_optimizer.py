"""
Fibonacci Strategy Optimizer
============================
Runs a grid search over multiple parameters to find the absolute BEST 
combination for Maximum Profit and sufficient Trade Count.
"""

import pandas as pd
import numpy as np
import os
import itertools

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up
DATA_FILE = "BTCUSDT_1h_Jan_to_Jul2026.csv"
STARTING_CAPITAL = 200.0
LEVERAGE = 10
COMMISSION_PCT = 0.0004
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

def simulate_fibonacci(df_1h, df_4h, lb, entry_lvl, ema_len, risk):
    sl_idxs, sh_idxs = detect_swings(df_4h['high'].values, df_4h['low'].values, lb)
    sl_times = [df_4h.index[i] for i in sl_idxs]
    sh_times = [df_4h.index[i] for i in sh_idxs]
    
    ema = df_4h['close'].ewm(span=ema_len, adjust=False).mean()
    
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
    trades = 0
    wins = 0
    last_trade_bar = 0

    for bar in range(50, len(closes)):
        if bar - last_trade_bar < 12: continue
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
            leg_high = df_4h.loc[last_sh_time]['high']
            leg_low = df_4h.loc[last_sl_time]['low']
            if closes[bar] < ev:
                entry_price = leg_low + (leg_high - leg_low) * entry_lvl
                stop_price = leg_low + (leg_high - leg_low) * 1.0 
                target_price = leg_low - (leg_high - leg_low) * 0.272
                if highs[bar] >= entry_price and closes[bar] < entry_price:
                    direction = "SHORT"
        else:
            leg_low = df_4h.loc[last_sl_time]['low']
            leg_high = df_4h.loc[last_sh_time]['high']
            if closes[bar] > ev:
                entry_price = leg_high - (leg_high - leg_low) * entry_lvl
                stop_price = leg_high - (leg_high - leg_low) * 1.0
                target_price = leg_high + (leg_high - leg_low) * 0.272
                if lows[bar] <= entry_price and closes[bar] > entry_price:
                    direction = "LONG"
                
        if not direction: continue
        exec_price = closes[bar]
        if direction == "SHORT" and stop_price <= exec_price: continue
        if direction == "LONG" and stop_price >= exec_price: continue
        
        stop_dist = abs(exec_price - stop_price)
        target_dist = abs(target_price - exec_price)
        if stop_dist == 0 or (target_dist / stop_dist) < 1.0: continue
        
        risk_amt = capital * risk
        pos_usd = min((risk_amt / stop_dist) * exec_price, capital * LEVERAGE)
        qty = pos_usd / exec_price
        
        exit_p = None
        end = min(bar + FORWARD_BARS, len(closes))
        for j in range(bar + 1, end):
            if direction == "SHORT":
                if highs[j] >= stop_price: exit_p = stop_price; break
                if lows[j] <= target_price: exit_p = target_price; break
            else:
                if lows[j] <= stop_price: exit_p = stop_price; break
                if highs[j] >= target_price: exit_p = target_price; break
        if exit_p is None: exit_p = closes[end-1]
            
        if direction == "LONG": pnl = qty * (exit_p - exec_price)
        else: pnl = qty * (exec_price - exit_p)
        
        comm = qty * exec_price * COMMISSION_PCT + qty * exit_p * COMMISSION_PCT
        net = pnl - comm
        
        capital += net
        trades += 1
        if net > 0: wins += 1
        last_trade_bar = bar
        if capital <= 0: break
        
    return trades, wins, capital

if __name__ == "__main__":
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df_1h = pd.read_csv(fpath)
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], dayfirst=True, format='mixed')
    df_1h.set_index('timestamp', inplace=True)
    df_1h.sort_index(inplace=True)
    df_4h = df_1h.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()

    lookbacks = [5, 8, 12, 15, 20]
    entry_levels = [0.382, 0.5, 0.618, 0.786]
    ema_lengths = [20, 50, 100]
    risks = [0.05, 0.08, 0.10]
    
    results = []
    
    print("Running Grid Search Optimizer for Fibonacci...")
    total = len(lookbacks) * len(entry_levels) * len(ema_lengths) * len(risks)
    count = 0
    
    for lb, el, ema, rsk in itertools.product(lookbacks, entry_levels, ema_lengths, risks):
        count += 1
        tr, w, cap = simulate_fibonacci(df_1h, df_4h, lb, el, ema, rsk)
        if tr >= 15:  # Require at least 15 trades to be considered valid
            results.append({
                'lb': lb, 'entry': el, 'ema': ema, 'risk': rsk,
                'trades': tr, 'wins': w, 'cap': cap
            })
            
    print("\nTOP 10 STRATEGIES BY PROFIT (Min 15 trades):")
    results.sort(key=lambda x: x['cap'], reverse=True)
    for i, res in enumerate(results[:10]):
        wr = res['wins']/res['trades']*100
        print(f"#{i+1} | LB: {res['lb']:2} | Fib: {res['entry']} | EMA: {res['ema']:3} | Risk: {res['risk']*100:2.0f}% | "
              f"Trades: {res['trades']:3} | WR: {wr:4.1f}% | Final Cap: ${res['cap']:.2f}")
