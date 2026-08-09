"""
Gann Square of 9 — Trading Simulation (2026)
=============================================
Simulates trading BTC with $200 starting capital using Gann levels.
Uses Binance Futures-style leverage with proper risk management.
"""

import pandas as pd
import numpy as np
import os

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
DATA_FILE = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0      # USD
LEVERAGE = 10                 # 10x leverage (conservative for BTC futures)
RISK_PER_TRADE_PCT = 0.03     # Risk 3% of capital per trade
SWING_LOOKBACK = 20           # Bars for swing detection
GANN_TOLERANCE_PCT = 0.003    # 0.3% tolerance for touching Gann level
STOP_LOSS_MULT = 1.5          # Stop at 1.5x the Gann level spacing below entry
MIN_RR_RATIO = 2.0            # Minimum reward:risk ratio to take a trade
TARGET_GANN_LEVELS = 2        # Target the 2nd Gann level above entry
COMMISSION_PCT = 0.0004       # 0.04% taker fee (Binance futures)
DEDUP_BARS = 48               # Minimum bars between trades
FORWARD_BARS = 200            # Max bars to hold a trade

# ─── Gann Math ──────────────────────────────────────────────────────────────

def gann_levels(price, n_levels=20):
    """Compute Gann Square of 9 support & resistance levels."""
    sqrt_p = np.sqrt(price)
    res = [(sqrt_p + i * 0.25) ** 2 for i in range(1, n_levels + 1)]
    sup = [(sqrt_p - i * 0.25) ** 2 for i in range(1, n_levels + 1) if (sqrt_p - i * 0.25) > 0]
    return sup, res


def nearest_gann_below(price, levels):
    """Find the nearest Gann level below the price."""
    below = [l for l in levels if l < price]
    return max(below) if below else None


def nearest_gann_above(price, levels):
    """Find the nearest Gann level above the price."""
    above = [l for l in levels if l > price]
    return min(above) if above else None


# ─── Swing Detection ───────────────────────────────────────────────────────

def detect_swings(df, lookback):
    swing_lows = []
    swing_highs = []
    lows = df['low'].values
    highs = df['high'].values
    for i in range(lookback, len(lows) - lookback):
        window_l = lows[i - lookback:i + lookback + 1]
        window_h = highs[i - lookback:i + lookback + 1]
        if lows[i] == window_l.min() and list(window_l).count(lows[i]) == 1:
            swing_lows.append(i)
        if highs[i] == window_h.max() and list(window_h).count(highs[i]) == 1:
            swing_highs.append(i)
    return swing_lows, swing_highs


# ─── Trading Simulation ────────────────────────────────────────────────────

