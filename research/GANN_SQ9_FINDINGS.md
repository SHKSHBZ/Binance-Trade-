# Gann Square-of-9 price levels — findings

Square of 9 makes a ladder of S/R levels at (sqrt(anchor) + k*deg/360)^2.
Tested on BTC 1H 2023-2026: anchor on major swing pivots, measure how often the
minor turns that follow land ON a Gann level, vs a NULL where the ladder's phase
is randomly shifted (same spacing, wrong exact levels). `research/gann_sq9_study.py`.

## Result: no better than a random grid

| Angle | Gann hit | chance | random-grid beats Gann |
|---|---|---|---|
| 45° (0.10 tol) | 19.8% | 20.0% | 55% |
| 90° | 20.1% | 20.0% | 51% |
| 180° | 19.2% | 20.0% | 90% |
| (0.05 tol variants) | ~10% | 10% | 34-56% |

Across every angle and tolerance, Gann levels catch turns at exactly the
chance rate, and random-phase ladders match or beat them ~half the time.

## WHY it feels like it works (the important part)

The Square-of-9 ladder is DENSE -- near BTC ~65k the 45-deg levels are only ~64
points apart. Price is therefore ALWAYS within a few points of *some* Gann level.
So every reversal can be pointed at "a Gann level nearby" after the fact. With a
tolerance covering 20% of all prices, ~20% of turns trivially "hit" -- but so do
20% of turns on a RANDOM grid. The feeling of "80% of the time it respects a
level" is true of ANY dense grid, Gann or random. That is confirmation bias
powered by grid density, not a real edge.

## On the Nifty experience
We can only test what we have data for (BTC). On BTC, rigorously, there is no
edge. There is no mechanism why sqrt-price levels would be special S/R, and the
dense-grid illusion explains the subjective "it works." A proper beat-random
test on Nifty data (if provided) would very likely show the same. This is the
4th "secret system" (SMC, Fib, Gann time-cycles, Gann Sq9) that looks magical
and tests as random.
