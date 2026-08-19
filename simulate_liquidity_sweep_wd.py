"""
SMC FVG + EMA 5/13/21 + RSI + Volume + Weekly/Daily Liquidity Sweep
====================================================================
Standalone variant of simulate_liquidity_sweep.py that replaces the
swing-based EQH/EQL pools with pure institutional reference levels:

  - PWH / PWL: Previous Week High / Low
  - PDH / PDL: Previous Day High / Low

Theory: these levels are watched by every participant (not just an
algorithmic "equal highs" pattern match), so sweeps of them should be
higher-quality liquidity grabs than swing-based EQH/EQL, at the cost of
far fewer setups (only one week/day boundary each).

Everything else (FVG detection, EMA 5/13/21 stack, RSI, volume
confirmation, sweep-then-reclaim logic, stop/target/time exit) is
identical to simulate_liquidity_sweep.py so the two pool sources can be
compared directly.
"""

import pandas as pd
import numpy as np
import os

from simulate_ema_rsi_vol import compute_rsi

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
DATA_FILE = "BTCUSDT_15m_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

EMA_FAST = 5
EMA_MID = 13
EMA_SLOW = 21

RSI_PERIOD = 14
RSI_LONG_MIN = 50
RSI_LONG_MAX = 70
RSI_SHORT_MAX = 50
RSI_SHORT_MIN = 30

VOLUME_MA_PERIOD = 20
VOLUME_MULT = 1.0

FORWARD_BARS = 200
FVG_EXPIRY_BARS = 48

SWEEP_VALID_BARS = 8        # a sweep event stays "active" for this many bars after it fires
POOL_EXPIRY_BARS = 4 * 96   # a week/day pool is dropped if not swept within ~4 days of bars (15m bars)


