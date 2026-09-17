"""
Volume Profile Rejection (the user's "absorption won" reversal).

Idea (faithful mechanization):
  - Build a FIXED-RANGE volume profile over the recent window (past-only).
    -> POC (highest-volume price node), HVNs (high-vol nodes), the profile.
  - TRIGGER: price pushes BEYOND the recent swing extreme -- into the
    low-volume void above the high (or below the low) -- but CLOSES back
    inside. That failed push = "no interest up/down there."
  - ENTRY : when price then CLOSES back through the POC (buyers/sellers
    trapped -> absorption won) -> reversal entry at that close.
  - TARGET: the biggest HVN on the OPPOSITE side of the POC (price
    magnetizes back to historical high-liquidity).
  - STOP  : just beyond the sweep extreme.

Causal: the profile uses only bars BEFORE the current one; the sweep is
known at a bar close; entry is a later bar close; stop/target on bars after.
Honest fees (entry+stop taker, target maker) and slippage. Scored with
trade_stats.

Run:  python3 volume_profile_rejection.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
LOOKBACK = 240        # bars in the "fixed range" profile (~2.5 days on 15m)
NBINS = 60            # price bins in the profile
ARM_WIN = 8           # bars after a sweep to wait for the POC re-cross
STOP_BUF = 0.0010     # stop this far beyond the sweep extreme
HVN_FRAC = 0.35       # a bin is an HVN if its volume >= this * POC volume


def build_profile(h, l, v, lo_i, hi_i, nbins):
    """Volume profile over bars [lo_i, hi_i): returns (bin_centers, vol_per_bin,
    price_lo, price_hi). Each bar's volume is spread uniformly across the bins
    its high-low range covers (standard VP approximation)."""
    ph = h[lo_i:hi_i]; pl = l[lo_i:hi_i]; pv = v[lo_i:hi_i]
    price_lo = pl.min(); price_hi = ph.max()
    if price_hi <= price_lo:
        return None
    edges = np.linspace(price_lo, price_hi, nbins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    width = (price_hi - price_lo) / nbins
    # spread each bar's volume uniformly across the bins its high-low covers,
    # vectorized via a difference array (identical math to a per-bar loop).
    b0 = np.clip(((pl - price_lo) / width).astype(int), 0, nbins - 1)
    b1 = np.clip(((ph - price_lo) / width).astype(int), 0, nbins - 1)
    contrib = pv / (b1 - b0 + 1)
    diff = np.zeros(nbins + 1)
    np.add.at(diff, b0, contrib)
    np.add.at(diff, b1 + 1, -contrib)
    vol = np.cumsum(diff)[:nbins]
    return centers, vol, price_lo, price_hi


def run(fname, start=None, end=None, target_mode="far"):
    # target_mode: "near" = biggest HVN just past the POC; "far" = the HVN
    #   cluster on the far opposite side of the profile (a bigger magnet).
    df = load_ohlcv(fname, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values
    c = df["close"].values; v = df["volume"].values
    t = df.index; n = len(c)

    capital = CAP; trades = []; busy = -1
    # armed state: (side, sweep_extreme, poc, target, arm_expiry)
    armed = None

    for i in range(LOOKBACK, n - 1):
        if i <= busy:
            continue
        prof = build_profile(h, l, v, i - LOOKBACK, i, NBINS)
        if prof is None:
            continue
        centers, vol, p_lo, p_hi = prof
        poc = centers[int(vol.argmax())]
        poc_vol = vol.max()
        rng_hi = h[i - LOOKBACK:i].max()
        rng_lo = l[i - LOOKBACK:i].min()

        # ---- manage an armed setup: wait for the POC re-cross ----
        if armed is not None:
            side, swept, poc0, tgt, expiry = armed
            if i > expiry:
                armed = None
            elif side == "SHORT" and c[i] < poc0:
                entry = c[i]; stop = swept * (1 + STOP_BUF)
                if tgt < entry < stop:
                    armed = ("FIRE", "SHORT", entry, stop, tgt);
            elif side == "LONG" and c[i] > poc0:
                entry = c[i]; stop = swept * (1 - STOP_BUF)
                if stop < entry < tgt:
                    armed = ("FIRE", "LONG", entry, stop, tgt)

        # ---- fire an entry ----
        if armed is not None and armed[0] == "FIRE":
            _, direction, entry, stop, tgt = armed
            armed = None
            risk = abs(entry - stop)
            qty = (capital * 0.01) / risk if risk > 0 else 0
            if qty <= 0:
                continue
            exit_px = exit_r = None; j = i + 1
            while j < n:
                if direction == "SHORT":
                    if h[j] >= stop: exit_px, exit_r = stop, "STOP"; break
                    if l[j] <= tgt:  exit_px, exit_r = tgt, "TARGET"; break
                else:
                    if l[j] <= stop: exit_px, exit_r = stop, "STOP"; break
                    if h[j] >= tgt:  exit_px, exit_r = tgt, "TARGET"; break
                j += 1
            if exit_px is None:
                j = n - 1; exit_px, exit_r = c[j], "END"
            if exit_r in ("STOP", "END"):
                exit_px *= (1 + SLIP) if direction == "SHORT" else (1 - SLIP)
            gross = qty * (entry - exit_px) if direction == "SHORT" else qty * (exit_px - entry)
            fee = qty * entry * TAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
            capital = max(capital + gross - fee, 0.0)
            rr = abs(tgt - entry) / risk
            trades.append({"dir": direction, "time": t[i], "entry": entry, "stop": stop,
                           "target": tgt, "qty": qty, "notional": qty * entry,
                           "pnl": gross - fee, "exit_r": exit_r, "rr": rr})
            busy = j
            if capital <= 0:
                break
            continue

        # ---- look for a NEW sweep to arm (only if not already armed) ----
        if armed is not None:
            continue
        # HVNs on either side of the POC (local high-volume nodes)
        hvn_mask = vol >= HVN_FRAC * poc_vol
        # SHORT setup: swept the range HIGH into the void, closed back inside
        if h[i] > rng_hi and c[i] < rng_hi:
            sel = (centers < poc) & hvn_mask
            if sel.any():
                tgt = centers[sel].min() if target_mode == "far" \
                    else centers[sel][np.argmax(vol[sel])]
            else:
                tgt = rng_lo
            armed = ("SHORT", h[i], poc, tgt, i + ARM_WIN)
        # LONG setup: swept the range LOW into the void, closed back inside
        elif l[i] < rng_lo and c[i] > rng_lo:
            sel = (centers > poc) & hvn_mask
            if sel.any():
                tgt = centers[sel].max() if target_mode == "far" \
                    else centers[sel][np.argmax(vol[sel])]
            else:
                tgt = rng_hi
            armed = ("LONG", l[i], poc, tgt, i + ARM_WIN)

    return trades


YEARS = [("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    print("VOLUME PROFILE REJECTION -- 15m BTC, causal profile, POC re-cross entry\n")
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
