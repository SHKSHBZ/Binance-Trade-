"""
Symmetric Multi-Timeframe Momentum System -- Backtest
=======================================================
Built on the ONE signal that survived every look-ahead fix in this
repo's analysis: 12-hour rate-of-change (roc48 on 15M bars), which held
lift 1.20 (2025) / 1.34 (2026) unchanged before and after the HTF bug
was corrected.

Design rationale, tied to the empirical findings:

  * SYMMETRIC. 2025 was a bull year and 2026 a bear year; a long-only
    signal fought the tape in one of them. Long on up-momentum, short on
    down-momentum.

  * MOMENTUM ENTRY, not reversal. FVG/sweep/consolidation setups all
    scored lift <= 1.0. Consolidation scored 0.79-0.88 (actively bad).
    So: enter WITH the move in progress, never waiting for a pause.

  * TRAILING EXIT. Profit in every profitable config we measured was
    concentrated in a handful of large trend runs. A fixed R target caps
    exactly the trades that pay for the year, so the stop trails and the
    winner decides its own exit.

  * HTF filter is OPTIONAL and off by default. After the look-ahead fix,
    h1/h4 alignment only scored ~1.10 -- much weaker than momentum
    itself. It is tested as a variant rather than assumed helpful.

No look-ahead: every indicator at bar i uses data up to and including
bar i only; HTF signals come from the last COMPLETED higher-timeframe
bar via .shift(1).
"""

import pandas as pd
import numpy as np
import os

from data_loader import load_ohlcv

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")

STARTING_CAPITAL = 1000.0
RISK_PER_TRADE_PCT = 0.01
LEVERAGE = 10
MARGIN_SAFETY_CAP = 0.80
COMMISSION_PCT = 0.0004
SLIPPAGE_PCT = 0.0002        # modelled explicitly -- momentum entries chase price

ROC_BARS = 48                # 12h on 15M
ROC_THRESHOLD = 0.02         # 2% -- the level that tested at lift 1.20/1.34
ATR_PERIOD = 14
ATR_STOP_MULT = 2.0
TRAIL_MULT = 3.0             # trailing distance in ATRs once in profit
MAX_HOLD_BARS = 480          # 5 days on 15M
COOLDOWN_BARS = 8            # bars to wait after a trade closes
DAILY_LOSS_LIMIT_PCT = 0.03


def htf_bull_series(df, rule):
    """Bullish flag from the last COMPLETED higher-timeframe bar (no look-ahead)."""
    s = df['close'].resample(rule).last().ffill()
    sig = (s > s.ewm(span=20, adjust=False).mean()).shift(1)
    return sig.reindex(df.index, method='ffill').fillna(False).values.astype(bool)


