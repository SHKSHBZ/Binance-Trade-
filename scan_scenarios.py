"""
Signal-quality scan — rank all six SMC scenarios on the SAME footing.

The Scenario 2 backtest showed management can mask a bad entry, so here we
strip management away and measure only the ENTRY edge. Every scenario's
trigger is forward-tested with an identical bracket:

    entry  = close of the signal bar (+ slippage)
    stop   = entry -/+ 1.0 * ATR(14)
    target = entry +/- 2.0 * ATR(14)        (fixed 2R)
    horizon= 96 bars, else exit at market
    costs  = 0.04% fee/side + 0.02% slippage
    fills  = conservative (stop before target within a bar)

Each signal is evaluated independently (a pure edge test, not a portfolio).
Everything is causal: signals come from the labeler's columns, which are
already placed on the bar they become known, and grabs/targets only use
swing levels confirmed as-of the signal bar.

An entry with a real edge clears >33% win rate (breakeven at 2R) and
positive expectancy. Anything at or below that is "not useful".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_luxalgo import label_smc_luxalgo
from backtest_smc_scenario2 import atr, rsi, adx

FEE = 0.0004
SLIP = 0.0002
STOP_ATR = 1.0
TARGET_ATR = 2.0
HORIZON = 96


def _forward(o, h, l, c, e, direction, a):
    """Forward-test one bracketed trade from signal bar e. Returns R (net)."""
    n = len(c)
    if direction == "LONG":
        entry = c[e] * (1 + SLIP)
        stop = entry - STOP_ATR * a
        target = entry + TARGET_ATR * a
    else:
        entry = c[e] * (1 - SLIP)
        stop = entry + STOP_ATR * a
        target = entry - TARGET_ATR * a
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    for j in range(e + 1, min(e + 1 + HORIZON, n)):
        if direction == "LONG":
            if l[j] <= stop:
                ex = stop * (1 - SLIP); break
            if h[j] >= target:
                ex = target; break
        else:
            if h[j] >= stop:
                ex = stop * (1 + SLIP); break
            if l[j] <= target:
                ex = target; break
    else:
        ex = c[min(e + HORIZON, n - 1)]
    gross = (ex - entry) * (1 if direction == "LONG" else -1)
    fee = FEE * (entry + ex)
    return (gross - fee) / risk


def scan(df):
    labeled, result = label_smc_luxalgo(df)
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
    n = len(c)
    a14 = atr(h, l, c, 14)
    r14 = rsi(c, 14)
    adx14 = adx(h, l, c, 14)
    trend = labeled["swing_trend"].to_numpy(object)

    def col(name):
        return labeled[name].to_numpy()

    # causal swing levels for grab detection
    sh = labeled["swing_pivot_high"].to_numpy(float)
    sl = labeled["swing_pivot_low"].to_numpy(float)
    swing_highs = [(i, sh[i]) for i in range(n) if not np.isnan(sh[i])]
    swing_lows = [(i, sl[i]) for i in range(n) if not np.isnan(sl[i])]

    obs = result.order_blocks
    bull_obs = [ob for ob in obs if ob["bias"] == "bullish"]
    bear_obs = [ob for ob in obs if ob["bias"] == "bearish"]

    signals = {k: [] for k in
               ["S1 breakout (BOS)", "S2 OB pullback", "S3 CHoCH reversal",
                "S4/B grab reversal", "S5 range edge"]}

    prem_top = col("premium_top"); prem_bot = col("premium_bottom")
    disc_top = col("discount_top"); disc_bot = col("discount_bottom")

    start = 210
    for i in range(start, n - 1):
        if np.isnan(a14[i]) or a14[i] <= 0:
            continue
        tr = trend[i]

        # --- S1: swing BOS in trend direction (Strategy A core) ---------
        if col("swing_bull_bos")[i] and r14[i] < 85:
            signals["S1 breakout (BOS)"].append((i, "LONG"))
        elif col("swing_bear_bos")[i] and r14[i] > 15:
            signals["S1 breakout (BOS)"].append((i, "SHORT"))

        # --- S3: swing CHoCH (reversal) ---------------------------------
        if col("swing_bull_choch")[i]:
            signals["S3 CHoCH reversal"].append((i, "LONG"))
        elif col("swing_bear_choch")[i]:
            signals["S3 CHoCH reversal"].append((i, "SHORT"))

        # --- S2: rejection into an unmitigated OB in trend --------------
        rng = h[i] - l[i]
        if rng > 0:
            if tr == "bullish" and (c[i] - l[i]) / rng >= 0.66 and c[i] > o[i]:
                for ob in bull_obs:
                    if ob["created_index"] <= i and (ob["mitigated_index"] is None or ob["mitigated_index"] > i) \
                            and l[i] <= ob["top"] and l[i] >= ob["bottom"] - a14[i]:
                        signals["S2 OB pullback"].append((i, "LONG")); break
            elif tr == "bearish" and (h[i] - c[i]) / rng >= 0.66 and c[i] < o[i]:
                for ob in bear_obs:
                    if ob["created_index"] <= i and (ob["mitigated_index"] is None or ob["mitigated_index"] > i) \
                            and h[i] >= ob["bottom"] and h[i] <= ob["top"] + a14[i]:
                        signals["S2 OB pullback"].append((i, "SHORT")); break

        # --- S4/B: liquidity grab (wick beyond swing, close back) -------
        for (ci, lvl) in swing_highs:
            if ci <= i and h[i] > lvl and c[i] < lvl and (h[i] - lvl) < 3 * a14[i]:
                signals["S4/B grab reversal"].append((i, "SHORT")); break
        for (ci, lvl) in swing_lows:
            if ci <= i and l[i] < lvl and c[i] > lvl and (lvl - l[i]) < 3 * a14[i]:
                signals["S4/B grab reversal"].append((i, "LONG")); break

        # --- S5: range edge, only in chop (ADX < 20) --------------------
        if not np.isnan(adx14[i]) and adx14[i] < 20 and not np.isnan(disc_top[i]):
            if l[i] <= disc_top[i] and c[i] > o[i]:          # bounce off discount
                signals["S5 range edge"].append((i, "LONG"))
            elif h[i] >= prem_bot[i] and c[i] < o[i]:        # reject off premium
                signals["S5 range edge"].append((i, "SHORT"))

    # --- evaluate each scenario -----------------------------------------
    print(f"\nSignal-quality scan  |  {df.index.min():%Y-%m-%d} -> {df.index.max():%Y-%m-%d}"
          f"  ({n:,} bars)")
    print(f"Fixed bracket: stop 1*ATR, target 2*ATR (2R), 96-bar horizon, net of costs")
    print("-" * 78)
    print(f"{'scenario':<22}{'signals':>8}{'win%':>8}{'exp R':>9}{'PF':>7}   verdict")
    print("-" * 78)
    rows = []
    for name, sigs in signals.items():
        rs = []
        for (i, d) in sigs:
            r = _forward(o, h, l, c, i, d, a14[i])
            if r is not None:
                rs.append(r)
        rs = np.array(rs)
        if len(rs) == 0:
            print(f"{name:<22}{0:>8}"); continue
        win = (rs > 0).mean()
        exp = rs.mean()
        gw = rs[rs > 0].sum(); gl = -rs[rs <= 0].sum()
        pf = gw / gl if gl > 0 else float("inf")
        verdict = "EDGE" if exp > 0.05 else ("marginal" if exp > -0.05 else "NOT USEFUL")
        rows.append((name, len(rs), win, exp, pf, verdict))
        print(f"{name:<22}{len(rs):>8}{win*100:>7.1f}%{exp:>+9.3f}{pf:>7.2f}   {verdict}")
    print(f"{'S6 premium/discount':<22}{'—':>8}   filter only, never a standalone trigger (by design)")
    print("-" * 78)

    # --- random-entry baseline (the honest yardstick) -------------------
    rng = np.random.default_rng(42)
    rrs = []
    for _ in range(8000):
        i = int(rng.integers(start, n - 2))
        if np.isnan(a14[i]) or a14[i] <= 0:
            continue
        d = "LONG" if rng.random() < 0.5 else "SHORT"
        r = _forward(o, h, l, c, i, d, a14[i])
        if r is not None:
            rrs.append(r)
    rrs = np.array(rrs)
    rwin, rexp = (rrs > 0).mean(), rrs.mean()
    rgw, rgl = rrs[rrs > 0].sum(), -rrs[rrs <= 0].sum()
    rpf = rgw / rgl if rgl > 0 else float("inf")
    print(f"{'RANDOM baseline':<22}{len(rrs):>8}{rwin*100:>7.1f}%{rexp:>+9.3f}{rpf:>7.2f}   "
          f"<- a scenario must BEAT this to be useful")
    print("-" * 78)
    print(f"Read: a scenario only has edge if its expectancy is clearly ABOVE the "
          f"random {rexp:+.3f} R.\n")
    return rows, rexp


if __name__ == "__main__":
    import sys
    files = sys.argv[1:] or ["BTCUSDT_15m_2023_to_2025.csv", "BTCUSDT_15m_Jan_to_Jul2026.csv"]
    for f in files:
        scan(load_ohlcv(f))
