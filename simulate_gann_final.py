"""
Gann Square of 9 — FINAL IMPROVED Strategy (2026)
==================================================
Filters Applied:
  1. Higher Timeframe: 4H Gann levels for S/R, 1H entries
  2. Wider Stops: 2nd Gann level below as stop
  3. Time-of-Day: 08:00-20:00 UTC only
  4. EMA Trend Filter: Only long above EMA-50 on 4H (CRITICAL FIX)
  5. Bounce Confirmation: Wait for bullish close above the Gann level
"""

import pandas as pd
import numpy as np
import os

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
DATA_FILE_1H = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05        # 5% risk per trade (more aggressive since fewer trades)
SWING_LOOKBACK_4H = 10
GANN_TOLERANCE_PCT = 0.005       # 0.5% tolerance
STOP_GANN_LEVEL = 2              # 2nd Gann level below
TARGET_GANN_LEVELS = 3           # 3rd Gann level above
COMMISSION_PCT = 0.0004
DEDUP_BARS_1H = 36               # Min 36 hours between trades
FORWARD_BARS = 400               # Max hold ~16 days
EMA_PERIOD_4H = 50               # EMA-50 on 4H for trend
ALLOWED_HOURS_UTC = list(range(8, 21))


# ─── Gann Math ──────────────────────────────────────────────────────────────

def gann_levels(price, n_levels=30):
    sqrt_p = np.sqrt(price)
    res = sorted([(sqrt_p + i * 0.25) ** 2 for i in range(1, n_levels + 1)])
    sup = sorted([(sqrt_p - i * 0.25) ** 2 for i in range(1, n_levels + 1) if (sqrt_p - i * 0.25) > 0], reverse=True)
    return sup, res


# ─── Swing Detection ───────────────────────────────────────────────────────

def detect_swings(highs, lows, lookback):
    swing_lows, swing_highs = [], []
    for i in range(lookback, len(lows) - lookback):
        wl = lows[i - lookback:i + lookback + 1]
        wh = highs[i - lookback:i + lookback + 1]
        if lows[i] == wl.min() and list(wl).count(lows[i]) == 1:
            swing_lows.append(i)
        if highs[i] == wh.max() and list(wh).count(highs[i]) == 1:
            swing_highs.append(i)
    return swing_lows, swing_highs


# ─── Resample & 4H Gann Zones ─────────────────────────────────────────────