def simulate_momentum(data_file, start=None, end=None,
                      roc_threshold=ROC_THRESHOLD, atr_stop_mult=ATR_STOP_MULT,
                      trail_mult=TRAIL_MULT, use_htf=False, allow_short=True,
                      risk_pct=RISK_PER_TRADE_PCT):
    # NOTE: must go through load_ohlcv -- the DATA/ files do not share a
    # timestamp format, and dayfirst parsing silently scrambles the ISO ones.
    df = load_ohlcv(data_file, start, end)

    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values
    times = df.index
    n = len(c)

    roc = np.zeros(n)
    roc[ROC_BARS:] = (c[ROC_BARS:] - c[:-ROC_BARS]) / c[:-ROC_BARS]

    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).rolling(ATR_PERIOD).mean().values

    h1_bull = htf_bull_series(df, '1h')
    h4_bull = htf_bull_series(df, '4h')

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0.0
    trades = []

    pos = None              # None or dict describing the open position
    cooldown_until = -1
    current_day = None
    day_start_balance = capital
    day_halted = False

    warmup = max(ROC_BARS, ATR_PERIOD) + 5

    for i in range(warmup, n):
        # --- daily circuit breaker ---
        d = times[i].normalize()
        if d != current_day:
            current_day = d
            day_start_balance = capital
            day_halted = False
        elif not day_halted and capital <= day_start_balance * (1 - DAILY_LOSS_LIMIT_PCT):
            day_halted = True

        # ---------------- manage an open position ----------------
        if pos is not None:
            exit_price = None
            reason = None

            if pos['dir'] == 'LONG':
                if l[i] <= pos['stop']:
                    exit_price, reason = pos['stop'], 'STOP'
                else:
                    pos['peak'] = max(pos['peak'], h[i])
                    trail = pos['peak'] - trail_mult * atr[i]
                    if trail > pos['stop']:
                        pos['stop'] = trail
            else:
                if h[i] >= pos['stop']:
                    exit_price, reason = pos['stop'], 'STOP'
                else:
                    pos['peak'] = min(pos['peak'], l[i])
                    trail = pos['peak'] + trail_mult * atr[i]
                    if trail < pos['stop']:
                        pos['stop'] = trail

            if exit_price is None and (i - pos['entry_bar']) >= MAX_HOLD_BARS:
                exit_price, reason = c[i], 'TIME'

            if exit_price is not None:
                fill = (exit_price * (1 - SLIPPAGE_PCT) if pos['dir'] == 'LONG'
                        else exit_price * (1 + SLIPPAGE_PCT))
                gross = (pos['qty'] * (fill - pos['entry']) if pos['dir'] == 'LONG'
                         else pos['qty'] * (pos['entry'] - fill))
                comm = pos['qty'] * pos['entry'] * COMMISSION_PCT + pos['qty'] * fill * COMMISSION_PCT
                net = gross - comm

                capital += net
                if capital <= 0:
                    capital = 0
                peak = max(peak, capital)
                dd = (peak - capital) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)

                trades.append({'dir': pos['dir'], 'time': pos['time'], 'exit_time': times[i],
                               'entry': pos['entry'], 'exit': fill, 'pnl': net,
                               'bal': capital, 'exit_r': reason,
                               'r_mult': net / pos['risk_amt'] if pos['risk_amt'] > 0 else 0})
                pos = None
                cooldown_until = i + COOLDOWN_BARS
                if capital <= 0:
                    break
            continue

        # ---------------- look for a new entry ----------------
        if i < cooldown_until or day_halted or np.isnan(atr[i]) or atr[i] <= 0:
            continue

        direction = None
        if roc[i] > roc_threshold:
            if not use_htf or (h1_bull[i] and h4_bull[i]):
                direction = 'LONG'
        elif allow_short and roc[i] < -roc_threshold:
            if not use_htf or ((not h1_bull[i]) and (not h4_bull[i])):
                direction = 'SHORT'

        if direction is None:
            continue

        raw = c[i]
        entry = raw * (1 + SLIPPAGE_PCT) if direction == 'LONG' else raw * (1 - SLIPPAGE_PCT)
        stop = (entry - atr_stop_mult * atr[i] if direction == 'LONG'
                else entry + atr_stop_mult * atr[i])
        stop_dist = abs(entry - stop)
        if stop_dist <= 0:
            continue

        risk_amt = capital * risk_pct
        pos_usd = min((risk_amt / stop_dist) * entry, capital * LEVERAGE * MARGIN_SAFETY_CAP)
        qty = pos_usd / entry
        if qty <= 0:
            continue

        pos = {'dir': direction, 'entry': entry, 'stop': stop, 'qty': qty,
               'entry_bar': i, 'time': times[i], 'risk_amt': risk_amt,
               'peak': h[i] if direction == 'LONG' else l[i]}

    return trades, capital, max_dd


def summarize(label, trades, final, mdd):
    if not trades:
        print(f"  {label:<34} no trades")
        return None
    wins = [t for t in trades if t['pnl'] > 0]
    wr = len(wins) / len(trades) * 100
    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    avg_w = np.mean([t['r_mult'] for t in wins]) if wins else 0
    losses = [t for t in trades if t['pnl'] <= 0]
    avg_l = np.mean([t['r_mult'] for t in losses]) if losses else 0
    pf = (sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses))
          if losses and sum(t['pnl'] for t in losses) != 0 else float('inf'))
    print(f"  {label:<34} n={len(trades):<5} WR={wr:4.1f}%  ret={ret:+9.1f}%  "
          f"DD={mdd:5.1f}%  avgW={avg_w:+5.2f}R avgL={avg_l:+5.2f}R  PF={pf:.2f}")
    return {'n': len(trades), 'wr': wr, 'ret': ret, 'dd': mdd, 'pf': pf}


PERIODS = [
    ("IN-SAMPLE  2023-03..2024-12", "BTCUSDT_15m_2023_to_2025.csv", "2023-03-01", "2024-12-31"),
    ("OUT-SAMPLE 2025",             "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
    ("OUT-SAMPLE 2026 Jan-Jul",     "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None),
]

VARIANTS = [
    ("baseline roc2% atr2 trail3",      dict()),
    ("+ HTF filter",                    dict(use_htf=True)),
    ("long only (no shorts)",           dict(allow_short=False)),
    ("roc 3% (stricter)",               dict(roc_threshold=0.03)),
    ("roc 1.5% (looser)",               dict(roc_threshold=0.015)),
    ("tighter stop atr1.5",             dict(atr_stop_mult=1.5)),
    ("wider trail 4atr",                dict(trail_mult=4.0)),
    ("tight trail 2atr",                dict(trail_mult=2.0)),
]

if __name__ == "__main__":
    print("SYMMETRIC MULTI-TIMEFRAME MOMENTUM SYSTEM")
    print(f"Risk {RISK_PER_TRADE_PCT*100}%/trade | commission {COMMISSION_PCT*100}%/side | "
          f"slippage {SLIPPAGE_PCT*100}%/side | ATR stop + ATR trail\n")

    for plabel, fname, start, end in PERIODS:
        print(f"{'='*118}")
        print(plabel)
        print(f"{'='*118}")
        for vlabel, kw in VARIANTS:
            tr, fin, dd = simulate_momentum(fname, start, end, **kw)
            summarize(vlabel, tr, fin, dd)
        print()
