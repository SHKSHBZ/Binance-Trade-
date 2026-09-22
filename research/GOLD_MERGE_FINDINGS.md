# GOLD-MERGE — liquidity + SMC internal/external sweep

Code: `gold_merge.py` (engine), `gold_merge_h1_gauntlet.py` (1H validation).

## The rules
1. Higher-timeframe trend (H4 or Daily): up after a close breaks the last swing
   high, down after a close breaks the last swing low. Trade only with it.
2. Entry timeframe: find the **external** low (the swing low anchoring the current
   leg) and the **internal** lows (smaller swing lows above it).
3. Signal: price sweeps the nearest internal low and closes back above it, while
   the external low stays intact. Long. (Mirror for shorts.)
4. Entry at the close; stop beyond the sweep candle (floored at max(0.05% of
   price, 4x spread)); target 3R; 100-bar hold limit.

## Result on 1H entries (the trader's suggestion) — best version so far

| | n | win | expR | P(<=0) |
|---|---|---|---|---|
| **1H entry, H4 trend, 3R, all hours** | 265 | 34.3% | **+0.303** | **0.4%** |
| 1H entry, Daily trend, 3R, all hours | 295 | 32.9% | +0.249 | 1.1% |
| 1H entry, H4 trend, 2R, all hours | 278 | 39.2% | +0.119 | 8.8% |

Checks on the H4/3R cell:
- LONG +0.248, SHORT **+0.510** — shorts stronger, so not gold's uptrend
- without its 10 best trades: **+0.198** — still positive
- walk-forward: train +0.285 -> test **+0.322**
- **positive in all 7 years** (2020-2026), weakest 2021 at +0.09
- random-direction null +0.096 +/- 0.123 -> edge over null +0.208, **z = +1.69**
  (Daily-trend variant: z = +2.85)
- median stop $5.89, spread 4.2% of risk (M15 version: $3.75 / 6.7%)
- the 12-16 UTC session filter is no longer needed; all-hours is better on 1H,
  which removes the in-sample window-selection concern from the M15 version

Internal beat external in **all 8** 1H comparisons on gold.

## Weaknesses, stated plainly
- **Does not replicate on BTC.** Best BTC cell +0.069, P(<=0)=28%.
- z vs null is only +1.69 on the headline cell; the null is noisy at n=265.
- 2R is much weaker than 3R (z=+0.79).
- ~30+ configurations of this strategy have now been examined across M15 and 1H.
  Some of the headline number is selection.
- The earlier M15 gauntlet was run on a superseded external-low definition.

## Status
Strongest mechanical candidate in the project, gold only. **Not proven.**
Right next step is forward paper-trading, not live money.
