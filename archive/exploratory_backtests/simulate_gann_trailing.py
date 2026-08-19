"""
Gann Square of 9 — TRAILING STOP Strategy
==========================================
Based on the corrected full-rotation bi-directional strategy (best version)
with the key improvement:

  TRAILING STOP: After price moves 1 Gann rotation in your favor,
  move stop to BREAKEVEN. This converts many losing trades into
  breakeven trades, boosting effective win rate from 35% toward 40%+.

  PARTIAL PROFIT: Take 50% off at 1st Gann rotation profit,
  trail the remaining 50% to the 2nd Gann rotation target.
"""

import pandas as pd
import numpy as np
import os

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DATA")  # archived: DATA/ lives at the repo root, two levels up

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05
SWING_LOOKBACK_4H = 20
GANN_ROTATION_STEP = 1.0         # Full 360-degree rotation
GANN_TOLERANCE_PCT = 0.004
STOP_ROTATIONS = 1               # Initial stop: 1 rotation beyond
TARGET_ROTATIONS = 2             # Final target: 2 rotations
PARTIAL_TAKE_PROFIT_AT = 1       # Take 50% profit at 1 rotation
COMMISSION_PCT = 0.0004
DEDUP_BARS_1H = 36
FORWARD_BARS = 400
EMA_PERIOD_4H = 50
ALLOWED_HOURS_UTC = list(range(8, 21))


# ─── Gann Math ──────────────────────────────────────────────────────────────

def gann_full_levels(price, n=10):
    sqrt_p = np.sqrt(price)
    res = sorted([(sqrt_p + i * GANN_ROTATION_STEP) ** 2 for i in range(1, n + 1)])
    sup = sorted([(sqrt_p - i * GANN_ROTATION_STEP) ** 2 for i in range(1, n + 1) if (sqrt_p - i * GANN_ROTATION_STEP) > 0], reverse=True)
    return sup, res

def gann_spacing(price):
    s = np.sqrt(price)
    return (s + GANN_ROTATION_STEP) ** 2 - s ** 2


# ─── Swing Detection ───────────────────────────────────────────────────────

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


# ─── 4H Infrastructure ────────────────────────────────────────────────────

def resample_4h(df):
    return df.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()

def build_gann_zones(df_4h, lb):
    h = df_4h['high'].values
    l = df_4h['low'].values
    t = df_4h.index
    sli, shi = detect_swings(h, l, lb)
    gz = {}
    for b in range(len(df_4h)):
        asl = [i for i in sli if i < b][-3:]
        ash = [i for i in shi if i < b][-3:]
        sups, ress = set(), set()
        for i in asl:
            s, r = gann_full_levels(l[i])
            sups.update(s); ress.update(r); sups.add(round(l[i], 1))
        for i in ash:
            s, r = gann_full_levels(h[i])
            sups.update(s); ress.update(r); ress.add(round(h[i], 1))
        gz[t[b]] = {'sup': sorted(sups, reverse=True), 'res': sorted(ress)}
    return gz, sli, shi


# ─── Simulation with Trailing Stop ─────────────────────────────────────────

