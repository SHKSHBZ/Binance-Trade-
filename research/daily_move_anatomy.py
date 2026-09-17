"""
Anatomy of a "normal" BTC day (measurement, not a strategy).

Answers the trader's two claims:
  1) On normal (non-news) days BTC moves ~500-800 points on average.
  2) Those moves are liquidity-driven: the day grabs the prior day's high/low
     (stops) and then runs -- pure ICT/SMC liquidity hunting.

Measures, per year (BTC $ level changed a lot, so report $ AND %):
  A) Daily high-low RANGE: median, mean, and "normal-day" mean (excludes the
     top-decile widest days as the news/event reactions).
  B) Liquidity taps: how often a day takes out the PRIOR day's high or low.
  C) Sweep-then-reverse ("judas"): sweeps one prior level, closes the day
     beyond the OPPOSITE side -- the classic grab-and-go.
  D) Does a prior-level sweep PRECEDE a bigger move than a no-sweep day?

Measurement only (no trading, no look-ahead concern). Run:
  python3 daily_move_anatomy.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv


def daily_from(fname, start=None, end=None):
    df = load_ohlcv(fname, start, end)
    d = df.resample("1D").agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last")).dropna()
    return d


def analyze(d, label):
    o, h, l, c = (d[x].values for x in ["open", "high", "low", "close"])
    n = len(d)
    rng = h - l                      # absolute daily range ($ / "points")
    rng_pct = rng / o * 100
    # normal days = exclude the widest 10% (news/event reactions)
    cut = np.percentile(rng, 90)
    normal = rng < cut

    pdh = np.roll(h, 1); pdl = np.roll(l, 1)          # prior-day high/low
    valid = np.arange(n) >= 1
    took_high = (h > pdh) & valid
    took_low = (l < pdl) & valid
    took_either = (took_high | took_low)
    took_both = (took_high & took_low)
    # sweep-then-reverse: took prior low but closed UP for the day (grabbed
    # sell-side liquidity then rallied), or took prior high but closed DOWN.
    up_day = c > o
    judas_long = took_low & up_day & ~took_high
    judas_short = took_high & ~up_day & ~took_low
    judas = judas_long | judas_short

    # size of move on sweep days vs no-sweep days
    swept = took_either
    rng_swept = rng_pct[valid & swept]
    rng_noswept = rng_pct[valid & ~swept]

    print(f"\n================  {label}   (days={n})  ================")
    print(f"A) DAILY RANGE (high-low):")
    print(f"     all days     : median ${np.median(rng):>8,.0f}   mean ${rng.mean():>8,.0f}"
          f"   ({np.median(rng_pct):.2f}% / {rng_pct.mean():.2f}%)")
    print(f"     normal (excl top-10% wild): mean ${rng[normal].mean():>8,.0f}"
          f"   ({rng_pct[normal].mean():.2f}%)")
    print(f"     typical BTC price this cut : ${np.median(o):>10,.0f}"
          f"   -> 800 pts = {800/np.median(o)*100:.2f}% of price")
    print(f"B) LIQUIDITY TAPS (day takes out a PRIOR-day level):")
    print(f"     took prior HIGH or LOW : {took_either[valid].mean()*100:5.1f}% of days")
    print(f"     took BOTH (swept both) : {took_both[valid].mean()*100:5.1f}% of days")
    print(f"C) SWEEP-THEN-REVERSE (grab one side, close beyond the other):")
    print(f"     'judas' reversal days  : {judas[valid].mean()*100:5.1f}% of days")
    print(f"D) MOVE SIZE, sweep day vs quiet day:")
    print(f"     day that swept a level : {rng_swept.mean():.2f}%  avg range")
    print(f"     day that swept nothing : {rng_noswept.mean():.2f}%  avg range")
    return dict(rng=rng, rng_pct=rng_pct, took_either=took_either[valid],
                judas=judas[valid], price=np.median(o))


YEARS = [("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    print("ANATOMY OF A NORMAL BTC DAY -- range + liquidity-sweep frequency")
    for label, f, s, e in YEARS:
        analyze(daily_from(f, s, e), label)
    print("\nread: 'points' = dollars. Compare the $ range to the price level to "
          "see when ~800 pts was a normal day. B/C test the liquidity thesis.")
