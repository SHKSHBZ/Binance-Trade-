# Equal-Highs/Lows Liquidity-Sweep reversal — findings

The user's Strategy 1: equal highs/lows (level tested 2+ times) -> sweep (wick
beyond, close back inside) -> enter opposite at the sweep close -> target opposite
liquidity. Executable entry (market at close, no fill illusion). 15m BTC, honest
fees. `research/liquidity_sweep.py`.

## Result: coin flip, no cross-year edge

| Year | win | return |
|---|---|---|
| 2023 | 50% | -13% |
| 2024 | 44% | -22% |
| 2025 | 57% | +20% |
| 2026 | 45% | -7% |
| Pooled | 50% | -23% (expR -0.068) |

~50% win at ~1.5 RR, but costs + time-exit losses tip it negative; only 2025
positive. Adding a trend filter (take sweeps only with the SMA200 trend) leaves
~2 trades -- sweeps occur at range extremes, which are counter-trend, so the two
ideas are mutually exclusive.

## Why (consistent with the entry-edge finding)
This is a FADE (reverse at a swept level). We already measured that mean-reversion
has negative expectancy on BTC and trend/let-winners-run is the only positive
recipe. The "smart money reverses the sweep" narrative is appealing but the tape
says fading a sweep is a coin flip after costs. 5th chart method tested (SMC
sweep, Fib, Gann time, Gann Sq9, liquidity sweep) -- all ~random.
