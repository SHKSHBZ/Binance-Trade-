"""
Gann Square of 9 — BTC Backtest
================================
Finds how many times price rallied 500+ points from a Gann support level.

Strategy:
1. Detect significant swing lows in the price data
2. From each swing low, compute Gann Square of 9 support levels below
3. When price revisits a Gann support level, mark a potential long entry
4. Track forward to see if price rallied 500+ points from that entry
5. Report all qualifying trades
"""

import pandas as pd
import numpy as np
import os
import sys
from collections import defaultdict

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
MIN_RALLY_POINTS = 500
SWING_LOOKBACK = 20          # Bars each side to confirm swing
GANN_MAX_ROTATIONS = 10      # Max full rotations for level calc
GANN_TOLERANCE_PCT = 0.003   # 0.3% proximity to count as "touching" a level
FORWARD_BARS = 300            # Max bars to look forward for rally measurement
DEDUP_HOURS = 48              # Minimum hours between distinct trade entries


# ─── Gann Math ──────────────────────────────────────────────────────────────

def gann_levels_from_price(price, max_rotations=10):
    """
    Compute Gann Square of 9 levels above and below a reference price.
    
    Formula: Level = (√price ± N/4)²
    where N = 1,2,3,... (each N = 90° rotation)
    """
    sqrt_p = np.sqrt(price)
    resistance = []
    support = []

    for n in range(1, max_rotations * 4 + 1):
        increment = n * 0.25

        # Resistance levels (above)
        res = (sqrt_p + increment) ** 2
        resistance.append({
            'price': round(res, 1),
            'degrees': n * 90,
            'n': n,
            'type': 'resistance'
        })

        # Support levels (below)
        sup_sqrt = sqrt_p - increment
        if sup_sqrt > 0:
            sup = sup_sqrt ** 2
            support.append({
                'price': round(sup, 1),
                'degrees': n * 90,
                'n': n,
                'type': 'support'
            })

    return support, resistance


# ─── Swing Detection ───────────────────────────────────────────────────────

def detect_swing_lows(df, lookback):
    """Detect swing lows: bar where low is the minimum in a ±lookback window."""
    swings = []
    lows = df['low'].values
    for i in range(lookback, len(lows) - lookback):
        window = lows[i - lookback: i + lookback + 1]
        if lows[i] == window.min() and list(window).count(lows[i]) == 1:
            swings.append({'idx': i, 'time': df.index[i], 'price': lows[i]})
    return swings


def detect_swing_highs(df, lookback):
    """Detect swing highs: bar where high is the maximum in a ±lookback window."""
    swings = []
    highs = df['high'].values
    for i in range(lookback, len(highs) - lookback):
        window = highs[i - lookback: i + lookback + 1]
        if highs[i] == window.max() and list(window).count(highs[i]) == 1:
            swings.append({'idx': i, 'time': df.index[i], 'price': highs[i]})
    return swings


# ─── Backtest Engine ───────────────────────────────────────────────────────

