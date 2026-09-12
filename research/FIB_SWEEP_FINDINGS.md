# Fib Strategy Sweep — the exhaustive answer

We stopped cherry-picking and ran **every combination** of both Fib strategies
(fade + golden-pocket continuation): all stops, targets, trend filters, and
entry/confirmation options — 42 combos — each graded across 2023/2024/2025/2026
separately, with 0.05% slippage. `research/fib_sweep.py`.

## Result: no dependable cross-year edge exists in these settings

| Positive in… | # of 42 combos |
|---|---|
| **4 of 4 years** | **0** |
| 3 of 4 years | 3 (all the wide-stop FADE) |
| 2 of 4 years | 15 |
| 1 of 4 years | 16 |
| 0 of 4 years | 8 |

**Zero** combinations are positive every year. This is not a code error — the
harness is causal and reproduces known results. It is the honest conclusion:
the Fibonacci patterns do not carry a strong, repeatable edge on BTC, and no
setting hides one.

## Best combination (most robust)

`FADE stop0.0 trend:off entry:touch` — wide stop at the prior extreme, immediate
entry at 0.5, no trend filter. Positive in 3 of 4 years (+15% / −3% / +6% / +1%),
+0.060R after slippage, edge-is-real 85%. Real but thin.

Continuation's best (`CONT stop1.0 tgtext1.618 trend:on confirm:on`) shows a
bigger pooled +0.137R but only 2 positive years — carried by 2024. Bigger
number, less trustworthy.

## Caveat on the search itself

With 42 tries, a few combos looking good in 3/4 years can happen by chance. The
fade is the most credible only because it is best *consistently across its
variants* and is structurally simple. Finding a 4/4 combo by adding ever more
knobs would most likely be luck (curve-fitting), not edge. The real test of the
thin fade edge is forward data, not more backtest search.
