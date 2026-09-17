"""
Equal Highs/Lows Liquidity-Sweep reversal (the user's Strategy 1).

Setup : a level tested 2+ times by swing highs (equal highs) or swing lows
        (equal lows) -- a pool of stops beyond it.
Trigger: a SWEEP -- a candle wicks BEYOND the level but CLOSES back inside.
Entry : opposite direction, at the sweep candle's CLOSE (market -> executable,
        no fill illusion).
Stop  : just beyond the sweep wick.
Target: the opposite liquidity (nearest opposing swing extreme).

Causal: sweep is known at the candle close; entry at that close; stop/target on
later bars. Honest fees (entry+stop = taker, target = maker). Scored with
trade_stats. Run:  python3 liquidity_sweep.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
PIVOT_HALF = 5          # swing pivots for building the pools
EQ_TOL = 0.0015         # two pivots are "equal" if within 0.15%
LOOKBACK = 300          # bars to look back for equal pivots / opposite target
STOP_BUF = 0.0015       # stop this far beyond the sweep wick
MIN_TOUCHES = 2


def pivots(h, l, half):
    n = len(h); ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for i in range(half, n - half):
        if h[i] == h[i-half:i+half+1].max():
            ph[i] = h[i]
        if l[i] == l[i-half:i+half+1].min():
            pl[i] = l[i]
    return ph, pl


def run(fname, start=None, end=None):
    df = load_ohlcv(fname, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    t = df.index; n = len(c)
    ph, pl = pivots(h, l, PIVOT_HALF)
    # pivots are only KNOWN PIVOT_HALF bars later (causal)
    known_high = np.full(n, np.nan); known_low = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(ph[i]) and i + PIVOT_HALF < n:
            known_high[i + PIVOT_HALF] = ph[i]
        if not np.isnan(pl[i]) and i + PIVOT_HALF < n:
            known_low[i + PIVOT_HALF] = pl[i]

    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    capital = CAP; trades = []; busy = -1

    for i in range(LOOKBACK, n - 1):
        if i <= busy:
            continue
        lo = max(0, i - LOOKBACK)
        recent_highs = known_high[lo:i][~np.isnan(known_high[lo:i])]
        recent_lows = known_low[lo:i][~np.isnan(known_low[lo:i])]

        direction = entry = stop = tgt = None

        # equal highs pool -> look for a sweep UP that closes back down -> SHORT
        if len(recent_highs) >= MIN_TOUCHES:
            level = recent_highs.max()
            eq = recent_highs[recent_highs >= level * (1 - EQ_TOL)]
            if len(eq) >= MIN_TOUCHES and h[i] > level and c[i] < level:
                direction = "SHORT"; entry = c[i]; stop = h[i] * (1 + STOP_BUF)
                below = recent_lows[recent_lows < entry]
                tgt = below.max() if len(below) else entry - 3 * (stop - entry)

        # equal lows pool -> sweep DOWN that closes back up -> LONG
        if direction is None and len(recent_lows) >= MIN_TOUCHES:
            level = recent_lows.min()
            eq = recent_lows[recent_lows <= level * (1 + EQ_TOL)]
            if len(eq) >= MIN_TOUCHES and l[i] < level and c[i] > level:
                direction = "LONG"; entry = c[i]; stop = l[i] * (1 - STOP_BUF)
                above = recent_highs[recent_highs > entry]
                tgt = above.min() if len(above) else entry + 3 * (entry - stop)

        if direction is None:
            continue
        if (direction == "SHORT" and not (tgt < entry < stop)) or \
           (direction == "LONG" and not (stop < entry < tgt)):
            continue
        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            continue

        exit_px = exit_r = None; j = i + 1
        while j < n:
            if direction == "SHORT":
                if h[j] >= stop:
                    exit_px, exit_r = stop, "STOP"; break
                if l[j] <= tgt:
                    exit_px, exit_r = tgt, "TARGET"; break
            else:
                if l[j] <= stop:
                    exit_px, exit_r = stop, "STOP"; break
                if h[j] >= tgt:
                    exit_px, exit_r = tgt, "TARGET"; break
            j += 1
        if exit_px is None:
            j = n - 1; exit_px, exit_r = c[j], "END"
        if exit_r in ("STOP", "END"):
            exit_px *= (1 + SLIP) if direction == "SHORT" else (1 - SLIP)

        gross = qty * (entry - exit_px) if direction == "SHORT" else qty * (exit_px - entry)
        fee = qty * entry * TAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
        capital = max(capital + gross - fee, 0.0)
        rr = abs(tgt - entry) / abs(entry - stop)
        trades.append({"dir": direction, "time": t[i], "entry": entry, "stop": stop,
                       "target": tgt, "qty": qty, "notional": notional,
                       "pnl": gross - fee, "exit_r": exit_r, "rr": rr})
        busy = j
        if capital <= 0:
            break
    return trades


YEARS = [("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    print("EQUAL H/L LIQUIDITY-SWEEP REVERSAL -- 15m BTC, entry at sweep close, honest fees\n")
    pooled = []
    for label, f, s, e in YEARS:
        tr = run(f, start=s, end=e); pooled += tr
        st = summarize_trades(tr, CAP, label=label)
        rr = np.mean([x["rr"] for x in tr]) if tr else 0
        print(f"  {label}: n={st.n:<4} win={st.win_rate:4.1f}%  avgRR={rr:.1f}  "
              f"ret={st.ret_pct:+7.1f}%  expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
    ps = summarize_trades(pooled, CAP)
    print(f"\n  POOLED: n={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
          f"expR={ps.expectancy_r:+.3f}  Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%")
