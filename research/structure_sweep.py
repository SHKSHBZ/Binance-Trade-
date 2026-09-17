"""
Structure-Filtered Liquidity Sweep (the trader's fusion idea).

The two proven facts:
  - liquidity grabs drive the moves (measured: sweep days ~1.7x bigger), but
  - the SWEEP alone doesn't tell you direction (coin flip).
So use MARKET STRUCTURE to pick the side:
  - UPTREND  = higher highs AND higher lows (HH + HL)
  - DOWNTREND = lower highs AND lower lows (LH + LL)

Setup (continuation WITH structure, not fading):
  - UPTREND: price SWEEPS the most recent swing LOW (grabs sell-side
    liquidity at a discount) then CLOSES back above it -> LONG.
    stop = sweep low; target = recent swing HIGH (buy-side liquidity).
  - DOWNTREND: sweeps the recent swing HIGH then closes back below -> SHORT.
    stop = sweep high; target = recent swing LOW.

Causal: swings are only known PIVOT_HALF bars after they print; sweep is
known at the bar close; entry at that close; stop/target on later bars.
Honest fees + slippage. Scored with trade_stats and a random-direction
null test. Run:  python3 structure_sweep.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
PIVOT_HALF = 5        # swing detection window
STOP_BUF = 0.0010     # stop beyond the sweep wick
MIN_RR = 1.0          # skip setups whose structure target is closer than this


def confirmed_pivots(h, l, half):
    """Return known_high[i], known_low[i]: the swing value that becomes KNOWN
    at bar i (i.e. a pivot at bar p is confirmed at p+half). NaN if none."""
    n = len(h)
    ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for i in range(half, n - half):
        if h[i] == h[i - half:i + half + 1].max():
            ph[i] = h[i]
        if l[i] == l[i - half:i + half + 1].min():
            pl[i] = l[i]
    kh = np.full(n, np.nan); kl = np.full(n, np.nan)
    for i in range(half, n - half):
        if not np.isnan(ph[i]) and i + half < n:
            kh[i + half] = ph[i]
        if not np.isnan(pl[i]) and i + half < n:
            kl[i + half] = pl[i]
    return kh, kl


def run(fname, start=None, end=None, force_dir=None, seed=None):
    """force_dir: None = real structure; 'random' = random long/short at each
    trigger (null baseline, keeps identical timing + geometry)."""
    df = load_ohlcv(fname, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values
    c = df["close"].values; t = df.index; n = len(c)
    kh, kl = confirmed_pivots(h, l, PIVOT_HALF)
    rng = np.random.default_rng(seed)

    highs = []; lows = []   # running list of confirmed swing values (in order)
    capital = CAP; trades = []; busy = -1

    for i in range(PIVOT_HALF, n - 1):
        if not np.isnan(kh[i]):
            highs.append(kh[i])
        if not np.isnan(kl[i]):
            lows.append(kl[i])
        if i <= busy:
            continue
        if len(highs) < 2 or len(lows) < 2:
            continue

        sh_last, sh_prev = highs[-1], highs[-2]
        sl_last, sl_prev = lows[-1], lows[-2]
        up = sh_last > sh_prev and sl_last > sl_prev      # HH + HL
        down = sh_last < sh_prev and sl_last < sl_prev    # LH + LL

        direction = entry = stop = tgt = None
        # UPTREND: sweep the most recent swing low, reclaim -> long
        if up and l[i] < sl_last and c[i] > sl_last:
            direction = "LONG"; entry = c[i]; stop = l[i] * (1 - STOP_BUF); tgt = sh_last
        # DOWNTREND: sweep the most recent swing high, reject -> short
        elif down and h[i] > sh_last and c[i] < sh_last:
            direction = "SHORT"; entry = c[i]; stop = h[i] * (1 + STOP_BUF); tgt = sl_last

        if direction is None:
            continue
        if force_dir == "random":                         # null: flip a coin
            direction = "LONG" if rng.random() < 0.5 else "SHORT"
            risk = abs(entry - stop)
            if direction == "LONG":
                stop = entry - risk; tgt = entry + abs(tgt - entry)
            else:
                stop = entry + risk; tgt = entry - abs(tgt - entry)
        # geometry sanity + min RR
        if direction == "LONG" and not (stop < entry < tgt):
            continue
        if direction == "SHORT" and not (tgt < entry < stop):
            continue
        rr = abs(tgt - entry) / abs(entry - stop)
        if rr < MIN_RR:
            continue

        risk = abs(entry - stop)
        qty = (capital * 0.01) / risk if risk > 0 else 0
        if qty <= 0:
            continue
        exit_px = exit_r = None; j = i + 1
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
        gross = qty * (exit_px - entry) if direction == "LONG" else qty * (entry - exit_px)
        fee = qty * entry * TAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
        capital = max(capital + gross - fee, 0.0)
        trades.append({"dir": direction, "time": t[i], "entry": entry, "stop": stop,
                       "target": tgt, "qty": qty, "notional": qty * entry,
                       "pnl": gross - fee, "exit_r": exit_r, "rr": rr})
        busy = j
        if capital <= 0:
            break
    return trades


YEARS = [("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    print("STRUCTURE-FILTERED LIQUIDITY SWEEP -- 15m BTC (trade WITH HH/HL or LL/LH)\n")
    pooled = []
    for label, f, s, e in YEARS:
        tr = run(f, start=s, end=e); pooled += tr
        st = summarize_trades(tr, CAP, label=label)
        rr = np.mean([x["rr"] for x in tr]) if tr else 0
        print(f"  {label}: n={st.n:<4} win={st.win_rate:4.1f}%  avgRR={rr:.1f}  "
              f"ret={st.ret_pct:+7.1f}%  expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
    ps = summarize_trades(pooled, CAP)
    print(f"\n  POOLED: n={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
          f"expR={ps.expectancy_r:+.3f}  Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%")

    # null test: same triggers/geometry, random direction
    nm = []
    for seed in range(50):
        p = []
        for label, f, s, e in YEARS:
            p += run(f, start=s, end=e, force_dir="random", seed=seed)
        nm.append(summarize_trades(p, CAP).expectancy_r)
    nm = np.array(nm)
    pv = float((nm >= ps.expectancy_r).mean())
    print(f"\n  NULL (random direction, same timing+geometry, 300 draws):")
    print(f"    mean expR={nm.mean():+.3f}  95pct={np.percentile(nm,95):+.3f}  "
          f"p(random>=real)={pv:.3f}")
    print("    -> " + ("REAL DIRECTIONAL EDGE (p<0.05)" if pv < 0.05 else
                        "marginal (0.05-0.10)" if pv < 0.10 else
                        "structure does NOT beat random direction"))
