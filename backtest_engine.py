"""
Backtest driven by smc_engine.SMCEngine -- the same code the live bot runs.

If this reproduces the validated Variant C numbers (2025: +105.4%, 79 trades;
2026: +66.3%, 30 trades) then the engine is faithful, and anything the live
bot does is something this backtest also does.

Execution assumptions are stated rather than hidden:
  * a resting limit fills if the candle's range touches its price
  * stop and target are exchange-side; whichever the candle reaches first wins
  * commission both sides; optional stop slippage and perpetual funding
"""

import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCEngine, SMCParams, position_size

STARTING_CAPITAL = 1000.0
COMMISSION_PCT = 0.0004
STOP_SLIPPAGE_PCT = 0.0      # set 0.001 to price in realistic stop slippage
FUNDING_PER_8H = 0.0         # set 0.0001 for typical perpetual funding
FORWARD_BARS = 800


def run(data_file, start=None, end=None, params: SMCParams = SMCParams(),
        stop_slippage=STOP_SLIPPAGE_PCT, funding_per_8h=FUNDING_PER_8H):
    df = load_ohlcv(data_file, start, end)
    eng = SMCEngine(params)
    eng.prepare(df)

    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    times = df.index
    n = len(c)

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0.0
    trades = []

    armed = None
    armed_bar = -1
    in_position_until = -1

    current_day = None
    day_start_balance = capital
    day_halted = False

    for bar in range(eng.start_bar(), n):
        day = times[bar].normalize()
        if day != current_day:
            current_day = day
            day_start_balance = capital
            day_halted = False
        elif not day_halted and capital <= day_start_balance * (1 - params.daily_loss_limit_pct):
            day_halted = True

        blocked = (armed is not None) or (bar <= in_position_until)
        setup = eng.step(bar, blocked)
        if setup is not None:
            armed, armed_bar = setup, bar

        if armed is None or bar <= in_position_until:
            continue

        if bar - armed_bar > params.retest_window_bars:
            armed, armed_bar = None, -1
            eng.clear_armed()
            continue

        touched = ((armed.direction == "LONG" and l[bar] <= armed.limit_price) or
                   (armed.direction == "SHORT" and h[bar] >= armed.limit_price))
        if not touched:
            continue

        if day_halted:
            armed, armed_bar = None, -1
            eng.clear_armed()
            continue

        entry = armed.limit_price
        stop = armed.stop_price
        direction = armed.direction
        stop_dist = abs(entry - stop)
        target, rr = eng.compute_target(armed)

        if stop_dist <= 0 or target is None or rr is None or rr < params.min_rr:
            armed, armed_bar = None, -1
            eng.clear_armed()
            continue

        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            armed, armed_bar = None, -1
            eng.clear_armed()
            continue

        exit_price = exit_reason = None
        exit_bar = None
        end = min(bar + FORWARD_BARS, n)
        for j in range(bar + 1, end):
            if direction == "SHORT":
                if h[j] >= stop:
                    exit_price, exit_reason, exit_bar = stop, "STOP", j
                    break
                if l[j] <= target:
                    exit_price, exit_reason, exit_bar = target, "TARGET", j
                    break
            else:
                if l[j] <= stop:
                    exit_price, exit_reason, exit_bar = stop, "STOP", j
                    break
                if h[j] >= target:
                    exit_price, exit_reason, exit_bar = target, "TARGET", j
                    break
        if exit_price is None:
            exit_price, exit_reason, exit_bar = c[end - 1], "TIME", end - 1

        fill = exit_price
        if exit_reason == "STOP" and stop_slippage:
            fill = (exit_price * (1 - stop_slippage) if direction == "LONG"
                    else exit_price * (1 + stop_slippage))

        gross = (qty * (fill - entry)) if direction == "LONG" else (qty * (entry - fill))
        comm = qty * entry * COMMISSION_PCT + qty * fill * COMMISSION_PCT
        hours = (times[exit_bar] - times[bar]).total_seconds() / 3600.0
        funding = notional * funding_per_8h * max(hours / 8.0, 0.0)
        net = gross - comm - funding

        capital += net
        if capital <= 0:
            capital = 0.0
        peak = max(peak, capital)
        dd = (peak - capital) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

        trades.append({
            "dir": direction, "time": times[bar], "exit_time": times[exit_bar],
            "entry": entry, "stop": stop, "target": target, "rr": rr,
            "qty": qty, "notional": notional, "pnl": net, "bal": capital,
            "exit_r": exit_reason,
            "sweep_time": armed.sweep_time, "choch_time": armed.choch_time,
        })

        in_position_until = exit_bar
        armed, armed_bar = None, -1
        eng.clear_armed()
        if capital <= 0:
            break

    return trades, capital, max_dd


def summarize(label, trades, final, mdd, expect=None):
    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0.0
    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    line = (f"{label:<16} trades={len(trades):<5} WR={wr:5.1f}%  "
            f"return={ret:+9.1f}%  maxDD={mdd:5.1f}%")
    if expect:
        en, eret = expect
        ok = (len(trades) == en) and abs(ret - eret) < 1.0
        line += f"   expected {en} trades / {eret:+.1f}%  ->  {'MATCH' if ok else 'DIFFERS'}"
    print(line)
    return len(trades), ret


if __name__ == "__main__":
    print("Engine-driven backtest -- Variant C\n")
    print("Reference (validated, original implementation):")
    print("  2025  79 trades  +105.4%   |   2026  30 trades  +66.3%\n")

    t25, f25, d25 = run("BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31")
    summarize("2025", t25, f25, d25, expect=(79, 105.4))

    t26, f26, d26 = run("BTCUSDT_15m_Jan_to_Jul2026.csv")
    summarize("2026", t26, f26, d26, expect=(30, 66.3))

    print("\nWith realistic execution costs (0.1% stop slippage, 0.01% funding/8h):")
    t25c, f25c, d25c = run("BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31",
                           stop_slippage=0.001, funding_per_8h=0.0001)
    summarize("2025 costed", t25c, f25c, d25c)
    t26c, f26c, d26c = run("BTCUSDT_15m_Jan_to_Jul2026.csv",
                           stop_slippage=0.001, funding_per_8h=0.0001)
    summarize("2026 costed", t26c, f26c, d26c)
