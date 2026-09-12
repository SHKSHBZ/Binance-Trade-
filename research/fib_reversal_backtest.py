"""
Fibonacci REVERSAL (fade) backtest -- 1H structure, 15M execution.

Idea (from FIB_STUDY_FINDINGS.md): once a real 1H leg retraces to its 0.5
level, it more often FAILS (breaks the origin) than continues. So we fade it:

    up-leg   -> price pulls back DOWN to 0.5 -> go SHORT, target the origin (1.0)
    down-leg -> price pulls back UP   to 0.5 -> go LONG,  target the origin (1.0)

Multi-timeframe, as requested:
  * LEVELS are marked on 1H legs (confirmed swing pivots, causal).
  * ENTRY/STOP/TARGET are executed on 15M candles for precise fills.

Sizing and the scoreboard are shared with the rest of the repo:
  1% risk/trade, 10x leverage cap (smc_engine.position_size), and every result
  is graded by trade_stats.summarize_trades (expectancy-R, Sharpe, Kelly,
  Monte-Carlo "edge is real").

Run:  python3 fib_reversal_backtest.py
"""
import _paths  # noqa: F401
import argparse

import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades
from fib_level_study import confirmed_pivots, daily_uptrend_flags

STARTING_CAPITAL = 1000.0
COMMISSION_PCT = 0.0004
PIVOT_HALF = 12
MIN_LEG_PCT = 2.0
MAX_HOLD_15M = 960      # give up after ~10 days of 15M bars (240*4)


def run(h1_file, m15_file, stop_level=0.3, trend_filter="off",
        start=None, end=None, slippage_pct=0.0, entry_mode="touch"):
    """stop_level: 0.3 or 0.0 (where the fade is invalidated, as a fib level).
    trend_filter: 'off' | 'with' (only fade WITH the daily trend, i.e. short an
    up-leg only in a daily downtrend) | 'against'.
    entry_mode:
      'touch'  -> enter the instant price tags the 0.5 level (blind, baseline)
      'close'  -> wait for a 15M candle to CLOSE in the fade direction past 0.5
                  (confirmation the level is rejecting, not bouncing); enter at
                  that close (worse price, but confirmed).
      'retag'  -> wait for that same close confirmation, THEN for price to pull
                  back to 0.5 and enter there (confirmed AND good price, but
                  some confirmations never retag -> fewer trades)."""
    df1 = load_ohlcv(h1_file, start, end)
    h1, l1 = df1["high"].values, df1["low"].values
    t1 = df1.index
    up_daily = daily_uptrend_flags(df1, 20)

    df15 = load_ohlcv(m15_file)
    h15, l15, c15 = df15["high"].values, df15["low"].values, df15["close"].values
    t15 = df15.index

    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)
    pivots = confirmed_pivots(h1, l1, PIVOT_HALF)

    capital = STARTING_CAPITAL
    trades = []
    busy_until_15 = -1          # no overlapping trades

    for a, b in zip(pivots, pivots[1:]):
        if a[3] == b[3]:
            continue
        direction_leg = "UP" if (a[3] == "L" and b[3] == "H") else "DOWN"
        origin = a[2]                      # 1.0
        extreme = b[2]                     # 0.0
        move = extreme - origin
        if move == 0 or abs(move) / origin * 100.0 < MIN_LEG_PCT:
            continue
        confirm_time = t1[b[0]]            # we know the leg here (causal)

        lvl_05 = extreme - 0.5 * move
        lvl_stop = extreme if stop_level == 0.0 else extreme - 0.3 * move
        lvl_target = origin               # 1.0

        # trend filter: fading an UP-leg is a SHORT; "with trend" = daily down
        if trend_filter != "off":
            daily_up = bool(up_daily[b[0]])
            fade_is_short = (direction_leg == "UP")
            with_trend = (fade_is_short and not daily_up) or \
                         (not fade_is_short and daily_up)
            if trend_filter == "with" and not with_trend:
                continue
            if trend_filter == "against" and with_trend:
                continue

        # step to 15M execution from the 1H confirmation onward
        i0 = t15.searchsorted(confirm_time)
        if i0 <= busy_until_15 or i0 >= len(t15):
            continue
        end_i = min(i0 + MAX_HOLD_15M, len(t15))

        trade_dir = "SHORT" if direction_leg == "UP" else "LONG"

        # Entry: first tag the 0.5 zone, then (in 'close' mode) wait for a 15M
        # candle to CLOSE past 0.5 in the fade direction before entering.
        # Bail if the stop/target level is reached before we get an entry.
        fill_i = None
        entry_price = None
        tagged = False
        confirmed = False
        for j in range(i0, end_i):
            if l15[j] <= lvl_05 <= h15[j]:
                tagged = True
            if tagged and not confirmed:
                if entry_mode == "touch":
                    fill_i, entry_price = j, lvl_05; break
                conf = (c15[j] < lvl_05) if trade_dir == "SHORT" else (c15[j] > lvl_05)
                if conf:
                    if entry_mode == "close":
                        fill_i, entry_price = j, c15[j]; break
                    confirmed = True          # 'retag': now wait for pullback
            elif confirmed:
                # entry_mode == 'retag': enter when price comes back to 0.5
                if l15[j] <= lvl_05 <= h15[j]:
                    fill_i, entry_price = j, lvl_05; break
            # invalidated before we ever got an entry -> no trade
            if trade_dir == "SHORT" and (h15[j] >= lvl_stop or l15[j] <= lvl_target):
                break
            if trade_dir == "LONG" and (l15[j] <= lvl_stop or h15[j] >= lvl_target):
                break
        if fill_i is None:
            continue

        qty, notional = position_size(capital, entry_price, lvl_stop, params)
        if qty <= 0:
            continue

        # race stop vs target on 15M from the fill bar
        exit_price = exit_reason = None
        exit_i = None
        for j in range(fill_i + 1, end_i):
            if trade_dir == "SHORT":
                if h15[j] >= lvl_stop:
                    exit_price, exit_reason, exit_i = lvl_stop, "STOP", j; break
                if l15[j] <= lvl_target:
                    exit_price, exit_reason, exit_i = lvl_target, "TARGET", j; break
            else:
                if l15[j] <= lvl_stop:
                    exit_price, exit_reason, exit_i = lvl_stop, "STOP", j; break
                if h15[j] >= lvl_target:
                    exit_price, exit_reason, exit_i = lvl_target, "TARGET", j; break
        if exit_price is None:
            exit_i = end_i - 1
            exit_price, exit_reason = c15[exit_i], "TIME"

        # realistic stop slippage: stops fill a touch worse than the level
        if exit_reason == "STOP" and slippage_pct:
            exit_price *= (1 + slippage_pct) if trade_dir == "SHORT" \
                else (1 - slippage_pct)

        gross = (qty * (entry_price - exit_price) if trade_dir == "SHORT"
                 else qty * (exit_price - entry_price))
        comm = qty * entry_price * COMMISSION_PCT + qty * exit_price * COMMISSION_PCT
        net = gross - comm
        capital += net
        if capital <= 0:
            capital = 0.0

        trades.append({
            "dir": trade_dir, "time": t15[fill_i], "exit_time": t15[exit_i],
            "entry": entry_price, "stop": lvl_stop, "target": lvl_target,
            "qty": qty, "notional": notional, "pnl": net, "bal": capital,
            "exit_r": exit_reason,
        })
        busy_until_15 = exit_i
        if capital <= 0:
            break

    return trades, capital


