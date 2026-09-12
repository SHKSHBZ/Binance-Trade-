"""
Fibonacci level hit-rate study  (MEASUREMENT ONLY -- no trades, no money)

The question: when we draw a Fib on a 1H leg, how does price actually REACT to
the 0.0 / 0.3 / 0.5 / 1.0 levels afterwards? Which levels get touched, how
often, and in what order? This is the "basic behaviour" check we do BEFORE
designing any entry/stop/target.

Convention (up-leg example: swing low L -> swing high H, move = H-L):
    0.0 = H          the extreme / end of the move
    0.3 = H-0.3*move shallow pullback (higher price, hit first on a pullback)
    0.5 = H-0.5*move halfway pullback (lower price, hit second)
    1.0 = L          the origin of the move  (breaking it = move fully failed)
Down-legs are the mirror image.

Everything is CAUSAL: a pivot at bar p is only *confirmed* L bars later (its
high/low is the extreme of the window [p-L, p+L]); we only start watching a leg
at that confirmation bar, never before. No look-ahead.

Run:  python3 fib_level_study.py
"""
import _paths  # noqa: F401  (adds repo root to path)
import numpy as np
import pandas as pd

from data_loader import load_ohlcv

PIVOT_HALF = 12       # bars each side to confirm a swing pivot (12h on 1H)
FWD_BARS = 240        # how long we watch a leg after it forms (~10 days on 1H)
DAILY_SMA = 20        # daily trend filter: price above its N-day average = up
MIN_LEG_PCT = 2.0     # a leg must be at least this % move to count as real
EXT1 = 1.272          # first extension target beyond the extreme (TP3 option)
EXT2 = 1.618          # second extension target


# ----------------------------------------------------------------------------
# causal swing pivots (fractal, confirmed PIVOT_HALF bars late)
# ----------------------------------------------------------------------------
def confirmed_pivots(h, l, half):
    """Return a time-ordered list of (confirm_bar, pivot_bar, price, kind).

    kind = 'H' (swing high) or 'L' (swing low). confirm_bar = pivot_bar + half
    is the first bar at which we could KNOW the pivot (no future data used).
    """
    n = len(h)
    piv = []
    for i in range(half, n - half):
        win_h = h[i - half:i + half + 1]
        win_l = l[i - half:i + half + 1]
        if h[i] == win_h.max() and (win_h.argmax() == half):
            piv.append((i + half, i, h[i], "H"))
        elif l[i] == win_l.min() and (win_l.argmin() == half):
            piv.append((i + half, i, l[i], "L"))
    piv.sort()
    # keep alternating H/L (collapse runs of same kind, keep the more extreme)
    clean = []
    for p in piv:
        if clean and clean[-1][3] == p[3]:
            if (p[3] == "H" and p[2] > clean[-1][2]) or \
               (p[3] == "L" and p[2] < clean[-1][2]):
                clean[-1] = p
        else:
            clean.append(p)
    return clean


def daily_uptrend_flags(df, sma_days):
    """Per-1H-bar boolean: is the daily close above its N-day SMA? Causal:
    a given day's SMA uses only days up to and including the prior close."""
    daily = df["close"].resample("1D").last().dropna()
    sma = daily.rolling(sma_days).mean()
    up = (daily > sma)
    # shift by 1 day so we only use info available before the current day opens
    up = up.shift(1).reindex(df.index, method="ffill")
    return up.fillna(False).values


