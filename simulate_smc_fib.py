"""
SMC FVG + Fibonacci Golden Pocket Confluence
============================================
Strategy: 
1. Detect 1H Fair Value Gaps (FVGs).
2. Detect 32-hour Swings (4H lookback=8).
3. The "Institutional Confluence": Only take trades where the 0.618 Fib 
   retracement level falls INSIDE the Fair Value Gap.
4. Enter exactly at the 0.618 level. Stop Loss beyond the Swing Extreme (1.0).
5. Target the Swing Extension (-0.272).
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
DATA_FILE = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

SWING_LOOKBACK_4H = 8
EMA_PERIOD = 50
FIB_LEVEL = 0.618
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

def simulate_confluence():
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    # 4H data for swings and EMA
    df_4h = df.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    sl_idxs, sh_idxs = detect_swings(df_4h['high'].values, df_4h['low'].values, SWING_LOOKBACK_4H)
    sl_times = [df_4h.index[i] for i in sl_idxs]
    sh_times = [df_4h.index[i] for i in sh_idxs]
    
    df_4h['ema'] = df_4h['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    
    lows = df['low'].values
    highs = df['high'].values
    closes = df['close'].values
    opens = df['open'].values
    times = df.index

    def get_ema(t):
        best = None
        for e in df_4h.index:
            if e <= t: best = e
            else: break
        return df_4h['ema'].get(best) if best is not None else None

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []
    
    active_fvgs = [] 
    last_trade_bar = 0

    for bar in range(50, len(closes)):
        current_time = times[bar]
        
        # 1. Detect 1H FVGs
        if lows[bar] > highs[bar-2] and closes[bar-1] > opens[bar-1]:
            active_fvgs.append({
                'dir': 'LONG', 'top': lows[bar], 'bottom': highs[bar-2], 
                'expiry': bar + 48, 'mitigated': False
            })
        elif highs[bar] < lows[bar-2] and closes[bar-1] < opens[bar-1]:
            active_fvgs.append({
                'dir': 'SHORT', 'top': lows[bar-2], 'bottom': highs[bar], 
                'expiry': bar + 48, 'mitigated': False
            })

        active_fvgs = [f for f in active_fvgs if bar <= f['expiry'] and not f['mitigated']]
        
        if bar - last_trade_bar < 24: continue
        
        # 2. Find Recent Swings for Fib
        recent_sls = [t for t in sl_times if t < current_time]
        recent_shs = [t for t in sh_times if t < current_time]
        if not recent_sls or not recent_shs: continue
        
        last_sl_time = recent_sls[-1]
        last_sh_time = recent_shs[-1]
        
        ev = get_ema(current_time)
        if ev is None: continue
        
        direction = None
        
        # Determine current swing leg direction
        if last_sl_time > last_sh_time:
            # Bear Leg -> Pulling up -> Look for SHORT
            leg_high = df_4h.loc[last_sh_time]['high']
            leg_low = df_4h.loc[last_sl_time]['low']
            
            if closes[bar] < ev:
                fib_618 = leg_low + (leg_high - leg_low) * FIB_LEVEL
                stop_price = leg_high
                target_price = leg_low - (leg_high - leg_low) * 0.272
                
                # Check CONFLUENCE: Does the 0.618 level fall inside any active BEARISH FVG?
                confluence = False
                for fvg in active_fvgs:
                    if fvg['dir'] == 'SHORT' and fvg['bottom'] <= fib_618 <= fvg['top']:
                        confluence = True
                        fvg['mitigated'] = True
                        break
                        
                if confluence:
                    if highs[bar] >= fib_618 and closes[bar] < fib_618:
                        direction = "SHORT"
                        entry_price = fib_618
        else:
            # Bull Leg -> Pulling down -> Look for LONG
            leg_low = df_4h.loc[last_sl_time]['low']
            leg_high = df_4h.loc[last_sh_time]['high']
            
            if closes[bar] > ev:
                fib_618 = leg_high - (leg_high - leg_low) * FIB_LEVEL
                stop_price = leg_low
                target_price = leg_high + (leg_high - leg_low) * 0.272
                
                # Check CONFLUENCE: Does the 0.618 level fall inside any active BULLISH FVG?
                confluence = False
                for fvg in active_fvgs:
                    if fvg['dir'] == 'LONG' and fvg['bottom'] <= fib_618 <= fvg['top']:
                        confluence = True
                        fvg['mitigated'] = True
                        break
                        
                if confluence:
                    if lows[bar] <= fib_618 and closes[bar] > fib_618:
                        direction = "LONG"
                        entry_price = fib_618
                        
        if not direction: continue
        
        # Execute Trade
        exec_price = closes[bar]
        if direction == "SHORT" and stop_price <= exec_price: continue
        if direction == "LONG" and stop_price >= exec_price: continue
        
        stop_dist = abs(exec_price - stop_price)
        if stop_dist == 0: continue
        
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
    print("Running SMC + Fibonacci Confluence Strategy...")
    trades, final, mdd = simulate_confluence()
    wins = len([t for t in trades if t['pnl'] > 0])
    
    print("\nTRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")
    
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Max DD: {mdd:.1f}%")