def resample_to_4h(df_1h):
    return df_1h.resample('4h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()


def build_4h_gann_zones(df_4h, lookback):
    highs = df_4h['high'].values
    lows = df_4h['low'].values
    times = df_4h.index
    sl_idxs, sh_idxs = detect_swings(highs, lows, lookback)

    gann_by_time = {}
    for bar_4h in range(len(df_4h)):
        bar_time = times[bar_4h]
        active_sl = [i for i in sl_idxs if i < bar_4h][-5:]
        active_sh = [i for i in sh_idxs if i < bar_4h][-5:]

        all_supports = set()
        all_resistances = set()

        for idx in active_sl:
            pivot = lows[idx]
            sup, res = gann_levels(pivot, 15)
            all_supports.update(sup[:8])
            all_resistances.update(res[:8])
            all_supports.add(pivot)

        for idx in active_sh:
            pivot = highs[idx]
            sup, res = gann_levels(pivot, 15)
            all_supports.update(sup[:8])
            all_resistances.update(res[:8])

        gann_by_time[bar_time] = {
            'supports': sorted(all_supports, reverse=True),
            'resistances': sorted(all_resistances),
        }

    return gann_by_time, sl_idxs, sh_idxs


# ─── Simulation ────────────────────────────────────────────────────────────

def simulate(df_1h, df_4h, gann_zones_4h):
    closes = df_1h['close'].values
    highs = df_1h['high'].values
    lows = df_1h['low'].values
    opens = df_1h['open'].values
    times = df_1h.index

    # Precompute 4H EMA-50
    ema_4h = df_4h['close'].ewm(span=EMA_PERIOD_4H, adjust=False).mean()

    gann_times = sorted(gann_zones_4h.keys())

    def get_gann_for_time(t):
        best = None
        for gt in gann_times:
            if gt <= t:
                best = gt
            else:
                break
        return gann_zones_4h.get(best) if best else None

    def get_4h_ema_for_time(t):
        best = None
        for et in ema_4h.index:
            if et <= t:
                best = et
            else:
                break
        return ema_4h.get(best) if best is not None else None

    capital = STARTING_CAPITAL
    peak_capital = capital
    max_drawdown = 0
    trades = []
    last_trade_idx = -DEDUP_BARS_1H

    for bar in range(60, len(closes)):
        if bar - last_trade_idx < DEDUP_BARS_1H:
            continue

        # ─── FILTER 3: Time-of-Day ───
        if times[bar].hour not in ALLOWED_HOURS_UTC:
            continue

        # ─── FILTER 1: 4H Gann levels ───
        gann = get_gann_for_time(times[bar])
        if gann is None:
            continue

        supports = gann['supports']
        resistances = gann['resistances']
        if not supports or not resistances:
            continue

        # ─── FILTER 4: EMA Trend Filter ───
        ema_val = get_4h_ema_for_time(times[bar])
        if ema_val is None:
            continue

        # Only go long if price is ABOVE the 4H EMA-50 (uptrend)
        if closes[bar] < ema_val:
            continue

        # Check if price LOW is near a 4H Gann support
        current_low = lows[bar]
        support_hit = None
        for s in supports:
            if s > current_low * 1.01:
                continue
            if abs(current_low - s) / current_low <= GANN_TOLERANCE_PCT:
                support_hit = s
                break

        if support_hit is None:
            continue

        # ─── FILTER 5: Bounce Confirmation ───
        # Price must close ABOVE the Gann level (bullish confirmation)
        if closes[bar] < support_hit:
            continue

        # Also check that the close is higher than the open (bullish candle)
        if closes[bar] <= opens[bar]:
            continue

        entry_price = closes[bar]

        # ─── FILTER 2: Wider Stops ───
        below = sorted([s for s in supports if s < entry_price], reverse=True)
        stop_level = below[STOP_GANN_LEVEL - 1] if len(below) >= STOP_GANN_LEVEL else entry_price * 0.97

        above = sorted([r for r in resistances if r > entry_price])
        target_price = above[TARGET_GANN_LEVELS - 1] if len(above) >= TARGET_GANN_LEVELS else entry_price * 1.03

        stop_distance = entry_price - stop_level
        target_distance = target_price - entry_price

        if stop_distance <= 0 or target_distance <= 0:
            continue

        rr = target_distance / stop_distance
        if rr < 1.5:
            continue

        # Position sizing
        risk_amount = capital * RISK_PER_TRADE_PCT
        position_size_usd = (risk_amount / stop_distance) * entry_price
        max_position = capital * LEVERAGE
        position_size_usd = min(position_size_usd, max_position)
        qty_btc = position_size_usd / entry_price

        # Execute trade
        exit_price = exit_time = exit_reason = None
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
        gross_pnl = qty_btc * (exit_price - entry_price)
        commission = qty_btc * entry_price * COMMISSION_PCT + qty_btc * exit_price * COMMISSION_PCT
        net_pnl = gross_pnl - commission

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
            'net_pnl': round(net_pnl, 2),
            'pnl_pct': round((net_pnl / (capital - net_pnl)) * 100, 2),
            'balance': round(capital, 2),
            'rr_ratio': round(rr, 1),
            'bars_held': bars_held,
            'stop_dist': round(stop_distance, 1),
            'target_dist': round(target_distance, 1),
            'ema_val': round(ema_val, 1),
        })

        last_trade_idx = bar

    return trades, capital, max_drawdown


# ─── Report ────────────────────────────────────────────────────────────────

