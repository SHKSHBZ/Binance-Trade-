# Prior-Day-Levels Fade — findings (and a fill-illusion caught)

The user's idea: on a small-gap day, fade the prior day's extremes (short at
yesterday's High, long at yesterday's Low), betting the range holds. 5m BTC,
targets A (opposite level) / B (fixed 2R) / C (range midpoint).
Code: `research/prior_day_levels_backtest.py`. 2026 trade log:
`research/prior_day_2026_trades.csv`.

## The trap we caught (this is the whole lesson)

A first pass looked spectacular -- Target B GROSS +2250%, positive in all 4
years, "edge is real" 100%. It was a FILL ILLUSION: the fill trigger let a limit
at the level fill when price only came WITHIN 0.1% of it and then reversed --
trades you can never get, because a limit at the low only fills if price actually
trades down TO the low.

When the fill is modelled honestly (limit fills only when price REACHES the
level), the edge inverts to a big loss:

| Target | Pooled return (honest fill, real fees) | Positive years |
|---|---|---|
| A (opposite level) | -340% | 0/4 |
| B (fixed 2R) | -319% | 0/4 |
| C (midpoint) | -341% | 0/4 |

No stop width rescues it (0.3%->2% all negative, edge 0%).

## Why it loses (2026, 320 trades, 30% win, -75%)

- **69% of trades hit the stop.** You are filled AT the level, and the level
  fails ~7 times out of 10 -- you get filled INTO breakdowns, not bounces
  (adverse selection at the fill).
- **Longs and shorts lose equally** (~30% win each) -- the premise "quiet days
  respect yesterday's range" does not hold on BTC 5m.
- **Re-entry compounds it**: the rule re-sells the same breaking level several
  times in a row (visible in the 2026 log), stacking losses on the worst setups.

## The lesson (again)

This is the SAME fill trap as the original SMC strategy: a level-limit backtest
looks great until you require the limit to actually be reached, at which point
the winners (clean approaches that reverse before touching) vanish and only the
losers (touch-and-break) fill. On BTC's liquid 5m tape, fading levels with a
tight stop is negative once fills and fees are honest. The direction premise is
not real; the earlier number was execution fantasy.

Only a forward test with real limit-order fills could ever validate a level
strategy -- a backtest cannot model queue position and touch-vs-through.
