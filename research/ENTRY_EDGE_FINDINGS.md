# The correct entry — what actually makes money on BTC

We asked: is there an entry that makes this profitable? Tested every common entry
with a target-independent 1:1 ATR race (does price go +1ATR before -1ATR).
`research/entry_scan.py`.

## 1. No entry predicts DIRECTION (all ~50% at 1:1)

| Entry | fav-first (1:1) |
|---|---|
| Momentum (24h) | 48.8% |
| Trend regime SMA200 | 49.6% |
| Trend regime SMA50 | 50.0% |
| Breakout 48h | 49.4% |
| RSI oversold/overbought | 46.3% |
| Momentum + trend | 49.1% |
| Breakout + trend | 49.8% |

BTC direction at intraday scale is ~a coin flip. There is no magic entry.

## 2. Profit comes from PAYOFF ASYMMETRY + trend (not the entry)

Trend entries (momentum WITH trend), stop = 1 ATR, widening the target:

| Target | Hit rate | Expectancy |
|---|---|---|
| 1 ATR | 49% | -0.017R |
| 2 ATR | 33% | +0.001R |
| 3 ATR | 25% | +0.016R |
| 5 ATR | 18% | **+0.090R** (n=20,815) |

Hit rate falls but expectancy rises: trend entries have a **fat right tail** --
win rarely, win big. Edge is in **letting winners run**, not in entry precision.

Mean-reversion (RSI) entries, same stop:

| Target | Expectancy |
|---|---|
| 1 ATR | -0.074R |
| 2 ATR | -0.141R |
| 3 ATR | -0.137R |

Negative everywhere, WORSE the longer held -- a fat LEFT tail.

## 3. The conclusion that ties the whole project together

Every strategy we tested (SMC sweep, Fib reversal, prior-day level fade) was a
FADE / mean-reversion bet. They all lost. This is why: **BTC punishes fading and
rewards trend-with-let-winners-run.** The winning recipe is the opposite of what
we kept trying:

  * enter WITH the trend (direction is ~coin flip, so don't over-engineer it),
  * small stop (~1 ATR),
  * let winners run to a large/trailing target (3-5x+),
  * accept a low win rate (~20-30%) for a big average winner.

This matches the earlier trend-following result (half the drawdown, beat
buy-and-hold). The edge was never the entry -- it is trend + asymmetric exit.
