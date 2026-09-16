# Clean trend-following — the outcome (regime beats breakout)

Built two honest trend-following forms on daily BTC (2023-2026), no level entries.

## Breakout + ATR chandelier trail (trend_system.py) -- FAILS
Donchian(20) breakout + SMA200 filter + ATR trail, long-only:
  22 trades over 3.5y, -3% pooled, expR -0.13. The ATR trail gets shaken out on
  BTC's choppy pullbacks -- it never rides the big moves. Long+short no better.
Lesson: "breakout + trailing stop" is chopped to pieces on BTC.

## Regime filter (trend_following.py) -- WORKS
Be long while price > moving average, else cash:

| System | Return | Sharpe | maxDD | in market |
|---|---|---|---|---|
| Buy & hold | +288% | 1.05 | -53% | 100% |
| **MA(50) long/flat** | **+205%** | **1.13** | **-26%** | 54% |
| MA(200) long/flat | +99% | 0.75 | -31% | 51% |
| Momentum(60) long/flat | +141% | 0.90 | -36% | 54% |
| MA long/SHORT (any) | negative/poor | | | never short BTC |

The regime filter captures most of the upside with HALF the drawdown and a
better Sharpe. The whole family (MA/momentum, long/flat) cuts drawdown ~in half
-- robust, not one lucky setting. Never short (fighting BTC's uptrend loses).

## Verdict
The deployable trend edge is the SIMPLE regime filter: hold BTC in uptrends,
cash in downtrends. Not a breakout/trailing system, not level entries. It trades
risk for similar return (half the drawdown), which is the honest, real benefit.

## Caveat + next
2023-2026 was mostly a bull, so the regime filter's biggest benefit (dodging a
multi-year bear like 2022's -65%) is UNDERSTATED here. Confirm on 2018/2022 bear
data (need older history) before trusting it, then forward-test.
