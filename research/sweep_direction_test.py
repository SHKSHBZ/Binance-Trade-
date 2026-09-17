"""
Does trend/structure predict the DIRECTION of the post-sweep move?  (pure test)

The trader's hypothesis, isolated from all trade mechanics (no stop/target/RR
noise): after a liquidity grab, price continues in the direction of the
prevailing trend. HH/HL -> up, LH/LL -> down.

Method (causal):
  - trend at each bar by TWO definitions:
      MA   : close > EMA(TREND_EMA)  -> up-bias, else down-bias
      HHLL : confirmed HH+HL -> up, LH+LL -> down (bigger swings)
  - liquidity sweep event: price wicks beyond the prior-day low (or high) then
    the bar CLOSES back inside (a grab + reclaim), known at that bar's close.
  - forward test: sign of the return over the next K bars vs the trend bias.
    hit = move went the trend's way. Compare:
       (a) post-sweep bars only  vs  (b) ALL bars (baseline)
    If the sweep+trend combo beats both 50% and the all-bar baseline, the
    idea has directional information.

Run:  python3 sweep_direction_test.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv

TREND_EMA = 200        # ~50h on 15m -- the regime filter that worked before
PIVOT_HALF = 20        # bigger swings for HH/HL structure
FWD = 16               # bars ahead to measure the move (~4h on 15m)


def ema(a, n):
    return pd.Series(a).ewm(span=n, adjust=False).mean().values


def confirmed_pivots(h, l, half):
    n = len(h); ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for i in range(half, n - half):
        if h[i] == h[i - half:i + half + 1].max(): ph[i] = h[i]
        if l[i] == l[i - half:i + half + 1].min(): pl[i] = l[i]
    kh = np.full(n, np.nan); kl = np.full(n, np.nan)
    for i in range(half, n - half):
        if not np.isnan(ph[i]) and i + half < n: kh[i + half] = ph[i]
        if not np.isnan(pl[i]) and i + half < n: kl[i + half] = pl[i]
    return kh, kl


def hhll_bias(kh, kl, n):
    """+1 up (HH+HL), -1 down (LH+LL), 0 undefined -- causal running structure."""
    bias = np.zeros(n); highs = []; lows = []
    for i in range(n):
        if not np.isnan(kh[i]): highs.append(kh[i])
        if not np.isnan(kl[i]): lows.append(kl[i])
        if len(highs) >= 2 and len(lows) >= 2:
            up = highs[-1] > highs[-2] and lows[-1] > lows[-2]
            dn = highs[-1] < highs[-2] and lows[-1] < lows[-2]
            bias[i] = 1 if up else -1 if dn else 0
    return bias


def analyze(fname, label):
    df = load_ohlcv(fname)
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    n = len(c)
    e = ema(c, TREND_EMA)
    ma_bias = np.where(c > e, 1, -1)
    kh, kl = confirmed_pivots(h, l, PIVOT_HALF)
    hb = hhll_bias(kh, kl, n)

    # prior-day levels on this intraday series
    d = df.resample("1D").agg(high=("high", "max"), low=("low", "min")).dropna()
    pdh = d["high"].shift(1); pdl = d["low"].shift(1)
    day = df.index.normalize()
    PDH = pd.Series(day).map(pdh.to_dict()).values
    PDL = pd.Series(day).map(pdl.to_dict()).values

    # sweep events (grab + reclaim), known at bar close
    swept_low = (l < PDL) & (c > PDL)     # grabbed sell-side, reclaimed
    swept_high = (h > PDH) & (c < PDH)    # grabbed buy-side, rejected
    swept = swept_low | swept_high

    fwd = np.full(n, np.nan)
    fwd[:n - FWD] = np.sign(c[FWD:] - c[:n - FWD])   # sign of forward move

    def hit(mask, bias):
        m = mask & ~np.isnan(fwd) & (bias != 0)
        if m.sum() == 0: return (0, 0.0)
        agree = (fwd[m] == bias[m])
        return (int(m.sum()), 100.0 * agree.mean())

    print(f"\n===============  {label}  (bars={n:,})  ===============")
    for bname, bias in [("MA(200)", ma_bias), ("HH/HL", hb)]:
        n_all, h_all = hit(np.ones(n, bool), bias)
        n_sw, h_sw = hit(swept, bias)
        print(f"  trend={bname:8}  forward {FWD} bars goes trend-way:")
        print(f"      ALL bars      : {h_all:5.1f}%   (n={n_all:,})")
        print(f"      POST-SWEEP    : {h_sw:5.1f}%   (n={n_sw:,})   "
              f"{'<-- edge' if h_sw>52 and h_sw>h_all+1 else '(no lift)'}")


if __name__ == "__main__":
    print(f"POST-SWEEP DIRECTION vs TREND  (forward {FWD} bars, 15m BTC)")
    print("does the trend predict which way price goes AFTER a liquidity grab?")
    for f, lab in [("BTCUSDT_15m_2023_to_2025.csv", "2023-2025"),
                   ("BTCUSDT_15m_Jan_to_Jul2026.csv", "2026")]:
        analyze(f, lab)
    print("\nread: 50% = coin flip. Need clearly >52% AND above the all-bar "
          "baseline for the sweep+trend combo to carry real direction.")
