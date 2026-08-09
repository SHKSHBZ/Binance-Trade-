"""
Gann Square of 9 — CORRECTED BI-DIRECTIONAL Strategy
=====================================================
KEY FIX: Use FULL ROTATION (360 deg) Gann levels, not quarter turns.

Quarter turn (90 deg) at BTC $90K = $150 apart → noise kills you
Full rotation (360 deg) at BTC $90K = $600 apart → meaningful levels
Double rotation (720 deg) at BTC $90K = $1,200 apart → strong S/R

Strategy:
  - Only use MAJOR pivots (weekly swing highs/lows on 4H)
  - Gann levels at 360 deg intervals (full rotations only)
  - LONG at Gann support when above EMA + bullish confirmation
  - SHORT at Gann resistance when below EMA + bearish confirmation
  - Stop: 1 full Gann rotation beyond entry
  - Target: 2 full Gann rotations in trade direction
"""

import pandas as pd
import numpy as np
import os

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05        # 5% risk (fewer trades, higher conviction)
SWING_LOOKBACK_4H = 20           # ~80 hours = major weekly swings only
GANN_ROTATION_STEP = 1.0         # FULL rotation (360 deg) = increment of 1.0
GANN_TOLERANCE_PCT = 0.004       # 0.4% tolerance
STOP_ROTATIONS = 1               # Stop 1 full rotation beyond entry
TARGET_ROTATIONS = 2             # Target 2 full rotations in trade direction
COMMISSION_PCT = 0.0004
DEDUP_BARS_1H = 36               # Min 36h between trades
FORWARD_BARS = 400               # Max hold ~16 days
EMA_PERIOD_4H = 50
ALLOWED_HOURS_UTC = list(range(8, 21))


# ─── Gann Math (FULL ROTATIONS) ────────────────────────────────────────────

def gann_full_rotation_levels(price, n_rotations=10):
    """
    Compute Gann Square of 9 levels using FULL 360-degree rotations.
    Level = (sqrt(price) +/- N)^2  where N = 1, 2, 3, ...
    Each N = one full rotation (360 degrees) around the square.
    """
    sqrt_p = np.sqrt(price)
    resistance = []
    support = []
    for n in range(1, n_rotations + 1):
        r = (sqrt_p + n * GANN_ROTATION_STEP) ** 2
        resistance.append(round(r, 1))
        s_val = sqrt_p - n * GANN_ROTATION_STEP
        if s_val > 0:
            support.append(round(s_val ** 2, 1))
    return sorted(support, reverse=True), sorted(resistance)


def gann_spacing_at_price(price):
    """Return approximate spacing between Gann full-rotation levels at a given price."""
    sqrt_p = np.sqrt(price)
    level_here = sqrt_p ** 2
    level_next = (sqrt_p + GANN_ROTATION_STEP) ** 2
    return level_next - level_here


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


# ─── 4H Infrastructure ────────────────────────────────────────────────────

