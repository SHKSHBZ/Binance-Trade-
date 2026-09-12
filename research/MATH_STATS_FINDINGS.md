# Math-Complete Backtest — what the proper statistics say

We added `trade_stats.py`: every backtest result now comes back with the
numbers that separate a real edge from one lucky run — expectancy in **R**
(profit measured in units of what we risked), **Sharpe** (reward per unit of
wobble), **Kelly** (the math-optimal bet size), **max drawdown**, and a
**Monte-Carlo** test that shuffles the trades thousands of times to ask:
*could a strategy with no edge at all have produced this?*

Run it:  `python3 trade_stats.py`  (defaults to the sane ATR stop, floored).

## What it revealed (ATR stop, 1% risk, floored so no microscopic stops)

| Year | Trades | Win rate | Return | Expectancy | "Edge is real" |
|---|---|---|---|---|---|
| 2023 | 66 | 17% | **−9%** | −0.12R | 36% |
| 2024 | 66 | 17% | +18% | +0.38R | 74% |
| 2025 | 82 | 20% | **+132%** | +1.25R | 93% |
| 2026 (Jan–Jul) | 33 | 15% | +21% | +0.70R | 80% |
| **Pooled** | **247** | **17%** | **+162%** | **+0.58R** | **95%** |

"Edge is real" = confidence a zero-edge strategy could **not** have made this
(above ~90% is the usual bar).

## Reading it honestly

- **The shape is a lottery ticket.** ~17% win rate with a ~7:1 payoff means a
  handful of big trend-following winners carry everything. The Monte-Carlo
  range proves the fragility: pooled 5th–95th percentile is **−7% to +997%**.
  Same edge, wildly different luck.
- **The pooled 95% is in-sample and 2025-heavy.** Pool four years and 2025's
  strength drags the average over the line, but **2023 loses and only 2025
  clears the bar on its own.** Per-year is the honest lens, and per-year it is
  *not* robustly significant.
- **This is not the same as "dead."** With a risk-capping stop (not the buggy
  default), the trend-following profile is real and positive on net — it just
  isn't dependable enough, year on year, to bet real money expecting a repeat.
- **Sharpe ~0.9 annualized pooled** (below the ~1.0 "good" line), and **Kelly
  says risk ~1.5% (quarter-Kelly)** — reassuringly close to our fixed 1%, so
  our sizing was never the problem.

## Why this matters going forward

This is the missing measuring stick. Any future change — the LLM analyst, a
news filter, a new entry — is now judged by **whether it lifts expectancy-R and
the "edge is real" number**, not by whether one year looks good. That is the
one guardrail that would have flagged "2025 carried it" on day one.
