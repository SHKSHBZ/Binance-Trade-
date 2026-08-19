"""
Portfolio backtest: SMC V2 (Variant C) across BTC, ETH, SOL, BNB, XRP
concurrently, sharing one account balance and one correlation cap.

Run fetch_data.py first -- this reads *_fetched.csv files it produces.
Each symbol runs the SAME smc_engine.SMCEngine unmodified; the only new
logic here is portfolio-level: a shared balance, and a cap on how many
positions can be open across the whole book at once.

WHY THE CAP MATTERS: BTC/ETH/SOL/BNB/XRP move together. Five 1%-risk
positions opened independently is not 5% risk -- if a market-wide move
hits all five stops together, realized loss approaches 5% at once. The
cap trades some of the multi-symbol trade-count benefit for keeping
that scenario survivable.

Two runs are printed: uncapped (all five can fire at once) and capped
(default: 2 concurrent), so the cost of the cap is visible rather than
assumed.
"""

import argparse
import glob
import os

import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCEngine, SMCParams, position_size

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
STARTING_CAPITAL = 1000.0
COMMISSION_PCT = 0.0004
FORWARD_BARS = 800

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


# Bundled BTC files, in the order they should be tried for a given period --
# a symbol resolver that ignores the requested date range will silently
# return zero bars for any period outside its one hardcoded file's coverage.
_BUNDLED_BTC_FILES = [
    "BTCUSDT_15m_2023_to_2025.csv",   # 2023-01-01 .. 2026-01-01
    "BTCUSDT_15m_Jan_to_Jul2026.csv",  # 2026-01-01 .. 2026-07-26
]


def find_symbol_file(symbol: str, start=None, end=None) -> str:
    """Prefer a freshly fetched file; fall back to bundled BTC data that
    actually covers the requested [start, end] range.

    An unbounded query (start=end=None) can't be disambiguated by content
    -- every bundled file is non-empty -- so it defaults to the most
    recent file rather than silently returning whichever is listed first.
    Callers that need one exact file regardless of ambiguity (equivalence
    tests) should pass it directly via run_portfolio's symbol_files.
    """
    fetched = glob.glob(os.path.join(DATA_DIR, f"{symbol}_*_fetched.csv"))
    if fetched:
        return os.path.basename(sorted(fetched)[-1])
    if symbol != "BTCUSDT":
        return None
    if start is None and end is None:
        return _BUNDLED_BTC_FILES[-1]
    for fname in _BUNDLED_BTC_FILES:
        df = load_ohlcv(fname, start, end)
        if len(df) > 0:
            return fname
    return _BUNDLED_BTC_FILES[-1]