def resample_to_4h(df_1h):
    return df_1h.resample('4h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()


def build_gann_zones(df_4h, lookback):
    highs = df_4h['high'].values
    lows = df_4h['low'].values
    times = df_4h.index
    sl_idxs, sh_idxs = detect_swings(highs, lows, lookback)

    gann_by_time = {}
    for bar in range(len(df_4h)):
        t = times[bar]
        active_sl = [i for i in sl_idxs if i < bar][-3:]  # Last 3 major swings only
        active_sh = [i for i in sh_idxs if i < bar][-3:]

        all_sup = set()
        all_res = set()

        for idx in active_sl:
            pivot = lows[idx]
            sup, res = gann_full_rotation_levels(pivot)
            all_sup.update(sup)
            all_res.update(res)
            all_sup.add(round(pivot, 1))

        for idx in active_sh:
            pivot = highs[idx]
            sup, res = gann_full_rotation_levels(pivot)
            all_sup.update(sup)
            all_res.update(res)
            all_res.add(round(pivot, 1))

        gann_by_time[t] = {
            'supports': sorted(all_sup, reverse=True),
            'resistances': sorted(all_res),
        }

    return gann_by_time, sl_idxs, sh_idxs


# ─── Simulation ────────────────────────────────────────────────────────────

def simulate(df_1h, df_4h, gann_zones, cap_start):
    closes = df_1h['close'].values
    highs = df_1h['high'].values
    lows = df_1h['low'].values
    opens = df_1h['open'].values
    times = df_1h.index

    ema_4h = df_4h['close'].ewm(span=EMA_PERIOD_4H, adjust=False).mean()
    gann_times = sorted(gann_zones.keys())

    def get_gann(t):
        best = None
        for gt in gann_times:
            if gt <= t:
                best = gt
            else:
                break
        return gann_zones.get(best) if best else None

    def get_ema(t):
        best = None
        for et in ema_4h.index:
            if et <= t:
                best = et
            else:
                break
        return ema_4h.get(best) if best is not None else None

    capital = cap_start
    peak = capital
    max_dd = 0
    trades = []
    last_idx = -DEDUP_BARS_1H

    for bar in range(80, len(closes)):
        if bar - last_idx < DEDUP_BARS_1H:
            continue
        if times[bar].hour not in ALLOWED_HOURS_UTC:
            continue

        gann = get_gann(times[bar])
        if not gann:
            continue
        sups = gann['supports']
        ress = gann['resistances']
        if not sups or not ress:
            continue

        ema_val = get_ema(times[bar])
        if ema_val is None:
            continue

        price = closes[bar]
        direction = None
        level_hit = None
        stop = target = None

        # ═══ LONG: above EMA, low touches Gann support, bullish candle ═══
        if price > ema_val:
            for s in sups:
                if abs(lows[bar] - s) / max(lows[bar], 1) <= GANN_TOLERANCE_PCT and s <= lows[bar] * 1.005:
                    level_hit = s
                    break
            if level_hit and price > level_hit and price > opens[bar]:
                direction = "LONG"
                # Stop: 1 full Gann rotation below the support level
                sqrt_lvl = np.sqrt(level_hit)
                stop = (sqrt_lvl - STOP_ROTATIONS * GANN_ROTATION_STEP) ** 2
                if stop <= 0:
                    stop = level_hit * 0.98
                # Target: 2 full rotations above entry
                sqrt_entry = np.sqrt(price)
                target = (sqrt_entry + TARGET_ROTATIONS * GANN_ROTATION_STEP) ** 2

        # ═══ SHORT: below EMA, high touches Gann resistance, bearish candle ═══
        if direction is None and price < ema_val:
            for r in ress:
                if abs(highs[bar] - r) / max(highs[bar], 1) <= GANN_TOLERANCE_PCT and r >= highs[bar] * 0.995:
                    level_hit = r
                    break
            if level_hit and price < level_hit and price < opens[bar]:
                direction = "SHORT"
                sqrt_lvl = np.sqrt(level_hit)
                stop = (sqrt_lvl + STOP_ROTATIONS * GANN_ROTATION_STEP) ** 2
                sqrt_entry = np.sqrt(price)
                t_val = sqrt_entry - TARGET_ROTATIONS * GANN_ROTATION_STEP
                target = t_val ** 2 if t_val > 0 else price * 0.98

        if direction is None:
            continue

        stop = round(stop, 1)
        target = round(target, 1)

        if direction == "LONG":
            stop_dist = price - stop
            target_dist = target - price
        else:
            stop_dist = stop - price
            target_dist = price - target

        if stop_dist <= 0 or target_dist <= 0:
            continue

        rr = target_dist / stop_dist
        if rr < 1.8:
            continue

        # Position sizing
        risk_amt = capital * RISK_PER_TRADE_PCT
        pos_usd = min((risk_amt / stop_dist) * price, capital * LEVERAGE)
        qty = pos_usd / price

        # Execute
        exit_p = exit_t = exit_r = None
        held = 0
        end = min(bar + FORWARD_BARS, len(closes))

        for j in range(bar + 1, end):
            held += 1
            if direction == "LONG":
                if lows[j] <= stop:
                    exit_p, exit_t, exit_r = stop, times[j], "STOP LOSS"
                    break
                if highs[j] >= target:
                    exit_p, exit_t, exit_r = target, times[j], "TARGET HIT"
                    break
            else:
                if highs[j] >= stop:
                    exit_p, exit_t, exit_r = stop, times[j], "STOP LOSS"
                    break
                if lows[j] <= target:
                    exit_p, exit_t, exit_r = target, times[j], "TARGET HIT"
                    break

        if exit_p is None:
            exit_p, exit_t, exit_r = closes[end - 1], times[end - 1], "TIME EXIT"

        if direction == "LONG":
            pnl = qty * (exit_p - price)
        else:
            pnl = qty * (price - exit_p)

        comm = qty * price * COMMISSION_PCT + qty * exit_p * COMMISSION_PCT
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
            'd': direction, 'et': times[bar], 'xt': exit_t,
            'ep': round(price, 1), 'gl': round(level_hit, 1),
            'sl': stop, 'tp': target, 'xp': round(exit_p, 1),
            'xr': exit_r, 'pnl': round(net, 2), 'bal': round(capital, 2),
            'rr': round(rr, 1), 'held': held,
            'sd': round(stop_dist, 1), 'td': round(target_dist, 1),
        })

        last_idx = bar
        if capital <= 0:
            break

    return trades, capital, max_dd


