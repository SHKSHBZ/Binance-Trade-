"""
ENTRY-QUALITY diagnostic for the Liquidity RUN -- is the ENTRY the barrier?

Strips out ALL exit/target/stop rules and measures only what price does AFTER
each Run entry, so we isolate whether the ENTRY POINT itself has directional
edge. Reported per timeframe (answers 'wrong timeframe?' too).

For each entry (liquidity taken -> FVG forms -> enter in run direction):
  - directional hit rate at forward horizons (price in the run's favour?)
  - MFE and MAE over W bars, expressed in R (R = |entry - FVG far side|):
      MFE = best favourable excursion, MAE = worst adverse excursion.
  - vs a random-entry baseline (same bars pool, random direction).

If MFE/MAE > ~1.1 and hit > ~52%, the entry is GOOD and the exit was the
problem. If both ~1.0 / ~50%, the ENTRY is the barrier.

Run:  python3 run_entry_diagnostic.py
"""
import _paths  # noqa: F401
import numpy as np
from data_loader import load_ohlcv
from structure_sweep import confirmed_pivots

SWING_HALF = 10
RUN_WIN = 10
W = 40                # forward window for MFE/MAE
FWDS = (8, 16, 32)


def entries(fname, start=None, end=None):
    df = load_ohlcv(fname, start, end)
    h = df["high"].values; l = df["low"].values; c = df["close"].values
    n = len(c)
    kh, kl = confirmed_pivots(h, l, SWING_HALF)
    highs = []; lows = []
    arm_long = arm_short = -1
    out = []
    for i in range(SWING_HALF, n - 1):
        if not np.isnan(kh[i]): highs.append(kh[i])
        if not np.isnan(kl[i]): lows.append(kl[i])
        if lows and l[i] < lows[-1]: arm_long = i + RUN_WIN
        if highs and h[i] > highs[-1]: arm_short = i + RUN_WIN
        if i <= arm_long and i >= 2 and l[i] > h[i - 2]:
            risk = c[i] - h[i - 2]
            if risk > 0: out.append((i, +1, c[i], risk))
        elif i <= arm_short and i >= 2 and h[i] < l[i - 2]:
            risk = l[i - 2] - c[i]
            if risk > 0: out.append((i, -1, c[i], risk))
    return h, l, c, n, out


def diagnose(h, l, c, n, ents, label):
    mfe = []; mae = []; hits = {f: [] for f in FWDS}
    for i, d, e, risk in ents:
        end = min(i + W, n)
        seg_h = h[i + 1:end]; seg_l = l[i + 1:end]
        if len(seg_h) == 0: continue
        if d > 0:
            mfe.append((seg_h.max() - e) / risk); mae.append((e - seg_l.min()) / risk)
        else:
            mfe.append((e - seg_l.min()) / risk); mae.append((seg_h.max() - e) / risk)
        for f in FWDS:
            if i + f < n:
                fwd = (c[i + f] - e) * d
                hits[f].append(fwd > 0)
    mfe = np.array(mfe); mae = np.array(mae)
    hitstr = "  ".join(f"F{f}:{100*np.mean(hits[f]):.0f}%" for f in FWDS)
    print(f"  {label:14} n={len(mfe):<5} MFE={mfe.mean():.2f}R MAE={mae.mean():.2f}R "
          f"ratio={mfe.mean()/mae.mean():.2f}  dir[{hitstr}]")
    return mfe, mae


def baseline(h, l, c, n, k, seed=0):
    rng = np.random.default_rng(seed)
    mfe = []; mae = []
    for _ in range(k):
        i = rng.integers(SWING_HALF, n - W - 1); d = 1 if rng.random() < .5 else -1
        e = c[i]
        # random risk drawn like a typical FVG (~0.1-0.3% of price)
        risk = e * rng.uniform(0.001, 0.003)
        seg_h = h[i + 1:i + W]; seg_l = l[i + 1:i + W]
        if d > 0:
            mfe.append((seg_h.max() - e) / risk); mae.append((e - seg_l.min()) / risk)
        else:
            mfe.append((e - seg_l.min()) / risk); mae.append((seg_h.max() - e) / risk)
    mfe = np.array(mfe); mae = np.array(mae)
    print(f"  {'RANDOM base':14} n={len(mfe):<5} MFE={mfe.mean():.2f}R MAE={mae.mean():.2f}R "
          f"ratio={mfe.mean()/mae.mean():.2f}")


TFS = [("XAUUSD_15m.csv", "GOLD 15m"), ("XAUUSD_30m.csv", "GOLD 30m"),
       ("XAUUSD_1h.csv", "GOLD 1h"), ("XAUUSD_4h.csv", "GOLD 4h")]

if __name__ == "__main__":
    print("RUN ENTRY QUALITY -- MFE/MAE (in R) + directional hit, per timeframe")
    print("(edge if ratio>~1.1 and dir>~52%; ~1.0/50% => the ENTRY is the barrier)\n")
    for f, lab in TFS:
        h, l, c, n, ents = entries(f)
        diagnose(h, l, c, n, ents, lab)
        baseline(h, l, c, n, max(len(ents), 500))
        print()