def simulate(df_1h, df_4h, gz, cap_start):
    c = df_1h['close'].values
    h = df_1h['high'].values
    l = df_1h['low'].values
    o = df_1h['open'].values
    t = df_1h.index

    ema = df_4h['close'].ewm(span=EMA_PERIOD_4H, adjust=False).mean()
    gt = sorted(gz.keys())

    def get_gz(tm):
        best = None
        for g in gt:
            if g <= tm: best = g
            else: break
        return gz.get(best) if best else None

    def get_ema(tm):
        best = None
        for e in ema.index:
            if e <= tm: best = e
            else: break
        return ema.get(best) if best is not None else None

    capital = cap_start
    peak = capital
    max_dd = 0
    trades = []
    last_idx = -DEDUP_BARS_1H

    for bar in range(80, len(c)):
        if bar - last_idx < DEDUP_BARS_1H: continue
        if t[bar].hour not in ALLOWED_HOURS_UTC: continue

        g = get_gz(t[bar])
        if not g: continue
        sups, ress = g['sup'], g['res']
        if not sups or not ress: continue

        ev = get_ema(t[bar])
        if ev is None: continue

        price = c[bar]
        direction = level_hit = stop = target = partial_tp = None

        # ═══ LONG ═══
        if price > ev:
            for s in sups:
                if abs(l[bar] - s) / max(l[bar], 1) <= GANN_TOLERANCE_PCT and s <= l[bar] * 1.005:
                    level_hit = s; break
            if level_hit and price > level_hit and price > o[bar]:
                direction = "LONG"
                sqrt_l = np.sqrt(level_hit)
                stop = (sqrt_l - STOP_ROTATIONS * GANN_ROTATION_STEP) ** 2
                if stop <= 0: stop = level_hit * 0.98
                sqrt_e = np.sqrt(price)
                partial_tp = (sqrt_e + PARTIAL_TAKE_PROFIT_AT * GANN_ROTATION_STEP) ** 2
                target = (sqrt_e + TARGET_ROTATIONS * GANN_ROTATION_STEP) ** 2

        # ═══ SHORT ═══
        if direction is None and price < ev:
            for r in ress:
                if abs(h[bar] - r) / max(h[bar], 1) <= GANN_TOLERANCE_PCT and r >= h[bar] * 0.995:
                    level_hit = r; break
            if level_hit and price < level_hit and price < o[bar]:
                direction = "SHORT"
                sqrt_l = np.sqrt(level_hit)
                stop = (sqrt_l + STOP_ROTATIONS * GANN_ROTATION_STEP) ** 2
                sqrt_e = np.sqrt(price)
                pt_val = sqrt_e - PARTIAL_TAKE_PROFIT_AT * GANN_ROTATION_STEP
                partial_tp = pt_val ** 2 if pt_val > 0 else price * 0.99
                tg_val = sqrt_e - TARGET_ROTATIONS * GANN_ROTATION_STEP
                target = tg_val ** 2 if tg_val > 0 else price * 0.98

        if direction is None: continue

        stop = round(stop, 1)
        target = round(target, 1)
        partial_tp = round(partial_tp, 1)

        if direction == "LONG":
            stop_dist = price - stop
            target_dist = target - price
        else:
            stop_dist = stop - price
            target_dist = price - target

        if stop_dist <= 0 or target_dist <= 0: continue
        rr = target_dist / stop_dist
        if rr < 1.8: continue

        # Position sizing
        risk = capital * RISK_PER_TRADE_PCT
        pos = min((risk / stop_dist) * price, capital * LEVERAGE)
        qty = pos / price
        remaining_qty = qty  # Tracks qty still in the trade

        # ═══ Execute with TRAILING STOP + PARTIAL PROFIT ═══
        exit_p = exit_t = exit_r = None
        held = 0
        partial_taken = False
        partial_pnl = 0.0
        current_stop = stop
        be_triggered = False
        end = min(bar + FORWARD_BARS, len(c))

        for j in range(bar + 1, end):
            held += 1

            if direction == "LONG":
                # Check stop first
                if l[j] <= current_stop:
                    exit_p = current_stop
                    exit_t = t[j]
                    exit_r = "BE STOP" if be_triggered else "STOP LOSS"
                    break

                # Check partial TP (1st Gann rotation)
                if not partial_taken and h[j] >= partial_tp:
                    # Take 50% off at partial TP
                    partial_qty = qty * 0.5
                    partial_pnl = partial_qty * (partial_tp - price)
                    partial_comm = partial_qty * price * COMMISSION_PCT + partial_qty * partial_tp * COMMISSION_PCT
                    partial_pnl -= partial_comm
                    remaining_qty = qty - partial_qty
                    partial_taken = True

                    # TRAIL STOP TO BREAKEVEN
                    current_stop = price  # breakeven
                    be_triggered = True

                # Check final target (2nd Gann rotation)
                if h[j] >= target:
                    exit_p = target
                    exit_t = t[j]
                    exit_r = "FULL TARGET"
                    break

            else:  # SHORT
                if h[j] >= current_stop:
                    exit_p = current_stop
                    exit_t = t[j]
                    exit_r = "BE STOP" if be_triggered else "STOP LOSS"
                    break

                if not partial_taken and l[j] <= partial_tp:
                    partial_qty = qty * 0.5
                    partial_pnl = partial_qty * (price - partial_tp)
                    partial_comm = partial_qty * price * COMMISSION_PCT + partial_qty * partial_tp * COMMISSION_PCT
                    partial_pnl -= partial_comm
                    remaining_qty = qty - partial_qty
                    partial_taken = True
                    current_stop = price
                    be_triggered = True

                if l[j] <= target:
                    exit_p = target
                    exit_t = t[j]
                    exit_r = "FULL TARGET"
                    break

        if exit_p is None:
            exit_p = c[end - 1]
            exit_t = t[end - 1]
            exit_r = "TIME EXIT"

        # Calculate remaining position P&L
        if direction == "LONG":
            remaining_pnl = remaining_qty * (exit_p - price)
        else:
            remaining_pnl = remaining_qty * (price - exit_p)

        remaining_comm = remaining_qty * price * COMMISSION_PCT + remaining_qty * exit_p * COMMISSION_PCT
        remaining_pnl -= remaining_comm

        total_pnl = partial_pnl + remaining_pnl

        capital += total_pnl
        if capital <= 0: capital = 0
        if capital > peak: peak = capital
        dd = (peak - capital) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd

        trades.append({
            'd': direction, 'et': t[bar], 'xt': exit_t,
            'ep': round(price, 1), 'gl': round(level_hit, 1),
            'sl': round(stop, 1), 'ptp': partial_tp, 'tp': target,
            'xp': round(exit_p, 1), 'xr': exit_r,
            'pnl': round(total_pnl, 2), 'ppnl': round(partial_pnl, 2),
            'bal': round(capital, 2), 'rr': round(rr, 1),
            'held': held, 'partial': partial_taken, 'be': be_triggered,
        })

        last_idx = bar
        if capital <= 0: break

    return trades, capital, max_dd


