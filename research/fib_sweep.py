"""
Full parameter sweep over BOTH Fib strategies (fade + continuation).

Goal: stop cherry-picking. Run every combination of every knob, score each by
how many YEARS it is positive in (robustness), not by the pooled number (which
is what a single lucky year inflates). Then rank and show the best.

For each combo we record per-year expectancy-R and return, count positive years
(2023/2024/2025/2026), pooled expectancy, and the "edge is real" significance.

Run:  python3 fib_sweep.py
"""
import _paths  # noqa: F401
import functools
import itertools

import data_loader
import fib_reversal_backtest as rev
import fib_continuation_backtest as con
from trade_stats import summarize_trades

# ---- cache CSV loads so ~200 runs don't re-read the same files -------------
_orig_load = data_loader.load_ohlcv


@functools.lru_cache(maxsize=64)
def _cached(fname, start=None, end=None):
    return _orig_load(fname, start, end)


rev.load_ohlcv = _cached
con.load_ohlcv = _cached

CAP = 1000.0
YEARS = [("2023", "BTCUSDT_1h_2023_to_2025.csv", "BTCUSDT_15m_2023_to_2025.csv",
          "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_1h_2023_to_2025.csv", "BTCUSDT_15m_2023_to_2025.csv",
          "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_1h_2023_to_2025.csv", "BTCUSDT_15m_2023_to_2025.csv",
          "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_1h_Jan_to_Jul2026.csv", "BTCUSDT_15m_Jan_to_Jul2026.csv",
          None, None)]
SLIP = 0.0005   # grade everything with realistic slippage


def evaluate(name, run_fn, **kw):
    per_year = {}
    pooled = []
    for y, f1, f15, s, e in YEARS:
        trades, _ = run_fn(f1, f15, start=s, end=e, slippage_pct=SLIP, **kw)
        st = summarize_trades(trades, CAP, label=y)
        per_year[y] = (st.ret_pct, st.expectancy_r, st.n)
        pooled += trades
    ps = summarize_trades(pooled, CAP, label=name)
    pos_years = sum(1 for (r, _, n) in per_year.values() if r > 0 and n >= 8)
    return {"name": name, "per_year": per_year, "pos_years": pos_years,
            "pooled_r": ps.expectancy_r, "pooled_ret": ps.ret_pct,
            "pooled_n": ps.n, "edge": ps.edge_confidence}


def sweep():
    rows = []

    # ---- FADE (reversal) ----
    for stop, trend, entry in itertools.product(
            [0.0, 0.3], ["off", "with", "against"], ["touch", "close", "retag"]):
        name = f"FADE stop{stop} trend:{trend} entry:{entry}"
        rows.append(evaluate(name, rev.run, stop_level=stop,
                             trend_filter=trend, entry_mode=entry))

    # ---- CONTINUATION (golden pocket) ----
    for stop, tgt, trend, conf in itertools.product(
            ["0.786", "1.0"], ["0.0", "ext1.272", "ext1.618"],
            [True, False], [True, False]):
        name = (f"CONT stop{stop} tgt{tgt} "
                f"trend:{'on' if trend else 'off'} confirm:{'on' if conf else 'off'}")
        rows.append(evaluate(name, con.run, stop_key=stop, target_key=tgt,
                             trend_filter=trend, confirm=conf))
    return rows


def show(rows):
    # distribution of robustness
    dist = {k: 0 for k in range(5)}
    for r in rows:
        dist[r["pos_years"]] += 1
    print(f"\nSwept {len(rows)} combinations (graded with 0.05% slippage).")
    print("How many combos are positive in N of 4 years:")
    for k in range(4, -1, -1):
        print(f"   {k}/4 years positive : {dist[k]:>3} combos")

    # rank: most positive years, then pooled expectancy
    rows.sort(key=lambda r: (r["pos_years"], r["pooled_r"]), reverse=True)
    print("\nTOP 12 by cross-year robustness:\n")
    hdr = f"{'combination':<46}{'+yrs':>5}{'23':>7}{'24':>7}{'25':>7}{'26':>7}{'poolR':>8}{'edge':>6}"
    print(hdr); print("-" * len(hdr))
    for r in rows[:12]:
        py = r["per_year"]
        def rp(y): return f"{py[y][0]:+.0f}%"
        print(f"{r['name']:<46}{r['pos_years']:>5}"
              f"{rp('2023'):>7}{rp('2024'):>7}{rp('2025'):>7}{rp('2026'):>7}"
              f"{r['pooled_r']:>+8.3f}{r['edge']:>5.0f}%")


if __name__ == "__main__":
    print("FIB STRATEGY SWEEP -- every combination, ranked by cross-year robustness")
    show(sweep())
