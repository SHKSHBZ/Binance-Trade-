"""
Gann Square of 9 — BI-DIRECTIONAL Strategy (Long + Short)
==========================================================
LONG at Gann support when above EMA (uptrend)
SHORT at Gann resistance when below EMA (downtrend)

Filters:
  1. Higher Timeframe: 4H Gann levels, 1H entries
  2. Wider Stops: 2nd Gann level beyond entry as stop
  3. Time-of-Day: 08:00-20:00 UTC only
  4. EMA Trend: Above EMA = long zone, Below EMA = short zone
  5. Candle Confirmation: Bullish close for longs, bearish close for shorts
"""

import pandas as pd
import numpy as np
import os

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.04        # 4% risk per trade
SWING_LOOKBACK_4H = 10
GANN_TOLERANCE_PCT = 0.005       # 0.5% tolerance
STOP_GANN_LEVEL = 2              # 2nd Gann level beyond entry
TARGET_GANN_LEVELS = 3           # 3rd Gann level in trade direction
COMMISSION_PCT = 0.0004          # 0.04% per side (Binance Futures)
DEDUP_BARS_1H = 24               # Min 24h between trades
FORWARD_BARS = 300               # Max hold ~12.5 days
EMA_PERIOD_4H = 50               # EMA-50 on 4H
ALLOWED_HOURS_UTC = list(range(8, 21))  # 08:00-20:00 UTC


# ─── Gann Math ──────────────────────────────────────────────────────────────

def gann_levels(price, n_levels=20):
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


# ─── Build 4H Infrastructure ──────────────────────────────────────────────

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
            all_resistances.add(pivot)

        gann_by_time[bar_time] = {
            'supports': sorted(all_supports, reverse=True),
            'resistances': sorted(all_resistances),
        }

    return gann_by_time, sl_idxs, sh_idxs


# ─── Simulation ────────────────────────────────────────────────────────────

def simulate(df_1h, df_4h, gann_zones_4h, capital_start):
    closes = df_1h['close'].values
    highs = df_1h['high'].values
    lows = df_1h['low'].values
    opens = df_1h['open'].values
    times = df_1h.index

    ema_4h = df_4h['close'].ewm(span=EMA_PERIOD_4H, adjust=False).mean()
    gann_times = sorted(gann_zones_4h.keys())

    def get_gann(t):
        best = None
        for gt in gann_times:
            if gt <= t:
                best = gt
            else:
                break
        return gann_zones_4h.get(best) if best else None

    def get_ema(t):
        best = None
        for et in ema_4h.index:
            if et <= t:
                best = et
            else:
                break
        return ema_4h.get(best) if best is not None else None

    capital = capital_start
    peak_capital = capital
    max_drawdown = 0
    trades = []
    last_trade_idx = -DEDUP_BARS_1H

    for bar in range(60, len(closes)):
        if bar - last_trade_idx < DEDUP_BARS_1H:
            continue

        # Time filter
        if times[bar].hour not in ALLOWED_HOURS_UTC:
            continue

        gann = get_gann(times[bar])
        if gann is None:
            continue

        supports = gann['supports']
        resistances = gann['resistances']
        if not supports or not resistances:
            continue

        ema_val = get_ema(times[bar])
        if ema_val is None:
            continue

        entry_price = closes[bar]
        direction = None
        gann_level_hit = None

        # ═══ LONG SETUP: Price above EMA + touching Gann support + bullish candle ═══
        if entry_price > ema_val:
            for s in supports:
                if s > lows[bar] * 1.01:
                    continue
                if abs(lows[bar] - s) / lows[bar] <= GANN_TOLERANCE_PCT:
                    gann_level_hit = s
                    break
            if gann_level_hit and closes[bar] > gann_level_hit and closes[bar] > opens[bar]:
                direction = "LONG"

        # ═══ SHORT SETUP: Price below EMA + touching Gann resistance + bearish candle ═══
        if direction is None and entry_price < ema_val:
            for r in resistances:
                if r < highs[bar] * 0.99:
                    continue
                if abs(highs[bar] - r) / highs[bar] <= GANN_TOLERANCE_PCT:
                    gann_level_hit = r
                    break
            if gann_level_hit and closes[bar] < gann_level_hit and closes[bar] < opens[bar]:
                direction = "SHORT"

        if direction is None:
            continue

        # ─── Calculate Stop & Target ───
        if direction == "LONG":
            below = sorted([s for s in supports if s < entry_price], reverse=True)
            stop_level = below[STOP_GANN_LEVEL - 1] if len(below) >= STOP_GANN_LEVEL else entry_price * 0.97
            above = sorted([r for r in resistances if r > entry_price])
            target_price = above[TARGET_GANN_LEVELS - 1] if len(above) >= TARGET_GANN_LEVELS else entry_price * 1.03
            stop_distance = entry_price - stop_level
            target_distance = target_price - entry_price
        else:  # SHORT
            above = sorted([r for r in resistances if r > entry_price])
            stop_level = above[STOP_GANN_LEVEL - 1] if len(above) >= STOP_GANN_LEVEL else entry_price * 1.03
            below = sorted([s for s in supports if s < entry_price], reverse=True)
            target_price = below[TARGET_GANN_LEVELS - 1] if len(below) >= TARGET_GANN_LEVELS else entry_price * 0.97
            stop_distance = stop_level - entry_price
            target_distance = entry_price - target_price

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
            if direction == "LONG":
                if lows[j] <= stop_level:
                    exit_price, exit_time, exit_reason = stop_level, times[j], "STOP LOSS"
                    break
                if highs[j] >= target_price:
                    exit_price, exit_time, exit_reason = target_price, times[j], "TARGET HIT"
                    break
            else:  # SHORT
                if highs[j] >= stop_level:
                    exit_price, exit_time, exit_reason = stop_level, times[j], "STOP LOSS"
                    break
                if lows[j] <= target_price:
                    exit_price, exit_time, exit_reason = target_price, times[j], "TARGET HIT"
                    break

        if exit_price is None:
            exit_price, exit_time, exit_reason = closes[end_bar - 1], times[end_bar - 1], "TIME EXIT"

        # P&L
        if direction == "LONG":
            gross_pnl = qty_btc * (exit_price - entry_price)
        else:
            gross_pnl = qty_btc * (entry_price - exit_price)

        commission = qty_btc * entry_price * COMMISSION_PCT + qty_btc * exit_price * COMMISSION_PCT
        net_pnl = gross_pnl - commission

        capital += net_pnl
        if capital <= 0:
            capital = 0
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital * 100 if peak_capital > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

        trades.append({
            'dir': direction,
            'entry_time': times[bar],
            'exit_time': exit_time,
            'entry_price': round(entry_price, 1),
            'gann_level': round(gann_level_hit, 1),
            'stop_loss': round(stop_level, 1),
            'target': round(target_price, 1),
            'exit_price': round(exit_price, 1),
            'exit_reason': exit_reason,
            'net_pnl': round(net_pnl, 2),
            'balance': round(capital, 2),
            'rr_ratio': round(rr, 1),
            'bars_held': bars_held,
            'stop_dist': round(stop_distance, 1),
            'target_dist': round(target_distance, 1),
        })

        last_trade_idx = bar
        if capital <= 0:
            break

    return trades, capital, max_drawdown


