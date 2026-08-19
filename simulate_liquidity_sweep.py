"""
SMC FVG + EMA 5/13/21 + RSI + Volume + Liquidity Sweep Backtester
====================================================================
Adds a Liquidity Sweep filter on top of the existing FVG + EMA + RSI +
Volume baseline (simulate_ema_rsi_vol.py):

1. Liquidity Pools:
   - EQH/EQL: Equal Highs / Equal Lows -- repeated swing extremes within
     a tight tolerance, where retail stop losses cluster.
   - PDH/PDL: Previous Day High / Low.
2. Sweep Event: price wicks through a pool level and closes back inside
   it on the same candle (a stop-hunt rejection).
3. Entry Gate: an FVG LONG entry is only taken if a bullish sweep
   (sell-side liquidity swept) occurred within the last SWEEP_VALID_BARS
   bars. SHORT entries require a bearish sweep (buy-side liquidity swept).

Everything else (FVG detection, EMA 5/13/21 stack, RSI, volume
confirmation, stop/target/time exit) is unchanged from the baseline so
the effect of the sweep filter can be isolated.
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

# --- Liquidity sweep params ---
SWING_LOOKBACK = 3          # bars each side to confirm a swing high/low
EQ_TOLERANCE_PCT = 0.0015   # swing highs/lows within 0.15% count as "equal"
POOL_EXPIRY_BARS = 200      # a pool is discarded if not swept within this many bars
SWEEP_VALID_BARS = 8        # a sweep event stays "active" for this many bars after it fires


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


def build_eq_pools(swing_idxs, values, tol_pct):
    """Given swing point bar indices and their price values, find pairs
    within tolerance of each other and emit a pool 'confirmed' at the
    bar index of the second (later) touch."""
    pools = []  # (confirmed_bar, level)
    for i in range(1, len(swing_idxs)):
        bar_j = swing_idxs[i]
        level_j = values[bar_j]
        # look back over recent prior swings for an equal level
        for k in range(i - 1, max(-1, i - 6), -1):
            bar_i = swing_idxs[k]
            level_i = values[bar_i]
            if abs(level_j - level_i) / level_i <= tol_pct:
                pool_level = (level_i + level_j) / 2
                pools.append((bar_j, pool_level))
                break
    return pools


def simulate_liquidity_sweep():
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
    df_daily = df.resample('1D').agg({'high': 'max', 'low': 'min'})
    df_daily['pdh'] = df_daily['high'].shift(1)
    df_daily['pdl'] = df_daily['low'].shift(1)
    dates = df.index.normalize()
    pdh_map = df_daily['pdh'].reindex(dates).values
    pdl_map = df_daily['pdl'].reindex(dates).values

    # --- Equal Highs / Equal Lows pools ---
    sl_idxs, sh_idxs = detect_swings(highs, lows, SWING_LOOKBACK)
    eql_pools_raw = build_eq_pools(sl_idxs, lows, EQ_TOLERANCE_PCT)   # (confirmed_bar, level)
    eqh_pools_raw = build_eq_pools(sh_idxs, highs, EQ_TOLERANCE_PCT)

    # Group pools by confirmation bar for quick lookup while iterating
    eql_by_bar = {}
    for bar, level in eql_pools_raw:
        eql_by_bar.setdefault(bar, []).append(level)
    eqh_by_bar = {}
    for bar, level in eqh_pools_raw:
        eqh_by_bar.setdefault(bar, []).append(level)

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []

    active_fvgs = []
    last_trade_bar = 0

    # Active liquidity pools not yet swept: list of dicts {level, type, expiry}
    active_sell_side = []  # EQL / PDL -- swept by price dropping through & reclaiming (bullish signal)
    active_buy_side = []   # EQH / PDH -- swept by price rising through & reclaiming (bearish signal)

    last_bull_sweep_bar = -10_000
    last_bear_sweep_bar = -10_000

    warmup = max(EMA_SLOW, RSI_PERIOD, VOLUME_MA_PERIOD, SWING_LOOKBACK * 2) + 2

    # seed PDL/PDH as pools once known
    seeded_pd_date = None

    for bar in range(warmup, len(closes)):
        # Register newly confirmed EQL/EQH pools
        if bar in eql_by_bar:
            for lvl in eql_by_bar[bar]:
                active_sell_side.append({'level': lvl, 'expiry': bar + POOL_EXPIRY_BARS})
        if bar in eqh_by_bar:
            for lvl in eqh_by_bar[bar]:
                active_buy_side.append({'level': lvl, 'expiry': bar + POOL_EXPIRY_BARS})

        # Register PDL/PDH as pools once per day
        cur_date = dates[bar]
        if cur_date != seeded_pd_date:
            seeded_pd_date = cur_date
            if not np.isnan(pdl_map[bar]):
                active_sell_side.append({'level': pdl_map[bar], 'expiry': bar + POOL_EXPIRY_BARS})
            if not np.isnan(pdh_map[bar]):
                active_buy_side.append({'level': pdh_map[bar], 'expiry': bar + POOL_EXPIRY_BARS})

        # Expire stale pools
        active_sell_side = [p for p in active_sell_side if bar <= p['expiry']]
        active_buy_side = [p for p in active_buy_side if bar <= p['expiry']]

        # Check for sweep events this bar (wick through level, close back inside)
        for p in list(active_sell_side):
            if lows[bar] < p['level'] and closes[bar] > p['level']:
                last_bull_sweep_bar = bar
                active_sell_side.remove(p)

        for p in list(active_buy_side):
            if highs[bar] > p['level'] and closes[bar] < p['level']:
                last_bear_sweep_bar = bar
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
                break

        if capital <= 0:
            break

    return trades, capital, max_dd


if __name__ == "__main__":
    print("Running SMC FVG + EMA 5/13/21 + RSI + Volume + Liquidity Sweep Strategy...")
    print(f"Config: EMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW} | RSI({RSI_PERIOD}) | Vol MA({VOLUME_MA_PERIOD}) "
          f"| Sweep window: {SWEEP_VALID_BARS} bars | Risk: {RISK_PER_TRADE_PCT*100}% | Leverage: {LEVERAGE}x")
    print(f"Data: {DATA_FILE}\n")

    trades, final, mdd = simulate_liquidity_sweep()
    wins = len([t for t in trades if t['pnl'] > 0])

    print("TRADE LOG (last 20):")
    for i, t in enumerate(trades[-20:]):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} "
              f"Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")

    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Return: {ret:,.1f}% | Max DD: {mdd:.1f}%")
