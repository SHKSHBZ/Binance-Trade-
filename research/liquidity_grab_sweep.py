"""
Liquidity GRAB and Liquidity SWEEP (the trader's two REVERSAL setups) on GOLD.

GRAB (no accumulation needed):
  - price pokes a prior swing level, the candle CLOSES BACK INSIDE, level
    stays intact -> reverse.
  - SHORT: high pierces last swing high, close < that high. LONG: mirror.
  - STOP: beyond the poke wick. TARGET: opposite prior swing (full range).

SWEEP (accumulation first):
  - a TIGHT accumulation range forms over the last ACC_N bars.
  - price takes liquidity beyond the range and a candle CLOSES BACK INSIDE
    the range -> reverse. (a fake breakout is NOT required.)
  - STOP: beyond the poke wick. TARGET: opposite side of the range (full range).

Both causal, min-stop filter (no sub-spread artifacts), honest fees + slippage,
scored with trade_stats + random-direction null.  Run: python3 liquidity_grab_sweep.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades
from structure_sweep import confirmed_pivots

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
SWING_HALF = 10
STOP_BUF = 0.0010
MIN_RISK_FRAC = 0.0005
ACC_N = 20            # accumulation lookback (bars)
ACC_MAX_FRAC = 0.010  # range is "accumulation" if width <= 1.0% of price


def _simulate(direction, entry, stop, tgt, h, l, c, i, n):
    j = i + 1
    exit_px = exit_r = None
    while j < n:
        if direction == "LONG":
            if l[j] <= stop: exit_px, exit_r = stop, "STOP"; break
            if h[j] >= tgt:  exit_px, exit_r = tgt, "TARGET"; break
        else:
            if h[j] >= stop: exit_px, exit_r = stop, "STOP"; break
            if l[j] <= tgt:  exit_px, exit_r = tgt, "TARGET"; break
        j += 1
    if exit_px is None:
        j = n - 1; exit_px, exit_r = c[j], "END"
    if exit_r in ("STOP", "END"):
        exit_px *= (1 - SLIP) if direction == "LONG" else (1 + SLIP)
    return exit_px, exit_r, j


def _book(trades, direction, entry, stop, tgt, exit_px, exit_r, cap, t_i):
    qty = (cap * 0.01) / abs(entry - stop)
    gross = qty * (exit_px - entry) if direction == "LONG" else qty * (entry - exit_px)
    fee = qty * entry * TAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
    trades.append({"dir": direction, "time": t_i, "entry": entry, "stop": stop,
                   "target": tgt, "qty": qty, "notional": qty * entry,
                   "pnl": gross - fee, "exit_r": exit_r,
                   "rr": abs(tgt - entry) / abs(entry - stop)})
    return gross - fee


def run(fname, start=None, end=None, mode="grab", force_dir=None, seed=None):
    df = load_ohlcv(fname, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values
    c = df["close"].values; t = df.index; n = len(c)
    kh, kl = confirmed_pivots(h, l, SWING_HALF)
    rng = np.random.default_rng(seed)
    highs = []; lows = []
    capital = CAP; trades = []; busy = -1

    for i in range(max(SWING_HALF, ACC_N), n - 1):
        if not np.isnan(kh[i]): highs.append(kh[i])
        if not np.isnan(kl[i]): lows.append(kl[i])
        if i <= busy:
            continue
        direction = entry = stop = tgt = None

        if mode == "grab":
            sh = highs[-1] if highs else None
            sl = lows[-1] if lows else None
            if sh is not None and h[i] > sh and c[i] < sh:
                direction = "SHORT"; entry = c[i]; stop = h[i] * (1 + STOP_BUF)
                below = [x for x in lows if x < entry]; tgt = max(below) if below else None
            elif sl is not None and l[i] < sl and c[i] > sl:
                direction = "LONG"; entry = c[i]; stop = l[i] * (1 - STOP_BUF)
                above = [x for x in highs if x > entry]; tgt = min(above) if above else None
        else:  # sweep
            rhi = h[i - ACC_N:i].max(); rlo = l[i - ACC_N:i].min()
            if (rhi - rlo) / c[i] <= ACC_MAX_FRAC:      # tight accumulation
                if h[i] > rhi and c[i] < rhi:
                    direction = "SHORT"; entry = c[i]; stop = h[i] * (1 + STOP_BUF); tgt = rlo
                elif l[i] < rlo and c[i] > rlo:
                    direction = "LONG"; entry = c[i]; stop = l[i] * (1 - STOP_BUF); tgt = rhi

        if direction is None or tgt is None:
            continue
        if abs(entry - stop) / entry < MIN_RISK_FRAC:
            continue
        if force_dir == "random":
            risk = abs(entry - stop); rr = abs(tgt - entry) / risk
            direction = "LONG" if rng.random() < 0.5 else "SHORT"
            if direction == "LONG": stop = entry - risk; tgt = entry + rr * risk
            else: stop = entry + risk; tgt = entry - rr * risk
        if direction == "LONG" and not (stop < entry < tgt): continue
        if direction == "SHORT" and not (tgt < entry < stop): continue
        if abs(tgt - entry) / abs(entry - stop) < 1.0: continue

        exit_px, exit_r, j = _simulate(direction, entry, stop, tgt, h, l, c, i, n)
        capital = max(capital + _book(trades, direction, entry, stop, tgt,
                                      exit_px, exit_r, capital, t[i]), 0.0)
        busy = j
        if capital <= 0: break
    return trades


def report(fname, mode, years):
    pooled = []
    for y in years:
        tr = run(fname, f"{y}-01-01", f"{y}-12-31", mode=mode); pooled += tr
        st = summarize_trades(tr, CAP, label=str(y))
        print(f"    {y}: n={st.n:<4} win={st.win_rate:4.1f}%  ret={st.ret_pct:+8.1f}%  expR={st.expectancy_r:+.3f}")
    ps = summarize_trades(pooled, CAP)
    rr = np.mean([x["rr"] for x in pooled]) if pooled else 0
    print(f"    POOLED: n={ps.n:<4} win={ps.win_rate:4.1f}%  avgRR={rr:.1f}  ret={ps.ret_pct:+7.1f}%  "
          f"expR={ps.expectancy_r:+.3f}  edge={ps.edge_confidence:.0f}%")


if __name__ == "__main__":
    YRS = list(range(2020, 2027))
    for mode in ("grab", "sweep"):
        print(f"\n=== LIQUIDITY {mode.upper()} on GOLD 30m ===")
        report("XAUUSD_30m.csv", mode, YRS)
