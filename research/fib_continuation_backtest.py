"""
Fibonacci GOLDEN-POCKET CONTINUATION backtest -- the video method.

Faithful to the 5 steps:
  1. Fib on a clean HTF (1H) swing leg (confirmed pivots, causal).
  2. Swings marked on 1H only (never 1m/5m).
  3. Only trade the GOLDEN POCKET: price must pull back into 0.5-0.618.
     Shallow (0.382) setups never trigger; too-deep (>0.786) ones invalidate.
  4. Drop to 15M for CONFIRMATION -- no blind limit at the line. Enter only
     after a 15M rejection candle in the pocket (trend-resumption signal).
  5. Risk below the pocket; targets are the prior extreme and high-RR extensions.

This is a CONTINUATION trade (bet the HTF trend resumes), the opposite of the
fade. Up-leg -> pull back into pocket -> go LONG toward new highs.

Scored with trade_stats (expectancy-R, Sharpe, Kelly, Monte-Carlo).
Run:  python3 fib_continuation_backtest.py
"""
import _paths  # noqa: F401
import argparse

import numpy as np

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades
from fib_level_study import confirmed_pivots, daily_uptrend_flags

STARTING_CAPITAL = 1000.0
COMMISSION_PCT = 0.0004
PIVOT_HALF = 12
MIN_LEG_PCT = 2.0
MAX_HOLD_15M = 960

# fib fractions of the leg, measured from the extreme (0.0) back toward origin (1.0)
GP_NEAR = 0.5      # golden-pocket near edge
GP_FAR = 0.618     # golden-pocket far edge
STOP_LEVELS = {"0.786": 0.786, "1.0": 1.0}
# targets as frac-from-extreme: 0.0 = prior extreme; extensions beyond the
# extreme are NEGATIVE fracs (1.272 ext = 0.272 of the leg past the extreme).
TARGET_LEVELS = {"0.0": 0.0, "ext1.272": -0.272, "ext1.618": -0.618}


def price_at(extreme, move, frac):
    """frac measured from the extreme (0.0) toward origin; >1 overshoots origin,
    <0 extends beyond the extreme (a projection target)."""
    return extreme - frac * move