def run_portfolio(symbols, start=None, end=None, params: SMCParams = SMCParams(),
                  max_concurrent: int = None, starting_capital: float = STARTING_CAPITAL,
                  symbol_files: dict = None):
    """max_concurrent=None means uncapped (any number of symbols can be open).

    symbol_files optionally maps symbol -> exact filename, bypassing the
    auto-resolver. Needed whenever start/end don't disambiguate which
    bundled file is intended (both bundled BTC files satisfy an
    unbounded start=None/end=None query) -- exact-equivalence tests
    against a specific reference file must pass this rather than guess.
    """
    symbol_files = symbol_files or {}
    data = {}
    for sym in symbols:
        fname = symbol_files.get(sym) or find_symbol_file(sym, start, end)
        if fname is None:
            print(f"  skipping {sym}: no data file found (run fetch_data.py)")
            continue
        df = load_ohlcv(fname, start, end)
        if len(df) < 300:
            print(f"  skipping {sym}: only {len(df)} bars, too little history")
            continue
        eng = SMCEngine(params)
        eng.prepare(df)
        data[sym] = {"df": df, "eng": eng, "armed": None, "armed_bar": -1,
                    "in_pos_until": -1, "open": False, "entry": None, "stop": None,
                    "target": None, "qty": None, "dir": None,
                    "start_bar": eng.start_bar()}

    if not data:
        return [], starting_capital, 0.0

    # Align on a shared timestamp axis so "concurrently open" is meaningful
    common_index = None
    for sym, d in data.items():
        idx = d["df"].index
        common_index = idx if common_index is None else common_index.union(idx)
    common_index = common_index.sort_values()

    capital = starting_capital
    peak = capital
    max_dd = 0.0
    trades = []
    open_count = 0
    current_day = None
    day_start_balance = capital
    day_halted = False

    for ts in common_index:
        day = ts.normalize()
        if day != current_day:
            current_day = day
            day_start_balance = capital
            day_halted = False
        elif not day_halted and capital <= day_start_balance * (1 - params.daily_loss_limit_pct):
            day_halted = True
        # Capture blocked-state as it stood BEFORE this bar's exits resolve.
        # backtest_engine.py's "bar <= in_position_until" stays true through
        # the exit bar itself -- a symbol only unblocks the bar AFTER it
        # exits. Using post-exit state here would let a new sweep fire one
        # bar early relative to the validated implementation.
        was_blocked = {sym: (d["open"] or (d["armed"] is not None))
                       for sym, d in data.items()}

        # first pass: manage exits (always allowed, never gated by the cap)
        for sym, d in data.items():
            df = d["df"]
            if ts not in df.index:
                continue
            bar = df.index.get_loc(ts)
            if not d["open"]:
                continue
            h, l, c = df["high"].values, df["low"].values, df["close"].values
            direction, stop, target = d["dir"], d["stop"], d["target"]
            hit_stop = (h[bar] >= stop) if direction == "SHORT" else (l[bar] <= stop)
            hit_target = (l[bar] <= target) if direction == "SHORT" else (h[bar] >= target)
            if hit_stop or hit_target:
                exit_price = stop if hit_stop else target
                reason = "STOP" if hit_stop else "TARGET"
                qty = d["qty"]
                gross = (qty * (exit_price - d["entry"]) if direction == "LONG"
                         else qty * (d["entry"] - exit_price))
                comm = qty * d["entry"] * COMMISSION_PCT + qty * exit_price * COMMISSION_PCT
                net = gross - comm
                capital += net
                if capital <= 0:
                    capital = 0
                peak = max(peak, capital)
                dd = (peak - capital) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
                trades.append({"symbol": sym, "dir": direction, "time": d["entry_time"],
                               "exit_time": ts, "entry": d["entry"], "stop": stop,
                               "target": target, "pnl": net, "bal": capital, "exit_r": reason})
                d["open"] = False
                open_count -= 1

        # second pass: advance each engine and look for new entries
        for sym, d in data.items():
            df = d["df"]
            if ts not in df.index:
                continue
            bar = df.index.get_loc(ts)
            if bar < d["start_bar"]:
                continue
            eng = d["eng"]

            setup = eng.step(bar, was_blocked[sym])
            if setup is not None:
                d["armed"], d["armed_bar"] = setup, bar

            if d["armed"] is None or d["open"]:
                continue
            if bar - d["armed_bar"] > params.retest_window_bars:
                d["armed"], d["armed_bar"] = None, -1
                eng.clear_armed()
                continue

            armed = d["armed"]
            l_, h_ = df["low"].values, df["high"].values
            touched = ((armed.direction == "LONG" and l_[bar] <= armed.limit_price) or
                       (armed.direction == "SHORT" and h_[bar] >= armed.limit_price))
            if not touched:
                continue

            if day_halted:
                # portfolio-level breaker: today's loss already hit the limit
                d["armed"], d["armed_bar"] = None, -1
                eng.clear_armed()
                continue

            if max_concurrent is not None and open_count >= max_concurrent:
                # setup is valid but the portfolio is already at its cap -- skip it
                d["armed"], d["armed_bar"] = None, -1
                eng.clear_armed()
                continue

            target, rr = eng.compute_target(armed)
            if target is None or rr is None or rr < params.min_rr:
                d["armed"], d["armed_bar"] = None, -1
                eng.clear_armed()
                continue

            qty, notional = position_size(capital, armed.limit_price, armed.stop_price, params)
            if qty <= 0:
                d["armed"], d["armed_bar"] = None, -1
                eng.clear_armed()
                continue

            d.update(open=True, entry=armed.limit_price, stop=armed.stop_price,
                     target=target, qty=qty, dir=armed.direction, entry_time=ts)
            d["armed"], d["armed_bar"] = None, -1
            eng.clear_armed()
            open_count += 1

        if capital <= 0:
            break

    return trades, capital, max_dd


def summarize(label, trades, final, mdd, starting=STARTING_CAPITAL):
    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0.0
    ret = (final - starting) / starting * 100
    print(f"\n{label}")
    print(f"  trades={len(trades):<5} WR={wr:5.1f}%  return={ret:+9.1f}%  maxDD={mdd:5.1f}%")
    if trades:
        by_symbol = {}
        for t in trades:
            by_symbol.setdefault(t["symbol"], []).append(t)
        print("  by symbol:")
        for sym, ts in sorted(by_symbol.items()):
            w = len([t for t in ts if t["pnl"] > 0])
            pnl = sum(t["pnl"] for t in ts)
            print(f"    {sym:<10} n={len(ts):<4} WR={w/len(ts)*100:5.1f}%  "
                  f"contributed ${pnl:+,.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--cap", type=int, default=2,
                    help="max concurrent open positions across the portfolio")
    args = ap.parse_args()

    print(f"Portfolio backtest: {', '.join(args.symbols)}")
    print(f"Data files in use:")
    for s in args.symbols:
        f = find_symbol_file(s, args.start, args.end)
        print(f"  {s:<10} {f if f else 'MISSING -- run fetch_data.py'}")

    print("\n--- UNCAPPED (all symbols can be open at once) ---")
    tr_u, fin_u, dd_u = run_portfolio(args.symbols, args.start, args.end, max_concurrent=None)
    summarize("Uncapped", tr_u, fin_u, dd_u)

    print(f"\n--- CAPPED at {args.cap} concurrent positions ---")
    tr_c, fin_c, dd_c = run_portfolio(args.symbols, args.start, args.end, max_concurrent=args.cap)
    summarize(f"Capped ({args.cap})", tr_c, fin_c, dd_c)

    print(f"\n{'='*60}")
    print(f"Uncapped: {dd_u:.1f}% max DD   |   Capped: {dd_c:.1f}% max DD")
    print("If uncapped drawdown is much worse, that's correlated exposure "
          "showing up exactly as expected -- keep the cap.")
