"""
Diagnose the body/wick fade: is the problem the ENTRY or the TAKE-PROFIT?

For every filled trade we ignore our chosen target and instead measure, over the
hold window, how far price traveled in our FAVOR vs AGAINST (in R = units of the
stop distance):

  fav_first  : did price reach +1R in our favor BEFORE -1R against (the stop)?
               -> pure entry quality at 1:1. Below 50% = the ENTRY is wrong.
  MFE (R)    : max favorable excursion -- the best profit the trade ever offered.
  MAE (R)    : max adverse excursion -- the worst heat before it resolved.
  reached +2R/+3R : how often a bigger winner was actually available.

If entries are good (fav_first > 50%, decent MFE) but we still lose, the exit is
the problem. If fav_first < 50% and MFE is small, the ENTRY is the problem.

Run:  python3 body_wick_diagnose.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd

from data_loader import load_ohlcv

HOLD_DAYS = 2
YEARS = [("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)]


def collect(fname, start=None, end=None):
    df = load_ohlcv(fname, start, end)
    daily = df.resample("1D").agg(o=("open", "first"), h=("high", "max"),
                                  l=("low", "min"), c=("close", "last")).dropna()
    days = list(df.groupby(df.index.normalize()))
    idx_of = {d: k for k, (d, _) in enumerate(days)}
    out = []
    for d, g in days:
        prev = d - pd.Timedelta(days=1)
        if prev not in daily.index:
            continue
        po, ph, pl, pc = daily.loc[prev, ["o", "h", "l", "c"]]
        body_hi, body_lo = max(po, pc), min(po, pc)
        k = idx_of[d]
        seg = pd.concat([days[k + mm][1] for mm in range(HOLD_DAYS) if k + mm < len(days)])
        h = seg["high"].values; l = seg["low"].values
        n = len(seg)
        if n < 3:
            continue
        for side in ("SHORT", "LONG"):
            entry, stop = (body_hi, ph) if side == "SHORT" else (body_lo, pl)
            risk = abs(entry - stop)
            if risk <= 0:
                continue
            # honest fill
            armed = False; fill = None
            for i in range(n):
                if side == "SHORT":
                    if h[i] < entry:
                        armed = True
                    if armed and entry <= h[i] < stop:
                        fill = i; break
                    if h[i] >= stop:
                        break
                else:
                    if l[i] > entry:
                        armed = True
                    if armed and stop < l[i] <= entry:
                        fill = i; break
                    if l[i] <= stop:
                        break
            if fill is None:
                continue
            # walk full window from fill, track favor/adverse in R
            fav_first = None; mfe = 0.0; mae = 0.0
            for j in range(fill + 1, n):
                if side == "SHORT":
                    fav = (entry - l[j]) / risk      # price down = favor
                    adv = (h[j] - entry) / risk
                else:
                    fav = (h[j] - entry) / risk
                    adv = (entry - l[j]) / risk
                mfe = max(mfe, fav); mae = max(mae, adv)
                if fav_first is None:
                    if fav >= 1.0:
                        fav_first = True
                    elif adv >= 1.0:
                        fav_first = False
            if fav_first is None:
                fav_first = mfe >= mae
            out.append((side, fav_first, mfe, mae))
    return out


def report(label, trades):
    if not trades:
        print(f"{label}: none"); return
    arr = trades
    n = len(arr)
    ff = np.mean([t[1] for t in arr]) * 100
    mfe = np.array([t[2] for t in arr]); mae = np.array([t[3] for t in arr])
    print(f"{label:<8} n={n:<5} fav-first(1:1)={ff:4.1f}%   "
          f"avgMFE={mfe.mean():.2f}R avgMAE={mae.mean():.2f}R   "
          f"reached +1R={100*(mfe>=1).mean():3.0f}%  +2R={100*(mfe>=2).mean():3.0f}%  "
          f"+3R={100*(mfe>=3).mean():3.0f}%")


if __name__ == "__main__":
    print("ENTRY vs EXIT diagnosis -- body/wick fade (entry quality is target-independent)\n")
    allt = []
    for label, f, s, e in YEARS:
        tr = collect(f, s, e); allt += tr
        report(label, tr)
    print()
    report("POOLED", allt)
    print("\nHow to read:")
    print("  fav-first < 50%  -> ENTRY is wrong (price hits your stop before +1R profit).")
    print("  fav-first > 50% but you still lose -> TAKE-PROFIT/stop placement is wrong.")