def run(h1_file, m15_file, stop_key="0.786", target_key="ext1.272",
        trend_filter=True, confirm=True, start=None, end=None, slippage_pct=0.0):
    df1 = load_ohlcv(h1_file, start, end)
    h1, l1 = df1["high"].values, df1["low"].values
    t1 = df1.index
    up_daily = daily_uptrend_flags(df1, 20)

    df15 = load_ohlcv(m15_file)
    o15, h15 = df15["open"].values, df15["high"].values
    l15, c15 = df15["low"].values, df15["close"].values
    t15 = df15.index

    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    pivots = confirmed_pivots(h1, l1, PIVOT_HALF)

    capital = STARTING_CAPITAL
    trades = []
    busy_until = -1

    for a, b in zip(pivots, pivots[1:]):
        if a[3] == b[3]:
            continue
        leg_up = (a[3] == "L" and b[3] == "H")
        origin, extreme = a[2], b[2]
        move = extreme - origin
        if move == 0 or abs(move) / origin * 100.0 < MIN_LEG_PCT:
            continue
        confirm_time = t1[b[0]]

        # continuation trades WITH the leg: up-leg -> LONG, down-leg -> SHORT
        trade_dir = "LONG" if leg_up else "SHORT"
        if trend_filter:
            daily_up = bool(up_daily[b[0]])
            if (trade_dir == "LONG") != daily_up:   # must align with daily trend
                continue

        gp_near = price_at(extreme, move, GP_NEAR)       # 0.5 line
        gp_far = price_at(extreme, move, GP_FAR)         # 0.618 line (deeper)
        stop = price_at(extreme, move, STOP_LEVELS[stop_key])
        target = price_at(extreme, move, TARGET_LEVELS[target_key])
        # pocket price bounds (near/far differ by direction)
        lo_pocket, hi_pocket = min(gp_near, gp_far), max(gp_near, gp_far)

        i0 = t15.searchsorted(confirm_time)
        if i0 <= busy_until or i0 >= len(t15):
            continue
        end_i = min(i0 + MAX_HOLD_15M, len(t15))

        # --- entry: price enters the golden pocket, then a 15M rejection ---
        fill_i = entry_price = None
        in_pocket = False
        for j in range(i0, end_i):
            touched_pocket = (l15[j] <= hi_pocket) and (h15[j] >= lo_pocket)
            if touched_pocket:
                in_pocket = True
            if in_pocket:
                if not confirm:
                    # enter at the pocket edge we care about (near edge = 0.5)
                    fill_i, entry_price = j, gp_near
                    break
                # rejection candle: closed back in the trend direction
                rej = (c15[j] > o15[j]) if trade_dir == "LONG" else (c15[j] < o15[j])
                if touched_pocket and rej:
                    fill_i, entry_price = j, c15[j]
                    break
            # invalidation before entry: stop or target reached first
            if trade_dir == "LONG" and (l15[j] <= stop or h15[j] >= target):
                break
            if trade_dir == "SHORT" and (h15[j] >= stop or l15[j] <= target):
                break
        if fill_i is None:
            continue

        # guard: entry must sit on the correct side of stop & target
        if trade_dir == "LONG" and not (stop < entry_price < target):
            continue
        if trade_dir == "SHORT" and not (target < entry_price < stop):
            continue

        qty, notional = position_size(capital, entry_price, stop, params)
        if qty <= 0:
            continue

        exit_price = exit_reason = exit_i = None
        for j in range(fill_i + 1, end_i):
            if trade_dir == "LONG":
                if l15[j] <= stop:
                    exit_price, exit_reason, exit_i = stop, "STOP", j; break
                if h15[j] >= target:
                    exit_price, exit_reason, exit_i = target, "TARGET", j; break
            else:
                if h15[j] >= stop:
                    exit_price, exit_reason, exit_i = stop, "STOP", j; break
                if l15[j] <= target:
                    exit_price, exit_reason, exit_i = target, "TARGET", j; break
        if exit_price is None:
            exit_i = end_i - 1
            exit_price, exit_reason = c15[exit_i], "TIME"

        if exit_reason == "STOP" and slippage_pct:
            exit_price *= (1 - slippage_pct) if trade_dir == "LONG" else (1 + slippage_pct)

        gross = (qty * (exit_price - entry_price) if trade_dir == "LONG"
                 else qty * (entry_price - exit_price))
        comm = qty * entry_price * COMMISSION_PCT + qty * exit_price * COMMISSION_PCT
        net = gross - comm
        capital = max(capital + net, 0.0)

        trades.append({
            "dir": trade_dir, "time": t15[fill_i], "exit_time": t15[exit_i],
            "entry": entry_price, "stop": stop, "target": target,
            "qty": qty, "notional": notional, "pnl": net, "bal": capital,
            "exit_r": exit_reason,
        })
        busy_until = exit_i
        if capital <= 0:
            break

    return trades, capital


SCENARIOS = [("2023", "2023-01-01", "2023-12-31"),
             ("2024", "2024-01-01", "2024-12-31"),
             ("2025", "2025-01-01", "2025-12-31")]
H1_MAIN, M15_MAIN = "BTCUSDT_1h_2023_to_2025.csv", "BTCUSDT_15m_2023_to_2025.csv"
H1_26, M15_26 = "BTCUSDT_1h_Jan_to_Jul2026.csv", "BTCUSDT_15m_Jan_to_Jul2026.csv"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Fib golden-pocket continuation")
    ap.add_argument("--stop", default="0.786", choices=list(STOP_LEVELS))
    ap.add_argument("--target", default="ext1.272", choices=list(TARGET_LEVELS))
    ap.add_argument("--trend", default="on", choices=["on", "off"])
    ap.add_argument("--confirm", default="on", choices=["on", "off"])
    ap.add_argument("--slippage", type=float, default=0.0)
    args = ap.parse_args()
    tf, cf = args.trend == "on", args.confirm == "on"

    print("FIB GOLDEN-POCKET CONTINUATION -- 1H levels, 15M confirmation")
    print(f"pocket 0.5-0.618  stop {args.stop}  target {args.target}  "
          f"HTF-trend {args.trend}  confirm {args.confirm}  risk 1%\n")

    pooled = []
    for label, s, e in SCENARIOS:
        tr, _ = run(H1_MAIN, M15_MAIN, args.stop, args.target, tf, cf, s, e, args.slippage)
        pooled += tr
        print(summarize_trades(tr, STARTING_CAPITAL, label=label).report()); print()
    tr26, _ = run(H1_26, M15_26, args.stop, args.target, tf, cf, slippage_pct=args.slippage)
    pooled += tr26
    print(summarize_trades(tr26, STARTING_CAPITAL, label="2026 (Jan-Jul)").report()); print()
    if pooled:
        print(summarize_trades(pooled, STARTING_CAPITAL, label="ALL YEARS POOLED").report())
