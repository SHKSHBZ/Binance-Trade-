"""
2-Day Support/Resistance Bounce Backtester (15M execution)
=============================================================
Variant of simulate_daily_sr_bounce.py using a wider reference window:

  - Resistance = High of the previous 2-day block
  - Support    = Low of the previous 2-day block

Days are grouped into non-overlapping 2-day blocks (e.g. Jan1-2,
Jan3-4, ...). Each block trades against the high/low of the block
before it. Rule: BUY when price wicks into Support and closes back
above it. SELL when price wicks into Resistance and closes back below
it. Target is the opposite level; stop is a small buffer beyond the
level tested.

Everything else (risk sizing, commission, cooldown) is identical to
simulate_daily_sr_bounce.py so the two window lengths can be compared
directly.
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up
DATA_FILE = "BTCUSDT_15m_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

STOP_BUFFER_PCT = 0.001    # stop placed 0.1% beyond the tested level
COOLDOWN_BARS = 6          # min bars between trades (mirrors rest of the suite)
FORWARD_BARS = 200

BLOCK_DAYS = 2


def simulate_2day_sr_bounce(stop_buffer_pct=STOP_BUFFER_PCT):
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    lows = df['low'].values
    highs = df['high'].values
    closes = df['close'].values
    times = df.index

    # --- Previous 2-Day Block High (resistance) / Low (support) ---
    day_key = df.index.normalize()
    day_number = (day_key - day_key.min()).days
    block_key = day_number // BLOCK_DAYS

    df_block = pd.DataFrame({'block': block_key, 'high': highs, 'low': lows})
    df_block = df_block.groupby('block').agg(high=('high', 'max'), low=('low', 'min'))
    df_block['prev_high'] = df_block['high'].shift(1)
    df_block['prev_low'] = df_block['low'].shift(1)

    resistance = pd.Series(block_key).map(df_block['prev_high']).values
    support = pd.Series(block_key).map(df_block['prev_low']).values

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []
    last_trade_bar = -COOLDOWN_BARS

    for bar in range(1, len(closes)):
        sup = support[bar]
        res = resistance[bar]
        if np.isnan(sup) or np.isnan(res):
            continue

        if bar - last_trade_bar < COOLDOWN_BARS:
            continue

        direction = None
        entry_price = stop_price = target_price = None

        # Bounce off Support -> LONG
        if lows[bar] <= sup and closes[bar] > sup:
            direction = 'LONG'
            entry_price = sup
            stop_price = sup * (1 - stop_buffer_pct)
            target_price = res

        # Rejection off Resistance -> SHORT
        elif highs[bar] >= res and closes[bar] < res:
            direction = 'SHORT'
            entry_price = res
            stop_price = res * (1 + stop_buffer_pct)
            target_price = sup

        if not direction:
            continue

        stop_dist = abs(entry_price - stop_price)
        if stop_dist == 0:
            continue

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

        last_trade_bar = bar
        if capital <= 0:
            break

    return trades, capital, max_dd


if __name__ == "__main__":
    print("Running 2-Day Support/Resistance Bounce Strategy (15M execution)...")
    print(f"Resistance = Prev 2-Day Block High | Support = Prev 2-Day Block Low")
    print(f"Risk: {RISK_PER_TRADE_PCT*100}% | Leverage: {LEVERAGE}x | Data: {DATA_FILE}\n")

    trades, final, mdd = simulate_2day_sr_bounce()
    wins = len([t for t in trades if t['pnl'] > 0])

    print("TRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} "
              f"Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")

    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Return: {ret:,.1f}% | Max DD: {mdd:.1f}%")
