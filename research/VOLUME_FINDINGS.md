# Volume Study — what volume actually tells us

Measurement only. `research/volume_study.py`. Causal throughout (relative volume
uses a trailing median shifted one bar).

## The three facts (stable across 2023–25 and 2026)

1. **Volume is very spiky** — std/mean ≈ 1.1–1.3, the biggest bar is ~20–50×
   the median, and the top 5% of bars carry ~26% of all volume.
2. **Volume clusters** — autocorrelation ≈ 0.71–0.77. A high-volume bar is very
   likely followed by another. (The cousin of volatility clustering.)
3. **Volume predicts the SIZE of the next move, not its DIRECTION.**
   - corr(volume, next-bar |return|) ≈ 0.29–0.34 — a real, useful link.
   - |next move| rises monotonically with volume: ~0.22% (low vol) → ~0.49%
     (spike). More than double.
   - But the up-rate stays ~50% in every volume bucket. **Volume gives you no
     edge on which way price goes.**

## What this means (the honest read)

Volume is a **volatility forecast**, not a buy/sell signal. You cannot trade
volume alone — it never tells you long or short. This is exactly why "high
volume = breakout up" folklore fails: the volume confirms a *move is coming*,
but the *direction* has to come from something else.

Where volume genuinely adds value:
- **Catch volatility expansions.** A quiet, low-volume contraction followed by a
  volume spike = a big move is starting. Pair the spike (says "go now") with a
  range-break (says "this way") → a volatility-breakout trade. The edge isn't in
  the volume; it's in being positioned when the expansion fires.
- **Filter out chop.** Skip low-volume dead zones where moves are too small to
  clear costs.
- **Size / set stops by expected volatility** rather than a fixed number.

## Next experiment

Build a **volatility-contraction → expansion breakout**: detect a low-range /
low-volume squeeze, then enter on the range-break when volume confirms, with the
break itself giving direction. Score it on the same honest scoreboard
(expectancy-R, Sharpe, Monte-Carlo, cross-year). This is the first idea in the
project where direction and timing come from *different, independent* signals —
structurally different from the chart-pattern attempts that all failed.
