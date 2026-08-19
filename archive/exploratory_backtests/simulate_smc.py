"""
Smart Money Concepts (SMC) & Fair Value Gap (FVG) Backtester
============================================================
Strategy: 
1. Detect Fair Value Gaps (FVGs) on the 1H timeframe.
2. Filter trades using the 4H EMA-50 to ensure we trade with the macro trend.
3. Wait for price to pull back and mitigate the FVG.
4. Stop Loss is placed beyond the Order Block (the origin of the move).
5. Target is a fixed Risk:Reward or the recent swing extreme.
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

EMA_PERIOD = 50
FORWARD_BARS = 200 # How long to hold a trade max
FVG_EXPIRY_BARS = 48 # An FVG becomes invalid if not tested within 48 bars

def simulate_smc():
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    # 4H EMA for trend filter
    df_4h = df.resample('4h').agg({'close': 'last'}).dropna()
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
    
    active_fvgs = [] # List of dicts: {'dir', 'top', 'bottom', 'ob_stop', 'target', 'expiry'}
    last_trade_bar = 0

    for bar in range(2, len(closes)):
        current_time = times[bar]
        
        # 1. Detect New FVGs at the close of the current bar (using bars bar-2, bar-1, bar)
        # Bullish FVG: Low of current bar > High of 2 bars ago
        if lows[bar] > highs[bar-2] and closes[bar-1] > opens[bar-1]:
            # The gap is between highs[bar-2] and lows[bar]
            gap_bottom = highs[bar-2]
            gap_top = lows[bar]
            
            # The Order Block (OB) is typically the down candle before this impulsive up move.
            # We'll use the low of the 3-candle pattern as a safe structural stop loss.
            ob_stop = min(lows[bar-2], lows[bar-1], lows[bar]) - 10 
            target = highs[bar] + abs(highs[bar] - ob_stop) * 1.5 # 1.5R target
            
            active_fvgs.append({
                'dir': 'LONG',
                'top': gap_top,
                'bottom': gap_bottom,
                'ob_stop': ob_stop,
                'target': target,
                'expiry': bar + FVG_EXPIRY_BARS,
                'mitigated': False
            })
            
        # Bearish FVG: High of current bar < Low of 2 bars ago
        elif highs[bar] < lows[bar-2] and closes[bar-1] < opens[bar-1]:
            # The gap is between highs[bar] and lows[bar-2]
            gap_bottom = highs[bar]
            gap_top = lows[bar-2]
            
            # OB Stop Loss is the high of the 3-candle pattern
            ob_stop = max(highs[bar-2], highs[bar-1], highs[bar]) + 10
            target = lows[bar] - abs(ob_stop - lows[bar]) * 1.5 # 1.5R target
            
            active_fvgs.append({
                'dir': 'SHORT',
                'top': gap_top,
                'bottom': gap_bottom,
                'ob_stop': ob_stop,
                'target': target,
                'expiry': bar + FVG_EXPIRY_BARS,
                'mitigated': False
            })

        # Remove expired FVGs
        active_fvgs = [f for f in active_fvgs if bar <= f['expiry'] and not f['mitigated']]
        
        # 2. Check for entry into active FVGs
        if bar - last_trade_bar < 6: continue # Cooldown
        
        ev = get_ema(current_time)
        if ev is None: continue
        
        for fvg in active_fvgs:
            direction = None
            
            if fvg['dir'] == 'LONG' and closes[bar] > ev:
                # Price drops into the Bullish FVG (touches gap top)
                if lows[bar] <= fvg['top'] and highs[bar] > fvg['top']:
                    direction = 'LONG'
                    entry_price = fvg['top']
                    
            elif fvg['dir'] == 'SHORT' and closes[bar] < ev:
                # Price rises into the Bearish FVG (touches gap bottom)
                if highs[bar] >= fvg['bottom'] and lows[bar] < fvg['bottom']:
                    direction = 'SHORT'
                    entry_price = fvg['bottom']
                    
            if direction:
                fvg['mitigated'] = True # Mark as used
                stop_price = fvg['ob_stop']
                target_price = fvg['target']
                
                stop_dist = abs(entry_price - stop_price)
                if stop_dist == 0: continue
                
                risk_amt = capital * RISK_PER_TRADE_PCT
                pos_usd = min((risk_amt / stop_dist) * entry_price, capital * LEVERAGE)
                qty = pos_usd / entry_price
                
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
                    
                if direction == "LONG": pnl = qty * (exit_p - entry_price)
                else: pnl = qty * (entry_price - exit_p)
                
                comm = qty * entry_price * COMMISSION_PCT + qty * exit_p * COMMISSION_PCT
                net = pnl - comm
                
                capital += net
                if capital <= 0: capital = 0
                if capital > peak: peak = capital
                dd = (peak - capital) / peak * 100 if peak > 0 else 0
                if dd > max_dd: max_dd = dd
                
                trades.append({
                    'dir': direction,
                    'time': times[bar],
                    'entry': entry_price,
                    'stop': stop_price,
                    'target': target_price,
                    'pnl': net,
                    'bal': capital,
                    'exit_r': exit_r
                })
                
                last_trade_bar = bar
                break # Only take one trade at a time
                
        if capital <= 0: break

    return trades, capital, max_dd

if __name__ == "__main__":
    print("Running SMC Fair Value Gap Strategy...")
    trades, final, mdd = simulate_smc()
    wins = len([t for t in trades if t['pnl'] > 0])
    
    print("\nTRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")
    
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Max DD: {mdd:.1f}%")
