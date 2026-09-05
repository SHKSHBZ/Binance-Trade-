"""
Does plain Support/Resistance catch the early move that lagging SMC misses?

S/R has one advantage over SMC structure: a level from a PAST swing is
known now, so you can rest an order at it and fill the instant price
arrives -- no confirmation lag. This tests whether that timeliness buys
an edge, using the same honest bracket + random baseline as scan_scenarios.

Setup (causal):
  * Support  = an earlier swing low  not yet closed below (still 'holding').
  * Resist.  = an earlier swing high not yet closed above.
  * Signal   = price trades into the NEAREST holding level and prints a
               rejection candle -> bounce trade (long at support / short
               at resistance), entered on that candle's close.
  * Bracket  = stop 1*ATR, target 2*ATR, 96-bar horizon, net of costs.

Compared head-to-head with the random baseline. If S/R can't beat random,
the early entry isn't worth the lower quality -- i.e. the lag is the PRICE
of the confirmation that gives SMC its edge.
"""

import numpy as np
import pandas as pd

import _paths  # noqa: F401  # puts repo root on sys.path

from data_loader import load_ohlcv
from smc_luxalgo import label_smc_luxalgo
from backtest_smc_scenario2 import atr
from regime_optimizer import FULL

FEE, SLIP, STOP_ATR, TARGET_ATR, HORIZON = 0.0004, 0.0002, 1.0, 2.0, 96


def _forward(o, h, l, c, e, direction, a):
    n = len(c)
    if direction == "LONG":
        entry = c[e] * (1 + SLIP); stop = entry - STOP_ATR * a; target = entry + TARGET_ATR * a
    else:
        entry = c[e] * (1 - SLIP); stop = entry + STOP_ATR * a; target = entry - TARGET_ATR * a
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    for j in range(e + 1, min(e + 1 + HORIZON, n)):
        if direction == "LONG":
            if l[j] <= stop: ex = stop * (1 - SLIP); break
            if h[j] >= target: ex = target; break
        else:
            if h[j] >= stop: ex = stop * (1 + SLIP); break
            if l[j] <= target: ex = target; break
    else:
        ex = c[min(e + HORIZON, n - 1)]
    gross = (ex - entry) * (1 if direction == "LONG" else -1)
    return (gross - FEE * (entry + ex)) / risk


def run(df):
    import bisect
    lab, _ = label_smc_luxalgo(df, swing_length=50)
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    n = len(c); a14 = atr(h, l, c, 14)

    sl = lab["swing_pivot_low"].to_numpy(float)     # new support at its confirm bar
    sh = lab["swing_pivot_high"].to_numpy(float)    # new resistance at its confirm bar

    rs = []
    start = 210
    active_sup = []   # sorted ascending; a support holds until close < it
    active_res = []   # sorted ascending; a resistance holds until close > it
    for i in range(start, n - 1):
        # register newly confirmed levels
        if not np.isnan(sl[i]):
            bisect.insort(active_sup, sl[i])
        if not np.isnan(sh[i]):
            bisect.insort(active_res, sh[i])
        # prune broken levels (close below a support / above a resistance)
        while active_sup and active_sup[-1] > c[i]:
            active_sup.pop()
        while active_res and active_res[0] < c[i]:
            active_res.pop(0)

        a = a14[i]
        rng = h[i] - l[i]
        if np.isnan(a) or a <= 0 or rng <= 0:
            continue

        sup = active_sup[-1] if active_sup else None   # nearest holding floor
        res = active_res[0] if active_res else None     # nearest holding ceiling

        if sup is not None and l[i] <= sup + 0.25 * a and l[i] >= sup - a \
                and (c[i] - l[i]) / rng >= 0.66 and c[i] > o[i]:
            r = _forward(o, h, l, c, i, "LONG", a)
            if r is not None:
                rs.append(r)
        elif res is not None and h[i] >= res - 0.25 * a and h[i] <= res + a \
                and (h[i] - c[i]) / rng >= 0.66 and c[i] < o[i]:
            r = _forward(o, h, l, c, i, "SHORT", a)
            if r is not None:
                rs.append(r)

    rs = np.array(rs)
    # random baseline on the same data
    rng_ = np.random.default_rng(42); rr = []
    for _ in range(8000):
        i = int(rng_.integers(start, n - 2))
        if np.isnan(a14[i]) or a14[i] <= 0:
            continue
        d = "LONG" if rng_.random() < 0.5 else "SHORT"
        v = _forward(o, h, l, c, i, d, a14[i])
        if v is not None:
            rr.append(v)
    rr = np.array(rr)

    def stats(x):
        gw = x[x > 0].sum(); gl = -x[x <= 0].sum()
        return len(x), (x > 0).mean() * 100, x.mean(), (gw / gl if gl > 0 else float("inf"))

    print(f"\nS/R bounce vs random  |  {df.index.min():%Y-%m-%d} -> {df.index.max():%Y-%m-%d}")
    print(f"{'strategy':<16}{'signals':>8}{'win%':>7}{'exp R':>9}{'PF':>7}")
    print("-" * 47)
    for name, x in [("S/R bounce", rs), ("RANDOM", rr)]:
        nn, w, e, pf = stats(x)
        print(f"{name:<16}{nn:>8}{w:>6.1f}%{e:>+9.3f}{pf:>7.2f}")
    edge = rs.mean() - rr.mean()
    print(f"\nS/R edge over random: {edge:+.3f} R  "
          f"-> {'BEATS random (timeliness helps)' if edge > 0.05 else 'does NOT beat random (early entry not worth it)'}")


if __name__ == "__main__":
    run(load_ohlcv(FULL))
