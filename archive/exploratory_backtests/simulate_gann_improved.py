"""
Gann Square of 9 — IMPROVED Trading Simulation (2026)
=====================================================
3 Improvements Applied:
  1. Higher Timeframe Alignment: 4H Gann levels, 1H entries
  2. Wider Stops: 2nd Gann level below as stop
  3. Time-of-Day Filter: Only trade during high-liquidity hours (08:00–20:00 UTC)
"""

import pandas as pd
import numpy as np
import os

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up
DATA_FILE_1H = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.03        # Risk 3% of capital per trade
SWING_LOOKBACK_4H = 10           # Bars for 4H swing detection (= ~40 hours)
GANN_TOLERANCE_PCT = 0.004       # 0.4% tolerance for price near Gann level
STOP_GANN_LEVEL = 2              # Use 2nd Gann level below as stop (WIDER)
TARGET_GANN_LEVELS = 3           # Target 3rd Gann level above (wider target to match wider stop)
COMMISSION_PCT = 0.0004          # 0.04% per side
DEDUP_BARS_1H = 24               # Min 24 hours between trades
FORWARD_BARS = 300               # Max bars to hold a trade (~12.5 days on 1H)

# Time-of-day filter: only enter during HIGH LIQUIDITY hours (UTC)
# London open (08:00) through US close (20:00)
ALLOWED_HOURS_UTC = list(range(8, 21))  # 08:00 to 20:00 UTC


# ─── Gann Math ──────────────────────────────────────────────────────────────

def gann_levels(price, n_levels=30):
    """Compute Gann Square of 9 support & resistance levels from a price."""
    sqrt_p = np.sqrt(price)
    res = sorted([(sqrt_p + i * 0.25) ** 2 for i in range(1, n_levels + 1)])
    sup = sorted([(sqrt_p - i * 0.25) ** 2 for i in range(1, n_levels + 1) if (sqrt_p - i * 0.25) > 0], reverse=True)
    return sup, res


def get_nth_gann_below(price, n=2):
    """Get the Nth Gann level below the given price."""
    sqrt_p = np.sqrt(price)
    levels = []
    for i in range(1, 40):
        val = sqrt_p - i * 0.25
        if val > 0:
            levels.append(val ** 2)
    levels.sort(reverse=True)
    # levels[0] is closest below, levels[1] is 2nd below, etc.
    if len(levels) >= n:
        return levels[n - 1]
    return price * 0.97  # fallback


def get_nth_gann_above(price, n=3):
    """Get the Nth Gann level above the given price."""
    sqrt_p = np.sqrt(price)
    levels = []
    for i in range(1, 40):
        levels.append((sqrt_p + i * 0.25) ** 2)
    levels.sort()
    if len(levels) >= n:
        return levels[n - 1]
    return price * 1.03  # fallback


# ─── Swing Detection ───────────────────────────────────────────────────────

def detect_swings(highs, lows, lookback):
    """Detect swing highs and lows."""
    swing_lows = []
    swing_highs = []
    for i in range(lookback, len(lows) - lookback):
        wl = lows[i - lookback:i + lookback + 1]
        wh = highs[i - lookback:i + lookback + 1]
        if lows[i] == wl.min() and list(wl).count(lows[i]) == 1:
            swing_lows.append(i)
        if highs[i] == wh.max() and list(wh).count(highs[i]) == 1:
            swing_highs.append(i)
    return swing_lows, swing_highs


# ─── Build 4H Data from 1H ────────────────────────────────────────────────

