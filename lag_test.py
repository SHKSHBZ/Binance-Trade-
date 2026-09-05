"""
Verify the 'SMC is a lagging indicator' worry with data.

Test 1: how far has price moved between a swing pivot's true extreme and
        the bar where our labeler CONFIRMS it (the lag, in bars and %).
Test 2: force every entry to happen K bars LATER than the (already causal)
        backtest does, and watch the P&L. If a few bars of extra lag wreck
        it, the worry is fatal; if the edge survives, it is robust to lag.
"""

import numpy as np
import pandas as pd

import backtest_engine as be
from smc_engine import SMCEngine, SMCParams, position_size
from smc_luxalgo import label_smc_luxalgo
from regime_optimizer import FULL

be.STARTING_CAPITAL = 500.0


# ---- Test 1: quantify the lag ------------------------------------------
def quantify_lag():
    df = be.load_ohlcv(FULL)
    lab, _ = label_smc_luxalgo(df, swing_length=50)
    h = df["high"].to_numpy(float); l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(c)
    swing_len = 50

    moves = []
    sph = lab["swing_pivot_high"].to_numpy(float)
    for conf_bar in np.where(~np.isnan(sph))[0]:
        extreme_bar = conf_bar - swing_len          # where the high really was
        if extreme_bar < 0:
            continue
        extreme_price = h[extreme_bar]
        price_at_confirm = c[conf_bar]
        move_pct = (price_at_confirm - extreme_price) / extreme_price * 100
        moves.append(move_pct)
    moves = np.array(moves)
    print("TEST 1 -- lag between a swing HIGH and the bar we confirm it")
    print(f"  swing pivots measured : {len(moves)}")
    print(f"  confirmation lag      : {swing_len} bars ({swing_len*15/60:.1f} h on 15m)")
    print(f"  price move by confirm : median {np.median(moves):+.2f}%   "
          f"mean {moves.mean():+.2f}%   (negative = price already fell off the high)")
    print(f"  so yes: by confirmation, price has typically moved "
          f"{abs(np.median(moves)):.1f}% from the pivot.\n")


# ---- Test 2: add artificial entry delay --------------------------------
def run_with_delay(delay, risk=0.02, lev=10):
    params = SMCParams(risk_per_trade_pct=risk, leverage=lev)
    df = be.load_ohlcv(FULL)
    eng = SMCEngine(params); eng.prepare(df)
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    times = df.index; n = len(c)

    capital = be.STARTING_CAPITAL; peak = capital; max_dd = 0.0
    trades = []
    armed = None; armed_bar = -1; in_position_until = -1
    current_day = None; day_start = capital; day_halted = False

    for bar in range(eng.start_bar(), n):
        day = times[bar].normalize()
        if day != current_day:
            current_day = day; day_start = capital; day_halted = False
        elif not day_halted and capital <= day_start * (1 - params.daily_loss_limit_pct):
            day_halted = True

        blocked = (armed is not None) or (bar <= in_position_until)
        setup = eng.step(bar, blocked)
        if setup is not None:
            armed, armed_bar = setup, bar

        if armed is None or bar <= in_position_until:
            continue
        # ---- THE LAG INJECTION: refuse to act for `delay` extra bars ----
        if bar < armed_bar + delay:
            continue
        if bar - armed_bar > params.retest_window_bars:
            armed, armed_bar = None, -1; eng.clear_armed(); continue

        touched = ((armed.direction == "LONG" and l[bar] <= armed.limit_price) or
                   (armed.direction == "SHORT" and h[bar] >= armed.limit_price))
        if not touched:
            continue
        if day_halted:
            armed, armed_bar = None, -1; eng.clear_armed(); continue

        entry = armed.limit_price; stop = armed.stop_price; direction = armed.direction
        stop_dist = abs(entry - stop)
        target, rr = eng.compute_target(armed)
        if stop_dist <= 0 or target is None or rr is None or rr < params.min_rr:
            armed, armed_bar = None, -1; eng.clear_armed(); continue
        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            armed, armed_bar = None, -1; eng.clear_armed(); continue

        exit_price = exit_bar = None
        end = min(bar + be.FORWARD_BARS, n)
        for j in range(bar + 1, end):
            if direction == "SHORT":
                if h[j] >= stop: exit_price, exit_bar = stop, j; break
                if l[j] <= target: exit_price, exit_bar = target, j; break
            else:
                if l[j] <= stop: exit_price, exit_bar = stop, j; break
                if h[j] >= target: exit_price, exit_bar = target, j; break
        if exit_price is None:
            exit_price, exit_bar = c[end - 1], end - 1

        fill = exit_price
        gross = (qty * (fill - entry)) if direction == "LONG" else (qty * (entry - fill))
        comm = qty * entry * be.COMMISSION_PCT + qty * fill * be.COMMISSION_PCT
        net = gross - comm
        capital += net
        peak = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100 if peak > 0 else 0.0)
        trades.append(net)
        in_position_until = exit_bar
        armed, armed_bar = None, -1; eng.clear_armed()

    wr = np.mean([1 for t in trades if t > 0]) if trades else 0
    return len(trades), (capital / be.STARTING_CAPITAL - 1) * 100, max_dd, \
        (sum(1 for t in trades if t > 0) / len(trades) * 100 if trades else 0)


if __name__ == "__main__":
    quantify_lag()
    print("TEST 2 -- force entries K bars LATER than the (already causal) backtest")
    print("  (2% risk, 10x, no-cost, full 2023->2026 data)")
    print(f"  {'extra lag':>10}{'trades':>8}{'return':>9}{'maxDD':>8}{'win%':>7}")
    for k in [0, 1, 2, 3, 5, 10]:
        nt, ret, dd, wr = run_with_delay(k)
        tag = "  <- baseline" if k == 0 else ""
        print(f"  {k:>7} bar{nt:>9}{ret:>+8.0f}%{dd:>7.1f}%{wr:>6.0f}%{tag}")
