"""
EMA20 Trend Filter + FVG Sniper Entry Backtester (1H)
========================================================
Tests the exact rule set as described:

1. Trend Filter (The Shield): 20 EMA on the 1H chart.
   - Price above EMA20 -> only LONG setups allowed.
   - Price below EMA20 -> only SHORT setups allowed.

2. Setup: Fair Value Gaps (3-candle imbalance pattern) on 1H candles.

3. Entry (The Sniper Shot): no immediate entry on FVG formation.
   Wait for price to retrace and touch (mitigate) the FVG zone while
   still on the correct side of EMA20.

4. Risk & Reward:
   - Stop Loss: just past the extreme wick of the 3-candle formation.
   - Position Sizing: sized so a stop-loss hit costs exactly 5% of
     account balance, using up to 50x leverage.
   - Take Profit: exactly 1.5x the stop-loss distance, measured from
     the actual entry price (not from the impulse candle's high/low).

One trade at a time (Sniper Limit) -- no new entry is considered while
a position is open, matching the live bot's single-position behavior.
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")

STARTING_CAPITAL = 1000.0
LEVERAGE = 50
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

EMA_PERIOD = 20
STOP_BUFFER_PCT = 0.001   # small buffer past the wick, consistent with the rest of the suite
FORWARD_BARS = 500        # generous max hold time before a time-based exit
FVG_EXPIRY_BARS = 48      # an FVG not mitigated within ~2 days (1H bars) is discarded as stale


def simulate_ema20_fvg_sniper(data_file, start=None, end=None):
    fpath = os.path.join(DATA_DIR, data_file)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    if start or end:
        df = df.loc[start:end]

    df['ema20'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()

    lows = df['low'].values
    highs = df['high'].values
    closes = df['close'].values
    opens = df['open'].values
    times = df.index
    ema20 = df['ema20'].values
    n = len(closes)

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []

    active_fvgs = []
    in_position_until_bar = -1  # Sniper Limit: no new entry while a trade is "open"

    for bar in range(EMA_PERIOD + 2, n):
        # --- 2. Detect FVGs (3-candle imbalance) ---
        if lows[bar] > highs[bar-2] and closes[bar-1] > opens[bar-1]:
            gap_top = lows[bar]
            ob_stop = min(lows[bar-2], lows[bar-1], lows[bar]) * (1 - STOP_BUFFER_PCT)
            active_fvgs.append({'dir': 'LONG', 'top': gap_top, 'ob_stop': ob_stop,
                                 'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False})
        elif highs[bar] < lows[bar-2] and closes[bar-1] < opens[bar-1]:
            gap_bottom = highs[bar]
            ob_stop = max(highs[bar-2], highs[bar-1], highs[bar]) * (1 + STOP_BUFFER_PCT)
            active_fvgs.append({'dir': 'SHORT', 'bottom': gap_bottom, 'ob_stop': ob_stop,
                                 'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False})

        active_fvgs = [f for f in active_fvgs if bar <= f['expiry'] and not f['mitigated']]

        # --- Sniper Limit: skip entry logic while a position is open ---
        if bar <= in_position_until_bar:
            continue

        # --- 1. Trend Filter: 20 EMA ---
        above_ema = closes[bar] > ema20[bar]
        below_ema = closes[bar] < ema20[bar]

        # --- 3. Entry: price retraces into the FVG while on the correct side of EMA20 ---
        for fvg in active_fvgs:
            direction = None

            if fvg['dir'] == 'LONG' and above_ema:
                if lows[bar] <= fvg['top']:
                    direction = 'LONG'
                    entry_price = fvg['top']

            elif fvg['dir'] == 'SHORT' and below_ema:
                if highs[bar] >= fvg['bottom']:
                    direction = 'SHORT'
                    entry_price = fvg['bottom']

            if direction:
                fvg['mitigated'] = True
                stop_price = fvg['ob_stop']
                stop_dist = abs(entry_price - stop_price)
                if stop_dist == 0:
                    continue

                # --- 4. Take Profit: exactly 1.5x stop distance, from entry ---
                if direction == 'LONG':
                    target_price = entry_price + stop_dist * 1.5
                else:
                    target_price = entry_price - stop_dist * 1.5

                # --- Position Sizing: 5% risk, up to 50x leverage ---
                risk_amt = capital * RISK_PER_TRADE_PCT
                pos_usd = min((risk_amt / stop_dist) * entry_price, capital * LEVERAGE)
                qty = pos_usd / entry_price

                exit_p = exit_r = None
                exit_bar = None
                end = min(bar + FORWARD_BARS, n)

                for j in range(bar + 1, end):
                    if direction == "SHORT":
                        if highs[j] >= stop_price:
                            exit_p, exit_r, exit_bar = stop_price, "STOP", j
                            break
                        if lows[j] <= target_price:
                            exit_p, exit_r, exit_bar = target_price, "TARGET", j
                            break
                    else:
                        if lows[j] <= stop_price:
                            exit_p, exit_r, exit_bar = stop_price, "STOP", j
                            break
                        if highs[j] >= target_price:
                            exit_p, exit_r, exit_bar = target_price, "TARGET", j
                            break

                if exit_p is None:
                    exit_p, exit_r, exit_bar = closes[end-1], "TIME", end - 1

                if direction == "LONG":
                    pnl = qty * (exit_p - entry_price)
                else:
                    pnl = qty * (entry_price - exit_p)

                comm = qty * entry_price * COMMISSION_PCT + qty * exit_p * COMMISSION_PCT
                net = pnl - comm

                capital += net
                if capital <= 0:
                    capital = 0
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

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

                in_position_until_bar = exit_bar
                break

        if capital <= 0:
            break

    return trades, capital, max_dd


if __name__ == "__main__":
    datasets = [
        ("2023-2025", "BTCUSDT_1h_2023_to_2025.csv", None, None),
        ("Jan-Jul 2026", "BTCUSDT_1h_Jan_to_Jul2026.csv", None, None),
    ]

    print("EMA20 Trend Filter + FVG Sniper Entry Backtester (1H)")
    print(f"Starting Capital: ${STARTING_CAPITAL:.2f} | Risk: {RISK_PER_TRADE_PCT*100}% | "
          f"Leverage: up to {LEVERAGE}x | Commission: {COMMISSION_PCT*100}%\n")

    for label, fname, start, end in datasets:
        trades, final, mdd = simulate_ema20_fvg_sniper(fname, start, end)
        wins = len([t for t in trades if t['pnl'] > 0])
        wr = wins / len(trades) * 100 if trades else 0
        ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        print(f"--- {label} ({fname}) ---")
        print(f"Trades: {len(trades)} | Wins: {wins} | WinRate: {wr:.1f}%")
        print(f"Final Capital: ${final:,.2f} | Return: {ret:,.1f}% | Max DD: {mdd:.1f}%\n")

        print("First 10 trades:")
        for i, t in enumerate(trades[:10], 1):
            m = "+" if t['pnl'] >= 0 else "-"
            print(f"  #{i:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} "
                  f"Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")
        print()
