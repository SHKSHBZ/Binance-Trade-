# Structure-Filtered Liquidity Sweep — tested, NO directional edge

The trader's best idea: liquidity + price move is proven (sweep days ~1.7x
bigger), the only gap is DIRECTION — so use market structure to pick the side.
HH/HL → trade up, LH/LL → trade down. Code: `structure_sweep.py` (traded
version) and `sweep_direction_test.py` (pure direction measurement).

## Traded version — negative across the board

`structure_sweep.py` (uptrend: sweep the swing low + reclaim → long; target
the swing high; symmetric short):

| PIVOT_HALF | Trades | Win | avgRR | Return | expR |
|---|---|---|---|---|---|
| 5  | 1,639 | 27% | 3.2 | −311% | −0.391 |
| 20 | 717 | 19% | 5.1 | −215% | −0.421 |
| 40 | 443 | 16% | 7.1 | −133% | −0.363 |
| 60 | 386 | 13% | 8.4 | −129% | −0.406 |

Negative at every swing size, every year, edge 0%. One real mechanical flaw:
sweeping the *last structural* swing low in an uptrend is a trend-*break*
signal, not a discount pullback — so this buys breakdowns. But the deeper
problem is directional, shown next.

## Pure direction test — the decisive one

`sweep_direction_test.py` strips out all trade mechanics (no stop/target/RR)
and asks only: **after a liquidity grab (prior-day level swept + reclaimed),
does price go the trend's way more than a coin flip?** Trend by MA(200) and
by HH/HL structure. Forward-move sign over several horizons:

| FWD bars | MA all | MA post-sweep | HH/HL all | HH/HL post-sweep |
|---|---|---|---|---|
| 2  | 48.8% | 49.8% | 49.3% | 50.3% |
| 4  | 48.4% | 47.5% | 48.9% | 49.2% |
| 8  | 48.1% | 47.1% | 48.2% | 48.4% |
| 16 | 47.3% | 44.8% | 47.7% | 46.9% |
| 32 | 47.4% | 45.2% | 47.1% | 46.5% |
| 96 | 47.4% | 45.0% | 47.9% | 47.0% |

**Every cell ≤ ~50%. Never > 52%, never above the all-bar baseline.** After a
grab, price does NOT continue in the trend direction — it's a coin flip at
short horizons and slightly MEAN-REVERTS at longer ones. Structure does not
predict post-sweep direction on BTC.

## Why (and what it means)

- Even the ALL-bar continuation rate is < 50% at these horizons → **BTC 15m
  mean-reverts intraday.** That's the deep reason short-TF trend-continuation
  entries struggle, and why the ONE trend edge that worked (regime filter)
  lived on the DAILY timeframe with multi-week holds — a different animal from
  real-time intraday trading.
- The liquidity/magnitude half of the thesis is real (see
  `daily_move_anatomy.py`); the DIRECTION half is not mechanically solvable
  with trend + sweep. Direction after a grab is genuinely discretionary
  (context, which side is trapped, real vs bait) — not a rule.

## Verdict

Not a directional edge on BTC. Filed with the other patterns that dissolved
under a clean test. Worth ONE honest re-run on real gold (different
instrument, trends differently) once XAUUSD data arrives — but this is a
measurement of BTC's nature, so expectations are low.

## Run
```
python3 structure_sweep.py        # traded version + random-direction null
python3 sweep_direction_test.py    # the pure direction measurement (decisive)
```
