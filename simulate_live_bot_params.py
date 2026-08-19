"""
Advanced SMC Bot V2 -- Backtest Simulator
============================================
Implements the approved V2 plan:

  1. HTF (4H, resampled from 15M for internal consistency) determines
     trend bias and maps External Liquidity Pools (fractal swing
     highs/lows). LTF (15M) internal swings are never used as sweep
     triggers -- this IS the Inducement (IDM) filter, by construction.

  2. Only a sweep of an unswept, active HTF external pool starts a
     pending sequence. Pools are marked exhausted once swept and
     never retrigger.

  3. LTF (15M) structure is tracked continuously (trend state via
     fractal swings). A break WITH the current trend is BOS. A break
     AGAINST the trend only counts as a tradeable CHoCH if it occurs
     within CHOCH_WINDOW_BARS of an active pending sweep, in the
     expected reversal direction.

  4. On a valid CHoCH, search backward through the impulsive leg (from
     the sweep bar to the CHoCH bar) for the OB/Breaker: the last
     opposite-colored candle that is immediately followed by a 3-candle
     FVG (the displacement requirement). Entry is a limit order at the
     50% mean-threshold of that candle's range.

  5. Stop = the original sweep wick +/- a 0.3% buffer (not the raw
     wick itself). Target = the nearest unswept, active *opposing*
     external liquidity pool ahead of price (liquidity-driven, not an
     arbitrary R-multiple). Trade is skipped if that target doesn't
     clear MIN_RR.

  6. Risk 1% per trade, up to 10x leverage capped at 80% margin. One
     trade at a time (Sniper Limit). A daily circuit breaker halts new
     entries for the rest of the calendar day if losses exceed 3% of
     that day's starting balance.

Simplifications, stated explicitly (not hidden):
  - Breaker Blocks are not distinguished from fresh OBs as a separate
    detection path; the OB found at the CHoCH leg is used uniformly
    for both cases. A true "failed OB that flips polarity" would need
    multi-leg OB history tracking not yet built.
  - HTF pools expire after HTF_POOL_EXPIRY_BARS (4H bars) if never
    swept, since the V2 spec didn't set an explicit HTF pool lifetime.
"""

import pandas as pd
import numpy as np
import os

from data_loader import load_ohlcv

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")

STARTING_CAPITAL = 1000.0
RISK_PER_TRADE_PCT = 0.01     # V2: start conservative at 1%
LEVERAGE = 10
MARGIN_SAFETY_CAP = 0.80
COMMISSION_PCT = 0.0004

HTF_SWING_LOOKBACK = 2         # fractal lookback on 4H bars
LTF_SWING_LOOKBACK = 3         # fractal lookback on 15M bars
HTF_POOL_EXPIRY_BARS = 60      # ~10 days of 4H bars before a pool is stale
CHOCH_WINDOW_BARS = 16         # 15M bars (~4h) -- CHoCH must confirm within this of the sweep
RETEST_WINDOW_BARS = 48        # 15M bars (~12h) -- OB must be retested (entry filled) within this of CHoCH
OB_SEARCH_BACK_BARS = 20       # how far back from the CHoCH bar to search for the OB candle

STOP_BUFFER_PCT = 0.003        # V2: 0.3% past the sweep wick
MIN_RR = 2.0                   # V2: R:R filter
TARGET_R_CAP = None            # if set, take profit at this R multiple instead of
                               # riding to the full liquidity pool (raises win rate,
                               # lowers per-win payout -- the core tradeoff)
DAILY_LOSS_LIMIT_PCT = 0.03    # V2: circuit breaker
FORWARD_BARS = 800


def detect_fractal_swings(highs, lows, lb):
    """Returns (swing_low_idxs, swing_high_idxs) using a symmetric lookback."""
    sl, sh = [], []
    for i in range(lb, len(lows) - lb):
        wl = lows[i - lb:i + lb + 1]
        wh = highs[i - lb:i + lb + 1]
        if lows[i] == wl.min() and list(wl).count(lows[i]) == 1:
            sl.append(i)
        if highs[i] == wh.max() and list(wh).count(highs[i]) == 1:
            sh.append(i)
    return sl, sh