def resample_to_4h(df_1h):
    """Resample 1H OHLCV data to 4H."""
    df_4h = df_1h.resample('4h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    return df_4h


# ─── Compute Active Gann Levels from 4H Swings ────────────────────────────

def build_4h_gann_zones(df_4h, lookback):
    """
    From 4H swing highs/lows, compute Gann support/resistance zones.
    Returns a list of (timestamp, support_levels, resistance_levels).
    """
    highs = df_4h['high'].values
    lows = df_4h['low'].values
    times = df_4h.index

    sl_idxs, sh_idxs = detect_swings(highs, lows, lookback)

    # Build a time-indexed dictionary of active Gann levels
    # For each 4H bar, gather all Gann levels from recent pivots
    gann_by_time = {}

    for bar_4h in range(len(df_4h)):
        bar_time = times[bar_4h]

        # Gather recent swing lows and highs BEFORE this bar
        active_sl = [i for i in sl_idxs if i < bar_4h][-5:]  # Last 5
        active_sh = [i for i in sh_idxs if i < bar_4h][-5:]

        all_supports = set()
        all_resistances = set()

        for idx in active_sl:
            pivot = lows[idx]
            sup, res = gann_levels(pivot, 20)
            all_supports.update(sup[:10])
            all_resistances.update(res[:10])
            all_supports.add(pivot)  # The swing low itself

        for idx in active_sh:
            pivot = highs[idx]
            sup, res = gann_levels(pivot, 20)
            all_supports.update(sup[:10])
            all_resistances.update(res[:10])

        gann_by_time[bar_time] = {
            'supports': sorted(all_supports, reverse=True),
            'resistances': sorted(all_resistances),
        }

    return gann_by_time, sl_idxs, sh_idxs


# ─── Find nearest 4H Gann support for a given price ───────────────────────

def find_nearest_support(price, supports, tolerance_pct):
    """Check if price is near any support level."""
    for s in supports:
        if s > price * 1.01:
            continue
        if abs(price - s) / price <= tolerance_pct:
            return s
    return None


def find_targets_and_stop(entry_price, supports, resistances):
    """
    Find stop loss (2nd Gann level below) and target (3rd Gann level above)
    from the 4H-derived Gann levels.
    """
    # Stop: 2nd support level below entry
    below = sorted([s for s in supports if s < entry_price], reverse=True)
    stop = below[STOP_GANN_LEVEL - 1] if len(below) >= STOP_GANN_LEVEL else entry_price * 0.97

    # Target: 3rd resistance level above entry
    above = sorted([r for r in resistances if r > entry_price])
    target = above[TARGET_GANN_LEVELS - 1] if len(above) >= TARGET_GANN_LEVELS else entry_price * 1.03

    return stop, target


# ─── Trading Simulation ────────────────────────────────────────────────────

def simulate(df_1h, gann_zones_4h):
    closes = df_1h['close'].values
    highs = df_1h['high'].values
    lows = df_1h['low'].values
    times = df_1h.index

    capital = STARTING_CAPITAL
    peak_capital = capital
    max_drawdown = 0
    trades = []
    last_trade_idx = -DEDUP_BARS_1H

    # Get the sorted 4H timestamps for mapping
    gann_times = sorted(gann_zones_4h.keys())

    def get_gann_for_time(t):
        """Find the most recent 4H Gann zone for a given 1H timestamp."""
        # Find the latest 4H bar <= t
        best = None
        for gt in gann_times:
            if gt <= t:
                best = gt
            else:
                break
        return gann_zones_4h.get(best) if best else None

    for bar in range(50, len(closes)):
        # Enforce minimum gap between trades
        if bar - last_trade_idx < DEDUP_BARS_1H:
            continue

        # ─── FILTER 3: Time-of-Day Filter ───
        bar_hour = times[bar].hour
        if bar_hour not in ALLOWED_HOURS_UTC:
            continue

        # ─── FILTER 1: Get 4H Gann levels (Higher Timeframe) ───
        gann = get_gann_for_time(times[bar])
        if gann is None:
            continue

        supports = gann['supports']
        resistances = gann['resistances']

        if not supports or not resistances:
            continue

        # Check if current price is near a 4H Gann support
        current_low = lows[bar]
        support_hit = find_nearest_support(current_low, supports, GANN_TOLERANCE_PCT)
        if support_hit is None:
            continue

        entry_price = closes[bar]

        # ─── FILTER 2: Wider Stops (2nd Gann level below) ───
        stop_level, target_price = find_targets_and_stop(entry_price, supports, resistances)

        stop_distance = entry_price - stop_level
        target_distance = target_price - entry_price

        if stop_distance <= 0 or target_distance <= 0:
            continue

        rr = target_distance / stop_distance
        if rr < 1.5:  # Min 1.5 R:R
            continue

        # Position sizing
        risk_amount = capital * RISK_PER_TRADE_PCT
        position_size_usd = (risk_amount / stop_distance) * entry_price
        max_position = capital * LEVERAGE
        position_size_usd = min(position_size_usd, max_position)
        qty_btc = position_size_usd / entry_price

        # Execute trade forward
        exit_price = None
        exit_time = None
        exit_reason = None
        bars_held = 0

        end_bar = min(bar + FORWARD_BARS, len(closes))
        for j in range(bar + 1, end_bar):
            bars_held += 1
            if lows[j] <= stop_level:
                exit_price = stop_level
                exit_time = times[j]
                exit_reason = "STOP LOSS"
                break
            if highs[j] >= target_price:
                exit_price = target_price
                exit_time = times[j]
                exit_reason = "TARGET HIT"
                break

        if exit_price is None:
            exit_price = closes[end_bar - 1]
            exit_time = times[end_bar - 1]
            exit_reason = "TIME EXIT"

        # P&L
        price_change = exit_price - entry_price
        gross_pnl = qty_btc * price_change
        commission = qty_btc * entry_price * COMMISSION_PCT + qty_btc * exit_price * COMMISSION_PCT
        net_pnl = gross_pnl - commission
        pnl_pct = (net_pnl / capital) * 100

        old_capital = capital
        capital += net_pnl
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital * 100
        if dd > max_drawdown:
            max_drawdown = dd

        trades.append({
            'entry_time': times[bar],
            'exit_time': exit_time,
            'entry_price': round(entry_price, 1),
            'gann_support': round(support_hit, 1),
            'stop_loss': round(stop_level, 1),
            'target': round(target_price, 1),
            'exit_price': round(exit_price, 1),
            'exit_reason': exit_reason,
            'qty_btc': round(qty_btc, 6),
            'position_usd': round(position_size_usd, 2),
            'gross_pnl': round(gross_pnl, 2),
            'commission': round(commission, 2),
            'net_pnl': round(net_pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'balance': round(capital, 2),
            'rr_ratio': round(rr, 1),
            'bars_held': bars_held,
            'stop_dist': round(stop_distance, 1),
            'target_dist': round(target_distance, 1),
        })

        last_trade_idx = bar

    return trades, capital, max_drawdown


# ─── Report ────────────────────────────────────────────────────────────────

def print_report(trades, final_capital, max_dd, df_1h):
    print(f"\n{'=' * 120}")
    print(f"  GANN SQUARE OF 9 — IMPROVED STRATEGY RESULTS")
    print(f"  Filters: 4H Gann Levels + Wider Stops (2nd level) + Time-of-Day (08-20 UTC)")
    print(f"{'=' * 120}")

    print(f"\n  Data:             {DATA_FILE_1H}")
    print(f"  Period:           {df_1h.index[0].strftime('%Y-%m-%d')} to {df_1h.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Starting Capital: ${STARTING_CAPITAL:,.2f}")
    print(f"  Leverage:         {LEVERAGE}x")
    print(f"  Risk/Trade:       {RISK_PER_TRADE_PCT*100:.1f}%")
    print(f"  Stop:             2nd Gann level below (WIDER)")
    print(f"  Target:           3rd Gann level above")
    print(f"  Hours:            08:00-20:00 UTC only")

    if not trades:
        print("\n  No trades executed.")
        return

    # Trade log
    print(f"\n  {'─' * 116}")
    print(f"  {'#':<3} {'Entry Date':<18} {'Exit Date':<18} {'Entry':>9} {'Gann Sup':>9} {'SL':>9} {'TP':>9} "
          f"{'Exit':>9} {'Result':<11} {'P&L':>9} {'Bal':>9} {'R:R':>5} {'Hrs':>4}")
    print(f"  {'─' * 116}")

    wins = losses = 0
    total_profit = total_loss = 0
    consecutive_wins = consecutive_losses = 0
    max_consec_wins = max_consec_losses = 0

    for i, t in enumerate(trades, 1):
        marker = "+" if t['net_pnl'] >= 0 else "-"
        if t['net_pnl'] >= 0:
            wins += 1
            total_profit += t['net_pnl']
            consecutive_wins += 1
            consecutive_losses = 0
            max_consec_wins = max(max_consec_wins, consecutive_wins)
        else:
            losses += 1
            total_loss += abs(t['net_pnl'])
            consecutive_losses += 1
            consecutive_wins = 0
            max_consec_losses = max(max_consec_losses, consecutive_losses)

        print(f"  {i:<3} {str(t['entry_time'])[:16]:<18} {str(t['exit_time'])[:16]:<18} "
              f"${t['entry_price']:>7,.0f} ${t['gann_support']:>7,.0f} ${t['stop_loss']:>7,.0f} ${t['target']:>7,.0f} "
              f"${t['exit_price']:>7,.0f} {t['exit_reason']:<11} {marker}${abs(t['net_pnl']):>7,.2f} "
              f"${t['balance']:>7,.2f} {t['rr_ratio']:>4.1f} {t['bars_held']:>4}")

    print(f"  {'─' * 116}")

    # Summary
    win_rate = (wins / len(trades) * 100) if trades else 0
    total_return = ((final_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    avg_win = total_profit / wins if wins > 0 else 0
    avg_loss = total_loss / losses if losses > 0 else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)
    avg_rr = np.mean([t['rr_ratio'] for t in trades])
    avg_bars = np.mean([t['bars_held'] for t in trades])
    avg_stop_dist = np.mean([t['stop_dist'] for t in trades])
    avg_target_dist = np.mean([t['target_dist'] for t in trades])

    print(f"""
  {'=' * 65}
  PERFORMANCE SUMMARY
  {'=' * 65}

  CAPITAL
    Starting:               ${STARTING_CAPITAL:>12,.2f}
    Final:                  ${final_capital:>12,.2f}
    Net Profit/Loss:        ${final_capital - STARTING_CAPITAL:>12,.2f}
    Total Return:           {total_return:>12.2f}%

  TRADES
    Total:                  {len(trades):>12}
    Winners:                {wins:>12}  ({win_rate:.1f}%)
    Losers:                 {losses:>12}  ({100 - win_rate:.1f}%)
    Max Consec. Wins:       {max_consec_wins:>12}
    Max Consec. Losses:     {max_consec_losses:>12}

  PROFITABILITY
    Gross Profit:           ${total_profit:>12,.2f}
    Gross Loss:             ${total_loss:>12,.2f}
    Profit Factor:          {profit_factor:>12.2f}
    Avg Win:                ${avg_win:>12,.2f}
    Avg Loss:               ${avg_loss:>12,.2f}
    Expectancy/Trade:       ${expectancy:>12,.2f}

  RISK
    Max Drawdown:           {max_dd:>12.2f}%
    Avg Stop Distance:      ${avg_stop_dist:>12,.1f}
    Avg Target Distance:    ${avg_target_dist:>12,.1f}
    Avg R:R Ratio:          {avg_rr:>12.1f}
    Avg Bars Held:          {avg_bars:>12.1f} hours
""")

    # Monthly
    print(f"  MONTHLY BREAKDOWN:")
    print(f"  {'─' * 75}")
    monthly = {}
    for t in trades:
        key = t['entry_time'].strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'pnl': 0, 'trades': 0, 'wins': 0}
        monthly[key]['pnl'] += t['net_pnl']
        monthly[key]['trades'] += 1
        if t['net_pnl'] >= 0:
            monthly[key]['wins'] += 1

    running_capital = STARTING_CAPITAL
    for month in sorted(monthly.keys()):
        m = monthly[month]
        wr = (m['wins'] / m['trades'] * 100) if m['trades'] > 0 else 0
        running_capital += m['pnl']
        marker = "+" if m['pnl'] >= 0 else " "
        bar = ("#" if m['pnl'] >= 0 else "-") * max(1, int(abs(m['pnl']) / 2))
        print(f"    {month}:  {m['trades']:>2} trades | WR: {wr:>5.1f}% | P&L: {marker}${m['pnl']:>8,.2f} | Bal: ${running_capital:>8,.2f}  {bar}")

    print(f"  {'─' * 75}")

    # Equity curve
    print(f"\n  EQUITY CURVE:")
    print(f"  {'─' * 65}")
    bal = STARTING_CAPITAL
    step = max(1, len(trades) // 30)  # Show ~30 points
    print(f"    Start          ${bal:>10,.2f}  |{'=' * 30}")
    for i, t in enumerate(trades):
        if i % step == 0 or i == len(trades) - 1:
            bal = t['balance']
            pct = (bal / STARTING_CAPITAL) * 100
            bar_len = max(1, int(pct / 100 * 30))
            char = '=' if t['net_pnl'] >= 0 else '-'
            label = f"#{i+1:>2} {str(t['entry_time'])[:10]}"
            print(f"    {label}   ${bal:>10,.2f}  |{char * bar_len} {pct:.0f}%")
    print(f"  {'─' * 65}")
    print(f"\n{'=' * 120}\n")

    # ── COMPARISON WITH PREVIOUS ──
    print(f"  {'=' * 65}")
    print(f"  COMPARISON: BEFORE vs AFTER IMPROVEMENTS")
    print(f"  {'=' * 65}")
    print(f"""
    Metric                   BEFORE (Raw)    AFTER (Improved)
    {'─' * 55}
    Final Capital            $127.41         ${final_capital:>10,.2f}
    Return                   -36.29%         {total_return:>10.2f}%
    Trades                   91              {len(trades):>10}
    Win Rate                 33.0%           {win_rate:>10.1f}%
    Profit Factor            0.65            {profit_factor:>10.2f}
    Max Drawdown             43.17%          {max_dd:>10.2f}%
    Avg Win                  $4.55           ${avg_win:>10,.2f}
    Avg Loss                 $3.43           ${avg_loss:>10,.2f}
    Expectancy               -$0.80          ${expectancy:>10,.2f}
    {'─' * 55}
""")
    print(f"{'=' * 120}\n")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 120)
    print("  GANN SQUARE OF 9 — IMPROVED STRATEGY (3 Filters)")
    print("  1. Higher Timeframe: 4H Gann levels for S/R, 1H for entries")
    print("  2. Wider Stops: 2nd Gann level below entry")
    print("  3. Time Filter: 08:00-20:00 UTC only (London + US session)")
    print("=" * 120)

    # Load 1H data
    fpath_1h = os.path.join(DATA_DIR, DATA_FILE_1H)
    df_1h = pd.read_csv(fpath_1h)
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], dayfirst=True, format='mixed')
    df_1h.set_index('timestamp', inplace=True)
    df_1h.sort_index(inplace=True)
    print(f"\n  1H Data: {len(df_1h):,} bars | {df_1h.index[0]} to {df_1h.index[-1]}")

    # Resample to 4H for higher-timeframe Gann levels
    df_4h = resample_to_4h(df_1h)
    print(f"  4H Data: {len(df_4h):,} bars (resampled from 1H)")

    # Detect 4H swings and compute Gann zones
    print(f"  Computing 4H Gann support/resistance zones...")
    gann_zones, sl_idxs, sh_idxs = build_4h_gann_zones(df_4h, SWING_LOOKBACK_4H)
    print(f"  4H Swing Lows:  {len(sl_idxs)}")
    print(f"  4H Swing Highs: {len(sh_idxs)}")

    # Run simulation on 1H data using 4H Gann levels
    print(f"\n  Running simulation with $200 capital...")
    trades, final_capital, max_dd = simulate(df_1h, gann_zones)

    print_report(trades, final_capital, max_dd, df_1h)


if __name__ == "__main__":
    main()
