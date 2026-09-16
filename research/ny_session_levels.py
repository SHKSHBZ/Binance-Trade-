"""
NY-session prior-day LEVELS fade -- gaps IGNORED (user's revised rules).

Day = New York regular session (09:30-16:00 ET). No gap logic. Use the session
open + opening range purely as the stop reference.

  SHORT: highs safe (session high < prior-session High) -> short when price tags
         the prior-session CLOSE from below; stop = opening-range HIGH.
  LONG : prior-session Low intact -> long when price tags the prior-session LOW
         from above; stop = opening-range LOW.

Targets: A = opposite prior level, B = fixed R, C = range midpoint.
Honest fill (price must REACH the level). Honest fees (limit=maker, market=taker
+slippage). Skip a setup if the opening-range stop is on the wrong side.

Run:  python3 ny_session_levels.py
"""
import _paths  # noqa: F401
import argparse
import datetime as dt
import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades

STARTING_CAPITAL = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
OR_BARS = 6           # first 30 min (6 x 5m)


def sessions(fname, start=None, end=None):
    df = load_ohlcv(fname, start, end).copy()
    df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")
    t = df.index.time
    df = df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))].copy()
    df["d"] = df.index.date
    return df


def run(fname, target="B", r_mult=2.0, start=None, end=None):
    ses = sessions(fname, start, end)
    daily = ses.groupby("d").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    PH, PL, PC = daily["h"].shift(1), daily["l"].shift(1), daily["c"].shift(1)
    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    capital = STARTING_CAPITAL
    trades = []

    for d, g in ses.groupby("d"):
        if d not in PH.index or np.isnan(PH[d]):
            continue
        ph, pl, pc = PH[d], PL[d], PC[d]
        h = g["high"].values; l = g["low"].values; c = g["close"].values
        n = len(g)
        if n < OR_BARS + 3:
            continue
        orh = h[:OR_BARS].max(); orl = l[:OR_BARS].min()
        mid = (ph + pl) / 2.0

        run_hi = h[:OR_BARS].max(); run_lo = l[:OR_BARS].min()
        short_armed = long_armed = False
        i = OR_BARS; busy = -1
        while i < n:
            run_hi = max(run_hi, h[i]); run_lo = min(run_lo, l[i])
            if h[i] < pc:
                short_armed = True
            if l[i] > pl:
                long_armed = True
            if i <= busy:
                i += 1; continue

            direction = entry = stop = tgt = None
            # SHORT: tag prior close from below, highs still safe, stop = OR high
            if short_armed and h[i] >= pc and run_hi < ph:
                entry = pc; stop = orh; short_armed = False
                if stop > entry:
                    tgt = pl if target == "A" else (entry - r_mult * (stop - entry)
                                                    if target == "B" else mid)
                    if tgt < entry:
                        direction = "SHORT"
            # LONG: tag prior low from above, stop = OR low
            elif long_armed and l[i] <= pl:
                entry = pl; stop = orl; long_armed = False
                if stop < entry:
                    tgt = ph if target == "A" else (entry + r_mult * (entry - stop)
                                                    if target == "B" else mid)
                    if tgt > entry:
                        direction = "LONG"

            if direction is None:
                i += 1; continue

            qty, notional = position_size(capital, entry, stop, params)
            if qty <= 0:
                i += 1; continue
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
            if exit_r in ("STOP", "EOD"):
                exit_px *= (1 + SLIP) if direction == "SHORT" else (1 - SLIP)
            gross = (qty * (entry - exit_px) if direction == "SHORT"
                     else qty * (exit_px - entry))
            fee = qty * entry * MAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
            capital = max(capital + gross - fee, 0.0)
            trades.append({"dir": direction, "time": g.index[i], "entry": entry,
                           "stop": stop, "target": tgt, "qty": qty, "notional": notional,
                           "pnl": gross - fee, "exit_r": exit_r})
            busy = exit_i; i = exit_i + 1
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
    ap = argparse.ArgumentParser(); ap.add_argument("--r", type=float, default=2.0)
    args = ap.parse_args()
    print("NY-SESSION PRIOR-DAY LEVELS FADE -- gaps ignored, OR stop, honest fills/fees\n")
    for tg in ["A", "B", "C"]:
        print(f"===== TARGET {tg} =====")
        pooled = []
        for label, f, s, e in YEARS:
            tr = run(f, target=tg, r_mult=args.r, start=s, end=e)
            pooled += tr
            st = summarize_trades(tr, STARTING_CAPITAL, label=label)
            print(f"  {label}: n={st.n:<4} win={st.win_rate:4.1f}%  ret={st.ret_pct:+7.1f}%  "
                  f"expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
        ps = summarize_trades(pooled, STARTING_CAPITAL)
        print(f"  POOLED: n={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
              f"expR={ps.expectancy_r:+.3f}  Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%\n")
