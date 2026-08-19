"""
Exact Replica Backtest of binance_live_bot.py (BTCUSDT only)
================================================================
This mirrors the actual uploaded live bot's logic as closely as a
historical OHLCV backtest allows:

  - Trend filter: 20 EMA on 1H, current price vs EMA.
  - FVG: identical 3-candle gap detection/ob_stop/target formulas as
    the live code (target = gap_top + 1.5*(gap_top - ob_stop) for
    LONG, symmetric for SHORT).
  - FVG expiry: 48 hours (matches the live code's wall-clock check).
  - Entry: price touches the FVG while trend still agrees, one trade
    at a time per symbol (Sniper Limit).
  - Risk: 1.5% of balance per trade (RISK_PER_TRADE_PCT = 0.015).
  - Leverage: up to 10x, capped at 80% margin (effective 8x) --
    matches the live code's "Strict 80% Margin Safety Cap".

Limitation: the live bot trades BTCUSDT + ETHUSDT + SOLUSDT + BNBUSDT
concurrently. This repo only has BTCUSDT historical data, so this
backtest covers BTCUSDT only -- it cannot reproduce the full 4-symbol
behavior. Commission (0.04% per side) is added since the live code
doesn't model it, but real trading would incur it.
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up

STARTING_CAPITAL = 1000.0
RISK_PER_TRADE_PCT = 0.015   # matches the live bot exactly
LEVERAGE = 10                # matches the live bot exactly
MARGIN_SAFETY_CAP = 0.8      # matches the live bot's "Strict 80% Margin Safety Cap"
COMMISSION_PCT = 0.0004

EMA_PERIOD = 20
FVG_EXPIRY_HOURS = 48        # matches the live bot's wall-clock expiry
FORWARD_BARS = 500


def simulate_live_bot_exact(data_file, start=None, end=None):
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
    in_position_until_bar = -1

    for bar in range(EMA_PERIOD + 4, n):
        # --- FVG detection (exact formulas from binance_live_bot.py) ---
        if lows[bar-2] > highs[bar-4] and closes[bar-3] > opens[bar-3]:
            gap_bottom, gap_top = highs[bar-4], lows[bar-2]
            ob_stop = min(lows[bar-4], lows[bar-3], lows[bar-2]) - (closes[bar] * 0.001)
            target = gap_top + abs(gap_top - ob_stop) * 1.5
            if not any(f['top'] == gap_top for f in active_fvgs):
                active_fvgs.append({'dir': 'LONG', 'top': gap_top, 'bottom': gap_bottom,
                                     'ob_stop': ob_stop, 'target': target,
                                     'formed_bar': bar, 'mitigated': False})
        elif highs[bar-2] < lows[bar-4] and closes[bar-3] < opens[bar-3]:
            gap_bottom, gap_top = highs[bar-2], lows[bar-4]
            ob_stop = max(highs[bar-4], highs[bar-3], highs[bar-2]) + (closes[bar] * 0.001)
            target = gap_bottom - abs(ob_stop - gap_bottom) * 1.5
            if not any(f['bottom'] == gap_bottom for f in active_fvgs):
                active_fvgs.append({'dir': 'SHORT', 'top': gap_top, 'bottom': gap_bottom,
                                     'ob_stop': ob_stop, 'target': target,
                                     'formed_bar': bar, 'mitigated': False})

        # Expire FVGs older than 48 hours (1H bars, so 48 bars)
        active_fvgs = [f for f in active_fvgs
                       if (bar - f['formed_bar']) < FVG_EXPIRY_HOURS and not f['mitigated']]

        if bar <= in_position_until_bar:
            continue

        current_price = closes[bar]
        trend = "LONG" if current_price > ema20[bar] else "SHORT"

        for fvg in active_fvgs:
            touched_long = (fvg['dir'] == 'LONG' and lows[bar] <= fvg['top'])
            touched_short = (fvg['dir'] == 'SHORT' and highs[bar] >= fvg['bottom'])

            if not (touched_long or touched_short):
                continue

            fvg['mitigated'] = True
            direction = None

            if fvg['dir'] == 'LONG' and trend == 'LONG' and current_price >= fvg['ob_stop']:
                direction = 'LONG'
                entry_price = current_price
            elif fvg['dir'] == 'SHORT' and trend == 'SHORT' and current_price <= fvg['ob_stop']:
                direction = 'SHORT'
                entry_price = current_price

            if not direction:
                continue

            stop_price = fvg['ob_stop']
            target_price = fvg['target']
            stop_dist = abs(entry_price - stop_price)
            if stop_dist == 0:
                continue

            risk_amt = capital * RISK_PER_TRADE_PCT
            pos_usd = min((risk_amt / stop_dist) * entry_price,
                           capital * LEVERAGE * MARGIN_SAFETY_CAP)
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

            pnl = qty * (exit_p - entry_price) if direction == "LONG" else qty * (entry_price - exit_p)
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
                'dir': direction, 'time': times[bar], 'entry': entry_price,
                'stop': stop_price, 'target': target_price, 'pnl': net,
                'bal': capital, 'exit_r': exit_r,
                'position_usd': pos_usd
            })

            in_position_until_bar = exit_bar
            break

        if capital <= 0:
            break

    return trades, capital, max_dd


if __name__ == "__main__":
    datasets = [
        ("2023-2025 (contains known Jan-2023 bad data window)", "BTCUSDT_1h_2023_to_2025.csv", None, None),
        ("2025 only", "BTCUSDT_1h_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
        ("Jan-Jul 2026", "BTCUSDT_1h_Jan_to_Jul2026.csv", None, None),
    ]

    print("Exact Replica Backtest of binance_live_bot.py (BTCUSDT only)")
    print(f"Starting Capital: ${STARTING_CAPITAL:.2f} | Risk: {RISK_PER_TRADE_PCT*100}% | "
          f"Leverage: {LEVERAGE}x (capped at {MARGIN_SAFETY_CAP*100:.0f}% margin = "
          f"{LEVERAGE*MARGIN_SAFETY_CAP:.1f}x effective) | Commission: {COMMISSION_PCT*100}%\n")

    for label, fname, start, end in datasets:
        trades, final, mdd = simulate_live_bot_exact(fname, start, end)
        wins = len([t for t in trades if t['pnl'] > 0])
        wr = wins / len(trades) * 100 if trades else 0
        ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        max_pos = max((t['position_usd'] for t in trades), default=0)
        print(f"--- {label} ({fname}) ---")
        print(f"Trades: {len(trades)} | Wins: {wins} | WinRate: {wr:.1f}%")
        print(f"Final Capital: ${final:,.2f} | Return: {ret:,.1f}% | Max DD: {mdd:.1f}%")
        print(f"Largest single position size: ${max_pos:,.2f}\n")
