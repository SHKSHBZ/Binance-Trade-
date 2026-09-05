# research/ — the evidence behind the strategy

These files are **not** part of the live system. The bot trades
`../smc_engine.py`; nothing here is imported by it. This folder records
*why* the strategy is built the way it is, so the conclusions don't have
to be re-discovered.

Run any script from the repo root, e.g. `python3 research/scan_scenarios.py`.
(`_paths.py` puts the repo root on the import path.)

## Files

| File | What it is / what it showed |
|---|---|
| `smc_luxalgo.py` | Faithful Python port of the LuxAlgo "Smart Money Concepts" indicator. Labels OHLCV with dual (internal-5 / swing-50) structure, BOS/CHoCH, volatility-filtered order blocks + mitigation, FVGs, EQH/EQL, premium/discount. Causal (no look-ahead). The accurate "eyes" used by the studies below. |
| `SMC_STRATEGY_SPEC_v3.md` | The frozen rulebook — every eyeball term pinned to a number, parameters marked frozen vs tunable. |
| `backtest_smc_scenario2.py` | Causal backtest of a single concept ("pullback into an order block"). **Finding: no edge** — raw entry wins 16.5% vs a 2:1 target. A single SMC concept alone does not work. |
| `scan_scenarios.py` | All six playbook scenarios vs a random baseline on one bracket. **Finding: no single concept beats random.** S6 (premium/discount) is a filter, not a trigger; S2 (OB pullback) is worst. |
| `regime_optimizer.py` | Capital(risk%)/leverage sweep across bull/bear/sideways. **Findings:** leverage is only a cap (25x ≈ or worse than 10x); risk% drives return *and* drawdown one-for-one; even 1% risk carries a ~38% full-cycle drawdown. |
| `lag_test.py` | Quantifies SMC's confirmation lag (~1.2%, 12.5h for a swing) and stress-tests it. **Finding: the edge survives extra lag** (still +64% when forced 10 bars slower) because entries are pullbacks-to-a-level, not chases — but the rosiest numbers assume unrealistic same-bar fills. |
| `sr_test.py` | Plain support/resistance bounce (timely, no lag) vs random. **Finding: ≈ random (+0.02 R).** Early entry at a level buys no edge; the lag is the *price* of the confirmation that creates the edge. |

## The one-line conclusion

Single SMC concepts (and plain S/R) are no better than random. The edge
lives in the **stacked sequence** — sweep → CHoCH → order block with
displacement → limit fill — which is what `../smc_engine.py` trades.
Survivable sizing is **1–2% risk, 10x**, and the one thing no backtest
here can settle is real limit-order fills — that's what testnet is for.