def simulate(df):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    times = df.index

    swing_low_idxs, swing_high_idxs = detect_swings(df, SWING_LOOKBACK)

    capital = STARTING_CAPITAL
    peak_capital = capital
    max_drawdown = 0
    trades = []
    last_trade_idx = -DEDUP_BARS

    # Walk through data bar by bar
    for bar in range(SWING_LOOKBACK * 2, len(closes)):
        # Skip if too close to last trade
        if bar - last_trade_idx < DEDUP_BARS:
            continue

        # Find the most recent swing high and swing low BEFORE this bar
        recent_sh = [s for s in swing_high_idxs if s < bar - 2]
        recent_sl = [s for s in swing_low_idxs if s < bar - 2]

        if not recent_sh and not recent_sl:
            continue

        # Compute Gann levels from recent pivots
        gann_supports = set()
        gann_resistances = set()

        # From recent swing highs → support levels below
        for sh_idx in recent_sh[-3:]:  # Last 3 swing highs
            sh_price = highs[sh_idx]
            sup, res = gann_levels(sh_price)
            for s in sup:
                if abs(s - lows[bar]) / lows[bar] < GANN_TOLERANCE_PCT:
                    gann_supports.add(round(s, 1))
            for r in res:
                gann_resistances.add(round(r, 1))

        # From recent swing lows → the low itself + levels
        for sl_idx in recent_sl[-3:]:
            sl_price = lows[sl_idx]
            sup, res = gann_levels(sl_price)
            # The swing low price itself is a Gann pivot
            if abs(sl_price - lows[bar]) / lows[bar] < GANN_TOLERANCE_PCT:
                gann_supports.add(round(sl_price, 1))
            for s in sup:
                if abs(s - lows[bar]) / lows[bar] < GANN_TOLERANCE_PCT:
                    gann_supports.add(round(s, 1))
            for r in res:
                gann_resistances.add(round(r, 1))

        if not gann_supports:
            continue

        # Price is touching a Gann support level → potential long entry
        entry_price = closes[bar]
        entry_level = min(gann_supports, key=lambda x: abs(x - entry_price))

        # Compute stop loss and take profit using Gann levels
        all_sup, all_res = gann_levels(entry_level)

        # Stop loss: next Gann level below the support
        stop_level = nearest_gann_below(entry_level, all_sup)
        if stop_level is None:
            stop_level = entry_level * 0.99  # fallback: 1% below

        stop_distance = entry_price - stop_level

        # Take profit: TARGET_GANN_LEVELS levels above entry
        sorted_res = sorted([r for r in all_res if r > entry_price])
        if len(sorted_res) < TARGET_GANN_LEVELS:
            continue
        target_price = sorted_res[TARGET_GANN_LEVELS - 1]
        target_distance = target_price - entry_price

        # Check minimum R:R
        if stop_distance <= 0:
            continue
        rr = target_distance / stop_distance
        if rr < MIN_RR_RATIO:
            continue

        # Position sizing: risk RISK_PER_TRADE_PCT of capital
        risk_amount = capital * RISK_PER_TRADE_PCT
        position_size_usd = (risk_amount / stop_distance) * entry_price
        max_position = capital * LEVERAGE
        position_size_usd = min(position_size_usd, max_position)
        qty_btc = position_size_usd / entry_price

        # Simulate the trade forward
        trade_result = None
        exit_price = None
        exit_time = None
        exit_reason = None

        end_bar = min(bar + FORWARD_BARS, len(closes))
        for j in range(bar + 1, end_bar):
            # Check stop loss hit (using low of candle)
            if lows[j] <= stop_level:
                exit_price = stop_level
                exit_time = times[j]
                exit_reason = "STOP LOSS"
                break
            # Check take profit hit (using high of candle)
            if highs[j] >= target_price:
                exit_price = target_price
                exit_time = times[j]
                exit_reason = "TARGET HIT"
                break

        # If neither hit, close at last bar
        if exit_price is None:
            exit_price = closes[end_bar - 1]
            exit_time = times[end_bar - 1]
            exit_reason = "TIME EXIT"

        # Calculate P&L
        price_change = exit_price - entry_price
        gross_pnl = qty_btc * price_change
        commission = qty_btc * entry_price * COMMISSION_PCT + qty_btc * exit_price * COMMISSION_PCT
        net_pnl = gross_pnl - commission
        pnl_pct = (net_pnl / capital) * 100

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
        })

        last_trade_idx = bar

    return trades, capital, max_drawdown


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    filepath = os.path.join(DATA_DIR, DATA_FILE)
    print("=" * 110)
    print("  GANN SQUARE OF 9 — TRADING SIMULATION")
    print("=" * 110)

    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    print(f"\n  Data:              {DATA_FILE}")
    print(f"  Period:            {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Starting Capital:  ${STARTING_CAPITAL:,.2f}")
    print(f"  Leverage:          {LEVERAGE}x")
    print(f"  Risk Per Trade:    {RISK_PER_TRADE_PCT*100:.1f}%")
    print(f"  Min R:R Ratio:     {MIN_RR_RATIO}:1")
    print(f"  Commission:        {COMMISSION_PCT*100:.3f}% per side")
    print(f"  Target:            {TARGET_GANN_LEVELS}nd Gann level above entry")

    trades, final_capital, max_dd = simulate(df)

    if not trades:
        print("\n  No trades executed.")
        return

    # ── Trade Log ──
    print(f"\n{'=' * 110}")
    print(f"  TRADE LOG ({len(trades)} trades)")
    print(f"{'=' * 110}")
    print(f"\n  {'#':<3} {'Entry Date':<18} {'Exit Date':<18} {'Entry':>10} {'SL':>10} {'TP':>10} {'Exit':>10} {'Result':<12} {'P&L':>10} {'Balance':>10}")
    print(f"  {'-' * 107}")

    wins = 0
    losses = 0
    total_profit = 0
    total_loss = 0

    for i, t in enumerate(trades, 1):
        result_marker = "+" if t['net_pnl'] >= 0 else "-"
        if t['net_pnl'] >= 0:
            wins += 1
            total_profit += t['net_pnl']
        else:
            losses += 1
            total_loss += abs(t['net_pnl'])

        print(f"  {i:<3} {str(t['entry_time'])[:16]:<18} {str(t['exit_time'])[:16]:<18} "
              f"${t['entry_price']:>8,.1f} ${t['stop_loss']:>8,.1f} ${t['target']:>8,.1f} ${t['exit_price']:>8,.1f} "
              f"{t['exit_reason']:<12} {result_marker}${abs(t['net_pnl']):>8,.2f} ${t['balance']:>8,.2f}")

    print(f"  {'-' * 107}")

    # ── Summary ──
    win_rate = (wins / len(trades)) * 100 if trades else 0
    total_return = ((final_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    avg_win = total_profit / wins if wins > 0 else 0
    avg_loss = total_loss / losses if losses > 0 else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)

    print(f"\n{'=' * 110}")
    print(f"  PERFORMANCE SUMMARY")
    print(f"{'=' * 110}")
    print(f"""
  Starting Capital:      ${STARTING_CAPITAL:>12,.2f}
  Final Capital:         ${final_capital:>12,.2f}
  Net Profit:            ${final_capital - STARTING_CAPITAL:>12,.2f}
  Total Return:          {total_return:>12.2f}%
  
  Total Trades:          {len(trades):>12}
  Winning Trades:        {wins:>12}  ({win_rate:.1f}%)
  Losing Trades:         {losses:>12}  ({100-win_rate:.1f}%)
  
  Gross Profit:          ${total_profit:>12,.2f}
  Gross Loss:            ${total_loss:>12,.2f}
  Profit Factor:         {profit_factor:>12.2f}
  
  Avg Win:               ${avg_win:>12,.2f}
  Avg Loss:              ${avg_loss:>12,.2f}
  Expectancy:            ${expectancy:>12,.2f} per trade
  
  Max Drawdown:          {max_dd:>12.2f}%
  Leverage Used:         {LEVERAGE:>12}x
""")

    # ── Monthly Breakdown ──
    print(f"  MONTHLY P&L:")
    print(f"  {'-' * 60}")
    monthly = {}
    for t in trades:
        key = t['entry_time'].strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'pnl': 0, 'trades': 0, 'wins': 0}
        monthly[key]['pnl'] += t['net_pnl']
        monthly[key]['trades'] += 1
        if t['net_pnl'] >= 0:
            monthly[key]['wins'] += 1

    for month in sorted(monthly.keys()):
        m = monthly[month]
        wr = (m['wins'] / m['trades'] * 100) if m['trades'] > 0 else 0
        marker = "+" if m['pnl'] >= 0 else ""
        print(f"    {month}:  {m['trades']:>3} trades  |  WR: {wr:>5.1f}%  |  P&L: {marker}${m['pnl']:>10,.2f}")

    print(f"  {'-' * 60}")

    # ── Equity Curve Data ──
    print(f"\n  EQUITY CURVE:")
    print(f"  {'-' * 60}")
    balance = STARTING_CAPITAL
    print(f"    Start       : ${balance:>10,.2f}  {'|' + '#' * int(balance / STARTING_CAPITAL * 20)}")
    for i, t in enumerate(trades):
        balance = t['balance']
        bar_len = max(1, int(balance / STARTING_CAPITAL * 20))
        bar_char = '#' if t['net_pnl'] >= 0 else '-'
        print(f"    Trade {i+1:>3}    : ${balance:>10,.2f}  {'|' + bar_char * bar_len}")

    print(f"  {'-' * 60}")
    print(f"\n{'=' * 110}\n")


if __name__ == "__main__":
    main()
