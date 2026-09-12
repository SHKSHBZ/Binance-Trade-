"""
market_brief.py -- the "eyes" of the LLM layer.

Turns our market data at a point in time into a compact, ANONYMISED brief that
an LLM can judge. Anonymised = no dates, no absolute prices, only relative
structure, percentages and R-multiples. That removes the obvious way an LLM
could cheat on historical data (recognising "BTC on 2025-03-15") -- see
research/LLM_DECISION_SYSTEM_PLAN.md.

The brief describes: higher-timeframe trend, where price sits in its range,
volatility, relative volume (our one real signal: volume forecasts move size),
and the current candidate setup (the Fib fade -- our most robust building block)
expressed purely in R-multiples.

Everything is CAUSAL: only bars up to "now" are used.

Demo:  python3 market_brief.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_loader import load_ohlcv

PIVOT_HALF = 12
MIN_LEG_PCT = 2.0


def _confirmed_pivots(h, l, half):
    n = len(h)
    piv = []
    for i in range(half, n - half):
        wh, wl = h[i - half:i + half + 1], l[i - half:i + half + 1]
        if h[i] == wh.max() and wh.argmax() == half:
            piv.append((i, h[i], "H"))
        elif l[i] == wl.min() and wl.argmin() == half:
            piv.append((i, l[i], "L"))
    clean = []
    for p in piv:
        if clean and clean[-1][2] == p[2]:
            if (p[2] == "H" and p[1] > clean[-1][1]) or \
               (p[2] == "L" and p[1] < clean[-1][1]):
                clean[-1] = p
        else:
            clean.append(p)
    return clean


def _atr_pct(df, n=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(n).mean().iloc[-1]
    return float(atr / c[-1] * 100)


def _rel_volume(df, n=50):
    v = df["volume"].values
    if len(v) < n + 1:
        return None
    med = np.median(v[-n - 1:-1])
    return float(v[-1] / med) if med > 0 else None


def build_brief(df1h: pd.DataFrame) -> dict:
    """Given 1H OHLCV up to 'now' (the last row is the current bar), return a
    dict with a human/LLM-readable `text` and the structured `setup` (or None)."""
    if len(df1h) < PIVOT_HALF * 2 + 60:
        return {"text": "not enough history", "setup": None}
    c = df1h["close"].values
    h, l = df1h["high"].values, df1h["low"].values

    # --- context ---
    sma50 = pd.Series(c).rolling(50).mean().iloc[-1]
    trend = "up" if c[-1] > sma50 else "down"
    look = min(240, len(c))
    hi, lo = h[-look:].max(), l[-look:].min()
    pos = (c[-1] - lo) / (hi - lo) if hi > lo else 0.5
    zone = "upper third (premium)" if pos > 0.66 else \
           "lower third (discount)" if pos < 0.33 else "middle of range"
    atrp = _atr_pct(df1h)
    relv = _rel_volume(df1h)

    # --- candidate setup: the Fib fade on the latest completed leg ---
    # only consider pivots confirmed at least PIVOT_HALF bars ago (causal)
    pivots = _confirmed_pivots(h[:-1], l[:-1], PIVOT_HALF)
    setup = None
    if len(pivots) >= 2:
        a, b = pivots[-2], pivots[-1]
        if a[2] != b[2]:
            leg_up = a[2] == "L"
            origin, extreme = a[1], b[1]
            move = extreme - origin
            leg_pct = abs(move) / origin * 100
            if leg_pct >= MIN_LEG_PCT:
                lvl_05 = extreme - 0.5 * move
                lvl_stop = extreme               # fade stop = prior extreme
                lvl_target = origin              # fade target = origin
                price = c[-1]
                # is price in / near the 0.5 fade zone right now?
                near = abs(price - lvl_05) / price < 0.01
                fade_dir = "SHORT" if leg_up else "LONG"
                risk = abs(lvl_05 - lvl_stop)
                reward = abs(lvl_target - lvl_05)
                rr = reward / risk if risk > 0 else 0
                setup = {
                    "type": "fib_fade",
                    "direction": fade_dir,
                    "leg_pct": round(leg_pct, 1),
                    "at_entry_zone": bool(near),
                    "reward_risk": round(rr, 2),
                    "target_R": round(rr, 2),   # target is rr R away
                    "stop_R": 1.0,
                }

    # --- assemble anonymised text ---
    lines = [
        f"Higher-timeframe trend: {trend}",
        f"Price vs range: {zone} ({pos*100:.0f}% of the last {look}h range)",
        f"Volatility ATR(14): {atrp:.2f}% per hour",
        f"Relative volume now: {relv:.1f}x median" if relv else "Relative volume: n/a",
    ]
    if setup:
        lines.append(
            f"Candidate: {setup['direction']} fade of a {setup['leg_pct']}% leg, "
            f"{'AT' if setup['at_entry_zone'] else 'approaching'} the 0.5 entry; "
            f"stop 1.0R (prior extreme), target {setup['reward_risk']}R (leg origin)")
    else:
        lines.append("Candidate: none (no qualifying leg in the 0.5 zone)")
    return {"text": "\n".join(lines), "setup": setup,
            "context": {"trend": trend, "range_pos": round(pos, 2),
                        "atr_pct": round(atrp, 2),
                        "rel_volume": round(relv, 2) if relv else None}}


if __name__ == "__main__":
    df = load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")
    # show a brief at the most recent bar, and one where a setup is armed
    print("=== market brief at the latest bar ===")
    print(build_brief(df)["text"])
    print("\n=== scanning history for an armed fade setup ===")
    for end in range(len(df) - 1, 300, -1):
        b = build_brief(df.iloc[:end])
        if b["setup"] and b["setup"]["at_entry_zone"]:
            print(f"(found {end} bars in)")
            print(b["text"])
            print("\nstructured:", b["setup"])
            break