SCENARIOS = [
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
]


def period_files(start):
    # 2026 lives in its own files; everything else in the 2023-2025 files
    return ("BTCUSDT_1h_2023_to_2025.csv", "BTCUSDT_15m_2023_to_2025.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Fib reversal backtest")
    ap.add_argument("--stop", type=float, default=0.3, choices=[0.0, 0.3],
                    help="fib level where the fade is invalidated (0.3 tight, 0.0 wide)")
    ap.add_argument("--trend", default="off", choices=["off", "with", "against"],
                    help="daily-trend filter on the fade direction")
    ap.add_argument("--slippage", type=float, default=0.0,
                    help="stop-fill slippage as a fraction, e.g. 0.0005 = 0.05%%")
    ap.add_argument("--entry", default="touch", choices=["touch", "close", "retag"],
                    help="'touch' = blind tag of 0.5; 'close' = wait for a 15M "
                         "close confirmation in the fade direction")
    args = ap.parse_args()

    print("FIB REVERSAL (fade) BACKTEST -- 1H levels, 15M execution")
    print(f"stop at fib {args.stop}   trend filter: {args.trend}   "
          f"entry: {args.entry}   risk 1%/trade, 10x cap\n")

    pooled = []
    for label, s, e in SCENARIOS:
        f1, f15 = period_files(s)
        trades, final = run(f1, f15, stop_level=args.stop, trend_filter=args.trend,
                            start=s, end=e, slippage_pct=args.slippage,
                            entry_mode=args.entry)
        pooled += trades
        print(summarize_trades(trades, STARTING_CAPITAL, label=label).report())
        print()

    # 2026 from its own files
    t26, _ = run("BTCUSDT_1h_Jan_to_Jul2026.csv", "BTCUSDT_15m_Jan_to_Jul2026.csv",
                 stop_level=args.stop, trend_filter=args.trend,
                 slippage_pct=args.slippage, entry_mode=args.entry)
    pooled += t26
    print(summarize_trades(t26, STARTING_CAPITAL, label="2026 (Jan-Jul)").report())
    print()

    if pooled:
        print(summarize_trades(pooled, STARTING_CAPITAL,
                               label="ALL YEARS POOLED").report())