def load_and_prepare(data_file, start=None, end=None):
    # Must route through load_ohlcv: the DATA/ files do not share a timestamp
    # format, and dayfirst parsing silently scrambles ~36% of the ISO files.
    return load_ohlcv(data_file, start, end)


def build_htf_pools(df_ltf):
    """Resample 15M -> 4H, detect fractal swings, and return a chronological
    list of (confirmation_time, level, kind) where kind is 'high' or 'low'.
    confirmation_time is when the pool becomes knowable without look-ahead
    (idx + lookback bars later on the 4H series)."""
    df_4h = df_ltf.resample('4h').agg({'open': 'first', 'high': 'max',
                                        'low': 'min', 'close': 'last'}).dropna()
    highs4h = df_4h['high'].values
    lows4h = df_4h['low'].values
    times4h = df_4h.index

    sl_idx, sh_idx = detect_fractal_swings(highs4h, lows4h, HTF_SWING_LOOKBACK)

    # A fractal at idx needs bars idx+1 .. idx+lookback to CLOSE before it is
    # knowable. times4h[conf] is the OPEN of bar conf, so the pool only becomes
    # tradeable once bar conf closes -- i.e. at the open of bar conf+1.
    pools = []
    for idx in sl_idx:
        conf = idx + HTF_SWING_LOOKBACK + 1
        if conf < len(times4h):
            pools.append({'confirm_time': times4h[conf], 'level': lows4h[idx], 'kind': 'low'})
    for idx in sh_idx:
        conf = idx + HTF_SWING_LOOKBACK + 1
        if conf < len(times4h):
            pools.append({'confirm_time': times4h[conf], 'level': highs4h[idx], 'kind': 'high'})

    pools.sort(key=lambda p: p['confirm_time'])
    return pools


def is_bull(o, c):
    return c > o


def find_ob_with_displacement(opens, highs, lows, closes, sweep_bar, choch_bar, want_bull_ob):
    """Search backward from choch_bar toward sweep_bar for the last
    opposite-colored candle immediately followed by a 3-candle FVG
    (the displacement requirement). Returns (ob_idx, ob_high, ob_low) or None."""
    # The FVG check reads bars k+1 and k+2, so k+2 must be at or before the
    # CHoCH bar -- otherwise the search peeks at a candle that has not printed
    # yet at decision time.
    start = max(sweep_bar, choch_bar - OB_SEARCH_BACK_BARS)
    for k in range(choch_bar - 2, start - 1, -1):
        if k - 2 < 0 or k + 2 > choch_bar:
            continue
        candle_is_bull = is_bull(opens[k], closes[k])
        # For a bullish reversal we want the OB to be the last DOWN candle
        if want_bull_ob and candle_is_bull:
            continue
        if not want_bull_ob and not candle_is_bull:
            continue

        # Displacement check: does an FVG form in the 3 candles starting at k?
        # (matches the established 3-candle gap convention used elsewhere in this repo)
        if k + 2 < len(closes):
            bull_fvg = lows[k + 2] > highs[k] and closes[k + 1] > opens[k + 1]
            bear_fvg = highs[k + 2] < lows[k] and closes[k + 1] < opens[k + 1]
            if want_bull_ob and bull_fvg:
                return k, highs[k], lows[k]
            if not want_bull_ob and bear_fvg:
                return k, highs[k], lows[k]
    return None


