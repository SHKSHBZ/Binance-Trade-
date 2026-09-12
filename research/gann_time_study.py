"""
Gann TIME-CYCLE test (measurement only) -- the one objective, testable claim
in Gann: do market turning points cluster at specific time distances from a
prior turning point (the "Gann numbers": 30/45/60/90/120/144/180/225/270/360
days), more than pure chance would produce?

No secret chart scaling needed (unlike Gann angles) -- this is just: find swing
highs/lows on the DAILY chart, measure the day-gaps between them, and check
whether those gaps land on Gann numbers more often than random numbers would.

Causal is not required here (we are measuring a statistical property of the
whole series, not trading it). Honest null: compare the Gann hit-rate to the
hit-rate of equally-many RANDOM "fake cycle" numbers over the same tolerance.

Run:  python3 gann_time_study.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd

from data_loader import load_ohlcv

GANN = [30, 45, 60, 90, 120, 144, 180, 225, 270, 360]
TOL = 3            # +/- days a gap may miss a cycle and still "count"
PIVOT_HALF = 5     # daily swing pivot half-window


def daily_pivots(df):
    d = df["close"].resample("1D").last().dropna()
    hi = df["high"].resample("1D").max().reindex(d.index)
    lo = df["low"].resample("1D").min().reindex(d.index)
    h, l = hi.values, lo.values
    n = len(d)
    piv = []
    for i in range(PIVOT_HALF, n - PIVOT_HALF):
        wh, wl = h[i - PIVOT_HALF:i + PIVOT_HALF + 1], l[i - PIVOT_HALF:i + PIVOT_HALF + 1]
        if h[i] == wh.max() and wh.argmax() == PIVOT_HALF:
            piv.append(i)
        elif l[i] == wl.min() and wl.argmin() == PIVOT_HALF:
            piv.append(i)
    return sorted(set(piv))


def hit_rate(gaps, cycles, tol):
    """fraction of gaps that land within tol of ANY cycle number."""
    if len(gaps) == 0:
        return 0.0
    hits = 0
    for g in gaps:
        if any(abs(g - cyc) <= tol for cyc in cycles):
            hits += 1
    return hits / len(gaps)


def study(fname, label):
    df = load_ohlcv(fname)
    piv = daily_pivots(df)
    # all forward gaps between pivots within a sensible horizon (<= 400 days)
    gaps = []
    for i in range(len(piv)):
        for j in range(i + 1, len(piv)):
            g = piv[j] - piv[i]
            if g > 400:
                break
            gaps.append(g)
    gaps = np.array(gaps)
    max_gap = gaps.max() if len(gaps) else 400

    real = hit_rate(gaps, GANN, TOL)

    # magnitude-matched null: JITTER each Gann number by a small random offset
    # (+/-4..20 days) so the cycle SIZES stay similar but the exact Gann values
    # are destroyed. If the exact Gann numbers carry real signal, they beat
    # their own jittered versions. This controls for the "small numbers sit
    # where gaps are dense" bias.
    rng = np.random.default_rng(11)
    null = np.empty(3000)
    for t in range(3000):
        off = rng.integers(4, 21, size=len(GANN)) * rng.choice([-1, 1], size=len(GANN))
        jitter = [max(20, g + o) for g, o in zip(GANN, off)]
        null[t] = hit_rate(gaps, jitter, TOL)
    p = float((null >= real).mean())

    print(f"\n================  {label}  ================")
    print(f"daily pivots: {len(piv)}   pivot-to-pivot gaps (<=400d): {len(gaps)}")
    print(f"Gann-cycle hit rate                 {real*100:5.1f}%")
    print(f"jittered (fake) cycles average      {null.mean()*100:5.1f}%   "
          "(same sizes, wrong exact values)")
    print(f"jittered cycles match or beat Gann  {p*100:5.1f}% of the time")
    print(f"  -> {'NO real edge: exact Gann numbers are no better than nearby ones' if p > 0.1 else 'the EXACT Gann numbers do stand out -- worth a closer look'}")


if __name__ == "__main__":
    print("GANN TIME-CYCLE TEST -- do BTC turns cluster at Gann day-numbers?")
    study("BTCUSDT_1h_2023_to_2025.csv", "BTC daily 2023-2025")
