"""
Volume study -- is there information in BTC volume? (measurement only)

Honest finding up front: volume predicts HOW BIG the next move is (volatility),
NOT which way (direction). So volume is a timing / risk / filter tool, never a
standalone buy-sell signal. This script reproduces the evidence.

All features are CAUSAL: relative volume uses a trailing median shifted by one
bar, so a bar is only compared to volume BEFORE it.

Run:  python3 volume_study.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd

from data_loader import load_ohlcv


def rel_volume(v, lookback=50):
    """volume / its trailing median (past-only)."""
    med = pd.Series(v).rolling(lookback).median().shift(1).values
    return v / med


def study(fname, label):
    df = load_ohlcv(fname)
    o, h, l, c, v = (df[x].values for x in ["open", "high", "low", "close", "volume"])
    n = len(c)
    relv = rel_volume(v)
    lv = np.log(v + 1)
    nextret = np.concatenate([np.diff(np.log(c)), [np.nan]]) * 100  # t -> t+1

    print(f"\n================  {label}  ================")
    print(f"bars={n:,}  mean vol={v.mean():,.0f}  median={np.median(v):,.0f}")
    print(f"spikiness (std/mean)        {v.std()/v.mean():.2f}")
    print(f"max / median                {v.max()/np.median(v):.0f}x")
    print(f"volume autocorrelation(1)   {np.corrcoef(lv[:-1], lv[1:])[0,1]:.2f}"
          "   <- volume clusters (high follows high)")
    ok = ~np.isnan(nextret)
    print(f"corr(volume[t], |ret|[t+1]) {np.corrcoef(lv[ok], np.abs(nextret[ok]))[0,1]:.2f}"
          "   <- predicts SIZE of next move")

    print("\n  by relative-volume bucket:")
    print(f"    {'bucket':<16}{'n':>7}{'mean next':>11}{'up-rate':>9}{'|next move|':>13}")
    valid = ~np.isnan(relv) & ~np.isnan(nextret)
    rv, nr = relv[valid], nextret[valid]
    for lo, hi, lbl in [(0, 0.7, "low  <0.7x"), (0.7, 1.3, "normal"),
                        (1.3, 3, "high 1.3-3x"), (3, 99, "spike >3x")]:
        m = (rv >= lo) & (rv < hi)
        if m.sum() == 0:
            continue
        print(f"    {lbl:<16}{m.sum():>7}{nr[m].mean():>+10.3f}%"
              f"{(nr[m] > 0).mean()*100:>8.1f}%{np.abs(nr[m]).mean():>12.3f}%")
    print("  read: move SIZE grows with volume; up-rate stays ~50% "
          "(no direction edge).")


if __name__ == "__main__":
    print("VOLUME STUDY -- does BTC volume carry information?")
    study("BTCUSDT_1h_2023_to_2025.csv", "1H  2023-2025")
    study("BTCUSDT_1h_Jan_to_Jul2026.csv", "1H  2026 (Jan-Jul)")
    print("\nCONCLUSION: volume forecasts VOLATILITY, not DIRECTION. Use it to")
    print("time/filter/size trades, or to catch volatility expansions -- never")
    print("as a buy/sell signal on its own.")