# ----------------------------------------------------------------------------
# the study
# ----------------------------------------------------------------------------
def study(files, label):
    frames = [load_ohlcv(f) for f in files]
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    n = len(c)
    up_daily = daily_uptrend_flags(df, DAILY_SMA)

    pivots = confirmed_pivots(h, l, PIVOT_HALF)

    # build legs from consecutive opposite pivots
    rows = []
    for a, b in zip(pivots, pivots[1:]):
        if a[3] == b[3]:
            continue
        direction = "UP" if (a[3] == "L" and b[3] == "H") else "DOWN"
        origin_price = a[2]        # level 1.0
        extreme_price = b[2]       # level 0.0
        confirm_bar = b[0]         # we know the leg here (causal)
        if confirm_bar >= n - 1:
            continue
        move = extreme_price - origin_price  # signed (+ up-leg, - down-leg)
        if move == 0:
            continue
        leg_pct = abs(move) / origin_price * 100.0
        if leg_pct < MIN_LEG_PCT:          # ignore noise-sized legs
            continue

        # fib levels (continuation perspective)
        lvl = {
            0.3: extreme_price - 0.3 * move,   # TP1 after a 0.5 entry
            0.5: extreme_price - 0.5 * move,   # the pullback entry zone
            0.0: extreme_price,                # TP2  (the prior extreme)
            "ext1": extreme_price + (EXT1 - 1.0) * move,  # TP3
            "ext2": extreme_price + (EXT2 - 1.0) * move,  # TP4
            1.0: origin_price,                 # invalidation (move failed)
        }
        end = min(confirm_bar + FWD_BARS, n)
        seg_h = h[confirm_bar + 1:end]
        seg_l = l[confirm_bar + 1:end]
        if len(seg_h) == 0:
            continue

        # entry trigger: price pulls back into the 0.5 zone
        if direction == "UP":
            trig = np.where(seg_l <= lvl[0.5])[0]
        else:
            trig = np.where(seg_h >= lvl[0.5])[0]
        entered = len(trig) > 0

        rec = {"dir": direction, "uptrend_day": bool(up_daily[confirm_bar]),
               "leg_pct": leg_pct, "entered": entered,
               "tp1_03": False, "tp2_00": False, "tp3_ext1": False,
               "tp4_ext2": False, "stopped": False}

        if entered:
            e = trig[0]                      # bar price first enters the zone
            ph, pl = seg_h[e:], seg_l[e:]    # forward from entry
            # first bar each level is reached (np.inf if never)
            def first(cond):
                w = np.where(cond)[0]
                return w[0] if len(w) else np.inf
            if direction == "UP":
                stop_b = first(pl <= lvl[1.0])
                t1 = first(ph >= lvl[0.3]); t2 = first(ph >= lvl[0.0])
                t3 = first(ph >= lvl["ext1"]); t4 = first(ph >= lvl["ext2"])
            else:
                stop_b = first(ph >= lvl[1.0])
                t1 = first(pl <= lvl[0.3]); t2 = first(pl <= lvl[0.0])
                t3 = first(pl <= lvl["ext1"]); t4 = first(pl <= lvl["ext2"])
            # a target "hits" only if it is reached before invalidation
            rec["tp1_03"] = t1 < stop_b
            rec["tp2_00"] = t2 < stop_b
            rec["tp3_ext1"] = t3 < stop_b
            rec["tp4_ext2"] = t4 < stop_b
            rec["stopped"] = np.isfinite(stop_b) and stop_b < t2  # stop before 0.0
        rows.append(rec)

    res = pd.DataFrame(rows)
    report(label, res, len(df), len(pivots))
    return res


def report(label, res, nbars, npiv):
    print(f"\n================  {label}  ================")
    print(f"1H bars: {nbars:,}   confirmed pivots: {npiv}   real legs (>= "
          f"{MIN_LEG_PCT}%): {len(res)}   (pivot half={PIVOT_HALF}, watch={FWD_BARS})")
    if res.empty:
        print("  no legs")
        return

    def block(sub, name):
        if sub.empty:
            print(f"  {name:<26} (no legs)")
            return
        k = len(sub)
        ent = sub[sub["entered"]]
        e = len(ent)
        print(f"  {name:<26} legs={k}   entered 0.5 zone={e} ({e/k*100:.0f}%)"
              f"   avg leg {sub['leg_pct'].mean():.1f}%")
        if e == 0:
            return
        # hit-rates are conditional on having entered the 0.5 zone
        print(f"      of entries -> TP1 (0.3) before invalidation  {ent['tp1_03'].mean()*100:5.1f}%")
        print(f"                    TP2 (0.0, prior extreme)        {ent['tp2_00'].mean()*100:5.1f}%"
              "   <- the real continuation win")
        print(f"                    TP3 (1.272 extension)           {ent['tp3_ext1'].mean()*100:5.1f}%")
        print(f"                    TP4 (1.618 extension)           {ent['tp4_ext2'].mean()*100:5.1f}%")
        print(f"                    invalidated (broke 1.0 first)   {ent['stopped'].mean()*100:5.1f}%")

    block(res, "ALL real legs")
    with_trend = res[((res["dir"] == "UP") & res["uptrend_day"]) |
                     ((res["dir"] == "DOWN") & ~res["uptrend_day"])]
    counter = res[((res["dir"] == "UP") & ~res["uptrend_day"]) |
                  ((res["dir"] == "DOWN") & res["uptrend_day"])]
    print("  --- split by daily trend filter ---")
    block(with_trend, "WITH daily trend")
    block(counter, "AGAINST daily trend")


if __name__ == "__main__":
    print("FIB LEVEL HIT-RATE STUDY -- measurement only, no trades")
    print("Entry = price pulls back into the 0.5 zone of a real 1H leg.")
    print("Then we race each target against invalidation (break of 1.0).")
    study(["BTCUSDT_1h_2023_to_2025.csv"], "2023-2025")
    study(["BTCUSDT_1h_Jan_to_Jul2026.csv"], "2026 (Jan-Jul)")