def simulate_v2(data_file, start=None, end=None, verbose_label=""):
    df = load_and_prepare(data_file, start, end)

    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    times = df.index
    n = len(closes)

    htf_pools = build_htf_pools(df)
    pool_ptr = 0  # index into htf_pools for lazy activation as time passes
    active_pools = []  # each: {'level','kind','formed_at_bar','swept':bool}

    sl_idx_ltf, sh_idx_ltf = detect_fractal_swings(highs, lows, LTF_SWING_LOOKBACK)
    ltf_swing_high_level = np.full(n, np.nan)
    ltf_swing_low_level = np.full(n, np.nan)
    for idx in sh_idx_ltf:
        cb = idx + LTF_SWING_LOOKBACK
        if cb < n:
            ltf_swing_high_level[cb] = highs[idx]
    for idx in sl_idx_ltf:
        cb = idx + LTF_SWING_LOOKBACK
        if cb < n:
            ltf_swing_low_level[cb] = lows[idx]

    trend_state = None  # 'bullish' / 'bearish' / None
    last_conf_swing_high = None
    last_conf_swing_low = None

    pending_seq = None  # {'dir','sweep_bar','sweep_extreme','expires_bar'}
    pending_entry = None  # {'dir','limit_price','stop_price','ob_high','ob_low','expires_bar'}

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []
    in_position_until_bar = -1

    current_day = None
    day_start_balance = capital
    day_halted = False

    for bar in range(max(HTF_SWING_LOOKBACK * 8, LTF_SWING_LOOKBACK * 2) + 5, n):
        # --- daily circuit breaker bookkeeping ---
        bar_day = times[bar].normalize()
        if bar_day != current_day:
            current_day = bar_day
            day_start_balance = capital
            day_halted = False
        elif not day_halted and capital <= day_start_balance * (1 - DAILY_LOSS_LIMIT_PCT):
            day_halted = True

        # --- activate newly-confirmed HTF pools ---
        while pool_ptr < len(htf_pools) and htf_pools[pool_ptr]['confirm_time'] <= times[bar]:
            p = htf_pools[pool_ptr]
            active_pools.append({'level': p['level'], 'kind': p['kind'],
                                  'formed_at_bar': bar, 'swept': False})
            pool_ptr += 1

        # --- expire stale HTF pools ---
        for p in active_pools:
            if not p['swept'] and (bar - p['formed_at_bar']) > HTF_POOL_EXPIRY_BARS * 16:
                p['swept'] = True  # treat "stale" the same as "exhausted": no longer tradeable

        # --- update LTF structure / trend state (continuous, independent of sequences) ---
        if not np.isnan(ltf_swing_high_level[bar]):
            last_conf_swing_high = ltf_swing_high_level[bar]
        if not np.isnan(ltf_swing_low_level[bar]):
            last_conf_swing_low = ltf_swing_low_level[bar]

        broke_up = last_conf_swing_high is not None and closes[bar] > last_conf_swing_high
        broke_down = last_conf_swing_low is not None and closes[bar] < last_conf_swing_low

        choch_up = broke_up and trend_state == 'bearish'
        choch_down = broke_down and trend_state == 'bullish'

        if broke_up:
            trend_state = 'bullish'
            last_conf_swing_high = None  # require a fresh swing before re-triggering
        if broke_down:
            trend_state = 'bearish'
            last_conf_swing_low = None

        # --- check for HTF external liquidity sweeps (only source of new sequences) ---
        if pending_seq is None and pending_entry is None and bar > in_position_until_bar:
            for p in active_pools:
                if p['swept']:
                    continue
                if p['kind'] == 'low' and lows[bar] < p['level']:
                    p['swept'] = True
                    pending_seq = {'dir': 'LONG', 'sweep_bar': bar, 'sweep_extreme': lows[bar],
                                    'expires_bar': bar + CHOCH_WINDOW_BARS}
                    break
                if p['kind'] == 'high' and highs[bar] > p['level']:
                    p['swept'] = True
                    pending_seq = {'dir': 'SHORT', 'sweep_bar': bar, 'sweep_extreme': highs[bar],
                                    'expires_bar': bar + CHOCH_WINDOW_BARS}
                    break

        # --- pending sequence: waiting for CHoCH in the swept direction ---
        if pending_seq is not None:
            if bar > pending_seq['expires_bar']:
                pending_seq = None
            else:
                want_choch = choch_up if pending_seq['dir'] == 'LONG' else choch_down
                if want_choch:
                    ob = find_ob_with_displacement(opens, highs, lows, closes,
                                                    pending_seq['sweep_bar'], bar,
                                                    want_bull_ob=(pending_seq['dir'] == 'LONG'))
                    if ob is not None:
                        ob_idx, ob_high, ob_low = ob
                        mid = (ob_high + ob_low) / 2.0
                        if pending_seq['dir'] == 'LONG':
                            stop_price = pending_seq['sweep_extreme'] * (1 - STOP_BUFFER_PCT)
                        else:
                            stop_price = pending_seq['sweep_extreme'] * (1 + STOP_BUFFER_PCT)
                        pending_entry = {'dir': pending_seq['dir'], 'limit_price': mid,
                                          'stop_price': stop_price,
                                          'expires_bar': bar + RETEST_WINDOW_BARS,
                                          # diagnostics: the stages that produced this setup
                                          'sweep_time': times[pending_seq['sweep_bar']],
                                          'sweep_extreme': pending_seq['sweep_extreme'],
                                          'choch_time': times[bar],
                                          'ob_time': times[ob_idx],
                                          'ob_high': ob_high, 'ob_low': ob_low}
                    pending_seq = None  # consumed either way (found OB or not)

        # --- pending entry: waiting for price to retest the 50% OB threshold ---
        if pending_entry is not None and bar > in_position_until_bar:
            if bar > pending_entry['expires_bar']:
                pending_entry = None
            else:
                touched = ((pending_entry['dir'] == 'LONG' and lows[bar] <= pending_entry['limit_price']) or
                           (pending_entry['dir'] == 'SHORT' and highs[bar] >= pending_entry['limit_price']))
                if touched and not day_halted:
                    entry_price = pending_entry['limit_price']
                    stop_price = pending_entry['stop_price']
                    direction = pending_entry['dir']
                    stop_dist = abs(entry_price - stop_price)

                    # Liquidity-driven target: nearest unswept OPPOSING active pool ahead of price
                    target_price = None
                    if direction == 'LONG':
                        candidates = [p['level'] for p in active_pools
                                      if not p['swept'] and p['kind'] == 'high' and p['level'] > entry_price]
                        if candidates:
                            target_price = min(candidates)
                    else:
                        candidates = [p['level'] for p in active_pools
                                      if not p['swept'] and p['kind'] == 'low' and p['level'] < entry_price]
                        if candidates:
                            target_price = max(candidates)

                    valid = stop_dist > 0 and target_price is not None
                    if valid:
                        reward = abs(target_price - entry_price)
                        rr = reward / stop_dist
                        valid = rr >= MIN_RR
                        # Optionally bank profit earlier than the liquidity pool.
                        # The setup still has to QUALIFY on the full liquidity
                        # target (MIN_RR above); this only moves the exit closer.
                        if valid and TARGET_R_CAP is not None and rr > TARGET_R_CAP:
                            if direction == 'LONG':
                                target_price = entry_price + stop_dist * TARGET_R_CAP
                            else:
                                target_price = entry_price - stop_dist * TARGET_R_CAP
                            rr = TARGET_R_CAP

                    if valid:
                        risk_amt = capital * RISK_PER_TRADE_PCT
                        pos_usd = min((risk_amt / stop_dist) * entry_price,
                                       capital * LEVERAGE * MARGIN_SAFETY_CAP)
                        qty = pos_usd / entry_price

                        exit_p = exit_r = None
                        exit_bar = None
                        end = min(bar + FORWARD_BARS, n)
                        for j in range(bar + 1, end):
                            if direction == 'SHORT':
                                if highs[j] >= stop_price:
                                    exit_p, exit_r, exit_bar = stop_price, 'STOP', j
                                    break
                                if lows[j] <= target_price:
                                    exit_p, exit_r, exit_bar = target_price, 'TARGET', j
                                    break
                            else:
                                if lows[j] <= stop_price:
                                    exit_p, exit_r, exit_bar = stop_price, 'STOP', j
                                    break
                                if highs[j] >= target_price:
                                    exit_p, exit_r, exit_bar = target_price, 'TARGET', j
                                    break
                        if exit_p is None:
                            exit_p, exit_r, exit_bar = closes[end - 1], 'TIME', end - 1

                        pnl = qty * (exit_p - entry_price) if direction == 'LONG' else qty * (entry_price - exit_p)
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

                        trades.append({'dir': direction, 'time': times[bar], 'entry': entry_price,
                                        'stop': stop_price, 'target': target_price, 'rr': rr,
                                        'pnl': net, 'bal': capital, 'exit_r': exit_r,
                                        'exit_time': times[exit_bar],
                                        'qty': qty, 'pos_usd': pos_usd, 'risk_amt': risk_amt,
                                        'sweep_time': pending_entry.get('sweep_time'),
                                        'sweep_extreme': pending_entry.get('sweep_extreme'),
                                        'choch_time': pending_entry.get('choch_time'),
                                        'ob_time': pending_entry.get('ob_time'),
                                        'ob_high': pending_entry.get('ob_high'),
                                        'ob_low': pending_entry.get('ob_low')})
                        in_position_until_bar = exit_bar

                    pending_entry = None  # consumed either way

        if capital <= 0:
            break

    return trades, capital, max_dd


