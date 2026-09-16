"""
NY-session GAP-FADE (gap fill) -- 5m BTC.

Under a New York regular-session day (09:30-16:00 ET), BTC gaps at the open
(mean ~1.3%) because the overnight move is excluded. Classic play: fade the gap,
betting price returns to the prior session's close (fills the gap).

  gap UP   (open > prior close): SHORT at open, target = prior close, stop above
  gap DOWN (open < prior close): LONG  at open, target = prior close, stop below

No fill illusion: entry is a MARKET order at the session open (taker). Target is
a limit (maker); stop is a market (taker). Exit at target/stop/session-close.

Also reports the BASE RATE: how often the gap fills during the session -- the
number that decides if there is anything here.

Run:  python3 ny_session_gap.py
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
MAKER, TAKER = 0.0002, 0.0004
SLIP = 0.0003


def ny_sessions(fname, start=None, end=None):
    df = load_ohlcv(fname, start, end)
    df = df.copy()
    df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")
    t = df.index.time
    rth = (t >= dt.time(9, 30)) & (t < dt.time(16, 0))
    ses = df[rth].copy()
    ses["d"] = ses.index.date
    return ses


def run(fname, gap_min=0.005, stop_pct=0.006, start=None, end=None,
        mode="fade", r_mult=1.5):
    ses = ny_sessions(fname, start, end)
    daily = ses.groupby("d").agg(o=("open", "first"), h=("high", "max"),
                                 l=("low", "min"), c=("close", "last"))
    prevC = daily["c"].shift(1)

    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    capital = STARTING_CAPITAL
    trades = []
    gap_fills = []   # base rate: did the gap fill this session?

    for d, g in ses.groupby("d"):
        if d not in prevC.index or np.isnan(prevC[d]):
            continue
        pc = prevC[d]
        o = g["open"].values; h = g["high"].values; l = g["low"].values; c = g["close"].values
        open_px = o[0]
        gap = (open_px - pc) / pc
        if abs(gap) < gap_min:
            continue

        # base rate: does price touch prior close during the session?
        filled = (l.min() <= pc <= h.max())
        gap_fills.append(filled)

        gap_size = abs(open_px - pc)
        if mode == "fade":               # bet the gap fills (back to prior close)
            if gap > 0:
                direction = "SHORT"; entry = open_px; tgt = pc; stop = open_px * (1 + stop_pct)
            else:
                direction = "LONG"; entry = open_px; tgt = pc; stop = open_px * (1 - stop_pct)
        else:                            # momentum: go WITH the gap (stop = prior close)
            if gap > 0:
                direction = "LONG"; entry = open_px; stop = pc; tgt = open_px + r_mult * gap_size
            else:
                direction = "SHORT"; entry = open_px; stop = pc; tgt = open_px - r_mult * gap_size

        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            continue

        exit_px = exit_r = None
        for j in range(1, len(g)):
            if direction == "SHORT":
                if h[j] >= stop:
                    exit_px, exit_r = stop, "STOP"; break
                if l[j] <= tgt:
                    exit_px, exit_r = tgt, "TARGET"; break
            else:
                if l[j] <= stop:
                    exit_px, exit_r = stop, "STOP"; break
                if h[j] >= tgt:
                    exit_px, exit_r = tgt, "TARGET"; break
        if exit_px is None:
            exit_px, exit_r = c[-1], "EOD"

        if exit_r in ("STOP", "EOD"):
            exit_px *= (1 + SLIP) if direction == "SHORT" else (1 - SLIP)
        gross = (qty * (entry - exit_px) if direction == "SHORT"
                 else qty * (exit_px - entry))
        fee = qty * entry * TAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
        net = gross - fee
        capital = max(capital + net, 0.0)
        trades.append({"dir": direction, "time": g.index[0], "entry": entry,
                       "stop": stop, "target": tgt, "qty": qty, "notional": notional,
                       "pnl": net, "exit_r": exit_r, "gap": gap * 100})
        if capital <= 0:
            break
    fill_rate = np.mean(gap_fills) * 100 if gap_fills else 0
    return trades, fill_rate


YEARS = [("2023", "BTCUSDT_5m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_5m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_5m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_5m_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=0.005, help="min gap to trade")
    ap.add_argument("--stop", type=float, default=0.006, help="stop % from open")
    args = ap.parse_args()
    print(f"NY-SESSION GAP-FADE -- fade gaps >= {args.gap*100:.1f}%, stop {args.stop*100:.1f}%, "
          f"target = prior close, real fees\n")
    pooled = []
    for label, f, s, e in YEARS:
        tr, fr = run(f, gap_min=args.gap, stop_pct=args.stop, start=s, end=e)
        pooled += tr
        st = summarize_trades(tr, STARTING_CAPITAL, label=label)
        print(f"  {label}: trades={st.n:<4} gap-fill base rate={fr:4.0f}%  "
              f"win={st.win_rate:4.1f}%  ret={st.ret_pct:+7.1f}%  expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
    ps = summarize_trades(pooled, STARTING_CAPITAL)
    print(f"\n  POOLED: trades={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
          f"expR={ps.expectancy_r:+.3f}  Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%")
