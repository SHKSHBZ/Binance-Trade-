"""
Liquidity RUN (the trader's continuation + FVG setup) -- tested on GOLD.

Spec (from the trader):
  - Liquidity is TAKEN (a prior swing extreme is swept), up or down.
  - Price then RUNS the other way (impulse) and leaves an FVG behind.
  - "As soon as the FVG forms that's very strong momentum" -> ENTER at FVG
    formation, in the run's direction (no waiting for a pullback).
  - An FVG after the break = momentum will carry on.

Mechanization (causal):
  - swing pool: confirmed pivots (SWING_HALF).
  - sell-side taken: low pierces the last confirmed swing low -> arm LONG.
    buy-side taken: high pierces the last confirmed swing high -> arm SHORT.
  - within RUN_WIN bars, a matching FVG forms:
        LONG  bullish FVG: low[k] > high[k-2]   (gap_lo=high[k-2], gap_hi=low[k])
        SHORT bearish FVG: high[k] < low[k-2]    (gap_hi=low[k-2],  gap_lo=high[k])
  - ENTER at close[k] (FVG formation). STOP = far side of the FVG (+buf).
  - TARGET: fixed R (rr) or opposite external liquidity ("extliq").
  - min-stop filter (risk >= MIN_RISK_FRAC of price) so sub-spread stops can't
    fake huge R. Honest fees + slippage. trade_stats + random-direction null.

Run:  python3 liquidity_run.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades
from structure_sweep import confirmed_pivots

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
SWING_HALF = 10       # swing pool for the liquidity that gets taken
RUN_WIN = 10          # FVG must form within this many bars of the sweep
STOP_BUF = 0.0010
MIN_RISK_FRAC = 0.0005   # reject stops tighter than 0.05% of price (unexecutable)


def run(fname, start=None, end=None, rr=3.0, target="fixed",
        force_dir=None, seed=None):
    df = load_ohlcv(fname, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values
    c = df["close"].values; t = df.index; n = len(c)
    kh, kl = confirmed_pivots(h, l, SWING_HALF)
    rng = np.random.default_rng(seed)

    highs = []; lows = []
    capital = CAP; trades = []; busy = -1
    arm_long_until = arm_short_until = -1

    for i in range(SWING_HALF, n - 1):
        if not np.isnan(kh[i]): highs.append(kh[i])
        if not np.isnan(kl[i]): lows.append(kl[i])
        if i <= busy:
            continue
        last_low = lows[-1] if lows else None
        last_high = highs[-1] if highs else None

        # liquidity taken -> arm the opposite-direction run
        if last_low is not None and l[i] < last_low:
            arm_long_until = i + RUN_WIN
        if last_high is not None and h[i] > last_high:
            arm_short_until = i + RUN_WIN

        direction = entry = stop = tgt = None
        # LONG: armed + bullish FVG forms now
        if i <= arm_long_until and i >= 2 and l[i] > h[i - 2]:
            gap_lo = h[i - 2]
            direction = "LONG"; entry = c[i]; stop = gap_lo * (1 - STOP_BUF)
        # SHORT: armed + bearish FVG forms now
        elif i <= arm_short_until and i >= 2 and h[i] < l[i - 2]:
            gap_hi = l[i - 2]
            direction = "SHORT"; entry = c[i]; stop = gap_hi * (1 + STOP_BUF)

        if direction is None:
            continue
        risk = abs(entry - stop)
        if risk / entry < MIN_RISK_FRAC:      # unexecutable sub-spread stop
            continue
        # target
        if target == "extliq":
            if direction == "LONG":
                above = [x for x in highs if x > entry]
                tgt = min(above) if above else entry + rr * risk
            else:
                below = [x for x in lows if x < entry]
                tgt = max(below) if below else entry - rr * risk
        else:
            tgt = entry + rr * risk if direction == "LONG" else entry - rr * risk

        if force_dir == "random":
            direction = "LONG" if rng.random() < 0.5 else "SHORT"
            if direction == "LONG":
                stop = entry - risk; tgt = entry + rr * risk
            else:
                stop = entry + risk; tgt = entry - rr * risk
        if direction == "LONG" and not (stop < entry < tgt): continue
        if direction == "SHORT" and not (tgt < entry < stop): continue
        rr_act = abs(tgt - entry) / risk
        if rr_act < 1.0: continue

        qty = (capital * 0.01) / risk if risk > 0 else 0
        if qty <= 0: continue
        exit_px = exit_r = None; j = i + 1
        while j < n:
            if direction == "LONG":
                if l[j] <= stop: exit_px, exit_r = stop, "STOP"; break
                if h[j] >= tgt:  exit_px, exit_r = tgt, "TARGET"; break
            else:
                if h[j] >= stop: exit_px, exit_r = stop, "STOP"; break
                if l[j] <= tgt:  exit_px, exit_r = tgt, "TARGET"; break
            j += 1
        if exit_px is None:
            j = n - 1; exit_px, exit_r = c[j], "END"
        if exit_r in ("STOP", "END"):
            exit_px *= (1 - SLIP) if direction == "LONG" else (1 + SLIP)
        gross = qty * (exit_px - entry) if direction == "LONG" else qty * (entry - exit_px)
        fee = qty * entry * TAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
        capital = max(capital + gross - fee, 0.0)
        trades.append({"dir": direction, "time": t[i], "entry": entry, "stop": stop,
                       "target": tgt, "qty": qty, "notional": qty * entry,
                       "pnl": gross - fee, "exit_r": exit_r, "rr": rr_act})
        busy = j
        if capital <= 0: break
    return trades


def report(fname, label, years, rr=3.0, target="fixed"):
    pooled = []
    for y in years:
        s, e = (f"{y}-01-01", f"{y}-12-31")
        tr = run(fname, s, e, rr=rr, target=target); pooled += tr
        st = summarize_trades(tr, CAP, label=str(y))
        print(f"  {y}: n={st.n:<4} win={st.win_rate:4.1f}%  ret={st.ret_pct:+8.1f}%  expR={st.expectancy_r:+.3f}")
    ps = summarize_trades(pooled, CAP)
    print(f"  POOLED {label}: n={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
          f"expR={ps.expectancy_r:+.3f}  edge={ps.edge_confidence:.0f}%")
    return ps, pooled


if __name__ == "__main__":
    print("LIQUIDITY RUN on GOLD -- enter at FVG formation after liquidity taken\n")
    YRS = list(range(2020, 2027))
    for target, rr in [("fixed", 3.0)]:
        print(f"[30m gold, target={target} rr={rr}]")
        report("XAUUSD_30m.csv", "30m", YRS, rr=rr, target=target)