def report(label, data_file, start, end):
    trades, final, mdd = simulate_v2(data_file, start, end)
    wins = len([t for t in trades if t['pnl'] > 0])
    wr = wins / len(trades) * 100 if trades else 0
    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    avg_rr = np.mean([t['rr'] for t in trades]) if trades else 0
    days = 0
    if trades:
        days = (trades[-1]['time'] - trades[0]['time']).days or 1
    freq = len(trades) / days if days else 0

    print(f"=== {label} ({data_file}) ===")
    print(f"Trades: {len(trades)} | Wins: {wins} | WinRate: {wr:.1f}% | Avg R:R at entry: {avg_rr:.2f}")
    print(f"Final Capital: ${final:,.2f} | Return: {ret:,.1f}% | Max DD: {mdd:.1f}%")
    print(f"Trade frequency: {freq:.2f}/day over {days} days\n")
    return trades, final, mdd, wr, len(trades)


if __name__ == "__main__":
    print("Advanced SMC Bot V2 -- Backtest\n")
    print(f"Config: Risk {RISK_PER_TRADE_PCT*100}% | Leverage {LEVERAGE}x (cap {MARGIN_SAFETY_CAP*100:.0f}%) | "
          f"Min R:R {MIN_RR} | Stop buffer {STOP_BUFFER_PCT*100}% | Daily loss limit {DAILY_LOSS_LIMIT_PCT*100}%\n")

    r1 = report("2025 (Jan-Dec)", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31")
    r2 = report("Jan-Jul 2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)

    total_trades = r1[4] + r2[4]
    print("=== Falsifiable Success Criteria Check ===")
    print(f"Win Rate >= 40%:      2025={'PASS' if r1[3]>=40 else 'FAIL'} ({r1[3]:.1f}%)  |  "
          f"2026={'PASS' if r2[3]>=40 else 'FAIL'} ({r2[3]:.1f}%)")
    print(f"Max DD < 30%:         2025={'PASS' if r1[2]<30 else 'FAIL'} ({r1[2]:.1f}%)  |  "
          f"2026={'PASS' if r2[2]<30 else 'FAIL'} ({r2[2]:.1f}%)")
    print(f"Min trade count >=100 (combined): {total_trades} -> {'PASS' if total_trades>=100 else 'FAIL'}")