def run_gann_backtest(df, min_rally=500):
    """
    Main backtest logic:
    1. Find swing highs → compute Gann support levels below them
    2. When price drops to a Gann support level, that's a potential buy
    3. Track if price rallies 500+ points from the entry
    """
    highs_arr = df['high'].values
    lows_arr = df['low'].values
    closes_arr = df['close'].values
    times = df.index

    # Detect swing highs (to compute Gann levels below them)
    swing_highs = detect_swing_highs(df, SWING_LOOKBACK)
    # Also detect swing lows (as natural Gann pivots)
    swing_lows = detect_swing_lows(df, SWING_LOOKBACK)

    print(f"  Swing highs detected: {len(swing_highs)}")
    print(f"  Swing lows detected:  {len(swing_lows)}")

    # Build a set of active Gann support levels over time
    # From each swing high, compute support levels below
    # From each swing low, the low itself is a Gann pivot → compute levels above & below
    trades = []

    # Approach: For each swing low, it IS a Gann-validated support.
    # Compute Gann levels from that swing low.
    # From the swing low, measure the rally forward.
    # Also: From each swing high, compute Gann support levels.
    # When price later touches those levels, enter long and measure rally.

    # === PHASE 1: Rallies directly from swing lows (Gann pivots) ===
    for sl in swing_lows:
        entry_idx = sl['idx']
        entry_price = sl['price']
        entry_time = sl['time']

        # Compute Gann levels from this pivot
        support_levels, resistance_levels = gann_levels_from_price(entry_price)

        # Measure rally from the swing low
        max_high = entry_price
        max_high_time = entry_time
        max_drawdown = 0.0

        end_idx = min(entry_idx + FORWARD_BARS, len(closes_arr))
        for j in range(entry_idx + 1, end_idx):
            if highs_arr[j] > max_high:
                max_high = highs_arr[j]
                max_high_time = times[j]
            dd = entry_price - lows_arr[j]
            if dd > max_drawdown:
                max_drawdown = dd

        rally = max_high - entry_price

        # Check which Gann resistance level the rally stopped near
        nearest_gann_res = None
        for rl in resistance_levels:
            if abs(rl['price'] - max_high) / max_high < 0.005:  # 0.5% tolerance
                nearest_gann_res = rl
                break

        if rally >= min_rally:
            trades.append({
                'source': 'Swing Low (Gann Pivot)',
                'pivot_price': round(entry_price, 1),
                'pivot_time': entry_time,
                'entry_price': round(entry_price, 1),
                'entry_time': entry_time,
                'entry_idx': entry_idx,
                'max_price': round(max_high, 1),
                'max_price_time': max_high_time,
                'rally_points': round(rally, 1),
                'max_drawdown': round(max_drawdown, 1),
                'gann_degrees': 0,
                'stopped_at_gann': nearest_gann_res is not None,
                'gann_target': nearest_gann_res['price'] if nearest_gann_res else None,
                'gann_target_deg': nearest_gann_res['degrees'] if nearest_gann_res else None,
            })

    # === PHASE 2: Entries at Gann support levels computed from swing highs ===
    for sh in swing_highs:
        pivot_price = sh['price']
        pivot_idx = sh['idx']
        pivot_time = sh['time']

        support_levels, _ = gann_levels_from_price(pivot_price)

        # For each support level, scan forward to see if price touches it
        for sl_info in support_levels:
            level = sl_info['price']
            if level <= 0 or level > pivot_price:
                continue

            # Only consider levels that are meaningfully below (at least 200 points)
            if pivot_price - level < 200:
                continue

            # Scan forward from the swing high
            for i in range(pivot_idx + 1, min(pivot_idx + FORWARD_BARS * 2, len(closes_arr))):
                tolerance = level * GANN_TOLERANCE_PCT

                # Price touches the Gann support level
                if lows_arr[i] <= level + tolerance and lows_arr[i] >= level - tolerance:
                    entry_price = level
                    entry_time = times[i]
                    entry_idx = i

                    # Measure rally from this entry
                    max_high = entry_price
                    max_high_time = entry_time
                    max_drawdown = 0.0

                    end_idx2 = min(entry_idx + FORWARD_BARS, len(closes_arr))
                    for j in range(entry_idx + 1, end_idx2):
                        if highs_arr[j] > max_high:
                            max_high = highs_arr[j]
                            max_high_time = times[j]
                        dd = entry_price - lows_arr[j]
                        if dd > max_drawdown:
                            max_drawdown = dd

                    rally = max_high - entry_price

                    if rally >= min_rally:
                        trades.append({
                            'source': 'Gann Support from Swing High',
                            'pivot_price': round(pivot_price, 1),
                            'pivot_time': pivot_time,
                            'entry_price': round(entry_price, 1),
                            'entry_time': entry_time,
                            'entry_idx': entry_idx,
                            'max_price': round(max_high, 1),
                            'max_price_time': max_high_time,
                            'rally_points': round(rally, 1),
                            'max_drawdown': round(max_drawdown, 1),
                            'gann_degrees': sl_info['degrees'],
                            'stopped_at_gann': False,
                            'gann_target': None,
                            'gann_target_deg': None,
                        })
                    break  # found a touch for this level, move on

    # === Deduplicate: remove trades with entries within DEDUP_HOURS of each other ===
    trades.sort(key=lambda x: x['entry_time'])
    unique = []
    for t in trades:
        if not unique:
            unique.append(t)
        else:
            hours_diff = (t['entry_time'] - unique[-1]['entry_time']).total_seconds() / 3600
            if hours_diff >= DEDUP_HOURS:
                unique.append(t)
            else:
                # Keep the one with the bigger rally
                if t['rally_points'] > unique[-1]['rally_points']:
                    unique[-1] = t

    return unique


# ─── Report ────────────────────────────────────────────────────────────────

