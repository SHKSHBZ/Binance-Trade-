"""
Body/Wick prior-day fade -- the user's refined rule. 15m BTC.

Levels from the PRIOR day (UTC day):
  body_high = max(open, close)   body_low = min(open, close)
  high_wick = day high           low_wick = day low          open = day open

  SHORT: enter at prev body_high, stop = prev high_wick, target = prev open + 200
  LONG : enter at prev body_low,  stop = prev low_wick,  target = prev open - 200

"High not secure" = the stop (prev high wick) has not been broken. Honest fills
(limit fills only when price REACHES the level). Honest fees (limit=maker,
market stop=taker+slip). Hold until target/stop, else exit at end of horizon.

Run:  python3 body_wick_fade.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
TARGET_OFFSET = 200.0
HOLD_DAYS = 2          # give the trade up to 2 days to hit target/stop


def run(fname, start=None, end=None, offset=TARGET_OFFSET):
    df = load_ohlcv(fname, start, end)
    daily = df.resample("1D").agg(o=("open", "first"), h=("high", "max"),
                                  l=("low", "min"), c=("close", "last")).dropna()
    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    capital = CAP
    trades = []

    days = list(df.groupby(df.index.normalize()))
    idx_of = {d: k for k, (d, _) in enumerate(days)}

    for d, g in days:
        prev = d - pd.Timedelta(days=1)
        if prev not in daily.index:
            continue
        po, ph, pl, pc = daily.loc[prev, ["o", "h", "l", "c"]]
        body_hi, body_lo = max(po, pc), min(po, pc)
        # today's bars + up to HOLD_DAYS forward for management
        k = idx_of[d]
        seg = pd.concat([days[k + m][1] for m in range(HOLD_DAYS) if k + m < len(days)])
        h = seg["high"].values; l = seg["low"].values; c = seg["close"].values
        t = seg.index
        n = len(seg)
        if n < 3:
            continue

        for side in ("SHORT", "LONG"):
            if side == "SHORT":
                entry, stop, tgt = body_hi, ph, po + offset
                if not (tgt < entry < stop):
                    continue
            else:
                entry, stop, tgt = body_lo, pl, po - offset
                if not (stop < entry < tgt):
                    continue

            # arm below/above the level, fill on honest touch, stop must be intact
            armed = False; fill = None
            for i in range(n):
                if side == "SHORT":
                    if h[i] < entry:
                        armed = True
                    if armed and h[i] >= entry and h[i] < stop:
                        fill = i; break
                    if h[i] >= stop:      # high broke before entry -> void
                        break
                else:
                    if l[i] > entry:
                        armed = True
                    if armed and l[i] <= entry and l[i] > stop:
                        fill = i; break
                    if l[i] <= stop:
                        break
            if fill is None:
                continue

            qty, notional = position_size(capital, entry, stop, params)
            if qty <= 0:
                continue
            exit_px = exit_r = None
            for j in range(fill + 1, n):
                if side == "SHORT":
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
                exit_px, exit_r = c[-1], "TIME"
            if exit_r in ("STOP", "TIME"):
                exit_px *= (1 + SLIP) if side == "SHORT" else (1 - SLIP)
            gross = (qty * (entry - exit_px) if side == "SHORT" else qty * (exit_px - entry))
            fee = qty * entry * MAKER + qty * exit_px * (MAKER if exit_r == "TARGET" else TAKER)
            capital = max(capital + gross - fee, 0.0)
            trades.append({"dir": side, "time": t[fill], "entry": entry, "stop": stop,
                           "target": tgt, "qty": qty, "notional": notional,
                           "pnl": gross - fee, "exit_r": exit_r, "exit_px": exit_px})
            if capital <= 0:
                break
        if capital <= 0:
            break
    return trades


YEARS = [("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--offset", type=float, default=200.0)
    args = ap.parse_args()
    print(f"BODY/WICK PRIOR-DAY FADE -- 15m BTC, target = prev open +/- {args.offset:.0f}, "
          f"honest fills/fees\n")
    pooled = []
    for label, f, s, e in YEARS:
        tr = run(f, start=s, end=e, offset=args.offset)
        pooled += tr
        st = summarize_trades(tr, CAP, label=label)
        longs = [x for x in tr if x["dir"] == "LONG"]; shorts = [x for x in tr if x["dir"] == "SHORT"]
        print(f"  {label}: n={st.n:<4} (L{len(longs)}/S{len(shorts)})  win={st.win_rate:4.1f}%  "
              f"ret={st.ret_pct:+7.1f}%  expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
    ps = summarize_trades(pooled, CAP)
    print(f"\n  POOLED: n={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
          f"expR={ps.expectancy_r:+.3f}  Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%")
