"""
Volatility squeeze -> volume-confirmed breakout  (1H).

The one idea in this project where DIRECTION and TIMING come from independent
signals (volume study: volume forecasts move size, not direction):

  1. SQUEEZE   : the last L-bar high/low "box" is the narrowest range in W bars
                 (price is coiling, volatility contracted).
  2. BREAKOUT  : a bar CLOSES outside the box -> that gives the DIRECTION.
  3. VOLUME    : the breakout bar's volume must be elevated (>= vol_th x its
                 trailing median) -> confirms the expansion is real.
  4. RISK      : stop at the opposite side of the box; target = R_mult x risk.

Causal: the box and the volume baseline use only past/closed bars. Scored with
trade_stats. Run:  python3 volume_breakout_backtest.py
"""
import _paths  # noqa: F401
import argparse
import itertools

import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades

STARTING_CAPITAL = 1000.0
COMMISSION_PCT = 0.0004


def run(fname, L=24, W=120, vol_th=1.5, R_mult=2.0, buffer_pct=0.0005,
        max_hold=120, start=None, end=None, slippage_pct=0.0005,
        exit_mode="fixed", trail_mult=1.5):
    """exit_mode: 'fixed' = target at R_mult x risk; 'trail' = no fixed target,
    trail a stop trail_mult x risk behind the best price (lets winners run --
    how breakout edges actually pay, via a fat right tail)."""
    df = load_ohlcv(fname, start, end)
    o, h, l, c, v = (df[x].values for x in ["open", "high", "low", "close", "volume"])
    t = df.index
    n = len(c)

    # trailing box (exclude current bar -> shift by 1), causal
    box_hi = pd.Series(h).rolling(L).max().shift(1).values
    box_lo = pd.Series(l).rolling(L).min().shift(1).values
    box_rng = box_hi - box_lo
    # squeeze: current box range is the narrowest in the last W bars
    min_rng_W = pd.Series(box_rng).rolling(W).min().shift(1).values
    # relative volume vs trailing median (past-only)
    vmed = pd.Series(v).rolling(50).median().shift(1).values
    relv = v / vmed

    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    capital = STARTING_CAPITAL
    trades = []
    busy_until = -1

    start_i = max(L + W, 51)
    for i in range(start_i, n):
        if i <= busy_until or np.isnan(box_rng[i]) or np.isnan(min_rng_W[i]):
            continue
        # must be in a squeeze: this box is ~the tightest in W bars
        if box_rng[i] > min_rng_W[i] * 1.05:
            continue
        if np.isnan(relv[i]) or relv[i] < vol_th:
            continue

        bh, bl = box_hi[i], box_lo[i]
        up_break = c[i] > bh * (1 + buffer_pct)
        dn_break = c[i] < bl * (1 - buffer_pct)
        if not (up_break or dn_break):
            continue
        trade_dir = "LONG" if up_break else "SHORT"

        entry = c[i]
        stop = bl if trade_dir == "LONG" else bh
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        target = entry + R_mult * risk if trade_dir == "LONG" else entry - R_mult * risk

        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            continue

        end_i = min(i + max_hold, n)
        exit_price = exit_reason = exit_i = None
        trail = stop                      # trailing stop (starts at initial stop)
        for j in range(i + 1, end_i):
            if trade_dir == "LONG":
                if l[j] <= trail:
                    exit_price, exit_reason, exit_i = trail, "STOP", j; break
                if exit_mode == "fixed" and h[j] >= target:
                    exit_price, exit_reason, exit_i = target, "TARGET", j; break
                if exit_mode == "trail":  # ratchet stop up behind the high
                    trail = max(trail, h[j] - trail_mult * risk)
            else:
                if h[j] >= trail:
                    exit_price, exit_reason, exit_i = trail, "STOP", j; break
                if exit_mode == "fixed" and l[j] <= target:
                    exit_price, exit_reason, exit_i = target, "TARGET", j; break
                if exit_mode == "trail":
                    trail = min(trail, l[j] + trail_mult * risk)
        if exit_price is None:
            exit_i = end_i - 1
            exit_price, exit_reason = c[exit_i], "TIME"

        if exit_reason == "STOP" and slippage_pct:
            exit_price *= (1 - slippage_pct) if trade_dir == "LONG" else (1 + slippage_pct)

        gross = (qty * (exit_price - entry) if trade_dir == "LONG"
                 else qty * (entry - exit_price))
        comm = qty * entry * COMMISSION_PCT + qty * exit_price * COMMISSION_PCT
        net = gross - comm
        capital = max(capital + net, 0.0)

        trades.append({
            "dir": trade_dir, "time": t[i], "exit_time": t[exit_i],
            "entry": entry, "stop": stop, "target": target,
            "qty": qty, "notional": notional, "pnl": net, "bal": capital,
            "exit_r": exit_reason,
        })
        busy_until = exit_i
        if capital <= 0:
            break
    return trades, capital


