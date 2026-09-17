"""
Inducement + FVG + Internal/External Liquidity (the trader's confluence setup).

Faithful mechanization:
  MACRO   : uptrend = HH + HL on MAJOR swings. Target = last major swing HIGH
            (external buy-side liquidity).
  FVG     : a bullish 3-candle gap left by an impulse: low[i] > high[i-2].
            zone = [gap_lo=high[i-2], gap_hi=low[i]].
  INDUCE  : after the FVG, a MINOR swing low prints ABOVE the FVG (gap_hi) --
            the trap that lures early longs.
  ENTRY   : price trades BELOW that minor low (sweeps internal sell-side),
            TAPS the FVG (low <= gap_hi), and REACTS OUT (closes back above
            gap_lo) -> long at that close.
  STOP    : below the FVG (gap_lo).
  TARGET  : the major swing high.

Causal: swings known PIVOT_HALF bars late; FVG known at formation; the
sweep/tap/react all read at bar close; stop/target on later bars. Honest fees
+ slippage. Scored with trade_stats and a random-direction null.
Run:  python3 inducement_fvg.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades
from structure_sweep import confirmed_pivots

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
MAJOR_HALF = 20        # macro swings (trend + target)
MINOR_HALF = 3         # inducement swing lows
STOP_BUF = 0.0010
FVG_MAXAGE = 200       # an FVG is tradable for this many bars after it forms
WAIT = 100             # bars to wait for the trigger after inducement prints
MIN_RR = 1.0


def run(fname, start=None, end=None, force_dir=None, seed=None,
        react_strong=False, fixed_rr=None):
    # react_strong: require the reaction bar to close ABOVE the FVG (gap_hi),
    #   not merely above gap_lo. fixed_rr: use entry + rr*risk as target
    #   instead of the far major swing high (None = keep major high).
    df = load_ohlcv(fname, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values
    c = df["close"].values; t = df.index; n = len(c)
    khM, klM = confirmed_pivots(h, l, MAJOR_HALF)
    khm, klm = confirmed_pivots(h, l, MINOR_HALF)
    rng = np.random.default_rng(seed)

    majH = []; majL = []          # confirmed major swing values
    fvgs = []                     # active bullish FVGs: dict(lo, hi, born)
    armed = []                    # armed setups
    capital = CAP; trades = []; busy = -1

    for i in range(MAJOR_HALF, n - 1):
        # update confirmed major swings
        if not np.isnan(khM[i]): majH.append((i, khM[i]))
        if not np.isnan(klM[i]): majL.append((i, klM[i]))
        # register a bullish FVG formed at i (gap between i-2 high and i low)
        if i >= 2 and l[i] > h[i - 2]:
            fvgs.append({"lo": h[i - 2], "hi": l[i], "born": i})
        # expire old / filled FVGs (close below gap_lo = mitigated)
        fvgs = [g for g in fvgs if i - g["born"] <= FVG_MAXAGE and c[i] >= g["lo"]]

        # trend from last two major highs & lows
        up = (len(majH) >= 2 and len(majL) >= 2 and
              majH[-1][1] > majH[-2][1] and majL[-1][1] > majL[-2][1])
        major_high = majH[-1][1] if majH else None

        # a NEW minor swing low just became known -> candidate inducement
        if not np.isnan(klm[i]) and up and major_high is not None:
            ind_low = klm[i]
            # find the most recent unfilled bullish FVG that sits BELOW the
            # inducement (gap_hi < inducement low) and formed before it
            cand = [g for g in fvgs if g["hi"] < ind_low and g["born"] <= i]
            if cand and major_high > ind_low:
                g = cand[-1]
                armed.append({"ind": ind_low, "lo": g["lo"], "hi": g["hi"],
                              "tgt": major_high, "exp": i + WAIT, "swept": False})

        # progress armed setups
        if i <= busy:
            armed = [a for a in armed if a["exp"] >= i]
            continue
        still = []
        fired = None
        for a in armed:
            if i > a["exp"]:
                continue
            if not a["swept"]:
                if l[i] < a["ind"]:            # swept internal sell-side
                    a["swept"] = True
            if a["swept"]:
                # tap the FVG and react out (close back above gap_lo, or the
                # stronger gap_hi if react_strong)
                react_lvl = a["hi"] if react_strong else a["lo"]
                if l[i] <= a["hi"] and c[i] > react_lvl:
                    fired = a; continue        # don't keep it
                if c[i] < a["lo"]:             # FVG failed
                    continue
            still.append(a)
        armed = still

        if fired is None:
            continue

        entry = c[i]; stop = fired["lo"] * (1 - STOP_BUF)
        tgt = entry + fixed_rr * (entry - stop) if fixed_rr else fired["tgt"]
        direction = "LONG"
        if force_dir == "random":
            direction = "LONG" if rng.random() < 0.5 else "SHORT"
            risk = abs(entry - stop)
            if direction == "LONG":
                stop = entry - risk; tgt = entry + abs(fired["tgt"] - entry)
            else:
                stop = entry + risk; tgt = entry - abs(fired["tgt"] - entry)
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
    print("INDUCEMENT + FVG + LIQUIDITY -- 15m BTC (long-only, macro uptrend)\n")
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
    # (random-direction null available via run(force_dir="random", seed=...);
    #  not run by default -- the pooled result is unambiguously negative.)