def simulate_liquidity_sweep_wd():
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    df['ema5'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema13'] = df['close'].ewm(span=EMA_MID, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    df['vol_ma'] = df['volume'].rolling(VOLUME_MA_PERIOD).mean()

    closes = df['close'].values
    df['rsi'] = compute_rsi(closes, RSI_PERIOD)

    lows = df['low'].values
    highs = df['high'].values
    opens = df['open'].values
    volumes = df['volume'].values
    vol_ma = df['vol_ma'].values
    times = df.index
    ema5 = df['ema5'].values
    ema13 = df['ema13'].values
    ema21 = df['ema21'].values
    rsi = df['rsi'].values

    # --- Previous Day High/Low ---
    day_key = df.index.normalize()
    df_daily = df.groupby(day_key).agg(high=('high', 'max'), low=('low', 'min'))
    df_daily['pdh'] = df_daily['high'].shift(1)
    df_daily['pdl'] = df_daily['low'].shift(1)
    pdh_map = df_daily['pdh'].reindex(day_key).values
    pdl_map = df_daily['pdl'].reindex(day_key).values

    # --- Previous Week High/Low ---
    week_key = df.index.to_period('W')
    df_weekly = df.groupby(week_key).agg(high=('high', 'max'), low=('low', 'min'))
    df_weekly['pwh'] = df_weekly['high'].shift(1)
    df_weekly['pwl'] = df_weekly['low'].shift(1)
    pwh_map = df_weekly['pwh'].reindex(week_key).values
    pwl_map = df_weekly['pwl'].reindex(week_key).values

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []

    active_fvgs = []
    last_trade_bar = 0

    active_sell_side = []  # PDL / PWL -- swept downward & reclaimed (bullish signal)
    active_buy_side = []   # PDH / PWH -- swept upward & reclaimed (bearish signal)

    last_bull_sweep_bar = -10_000
    last_bear_sweep_bar = -10_000
    sweep_source = {}  # bar -> 'PDL'/'PWL'/'PDH'/'PWH' for reporting

    seeded_day = None
    seeded_week = None

    warmup = max(EMA_SLOW, RSI_PERIOD, VOLUME_MA_PERIOD) + 2

    for bar in range(warmup, len(closes)):
        cur_day = day_key[bar]
        cur_week = week_key[bar]

        if cur_day != seeded_day:
            seeded_day = cur_day
            if not np.isnan(pdl_map[bar]):
                active_sell_side.append({'level': pdl_map[bar], 'type': 'PDL', 'expiry': bar + POOL_EXPIRY_BARS})
            if not np.isnan(pdh_map[bar]):
                active_buy_side.append({'level': pdh_map[bar], 'type': 'PDH', 'expiry': bar + POOL_EXPIRY_BARS})

        if cur_week != seeded_week:
            seeded_week = cur_week
            if not np.isnan(pwl_map[bar]):
                active_sell_side.append({'level': pwl_map[bar], 'type': 'PWL', 'expiry': bar + POOL_EXPIRY_BARS})
            if not np.isnan(pwh_map[bar]):
                active_buy_side.append({'level': pwh_map[bar], 'type': 'PWH', 'expiry': bar + POOL_EXPIRY_BARS})

        active_sell_side = [p for p in active_sell_side if bar <= p['expiry']]
        active_buy_side = [p for p in active_buy_side if bar <= p['expiry']]

        for p in list(active_sell_side):
            if lows[bar] < p['level'] and closes[bar] > p['level']:
                last_bull_sweep_bar = bar
                sweep_source[bar] = p['type']
                active_sell_side.remove(p)

        for p in list(active_buy_side):
            if highs[bar] > p['level'] and closes[bar] < p['level']:
                last_bear_sweep_bar = bar
                sweep_source[bar] = p['type']
                active_buy_side.remove(p)

        recent_bull_sweep = (bar - last_bull_sweep_bar) <= SWEEP_VALID_BARS
        recent_bear_sweep = (bar - last_bear_sweep_bar) <= SWEEP_VALID_BARS

        # --- FVG detection (unchanged) ---
        impulse_vol_ok = (not np.isnan(vol_ma[bar-1])) and volumes[bar-1] >= vol_ma[bar-1] * VOLUME_MULT

        if lows[bar] > highs[bar-2] and closes[bar-1] > opens[bar-1] and impulse_vol_ok:
            gap_bottom = highs[bar-2]
            gap_top = lows[bar]
            ob_stop = min(lows[bar-2], lows[bar-1], lows[bar]) - (closes[bar] * 0.0005)
            target = highs[bar] + abs(highs[bar] - ob_stop) * 1.5

            active_fvgs.append({
                'dir': 'LONG', 'top': gap_top, 'bottom': gap_bottom,
                'ob_stop': ob_stop, 'target': target,
                'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False
            })

        elif highs[bar] < lows[bar-2] and closes[bar-1] < opens[bar-1] and impulse_vol_ok:
            gap_bottom = highs[bar]
            gap_top = lows[bar-2]
            ob_stop = max(highs[bar-2], highs[bar-1], highs[bar]) + (closes[bar] * 0.0005)
            target = lows[bar] - abs(ob_stop - lows[bar]) * 1.5

            active_fvgs.append({
                'dir': 'SHORT', 'top': gap_top, 'bottom': gap_bottom,
                'ob_stop': ob_stop, 'target': target,
                'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False
            })

        active_fvgs = [f for f in active_fvgs if bar <= f['expiry'] and not f['mitigated']]

        if bar - last_trade_bar < 6:
            continue

        bullish_stack = ema5[bar] > ema13[bar] > ema21[bar]
        bearish_stack = ema5[bar] < ema13[bar] < ema21[bar]
        rsi_ok_long = RSI_LONG_MIN < rsi[bar] < RSI_LONG_MAX
        rsi_ok_short = RSI_SHORT_MIN < rsi[bar] < RSI_SHORT_MAX

        for fvg in active_fvgs:
            direction = None

            if (fvg['dir'] == 'LONG' and bullish_stack and rsi_ok_long and recent_bull_sweep):
                if lows[bar] <= fvg['top'] and highs[bar] > fvg['top']:
                    direction = 'LONG'
                    entry_price = fvg['top']

            elif (fvg['dir'] == 'SHORT' and bearish_stack and rsi_ok_short and recent_bear_sweep):
                if highs[bar] >= fvg['bottom'] and lows[bar] < fvg['bottom']:
                    direction = 'SHORT'
                    entry_price = fvg['bottom']

            if direction:
                fvg['mitigated'] = True
                stop_price = fvg['ob_stop']
                target_price = fvg['target']

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

                # find nearest recorded sweep source for reporting
                src = None
                for b in range(bar, max(bar - SWEEP_VALID_BARS - 1, -1), -1):
                    if b in sweep_source:
                        src = sweep_source[b]
                        break

                trades.append({
                    'dir': direction,
                    'time': times[bar],
                    'entry': entry_price,
                    'stop': stop_price,
                    'target': target_price,
                    'pnl': net,
                    'bal': capital,
                    'exit_r': exit_r,
                    'sweep_src': src
                })

                last_trade_bar = bar
                break

        if capital <= 0:
            break

    return trades, capital, max_dd


if __name__ == "__main__":
    print("Running SMC FVG + EMA 5/13/21 + RSI + Volume + Weekly/Daily Liquidity Sweep Strategy...")
    print(f"Config: EMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW} | RSI({RSI_PERIOD}) | Vol MA({VOLUME_MA_PERIOD}) "
          f"| Pools: PWH/PWL + PDH/PDL | Sweep window: {SWEEP_VALID_BARS} bars "
          f"| Risk: {RISK_PER_TRADE_PCT*100}% | Leverage: {LEVERAGE}x")
    print(f"Data: {DATA_FILE}\n")

    trades, final, mdd = simulate_liquidity_sweep_wd()
    wins = len([t for t in trades if t['pnl'] > 0])

    print("TRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} "
              f"Target: ${t['target']:.0f} Src: {t['sweep_src']} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")

    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Return: {ret:,.1f}% | Max DD: {mdd:.1f}%")
