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

## Waiting for confirmation — tested, and it HURT

We suspected entering on a blind touch of 0.5 was naive, so we tried waiting for
a 15M confirmation two sensible ways. Both made the edge thinner:

| Entry | Win rate | Pooled expectancy | "Edge is real" | Positive years |
|---|---|---|---|---|
| **touch** (enter at 0.5 immediately) | 55% | **+0.070R** | **89%** | 3 of 4 |
| close (wait for a 15M close past 0.5) | 58% | +0.038R | 77% | 2 of 4 |
| retag (confirm, then re-enter at 0.5) | 52% | +0.015R | 60% | 2 of 4 |

Why confirmation backfires here:
- **close:** waiting for a candle to close below 0.5 means we enter *lower* (for
  a short), so the reward to the origin shrinks and the risk to the extreme
  grows. Win rate rises (58%) but each win is smaller — net worse.
- **retag:** demanding a pullback to 0.5 *after* confirmation throws away the
  fades that run straight to target (the best ones) and selects for setups that
  already bounced (the weaker ones). Fewer trades, lower quality.

The fade at 0.5 is already an entry *in the direction of the pullback*, so
there is nothing to "confirm" — the best fades just go. This is the same lesson
as the SMC entry-depth test: chasing a better/safer entry costs more price than
it saves. **The simple immediate entry is the honest best.**

## Verdict and next step

A **small, real, cross-year positive tilt** — genuinely better than the SMC
strategy (which rode 2025 alone). The 15M-confirmation refinement was tested
and did not help (above); the simple immediate entry at 0.5 remains the best
version, at +0.070R / Sharpe ~0.67. That is **real but thin** — positive in 3
of 4 years, survives 0.05% slippage, but small enough that worse fills could
erase it.

Honest options from here:
1. **Forward-test the simple fade on testnet** — the only way to learn if the
   thin edge holds with live fills/slippage, at zero financial risk.
2. **Stop refining.** We have tested stop placement, the trend filter, and two
   confirmation entries; each extra knob risks curve-fitting a ~+0.07R edge.
3. Combine the fade as one input to the planned LLM decision layer.
