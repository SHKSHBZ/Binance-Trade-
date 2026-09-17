"""
Gann Square-of-9 PRICE levels -- do market turns land on them? (measurement)

Square of 9: from an anchor price A, levels sit at (sqrt(A) + k*step)^2, where
step = degrees/360 (45 deg = 0.125) and k = ...,-2,-1,1,2,... -- a ladder of
support/resistance at sqrt-based spacing.

Honest test (same discipline as our Gann time-cycle test): anchor on major swing
pivots; collect the minor turning points that follow; measure how often those
turns sit ON a Gann level (within a tolerance, in sqrt space). Then compare to a
NULL where the ladder's PHASE is shifted at random (same spacing, wrong exact
levels). If the exact Gann levels matter, real turns cluster on them far more
than random phases -- otherwise it's a grid that catches turns by density alone.

Causal is not required (measuring a statistical property, not trading it).
1H BTC 2023-2026.  Run:  python3 gann_sq9_study.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv

STEP = 45.0 / 360.0     # 45-degree Square-of-9 spacing in sqrt space
TOL_FRAC = 0.10         # a turn "hits" a level if within 10% of the step (=4.5 deg)
ANCHOR_HALF = 48        # major pivots (anchors): ~2 days on 1H
TURN_HALF = 6           # minor turning points to test


def pivots(h, l, half):
    n = len(h); out = []
    for i in range(half, n - half):
        wh = h[i-half:i+half+1]; wl = l[i-half:i+half+1]
        if h[i] == wh.max() and wh.argmax() == half:
            out.append((i, h[i]))
        elif l[i] == wl.min() and wl.argmin() == half:
            out.append((i, l[i]))
    return out


def load_all():
    a = load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"); b = load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")
    df = pd.concat([a, b]); return df[~df.index.duplicated(keep="first")].sort_index()


def phase_dist(price, anchor):
    """distance (0..0.5) of price from the nearest Gann level of `anchor`, in
    units of the sqrt-step."""
    frac = ((np.sqrt(price) - np.sqrt(anchor)) / STEP) % 1.0
    return np.minimum(frac, 1.0 - frac)


if __name__ == "__main__":
    df = load_all()
    h = df["high"].values; l = df["low"].values
    anchors = pivots(h, l, ANCHOR_HALF)
    turns = pivots(h, l, TURN_HALF)
    ta = np.array([i for i, _ in anchors]); pa = np.array([p for _, p in anchors])
    tt = np.array([i for i, _ in turns]);   pt = np.array([p for _, p in turns])

    # each turn is governed by the most recent major anchor BEFORE it
    dists = []
    for ti, tp in zip(tt, pt):
        j = np.searchsorted(ta, ti) - 1
        if j < 0:
            continue
        dists.append(phase_dist(tp, pa[j]))
    dists = np.array(dists)
    hit = float((dists < TOL_FRAC).mean())

    # NULL: random global phase offset (same spacing, wrong exact levels)
    rng = np.random.default_rng(7)
    null = np.empty(5000)
    # distance under a random phase shift phi: min(|frac-phi|, ...) -- just
    # recompute with a random offset added to every turn's frac
    base_frac = np.array([((np.sqrt(pt[k]) - np.sqrt(pa[np.searchsorted(ta, tt[k]) - 1]))/STEP) % 1.0
                          for k in range(len(tt)) if np.searchsorted(ta, tt[k]) - 1 >= 0])
    for m in range(5000):
        phi = rng.random()
        f = (base_frac + phi) % 1.0
        d = np.minimum(f, 1 - f)
        null[m] = (d < TOL_FRAC).mean()
    p = float((null >= hit).mean())
    expected = 2 * TOL_FRAC * 100

    print("GANN SQUARE-OF-9 PRICE LEVELS -- do BTC turns land on them?\n")
    print(f"major anchors: {len(anchors)}   minor turns tested: {len(dists)}")
    print(f"turns landing ON a Gann level (<{TOL_FRAC:.2f} step):  {hit*100:5.1f}%")
    print(f"expected by chance (random phase):               {expected:5.1f}%")
    print(f"random phases matching or beating Gann:          {p*100:5.1f}%")
    print(f"  -> {'NO edge: Gann levels are no better than a random grid' if p > 0.1 else 'the exact Gann levels DO stand out -- look closer'}")
