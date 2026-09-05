"""
Find the capital(risk%)/leverage combination that survives EVERY market
regime -- bull, bear, and sideways -- not just one good year.

Runs the validated SMC engine continuously across all available BTC data
(2023-01 -> 2026-07) for each combo, then buckets every trade by the
market regime it was taken in (regimes classified from BTC's own quarterly
price action). A combo is only "suitable in every market" if it is
profitable (or at least not ruinous) in ALL THREE regimes with a drawdown
you could actually sit through.

Realistic costs (stop slippage + funding) are always on -- optimizing on
the clean, cost-free numbers is how people fool themselves.
"""

import numpy as np
import pandas as pd

import _paths  # noqa: F401  # puts repo root on sys.path

import backtest_engine as be
from smc_engine import SMCParams

FULL = ("/tmp/claude-0/-home-user-Binance-Trade-/"
        "6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/BTC_full.csv")
be.STARTING_CAPITAL = 500.0


def regime_map(df):
    q = df["close"].resample("QE").agg(["first", "last"])
    q["ret"] = q["last"] / q["first"] - 1
    q["regime"] = np.where(q["ret"] > 0.15, "BULL",
                           np.where(q["ret"] < -0.15, "BEAR", "SIDEWAYS"))
    return q["regime"]


def classify(ts, reg):
    """Regime of the quarter containing ts."""
    qend = ts.to_period("Q").end_time
    idx = reg.index.searchsorted(qend)
    idx = min(idx, len(reg) - 1)
    return reg.iloc[idx]


def analyse(trades, reg):
    """Per-regime compounded return + overall max drawdown, from $500."""
    buckets = {"BULL": [], "BEAR": [], "SIDEWAYS": []}
    bals = [be.STARTING_CAPITAL]
    for t in trades:
        r = classify(t["time"], reg)
        prev = t["bal"] - t["pnl"]
        factor = t["bal"] / prev if prev > 0 else 1.0
        buckets[r].append(factor)
        bals.append(t["bal"])
    bals = np.array(bals)
    peak = np.maximum.accumulate(bals)
    max_dd = float(((peak - bals) / peak).max()) * 100

    out = {}
    for r, facs in buckets.items():
        mult = np.prod(facs) if facs else 1.0
        out[r] = {"trades": len(facs), "ret_pct": (mult - 1) * 100}
    final = bals[-1]
    return out, max_dd, final


if __name__ == "__main__":
    df = be.load_ohlcv(FULL)
    reg = regime_map(df)

    risks = [0.01, 0.02, 0.03, 0.05]
    levs = [10, 25]

    print("SMC engine across ALL regimes (2023-01 -> 2026-07), start $500, "
          "realistic costs")
    print("Regimes in data: BULL, BEAR, SIDEWAYS (neutral = sideways)\n")
    hdr = (f"{'risk':>5} {'lev':>4} | {'end $':>8} {'overall':>8} {'maxDD':>7} | "
           f"{'BULL':>8} {'BEAR':>8} {'SIDE':>8} | worst regime")
    print(hdr); print("-" * len(hdr))

    for risk in risks:
        for lev in levs:
            p = SMCParams(risk_per_trade_pct=risk, leverage=lev)
            trades, final, _ = be.run(FULL, params=p,
                                      stop_slippage=0.001, funding_per_8h=0.0001)
            per, mdd, fin = analyse(trades, reg)
            worst = min(per.values(), key=lambda x: x["ret_pct"])
            worst_name = [k for k, v in per.items() if v is worst][0]
            print(f"{risk*100:>4.0f}% {lev:>3}x | {fin:>8,.0f} "
                  f"{(fin/500-1)*100:>+7.0f}% {mdd:>6.1f}% | "
                  f"{per['BULL']['ret_pct']:>+7.0f}% {per['BEAR']['ret_pct']:>+7.0f}% "
                  f"{per['SIDEWAYS']['ret_pct']:>+7.0f}% | {worst_name} "
                  f"{worst['ret_pct']:+.0f}%")

    # trade counts per regime (same for all, from the last run)
    print()
    counts = {k: v["trades"] for k, v in per.items()}
    print(f"trades per regime (approx): {counts}   total {sum(counts.values())}")