# ─── Report ────────────────────────────────────────────────────────────────

def print_report(trades, final_capital, max_dd, df_1h, label):
    print(f"\n{'=' * 125}")
    print(f"  GANN SQUARE OF 9 -- BI-DIRECTIONAL (LONG + SHORT)")
    print(f"  {label}")
    print(f"{'=' * 125}")

    print(f"\n  Period:      {df_1h.index[0].strftime('%Y-%m-%d')} to {df_1h.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Capital:     ${STARTING_CAPITAL:,.2f} | Leverage: {LEVERAGE}x | Risk: {RISK_PER_TRADE_PCT*100:.0f}%/trade")
    print(f"  Filters:     4H Gann | Wider Stops (2nd level) | 08-20 UTC | EMA-50 Trend | Candle Confirm")

    if not trades:
        print("\n  No trades executed.\n")
        return final_capital

    # Trade log
    print(f"\n  {'#':<3} {'Dir':<6} {'Entry Date':<18} {'Exit Date':<18} {'Entry':>9} {'SL':>9} {'TP':>9} "
          f"{'Exit':>9} {'Result':<11} {'P&L':>10} {'Balance':>10} {'R:R':>5}")
    print(f"  {'_' * 122}")

    wins = losses = 0
    long_wins = long_losses = short_wins = short_losses = 0
    total_profit = total_loss = 0
    max_cw = max_cl = cw = cl = 0

    for i, t in enumerate(trades, 1):
        m = "+" if t['net_pnl'] >= 0 else "-"
        if t['net_pnl'] >= 0:
            wins += 1
            total_profit += t['net_pnl']
            cw += 1; cl = 0; max_cw = max(max_cw, cw)
            if t['dir'] == 'LONG':
                long_wins += 1
            else:
                short_wins += 1
        else:
            losses += 1
            total_loss += abs(t['net_pnl'])
            cl += 1; cw = 0; max_cl = max(max_cl, cl)
            if t['dir'] == 'LONG':
                long_losses += 1
            else:
                short_losses += 1

        dir_icon = "^L" if t['dir'] == 'LONG' else "vS"
        print(f"  {i:<3} {dir_icon:<6} {str(t['entry_time'])[:16]:<18} {str(t['exit_time'])[:16]:<18} "
              f"${t['entry_price']:>7,.0f} ${t['stop_loss']:>7,.0f} ${t['target']:>7,.0f} "
              f"${t['exit_price']:>7,.0f} {t['exit_reason']:<11} {m}${abs(t['net_pnl']):>8,.2f} "
              f"${t['balance']:>8,.2f} {t['rr_ratio']:>4.1f}")

    print(f"  {'_' * 122}")

    wr = (wins / len(trades) * 100) if trades else 0
    ret = ((final_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    aw = total_profit / wins if wins > 0 else 0
    al = total_loss / losses if losses > 0 else 0
    pf = total_profit / total_loss if total_loss > 0 else float('inf')
    exp = (wr / 100 * aw) - ((100 - wr) / 100 * al)

    total_longs = long_wins + long_losses
    total_shorts = short_wins + short_losses
    long_wr = (long_wins / total_longs * 100) if total_longs > 0 else 0
    short_wr = (short_wins / total_shorts * 100) if total_shorts > 0 else 0

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

  BY DIRECTION
    Longs:                  {total_longs:>12}  (Win Rate: {long_wr:.1f}%)
    Shorts:                 {total_shorts:>12}  (Win Rate: {short_wr:.1f}%)

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
""")

    # Monthly
    print(f"  MONTHLY BREAKDOWN:")
    print(f"  {'_' * 85}")
    monthly = {}
    for t in trades:
        key = t['entry_time'].strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'pnl': 0, 'trades': 0, 'wins': 0, 'longs': 0, 'shorts': 0}
        monthly[key]['pnl'] += t['net_pnl']
        monthly[key]['trades'] += 1
        if t['net_pnl'] >= 0:
            monthly[key]['wins'] += 1
        if t['dir'] == 'LONG':
            monthly[key]['longs'] += 1
        else:
            monthly[key]['shorts'] += 1

    rc = STARTING_CAPITAL
    for month in sorted(monthly.keys()):
        m = monthly[month]
        mwr = (m['wins'] / m['trades'] * 100) if m['trades'] > 0 else 0
        rc += m['pnl']
        marker = "+" if m['pnl'] >= 0 else " "
        bar_len = max(1, int(abs(m['pnl']) / 3))
        bar = ("#" if m['pnl'] >= 0 else "-") * min(bar_len, 30)
        print(f"    {month}: {m['trades']:>3} ({m['longs']}L/{m['shorts']}S) | WR: {mwr:>5.1f}% | "
              f"P&L: {marker}${m['pnl']:>9,.2f} | Bal: ${rc:>9,.2f}  {bar}")

    print(f"  {'_' * 85}")

    # Equity curve
    print(f"\n  EQUITY CURVE:")
    print(f"  {'_' * 65}")
    print(f"    {'Start':<18} ${STARTING_CAPITAL:>10,.2f}  |{'=' * 30}")
    step = max(1, len(trades) // 25)
    for i, t in enumerate(trades):
        if i % step == 0 or i == len(trades) - 1:
            pct = (t['balance'] / STARTING_CAPITAL) * 100
            bar_len = max(1, int(pct / 100 * 30))
            char = '=' if t['net_pnl'] >= 0 else '-'
            d = "L" if t['dir'] == 'LONG' else "S"
            label = f"#{i+1:<3}{d} {str(t['entry_time'])[:10]}"
            print(f"    {label:<18} ${t['balance']:>10,.2f}  |{char * bar_len} {pct:.0f}%")
    print(f"  {'_' * 65}")
    print(f"\n{'=' * 125}\n")

    return final_capital


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 125)
    print("  GANN SQUARE OF 9 -- BI-DIRECTIONAL STRATEGY (LONG + SHORT)")
    print("  LONG at Gann support (above EMA)  |  SHORT at Gann resistance (below EMA)")
    print("=" * 125)

    datasets = [
        ("BTCUSDT_1h_Jan_to_Jul2026.csv", "2026 (Jan-Jul) -- The Bear Market Test"),
        ("BTCUSDT_1h_2023_to_2025.csv", "2023-2025 -- Full Cycle (Bear to Bull)"),
    ]

    for fname, label in datasets:
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"\n  Skipping {fname} (not found)")
            continue

        print(f"\n  Loading: {fname}")
        df_1h = pd.read_csv(fpath)
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], dayfirst=True, format='mixed')
        df_1h.set_index('timestamp', inplace=True)
        df_1h.sort_index(inplace=True)
        print(f"  1H: {len(df_1h):,} bars | {df_1h.index[0]} to {df_1h.index[-1]}")

        df_4h = resample_to_4h(df_1h)
        print(f"  4H: {len(df_4h):,} bars")

        gann_zones, sl_idxs, sh_idxs = build_4h_gann_zones(df_4h, SWING_LOOKBACK_4H)
        print(f"  4H Swings: {len(sl_idxs)} lows, {len(sh_idxs)} highs")

        trades, final_capital, max_dd = simulate(df_1h, df_4h, gann_zones, STARTING_CAPITAL)
        print_report(trades, final_capital, max_dd, df_1h, label)


if __name__ == "__main__":
    main()