# ─── Report ────────────────────────────────────────────────────────────────

def report(trades, final_cap, max_dd, df, label):
    spacing = gann_spacing_at_price(df['close'].mean())

    print(f"\n{'=' * 125}")
    print(f"  GANN SQUARE OF 9 -- CORRECTED BI-DIRECTIONAL STRATEGY")
    print(f"  {label}")
    print(f"{'=' * 125}")
    print(f"\n  Period:         {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Capital:        ${STARTING_CAPITAL:,.2f} | Leverage: {LEVERAGE}x | Risk: {RISK_PER_TRADE_PCT*100:.0f}%/trade")
    print(f"  Gann Spacing:   ~${spacing:,.0f} between full-rotation levels at avg BTC price")
    print(f"  Stop:           1 Gann rotation (~${spacing:,.0f}) | Target: 2 rotations (~${spacing*2:,.0f})")

    if not trades:
        print(f"\n  No trades found.\n")
        return

    # Trade log
    print(f"\n  {'#':<3} {'Dir':<5} {'Entry Date':<18} {'Exit Date':<18} {'Entry':>9} {'Gann Lvl':>9} "
          f"{'SL':>9} {'TP':>9} {'Exit':>9} {'Result':<11} {'P&L':>10} {'Balance':>10} {'R:R':>5} {'Hrs':>5}")
    print(f"  {'_' * 122}")

    w = l = 0
    lw = ll = sw = sl_ = 0
    tp = tl = 0.0
    cw = cl = mcw = mcl = 0

    for i, t in enumerate(trades, 1):
        m = "+" if t['pnl'] >= 0 else "-"
        icon = "^L" if t['d'] == 'LONG' else "vS"
        if t['pnl'] >= 0:
            w += 1; tp += t['pnl']; cw += 1; cl = 0; mcw = max(mcw, cw)
            if t['d'] == 'LONG': lw += 1
            else: sw += 1
        else:
            l += 1; tl += abs(t['pnl']); cl += 1; cw = 0; mcl = max(mcl, cl)
            if t['d'] == 'LONG': ll += 1
            else: sl_ += 1

        print(f"  {i:<3} {icon:<5} {str(t['et'])[:16]:<18} {str(t['xt'])[:16]:<18} "
              f"${t['ep']:>7,.0f} ${t['gl']:>7,.0f} ${t['sl']:>7,.0f} ${t['tp']:>7,.0f} "
              f"${t['xp']:>7,.0f} {t['xr']:<11} {m}${abs(t['pnl']):>8,.2f} "
              f"${t['bal']:>8,.2f} {t['rr']:>4.1f} {t['held']:>5}")

    print(f"  {'_' * 122}")

    n = len(trades)
    wr = w / n * 100 if n else 0
    ret = (final_cap - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    aw = tp / w if w else 0
    al = tl / l if l else 0
    pf = tp / tl if tl > 0 else float('inf')
    exp = (wr/100 * aw) - ((100-wr)/100 * al)
    tl_n = lw + ll; ts_n = sw + sl_
    lwr = lw / tl_n * 100 if tl_n else 0
    swr = sw / ts_n * 100 if ts_n else 0

    print(f"""
  {'=' * 65}
  PERFORMANCE SUMMARY
  {'=' * 65}

  CAPITAL
    Starting:               ${STARTING_CAPITAL:>12,.2f}
    Final:                  ${final_cap:>12,.2f}
    Net Profit/Loss:        ${final_cap - STARTING_CAPITAL:>12,.2f}
    Total Return:           {ret:>12.2f}%

  TRADES
    Total:                  {n:>12}
    Winners:                {w:>12}  ({wr:.1f}%)
    Losers:                 {l:>12}  ({100-wr:.1f}%)
    Max Consec Wins:        {mcw:>12}
    Max Consec Losses:      {mcl:>12}

  BY DIRECTION
    Longs:   {tl_n:>3} trades    (Win: {lw}, Loss: {ll}, WR: {lwr:.1f}%)
    Shorts:  {ts_n:>3} trades    (Win: {sw}, Loss: {sl_}, WR: {swr:.1f}%)

  PROFITABILITY
    Gross Profit:           ${tp:>12,.2f}
    Gross Loss:             ${tl:>12,.2f}
    Profit Factor:          {pf:>12.2f}
    Avg Win:                ${aw:>12,.2f}
    Avg Loss:               ${al:>12,.2f}
    Expectancy/Trade:       ${exp:>12,.2f}

  RISK
    Max Drawdown:           {max_dd:>12.2f}%
""")

    # Monthly
    print(f"  MONTHLY BREAKDOWN:")
    print(f"  {'_' * 90}")
    monthly = {}
    for t in trades:
        k = t['et'].strftime('%Y-%m')
        if k not in monthly:
            monthly[k] = {'pnl': 0, 'n': 0, 'w': 0, 'long': 0, 'short': 0}
        monthly[k]['pnl'] += t['pnl']
        monthly[k]['n'] += 1
        if t['pnl'] >= 0: monthly[k]['w'] += 1
        if t['d'] == 'LONG': monthly[k]['long'] += 1
        else: monthly[k]['short'] += 1

    rc = STARTING_CAPITAL
    for mo in sorted(monthly.keys()):
        v = monthly[mo]
        mwr = v['w'] / v['n'] * 100 if v['n'] else 0
        rc += v['pnl']
        mk = "+" if v['pnl'] >= 0 else " "
        bar_len = max(1, int(abs(v['pnl']) / max(STARTING_CAPITAL * 0.01, 1)))
        bar = ("#" if v['pnl'] >= 0 else "-") * min(bar_len, 35)
        print(f"    {mo}: {v['n']:>2} ({v['long']}L/{v['short']}S) | WR: {mwr:>5.1f}% | "
              f"P&L: {mk}${v['pnl']:>9,.2f} | Bal: ${rc:>9,.2f}  {bar}")

    print(f"  {'_' * 90}")

    # Equity curve
    print(f"\n  EQUITY CURVE:")
    print(f"  {'_' * 65}")
    print(f"    {'Start':<18} ${STARTING_CAPITAL:>10,.2f}  |{'=' * 30}")
    step = max(1, len(trades) // 20)
    for i, t in enumerate(trades):
        if i % step == 0 or i == len(trades) - 1:
            pct = (t['bal'] / STARTING_CAPITAL) * 100
            blen = max(1, int(pct / 100 * 30))
            ch = '=' if t['pnl'] >= 0 else '-'
            d = "L" if t['d'] == 'LONG' else "S"
            lb = f"#{i+1:<3}{d} {str(t['et'])[:10]}"
            print(f"    {lb:<18} ${t['bal']:>10,.2f}  |{ch * blen} {pct:.0f}%")
    print(f"  {'_' * 65}")
    print(f"\n{'=' * 125}\n")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 125)
    print("  GANN SQUARE OF 9 -- CORRECTED STRATEGY (Full 360-degree Rotation Levels)")
    print("  FIX: Using FULL rotations instead of quarter turns")
    print("  Quarter turn (90 deg) at $90K = ~$150 apart (too tight, noise kills you)")
    print("  Full rotation (360 deg) at $90K = ~$600 apart (meaningful S/R levels)")
    print("=" * 125)

    datasets = [
        ("BTCUSDT_1h_Jan_to_Jul2026.csv", "2026 (Jan-Jul) -- Bear Market"),
        ("BTCUSDT_1h_2023_to_2025.csv", "2023-2025 -- Full Cycle"),
    ]

    for fname, label in datasets:
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            continue

        print(f"\n  Loading: {fname}")
        df_1h = pd.read_csv(fpath)
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], dayfirst=True, format='mixed')
        df_1h.set_index('timestamp', inplace=True)
        df_1h.sort_index(inplace=True)

        df_4h = resample_to_4h(df_1h)
        gz, sli, shi = build_gann_zones(df_4h, SWING_LOOKBACK_4H)

        avg_price = df_1h['close'].mean()
        spacing = gann_spacing_at_price(avg_price)
        print(f"  1H: {len(df_1h):,} bars | 4H: {len(df_4h):,} bars")
        print(f"  Swings: {len(sli)} lows, {len(shi)} highs")
        print(f"  Avg Price: ${avg_price:,.0f} | Gann Full-Rotation Spacing: ~${spacing:,.0f}")

        trades, final, mdd = simulate(df_1h, df_4h, gz, STARTING_CAPITAL)
        report(trades, final, mdd, df_1h, label)


if __name__ == "__main__":
    main()