YEARS = [("2023", "BTCUSDT_1h_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_1h_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_1h_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_1h_Jan_to_Jul2026.csv", None, None)]


def evaluate(**kw):
    per_year, pooled = {}, []
    for y, f, s, e in YEARS:
        tr, _ = run(f, start=s, end=e, **kw)
        st = summarize_trades(tr, STARTING_CAPITAL, label=y)
        per_year[y] = (st.ret_pct, st.expectancy_r, st.n)
        pooled += tr
    ps = summarize_trades(pooled, STARTING_CAPITAL, label="pooled")
    pos = sum(1 for (r, _, nn) in per_year.values() if r > 0 and nn >= 5)
    return per_year, pos, ps


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="grid-search the knobs")
    ap.add_argument("--L", type=int, default=24)
    ap.add_argument("--W", type=int, default=120)
    ap.add_argument("--vol", type=float, default=1.5)
    ap.add_argument("--R", type=float, default=2.0)
    args = ap.parse_args()

    if not args.sweep:
        print("VOLATILITY SQUEEZE -> VOLUME BREAKOUT (1H)")
        print(f"box L={args.L}  squeeze window W={args.W}  vol>= {args.vol}x  "
              f"target {args.R}R  risk 1%  0.05% slippage\n")
        pooled = []
        for y, f, s, e in YEARS:
            tr, _ = run(f, L=args.L, W=args.W, vol_th=args.vol, R_mult=args.R, start=s, end=e)
            pooled += tr
            print(summarize_trades(tr, STARTING_CAPITAL, label=y).report()); print()
        print(summarize_trades(pooled, STARTING_CAPITAL, label="ALL YEARS POOLED").report())
    else:
        print("SWEEP -- ranked by positive years, then pooled expectancy\n")
        hdr = f"{'L':>4}{'W':>5}{'vol':>5}{'R':>5}{'+yrs':>5}{'23':>7}{'24':>7}{'25':>7}{'26':>7}{'poolR':>8}{'edge':>6}{'n':>5}"
        print(hdr); print("-" * len(hdr))
        rows = []
        for L, W, vol, R in itertools.product([12, 24, 48], [120, 240], [1.3, 1.7, 2.5], [1.5, 2.0, 3.0]):
            py, pos, ps = evaluate(L=L, W=W, vol_th=vol, R_mult=R)
            rows.append((pos, ps.expectancy_r, L, W, vol, R, py, ps))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        for pos, pr, L, W, vol, R, py, ps in rows[:15]:
            def rp(y): return f"{py[y][0]:+.0f}%"
            print(f"{L:>4}{W:>5}{vol:>5}{R:>5}{pos:>5}"
                  f"{rp('2023'):>7}{rp('2024'):>7}{rp('2025'):>7}{rp('2026'):>7}"
                  f"{pr:>+8.3f}{ps.edge_confidence:>5.0f}%{ps.pooled_n if hasattr(ps,'pooled_n') else ps.n:>5}")