# ─── Report ────────────────────────────────────────────────────────────────

def report(trades, final, mdd, df, label):
    sp = gann_spacing(df['close'].mean())

    print(f"\n{'=' * 130}")
    print(f"  GANN SQUARE OF 9 -- TRAILING STOP + PARTIAL PROFIT STRATEGY")
    print(f"  {label}")
    print(f"{'=' * 130}")
    print(f"\n  Period:      {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Capital:     ${STARTING_CAPITAL:,.2f} | Leverage: {LEVERAGE}x | Risk: {RISK_PER_TRADE_PCT*100:.0f}%/trade")
    print(f"  Gann Spacing: ~${sp:,.0f} | Stop: 1 rot | Partial TP: 1 rot (50%) | Full TP: 2 rot")
    print(f"  Trail:       Stop moves to BREAKEVEN after 1st rotation profit taken")

    if not trades:
        print(f"\n  No trades found.\n")
        return

    # Trade log
    print(f"\n  {'#':<3} {'Dir':<5} {'Entry Date':<18} {'Exit Date':<18} {'Entry':>9} {'SL':>9} {'TP1':>9} "
          f"{'TP2':>9} {'Exit':>9} {'Result':<12} {'P&L':>10} {'Balance':>10} {'Part':>5}")
    print(f"  {'_' * 127}")

    w = lo = 0; be_count = 0
    lw = ll = sw = sl_ = 0
    tp = tl = 0.0
    full_hits = partial_only = 0
    cw = cl = mcw = mcl = 0

    for i, tr in enumerate(trades, 1):
        m = "+" if tr['pnl'] >= 0 else "-"
        icon = "^L" if tr['d'] == 'LONG' else "vS"
        part = "Y" if tr['partial'] else ""

        is_win = tr['pnl'] >= 0
        is_be = tr['xr'] == 'BE STOP' and abs(tr['pnl']) < 2.0  # Near breakeven

        if is_win:
            w += 1; tp += tr['pnl']; cw += 1; cl = 0; mcw = max(mcw, cw)
            if tr['d'] == 'LONG': lw += 1
            else: sw += 1
        else:
            lo += 1; tl += abs(tr['pnl']); cl += 1; cw = 0; mcl = max(mcl, cl)
            if tr['d'] == 'LONG': ll += 1
            else: sl_ += 1

        if tr['xr'] == 'BE STOP': be_count += 1
        if tr['xr'] == 'FULL TARGET': full_hits += 1
        if tr['partial'] and tr['xr'] != 'FULL TARGET': partial_only += 1

        print(f"  {i:<3} {icon:<5} {str(tr['et'])[:16]:<18} {str(tr['xt'])[:16]:<18} "
              f"${tr['ep']:>7,.0f} ${tr['sl']:>7,.0f} ${tr['ptp']:>7,.0f} ${tr['tp']:>7,.0f} "
              f"${tr['xp']:>7,.0f} {tr['xr']:<12} {m}${abs(tr['pnl']):>8,.2f} "
              f"${tr['bal']:>8,.2f} {part:>5}")

    print(f"  {'_' * 127}")

    n = len(trades)
    wr = w / n * 100 if n else 0
    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    aw = tp / w if w else 0
    al = tl / lo if lo else 0
    pf = tp / tl if tl > 0 else float('inf')
    exp = (wr/100 * aw) - ((100-wr)/100 * al)
    tln = lw + ll; tsn = sw + sl_
    lwr = lw / tln * 100 if tln else 0
    swr = sw / tsn * 100 if tsn else 0

    print(f"""
  {'=' * 70}
  PERFORMANCE SUMMARY
  {'=' * 70}

  CAPITAL
    Starting:               ${STARTING_CAPITAL:>12,.2f}
    Final:                  ${final:>12,.2f}
    Net Profit/Loss:        ${final - STARTING_CAPITAL:>12,.2f}
    Total Return:           {ret:>12.2f}%

  TRADES
    Total:                  {n:>12}
    Winners (incl. BE):     {w:>12}  ({wr:.1f}%)
    Losers:                 {lo:>12}  ({100-wr:.1f}%)
    Max Consec Wins:        {mcw:>12}
    Max Consec Losses:      {mcl:>12}

  EXIT BREAKDOWN
    Full Target (2R):       {full_hits:>12}  (best outcome)
    Partial TP + BE Stop:   {partial_only:>12}  (small profit from partial)
    Breakeven Stops:        {be_count:>12}  (trail saved these from loss)
    Pure Stop Loss:         {n - full_hits - be_count:>12}  (no trail triggered)

  BY DIRECTION
    Longs:   {tln:>3} trades    (Win: {lw}, Loss: {ll}, WR: {lwr:.1f}%)
    Shorts:  {tsn:>3} trades    (Win: {sw}, Loss: {sl_}, WR: {swr:.1f}%)

  PROFITABILITY
    Gross Profit:           ${tp:>12,.2f}
    Gross Loss:             ${tl:>12,.2f}
    Profit Factor:          {pf:>12.2f}
    Avg Win:                ${aw:>12,.2f}
    Avg Loss:               ${al:>12,.2f}
    Expectancy/Trade:       ${exp:>12,.2f}

  RISK
    Max Drawdown:           {mdd:>12.2f}%
""")

    # Comparison table
    print(f"  {'=' * 70}")
    print(f"  COMPARISON: PREVIOUS BEST vs TRAILING STOP")
    print(f"  {'=' * 70}")
    print(f"""
    Metric                   Previous (v5)   Trailing Stop
    {'_' * 58}
    Final Capital            $147.82         ${final:>10,.2f}
    Return                   -26.09%         {ret:>10.2f}%
    Win Rate                 35.3%           {wr:>10.1f}%
    Profit Factor            0.84            {pf:>10.2f}
    Max Drawdown             29.76%          {mdd:>10.2f}%
    Expectancy               -$1.02          ${exp:>10,.2f}
    {'_' * 58}
""")

    # Monthly
    print(f"  MONTHLY BREAKDOWN:")
    print(f"  {'_' * 90}")
    monthly = {}
    for tr in trades:
        k = tr['et'].strftime('%Y-%m')
        if k not in monthly:
            monthly[k] = {'pnl': 0, 'n': 0, 'w': 0, 'l': 0, 's': 0}
        monthly[k]['pnl'] += tr['pnl']
        monthly[k]['n'] += 1
        if tr['pnl'] >= 0: monthly[k]['w'] += 1
        if tr['d'] == 'LONG': monthly[k]['l'] += 1
        else: monthly[k]['s'] += 1

    rc = STARTING_CAPITAL
    for mo in sorted(monthly.keys()):
        v = monthly[mo]
        mwr = v['w'] / v['n'] * 100 if v['n'] else 0
        rc += v['pnl']
        mk = "+" if v['pnl'] >= 0 else " "
        blen = max(1, int(abs(v['pnl']) / max(STARTING_CAPITAL * 0.008, 1)))
        bar = ("#" if v['pnl'] >= 0 else "-") * min(blen, 35)
        print(f"    {mo}: {v['n']:>2} ({v['l']}L/{v['s']}S) | WR: {mwr:>5.1f}% | "
              f"P&L: {mk}${v['pnl']:>9,.2f} | Bal: ${rc:>9,.2f}  {bar}")

    print(f"  {'_' * 90}")

    # Equity
    print(f"\n  EQUITY CURVE:")
    print(f"  {'_' * 65}")
    print(f"    {'Start':<18} ${STARTING_CAPITAL:>10,.2f}  |{'=' * 30}")
    step = max(1, len(trades) // 20)
    for i, tr in enumerate(trades):
        if i % step == 0 or i == len(trades) - 1:
            pct = (tr['bal'] / STARTING_CAPITAL) * 100
            bl = max(1, int(pct / 100 * 30))
            ch = '=' if tr['pnl'] >= 0 else '-'
            d = "L" if tr['d'] == 'LONG' else "S"
            lb = f"#{i+1:<3}{d} {str(tr['et'])[:10]}"
            print(f"    {lb:<18} ${tr['bal']:>10,.2f}  |{ch * bl} {pct:.0f}%")
    print(f"  {'_' * 65}")
    print(f"\n{'=' * 130}\n")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 130)
    print("  GANN SQUARE OF 9 -- TRAILING STOP + PARTIAL PROFIT")
    print("  NEW: Take 50% profit at 1st Gann rotation, trail stop to breakeven, let rest run to 2nd rotation")
    print("=" * 130)

    datasets = [
        ("BTCUSDT_1h_Jan_to_Jul2026.csv", "2026 (Jan-Jul) -- Bear Market"),
        ("BTCUSDT_1h_2023_to_2025.csv", "2023-2025 -- Full Cycle"),
    ]

    for fname, label in datasets:
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath): continue

        print(f"\n  Loading: {fname}")
        df = pd.read_csv(fpath)
        df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)

        d4 = resample_4h(df)
        gz, sli, shi = build_gann_zones(d4, SWING_LOOKBACK_4H)

        print(f"  1H: {len(df):,} | 4H: {len(d4):,} | Swings: {len(sli)}L {len(shi)}H")

        trades, final, mdd = simulate(df, d4, gz, STARTING_CAPITAL)
        report(trades, final, mdd, df, label)


if __name__ == "__main__":
    main()
