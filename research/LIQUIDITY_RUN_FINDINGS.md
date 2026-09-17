# Liquidity Run (+ Grab/Sweep concepts) — tested on gold, NO mechanical edge

The trader's most refined, chart-illustrated setup (see the two annotated
Exness charts). Spec captured faithfully in `liquidity_run.py`:
liquidity taken (swing swept) → price runs the other way → FVG forms →
ENTER at FVG formation in the run's direction (momentum). Tested on real
gold with a min-stop filter (no sub-spread artifacts), honest fees.

## Result — negative everywhere, win rate = breakeven

Gold 30m, 2020-2026, target sweep:

| Target | Trades | Win | Breakeven win | Return | expR | Edge |
|---|---|---|---|---|---|---|
| 1.5R | 2370 | 40% | 40% | −486% | −0.366 | 0% |
| 2R | 2069 | 34% | 33% | −434% | −0.341 | 0% |
| 3R | 1793 | 26% | 25% | −402% | −0.356 | 0% |
| 5R | 1332 | 16% | 17% | −382% | −0.430 | 0% |

Tightening selectivity (SWING_HALF 20/30, faster FVG, extliq target) did not
change it — still ~breakeven, edge 0%. **The win rate sitting exactly on the
geometric breakeven at every RR is the mathematical signature of random entry
direction** — the setup carries no directional information the market prices.

## The important nuance (why this isn't the final word on the trader)

The mechanical rule fires on **1,600-2,400 setups**; the trader takes a
handful, chosen by live context (which liquidity mattered, was the momentum
real, HTF alignment). **This test measures the RULE, not the trader's
DISCRETION.** The gap between "2,000 mechanical setups = coin flip" and "the 5
setups the trader actually picks" IS where any edge would live — and it is not
mechanizable from OHLC alone.

## Only two honest ways to test discretionary edge

1. **Label real trades**: the trader supplies their actual entries (dates,
   prices, direction) from real or demo history → analyze whether THOSE
   specific picks beat random. This is testable and is the right next step.
2. **Forward demo test** with a trade journal, then measure.

Backtesting fixed rules has now been exhausted (~11 setups, BTC + gold, all
coin-flip after costs). The productive path is measuring the trader's own
decisions + building live marking tools to support them.