def print_report(trades, final_capital, max_dd, df_1h):
    print(f"\n{'=' * 125}")
    print(f"  GANN SQUARE OF 9 -- FINAL IMPROVED STRATEGY RESULTS")
    print(f"  Filters: 4H Gann Levels + Wider Stops + Time-of-Day + EMA-50 Trend + Bounce Confirm")
    print(f"{'=' * 125}")

    print(f"\n  Data:        {DATA_FILE_1H}")
    print(f"  Period:      {df_1h.index[0].strftime('%Y-%m-%d')} to {df_1h.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Capital:     ${STARTING_CAPITAL:,.2f} | Leverage: {LEVERAGE}x | Risk: {RISK_PER_TRADE_PCT*100:.0f}%/trade")
    print(f"  Stop:        2nd Gann below | Target: 3rd Gann above | Hours: 08-20 UTC")

    if not trades:
        print("\n  No trades found. The filters may be too strict for this dataset.")
        print("  Try adjusting: increase GANN_TOLERANCE_PCT, reduce DEDUP_BARS_1H, or use EMA-20.")
        return

    # Trade log
    print(f"\n  {'#':<3} {'Entry Date':<18} {'Exit Date':<18} {'Entry':>9} {'SL':>9} {'TP':>9} "
          f"{'Exit':>9} {'Result':<11} {'P&L':>10} {'Balance':>10} {'R:R':>5} {'Hrs':>4}")
    print(f"  {'_' * 120}")

    wins = losses = 0
    total_profit = total_loss = 0
    max_cw = max_cl = cw = cl = 0

    for i, t in enumerate(trades, 1):
        m = "+" if t['net_pnl'] >= 0 else "-"
        if t['net_pnl'] >= 0:
            wins += 1
            total_profit += t['net_pnl']
            cw += 1; cl = 0
            max_cw = max(max_cw, cw)
        else:
            losses += 1
            total_loss += abs(t['net_pnl'])
            cl += 1; cw = 0
            max_cl = max(max_cl, cl)

        print(f"  {i:<3} {str(t['entry_time'])[:16]:<18} {str(t['exit_time'])[:16]:<18} "
              f"${t['entry_price']:>7,.0f} ${t['stop_loss']:>7,.0f} ${t['target']:>7,.0f} "
              f"${t['exit_price']:>7,.0f} {t['exit_reason']:<11} {m}${abs(t['net_pnl']):>8,.2f} "
              f"${t['balance']:>8,.2f} {t['rr_ratio']:>4.1f} {t['bars_held']:>4}")

    print(f"  {'_' * 120}")

    wr = (wins / len(trades) * 100) if trades else 0
    ret = ((final_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    aw = total_profit / wins if wins > 0 else 0
    al = total_loss / losses if losses > 0 else 0
    pf = total_profit / total_loss if total_loss > 0 else float('inf')
    exp = (wr / 100 * aw) - ((100 - wr) / 100 * al)

    print(f"""
  {'=' * 65}
  PERFORMANCE SUMMARY
  {'=' * 65}

  CAPITAL
    Starting:               ${STARTING_CAPITAL:>12,.2f}
    Final:                  ${final_capital:>12,.2f}
    Net Profit/Loss:        ${final_capital - STARTING_CAPITAL:>12,.2f}
    Total Return:           {ret:>12.2f}%

  TRADES
    Total:                  {len(trades):>12}
    Winners:                {wins:>12}  ({wr:.1f}%)
    Losers:                 {losses:>12}  ({100-wr:.1f}%)
    Max Consec Wins:        {max_cw:>12}
    Max Consec Losses:      {max_cl:>12}

  PROFITABILITY
    Gross Profit:           ${total_profit:>12,.2f}
    Gross Loss:             ${total_loss:>12,.2f}
    Profit Factor:          {pf:>12.2f}
    Avg Win:                ${aw:>12,.2f}
    Avg Loss:               ${al:>12,.2f}
    Expectancy/Trade:       ${exp:>12,.2f}

  RISK
    Max Drawdown:           {max_dd:>12.2f}%
    Leverage:               {LEVERAGE:>12}x

  {'=' * 65}
  COMPARISON: RAW vs IMPROVED
  {'=' * 65}

    Metric                   RAW Gann        IMPROVED
    {'_' * 55}
    Final Capital            $127.41         ${final_capital:>10,.2f}
    Return                   -36.29%         {ret:>10.2f}%
    Trades                   91              {len(trades):>10}
    Win Rate                 33.0%           {wr:>10.1f}%
    Profit Factor            0.65            {pf:>10.2f}
    Max Drawdown             43.17%          {max_dd:>10.2f}%
    Expectancy               -$0.80          ${exp:>10,.2f}
    {'_' * 55}
""")

    # Monthly
    print(f"  MONTHLY BREAKDOWN:")
    print(f"  {'_' * 75}")
    monthly = {}
    for t in trades:
        key = t['entry_time'].strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'pnl': 0, 'trades': 0, 'wins': 0}
        monthly[key]['pnl'] += t['net_pnl']
        monthly[key]['trades'] += 1
        if t['net_pnl'] >= 0:
            monthly[key]['wins'] += 1

    rc = STARTING_CAPITAL
    for month in sorted(monthly.keys()):
        m = monthly[month]
        mwr = (m['wins'] / m['trades'] * 100) if m['trades'] > 0 else 0
        rc += m['pnl']
        marker = "+" if m['pnl'] >= 0 else " "
        bar = ("#" if m['pnl'] >= 0 else "-") * max(1, int(abs(m['pnl'])))
        print(f"    {month}: {m['trades']:>3} trades | WR: {mwr:>5.1f}% | P&L: {marker}${m['pnl']:>9,.2f} | Bal: ${rc:>9,.2f}  {bar}")

    print(f"  {'_' * 75}")
    print(f"\n{'=' * 125}\n")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 125)
    print("  GANN SQUARE OF 9 -- FINAL IMPROVED STRATEGY")
    print("  1. 4H Gann levels (higher timeframe alignment)")
    print("  2. Wider stops (2nd Gann below)")
    print("  3. Time filter (08:00-20:00 UTC)")
    print("  4. EMA-50 trend filter on 4H (ONLY long in uptrend)")
    print("  5. Bounce confirmation (bullish candle close above Gann level)")
    print("=" * 125)

    fpath_1h = os.path.join(DATA_DIR, DATA_FILE_1H)
    df_1h = pd.read_csv(fpath_1h)
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], dayfirst=True, format='mixed')
    df_1h.set_index('timestamp', inplace=True)
    df_1h.sort_index(inplace=True)
    print(f"\n  1H Data: {len(df_1h):,} bars | {df_1h.index[0]} to {df_1h.index[-1]}")

    df_4h = resample_to_4h(df_1h)
    print(f"  4H Data: {len(df_4h):,} bars (resampled)")

    gann_zones, sl_idxs, sh_idxs = build_4h_gann_zones(df_4h, SWING_LOOKBACK_4H)
    print(f"  4H Swings: {len(sl_idxs)} lows, {len(sh_idxs)} highs")

    print(f"\n  Simulating $200 capital with ALL filters...")
    trades, final_capital, max_dd = simulate(df_1h, df_4h, gann_zones)
    print_report(trades, final_capital, max_dd, df_1h)


if __name__ == "__main__":
    main()