def print_report(trades, df_name, df):
    print(f"\n{'═' * 100}")
    print(f"  GANN SQUARE OF 9 — BACKTEST RESULTS")
    print(f"  Data: {df_name}")
    print(f"  Period: {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Price Range: ${df['low'].min():,.1f} — ${df['high'].max():,.1f}")
    print(f"  Min Rally Target: {MIN_RALLY_POINTS} points")
    print(f"{'═' * 100}")

    if not trades:
        print("\n  ❌ No trades found matching criteria.\n")
        return

    print(f"\n  ✅ Found {len(trades)} trades with 500+ point rallies from Gann levels\n")

    print(f"  {'#':<4} {'Entry Date':<22} {'Entry $':>12} {'Rally':>10} {'Max High':>12} {'Max DD':>10} {'R:R':>8} {'Gann °':>8} {'Source'}")
    print(f"  {'─' * 96}")

    total_rally = 0
    total_dd = 0
    rallies = []

    for i, t in enumerate(trades, 1):
        total_rally += t['rally_points']
        total_dd += t['max_drawdown']
        rallies.append(t['rally_points'])
        rr = t['rally_points'] / t['max_drawdown'] if t['max_drawdown'] > 0 else 999.9
        src = 'Pivot' if 'Pivot' in t['source'] else f"SH→{t['gann_degrees']}°"
        print(f"  {i:<4} {str(t['entry_time'])[:19]:<22} ${t['entry_price']:>10,.1f} {t['rally_points']:>9,.1f} ${t['max_price']:>10,.1f} {t['max_drawdown']:>9,.1f} {rr:>7.1f}x {t['gann_degrees']:>6}° {src}")

    print(f"  {'─' * 96}")
    avg_rally = total_rally / len(trades)
    avg_dd = total_dd / len(trades)
    avg_rr = avg_rally / avg_dd if avg_dd > 0 else 999.9

    print(f"\n  {'─' * 50}")
    print(f"  SUMMARY")
    print(f"  {'─' * 50}")
    print(f"  Total qualifying trades:    {len(trades)}")
    print(f"  Total rally captured:       {total_rally:>12,.1f} pts")
    print(f"  Average rally per trade:    {avg_rally:>12,.1f} pts")
    print(f"  Median rally:               {np.median(rallies):>12,.1f} pts")
    print(f"  Best rally:                 {max(rallies):>12,.1f} pts")
    print(f"  Worst rally (still 500+):   {min(rallies):>12,.1f} pts")
    print(f"  Average max drawdown:       {avg_dd:>12,.1f} pts")
    print(f"  Average R:R ratio:          {avg_rr:>12.1f}x")

    print(f"\n  RALLY DISTRIBUTION:")
    for threshold in [500, 1000, 2000, 3000, 5000, 10000, 20000]:
        count = sum(1 for r in rallies if r >= threshold)
        if count > 0:
            bar = '█' * count
            print(f"    ≥ {threshold:>6,} pts:  {count:>4} trades  {bar}")

    # Monthly breakdown
    print(f"\n  MONTHLY BREAKDOWN:")
    monthly = defaultdict(list)
    for t in trades:
        key = t['entry_time'].strftime('%Y-%m')
        monthly[key].append(t['rally_points'])
    
    for month in sorted(monthly.keys()):
        rs = monthly[month]
        print(f"    {month}:  {len(rs)} trade(s), avg rally: {np.mean(rs):,.1f} pts, best: {max(rs):,.1f} pts")

    print(f"\n{'═' * 100}\n")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    # Find all CSV files in DATA directory
    data_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.csv')])

    if not data_files:
        print("❌ No CSV files found in DATA directory!")
        sys.exit(1)

    print("=" * 100)
    print("  GANN SQUARE OF 9 — BTC BACKTEST ENGINE")
    print("=" * 100)
    print(f"\n  Data files found: {len(data_files)}")
    for f in data_files:
        print(f"    • {f}")

    # Run on primary datasets (1h is best balance of signal quality & speed)
    primary_files = [
        "BTCUSDT_1h_2023_to_2025.csv",
        "BTCUSDT_1h_Jan_to_Jul2026.csv",
        "BTCUSDT_4h_2023_to_2025.csv",
        "BTCUSDT_1d_Jan_to_Jul2026.csv",
    ]

    for fname in primary_files:
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"\n  ⚠ Skipping {fname} (not found)")
            continue

        print(f"\n{'─' * 100}")
        print(f"  Processing: {fname}")
        print(f"{'─' * 100}")

        df = pd.read_csv(fpath)
        df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)

        print(f"  Loaded {len(df):,} bars | {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")

        trades = run_gann_backtest(df, MIN_RALLY_POINTS)
        print_report(trades, fname, df)


if __name__ == "__main__":
    main()
