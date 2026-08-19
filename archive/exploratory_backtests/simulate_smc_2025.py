import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up
DATA_FILE = "BTCUSDT_1h_2023_to_2025.csv"

STARTING_CAPITAL = 1000.0
LEVERAGE = 50
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

EMA_PERIOD = 50
FORWARD_BARS = 200
FVG_EXPIRY_BARS = 48

def simulate_smc():
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    # Filter for 2025 data only
    df = df[df.index.year == 2025]

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
    
    active_fvgs = []
    last_trade_bar = 0

    for bar in range(2, len(closes)):
        current_time = times[bar]
        
        # Bullish FVG
        if lows[bar] > highs[bar-2] and closes[bar-1] > opens[bar-1]:
            gap_bottom = highs[bar-2]
            gap_top = lows[bar]
            ob_stop = min(lows[bar-2], lows[bar-1], lows[bar]) - 10 
            target = highs[bar] + abs(highs[bar] - ob_stop) * 1.5 
            
            active_fvgs.append({
                'dir': 'LONG', 'top': gap_top, 'bottom': gap_bottom,
                'ob_stop': ob_stop, 'target': target, 'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False
            })
            
        # Bearish FVG
        elif highs[bar] < lows[bar-2] and closes[bar-1] < opens[bar-1]:
            gap_bottom = highs[bar]
            gap_top = lows[bar-2]
            ob_stop = max(highs[bar-2], highs[bar-1], highs[bar]) + 10
            target = lows[bar] - abs(ob_stop - lows[bar]) * 1.5 
            
            active_fvgs.append({
                'dir': 'SHORT', 'top': gap_top, 'bottom': gap_bottom,
                'ob_stop': ob_stop, 'target': target, 'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False
            })

        active_fvgs = [f for f in active_fvgs if bar <= f['expiry'] and not f['mitigated']]
        
        if bar - last_trade_bar < 6: continue 
        
        ev = get_ema(current_time)
        if ev is None: continue
        
        for fvg in active_fvgs:
            direction = None
            if fvg['dir'] == 'LONG' and closes[bar] > ev:
                if lows[bar] <= fvg['top'] and highs[bar] > fvg['top']:
                    direction = 'LONG'
                    entry_price = fvg['top']
            elif fvg['dir'] == 'SHORT' and closes[bar] < ev:
                if highs[bar] >= fvg['bottom'] and lows[bar] < fvg['bottom']:
                    direction = 'SHORT'
                    entry_price = fvg['bottom']
                    
            if direction:
                fvg['mitigated'] = True
                stop_price = fvg['ob_stop']
                target_price = fvg['target']
                
                stop_dist = abs(entry_price - stop_price)
                if stop_dist == 0: continue
                
                # Check for 50x leverage liquidation! 
                # If stop is wider than 1.9%, we get liquidated before hitting stop loss.
                liq_dist = entry_price * (0.95 / LEVERAGE)
                if stop_dist > liq_dist:
                    stop_price = entry_price - liq_dist if direction == 'LONG' else entry_price + liq_dist
                    exit_r_override = "LIQUIDATED"
                else:
                    exit_r_override = "STOP"
                
                risk_amt = capital * RISK_PER_TRADE_PCT
                pos_usd = min((risk_amt / stop_dist) * entry_price, capital * LEVERAGE)
                qty = pos_usd / entry_price
                
                exit_p = exit_r = None
                end = min(bar + FORWARD_BARS, len(closes))
                
                for j in range(bar + 1, end):
                    if direction == "SHORT":
                        if highs[j] >= stop_price:
                            exit_p, exit_r = stop_price, exit_r_override
                            break
                        if lows[j] <= target_price:
                            exit_p, exit_r = target_price, "TARGET"
                            break
                    else:
                        if lows[j] <= stop_price:
                            exit_p, exit_r = stop_price, exit_r_override
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
                    'dir': direction, 'time': times[bar],
                    'entry': entry_price, 'stop': stop_price, 'target': target_price,
                    'pnl': net, 'bal': capital, 'exit_r': exit_r
                })
                last_trade_bar = bar
                break 
                
        if capital <= 0: break

    return trades, capital, max_dd

if __name__ == "__main__":
    print("Running SMC 2025 Strategy (50X Leverage | $1000 Start)...")
    trades, final, mdd = simulate_smc()
    wins = len([t for t in trades if t['pnl'] > 0])
    
    print("\nTRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")
    
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Max DD: {mdd:.1f}%")
