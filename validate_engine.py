"""
Regression test: the engine-driven backtest must equal the original one.

binance_live_bot_v2.py drives smc_engine.SMCEngine. backtest_engine.py
drives the same engine. simulate_live_bot_params.py is the original,
independent implementation whose numbers were validated. If the two
implementations agree trade-for-trade, then the live bot trades what was
validated -- which is the only reason to trust the backtest at all.

An earlier attempt at this engine was a separate re-implementation and
disagreed with the original on 43 of 79 setups. That is exactly the class
of bug this file exists to catch, so run it after ANY strategy change.

    python3 validate_engine.py     ->  exit 0 on match, 1 on divergence
"""

import sys

import backtest_engine as new
import simulate_live_bot_params as old
from smc_engine import SMCParams

PARAMS = SMCParams()

VARIANT_C = {
    "HTF_SWING_LOOKBACK": 2, "LTF_SWING_LOOKBACK": 3, "HTF_POOL_EXPIRY_BARS": 20,
    "CHOCH_WINDOW_BARS": 32, "RETEST_WINDOW_BARS": 96, "OB_SEARCH_BACK_BARS": 30,
    "STOP_BUFFER_PCT": 0.003, "MIN_RR": 2.0, "DAILY_LOSS_LIMIT_PCT": 0.03,
}

PERIODS = [
    ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
    ("Jan-Jul 2026", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None),
]

PRICE_TOL = 0.01     # cents
PNL_TOL = 0.05       # dollars


def compare(label, data_file, start, end):
    for k, v in VARIANT_C.items():
        setattr(old, k, v)
    old.TARGET_R_CAP = None

    old_trades, old_final, old_dd = old.simulate_v2(data_file, start, end)
    new_trades, new_final, new_dd = new.run(data_file, start, end, PARAMS)

    print(f"\n=== {label} ===")
    print(f"  original : {len(old_trades):>3} trades   final ${old_final:>10,.2f}   DD {old_dd:5.1f}%")
    print(f"  engine   : {len(new_trades):>3} trades   final ${new_final:>10,.2f}   DD {new_dd:5.1f}%")

    problems = []
    if len(old_trades) != len(new_trades):
        problems.append(f"trade count differs: {len(old_trades)} vs {len(new_trades)}")

    for i, (a, b) in enumerate(zip(old_trades, new_trades), 1):
        if a["dir"] != b["dir"]:
            problems.append(f"#{i} direction {a['dir']} vs {b['dir']}")
        if abs(a["entry"] - b["entry"]) > PRICE_TOL:
            problems.append(f"#{i} entry {a['entry']:.2f} vs {b['entry']:.2f}")
        if abs(a["stop"] - b["stop"]) > PRICE_TOL:
            problems.append(f"#{i} stop {a['stop']:.2f} vs {b['stop']:.2f}")
        if abs(a["target"] - b["target"]) > PRICE_TOL:
            problems.append(f"#{i} target {a['target']:.2f} vs {b['target']:.2f}")
        if abs(a["pnl"] - b["pnl"]) > PNL_TOL:
            problems.append(f"#{i} pnl {a['pnl']:.2f} vs {b['pnl']:.2f}")

    if problems:
        print(f"  DIVERGENCE ({len(problems)} issues, first 10):")
        for p in problems[:10]:
            print(f"    - {p}")
    else:
        print("  identical, trade for trade")
    return problems


if __name__ == "__main__":
    print("ENGINE EQUIVALENCE REGRESSION TEST")
    print("original implementation  vs  the engine the live bot runs")

    all_problems = []
    for label, f, s, e in PERIODS:
        all_problems += compare(label, f, s, e)

    print("\n" + "=" * 62)
    if all_problems:
        print(f"FAIL -- {len(all_problems)} divergences. Do NOT run the bot live.")
        sys.exit(1)
    print("PASS -- the live bot's engine reproduces the validated backtest exactly.")
    sys.exit(0)
