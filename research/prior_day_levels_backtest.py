"""
Prior-Day-Levels intraday fade -- 5m BTC.

Idea (the user's): on a day that opens NEAR yesterday's close (small gap), price
respects yesterday's range, so fade the extremes back inward.

  SHORT: small gap AND yesterday's High (PDH) not broken -> short when price tags
         yesterday's Close (PDC); stop = opening-range high; exit if broken.
  LONG : small gap AND yesterday's Low (PDL) intact -> long when price tags PDL;
         stop = opening-range low.

Targets tested (switch):
  A = opposite prior-day level (short->PDL, long->PDH)
  B = fixed R multiple of the stop distance
  C = prior-day range midpoint (PDH+PDL)/2

Causal: prior-day levels are known at today's open; the opening range is known
after the first OR_MIN minutes; entries only after that. Re-entry allowed same
day if a level is tagged again. Scored with trade_stats.

Run:  python3 prior_day_levels_backtest.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades

STARTING_CAPITAL = 1000.0
MAKER_FEE = 0.0002      # limit-order fill (entry at level, target) -- Binance maker
TAKER_FEE = 0.0004      # market exit (stop, end-of-day)
GAP_THRESH = 0.003      # skip days that open >0.3% from yesterday's close
NEAR = 0.0010           # "tag" a level if within 0.10%
OR_MIN = 30             # opening range = first 30 minutes
STOP_MIN_PCT = 0.0015   # floor so stops aren't microscopic (avoids hair-triggers)
BAR_MIN = 5


def run(fname, target="A", r_mult=2.0, start=None, end=None, slippage=0.0005, stop_buf=0.003):
    df = load_ohlcv(fname, start, end)
    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)

    daily = df.resample("1D").agg(o=("open", "first"), h=("high", "max"),
                                  l=("low", "min"), c=("close", "last")).dropna()
    PDH = daily["h"].shift(1); PDL = daily["l"].shift(1); PDC = daily["c"].shift(1)

    or_bars = OR_MIN // BAR_MIN
    capital = STARTING_CAPITAL
    trades = []

    for day, g in df.groupby(df.index.normalize()):
        if day not in PDH.index or np.isnan(PDH[day]):
            continue
        pdh, pdl, pdc = PDH[day], PDL[day], PDC[day]
        o = g["open"].values; h = g["high"].values; l = g["low"].values; c = g["close"].values
        n = len(g)
        if n < or_bars + 5:
            continue
        open_px = o[0]
        if abs(open_px - pdc) / pdc > GAP_THRESH:      # gap filter
            continue
        mid = (pdh + pdl) / 2.0
        STOP_BUF = stop_buf

        # fade the prior-day EXTREMES: short at PDH (resistance), long at PDL
        # (support). One entry per FRESH touch: a level is "armed" only while
        # price is away from it, and disarms after an entry until price leaves.
        short_armed = False; long_armed = False
        i = or_bars
        busy_until = -1
        while i < n:
            # arming: price must be clearly away from the level to re-arm it
            if h[i] < pdh * (1 - 2 * NEAR):
                short_armed = True
            if l[i] > pdl * (1 + 2 * NEAR):
                long_armed = True
            if i <= busy_until:
                i += 1; continue

            # limit fills only when price actually REACHES the level (honest fill)
            short_ok = short_armed and (h[i] >= pdh)
            long_ok = long_armed and (l[i] <= pdl)

            entry = stop = tgt = None
            direction = None
            if short_ok:
                direction = "SHORT"; short_armed = False
                entry = pdh; stop = pdh * (1 + STOP_BUF)
                if target == "A":
                    tgt = pdl
                elif target == "B":
                    tgt = entry - r_mult * (stop - entry)
                else:
                    tgt = mid
                if not (tgt < entry < stop):
                    direction = None
            elif long_ok:
                direction = "LONG"; long_armed = False
                entry = pdl; stop = pdl * (1 - STOP_BUF)
                if target == "A":
                    tgt = pdh
                elif target == "B":
                    tgt = entry + r_mult * (entry - stop)
                else:
                    tgt = mid
                if not (stop < entry < tgt):
                    direction = None

            if direction is None:
                i += 1; continue

            qty, notional = position_size(capital, entry, stop, params)
            if qty <= 0:
                i += 1; continue

            # walk forward to stop/target/day-end
            exit_px = exit_r = None; exit_i = None
            for j in range(i, n):
                if direction == "SHORT":
                    if h[j] >= stop:
                        exit_px, exit_r, exit_i = stop, "STOP", j; break
                    if l[j] <= tgt:
                        exit_px, exit_r, exit_i = tgt, "TARGET", j; break
                else:
                    if l[j] <= stop:
                        exit_px, exit_r, exit_i = stop, "STOP", j; break
                    if h[j] >= tgt:
                        exit_px, exit_r, exit_i = tgt, "TARGET", j; break
            if exit_px is None:
                exit_i = n - 1; exit_px, exit_r = c[-1], "EOD"

            # stops/EOD are MARKET exits (taker + slippage); targets are LIMIT (maker)
            if exit_r in ("STOP", "EOD") and slippage:
                exit_px *= (1 + slippage) if direction == "SHORT" else (1 - slippage)

            gross = (qty * (entry - exit_px) if direction == "SHORT"
                     else qty * (exit_px - entry))
            entry_fee = qty * entry * MAKER_FEE          # limit at the level = maker
            exit_fee = qty * exit_px * (MAKER_FEE if exit_r == "TARGET" else TAKER_FEE)
            net = gross - entry_fee - exit_fee
            capital = max(capital + net, 0.0)
            trades.append({"dir": direction, "time": g.index[i], "entry": entry,
                           "stop": stop, "target": tgt, "qty": qty,
                           "notional": notional, "pnl": net, "exit_r": exit_r})
            busy_until = exit_i
            i = exit_i + 1
            if capital <= 0:
                break
        if capital <= 0:
            break
    return trades


YEARS = [("2023", "BTCUSDT_5m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_5m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_5m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_5m_Jan_to_Jul2026.csv", None, None)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="all", choices=["A", "B", "C", "all"])
    ap.add_argument("--r", type=float, default=2.0)
    args = ap.parse_args()
    names = {"A": "opposite level", "B": f"fixed {args.r}R", "C": "range midpoint"}
    targets = ["A", "B", "C"] if args.target == "all" else [args.target]

    print("PRIOR-DAY-LEVELS FADE -- 5m BTC, small-gap days, 1% risk, 0.05% slip\n")
    for tg in targets:
        print(f"===== TARGET {tg} ({names[tg]}) =====")
        pooled = []
        for label, f, s, e in YEARS:
            tr = run(f, target=tg, r_mult=args.r, start=s, end=e)
            pooled += tr
            st = summarize_trades(tr, STARTING_CAPITAL, label=label)
            print(f"  {label}: trades={st.n:<4} win={st.win_rate:4.1f}%  "
                  f"ret={st.ret_pct:+7.1f}%  expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
        ps = summarize_trades(pooled, STARTING_CAPITAL, label="pooled")
        pos = "?"
        print(f"  POOLED: trades={ps.n:<4} win={ps.win_rate:4.1f}%  "
              f"ret={ps.ret_pct:+7.1f}%  expR={ps.expectancy_r:+.3f}  "
              f"Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%\n")
