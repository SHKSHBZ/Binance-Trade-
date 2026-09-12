# Fib Reversal (fade) — backtest findings

Built from the measurement lead: a 1H leg that retraces to 0.5 more often breaks
its origin (1.0) than continues. So we **fade** it — short a pulled-back up-leg
(long a pulled-back down-leg), targeting the origin. Levels marked on **1H**,
entry/stop/target executed on **15M**. Scored with `trade_stats`.
Code: `research/fib_reversal_backtest.py`.

## Stop placement decides everything

| Stop | Win rate | Pooled return | Pooled expectancy | Verdict |
|---|---|---|---|---|
| **0.3 (tight)** | ~16% | **−243%** (blow-up) | −0.54R | dead — noise stops us out before the fade works |
| **0.0 (wide, = prior extreme)** | ~55% | **+22%** | +0.070R | the real candidate |

The tight stop sits just above the entry, so normal wiggle stops us out. The
wide stop (risk to the prior extreme, reward to the origin — a clean 1:1) is the
only geometry that works.

## Best config: wide stop, NO trend filter

| Year | Win rate | Return | Expectancy | "Edge is real" |
|---|---|---|---|---|
| 2023 | 59% | +16% | +0.16R | 95% |
| 2024 | 52% | −2% | −0.02R | 43% |
| 2025 | 55% | +7% | +0.09R | 80% |
| 2026 (Jan–Jul) | 51% | +1% | +0.02R | 59% |
| **Pooled** | **55%** | **+22%** | **+0.070R** | **89%** |

- **Positive in 3 of 4 years** and a >50% win rate at 1:1 — the first thing in
  this whole project that isn't carried by a single year.
- **But it is thin.** +0.07R means we net 7% of what we risk per trade. Sharpe
  ~0.67 (below the 1.0 "good" line). 2024 is a small loss.

## The trend filter is a curve-fit trap

| Filter | Pooled expectancy | Which year it flatters |
|---|---|---|
| off | **+0.070R** | most robust |
| with daily trend | +0.045R | 2026 great, 2025 negative |
| against daily trend | +0.002R | 2023 great, rest negative |

Each filter wins the year it happens to suit and loses others. **No filter** is
the honest best — a reminder that the daily-trend "help" we saw in the
measurement was a single-period artifact.

## Does it survive costs? (the real question for a thin edge)

With **0.05% stop slippage** added: pooled expectancy +0.060R (from +0.070R),
still positive in 3/4 years, "edge is real" 85%. It survives — but half the
edge could disappear under worse fills. This is a marginal edge, not a strong one.

## Verdict and next step

A **small, real, cross-year positive tilt** — genuinely better than the SMC
strategy (which rode 2025 alone). It is too thin to trade as-is. The user's
plan was to **refine the 15M entry** (right now entry is a blind touch of 0.5).
Natural next experiment: require a 15M confirmation at the 0.5 zone (e.g. a 15M
reversal candle / micro lower-high) to improve fill quality and win rate, then
re-score. If that lifts expectancy meaningfully, we forward-test; if not, the
fade is real but too thin to risk money on.
