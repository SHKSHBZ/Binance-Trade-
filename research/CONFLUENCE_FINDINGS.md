# Confluence across strategies — tested, WORTH EXACTLY NOTHING

"Wait for multiple factors to align" is one of the most universally taught
ideas in technical/SMC trading. It had never been tested here. Using the
consolidated 5,368-trade cross-strategy ledger, a trade counts as CONFIRMED
when another strategy opened in the same direction, nearby in time, at a
similar price. Code: `confluence_test.py`.

## Result: confluence is neutral, and at wider tolerance slightly harmful

Match window +/-4h, price within 0.3%:

| confirmations | n | win% | expR | totR |
|---|---|---|---|---|
| SOLO (none) | 3,345 | 29.7% | **−0.432** | −1,444.6 |
| 1 other | 1,602 | 33.0% | −0.413 | −660.9 |
| 2 others | 386 | 32.4% | −0.450 | −173.6 |
| 3 others | 35 | 14.3% | **−1.136** | −39.8 |

**SOLO −0.432 vs CONFIRMED −0.432. Difference: −0.000.**

Identical to three decimal places on 3,345 vs 2,023 trades. Widening the match
to +/-12h and 0.5% makes confluence actively *worse*: SOLO −0.381 vs
CONFIRMED −0.460, a difference of **−0.079**.

Triple-confirmed trades are the worst cell in the table.

## Why this is the expected result, in hindsight

Each individual signal was already measured as carrying ~zero directional
information. **Stacking signals that each carry zero still gives zero.**
Agreement between two coin flips does not make a better coin — it just makes
you more confident about a coin flip, which is worse than useless because
confidence is what drives position size.

## Bonus finding: several "different" strategies are the same strategy

Shared trades between pairs (+/-4h, 0.3%):

| pair | shared trades |
|---|---|
| **LiquidityRun + LiquiditySweep** | **335** |
| LiquidityRun + PriorDayLevels | 153 |
| LiquidityRun + StructureSweep | 133 |
| LiquiditySweep + PriorDayLevels | 123 |
| Inducement+FVG + LiquidityRun | 111 |

**37.7% of all trades are fired by at least one other strategy.** The catalogue
of ~13 strategies is not 13 independent ideas — it is a much smaller number of
ideas wearing different names. That also explains the earlier day-level result
(strategies lose together on 30% of shared days but win together on only 5%):
they are correlated on entries and uncorrelated on outcomes, which is the
worst possible combination.

## Practical consequence

Adding a second confirmation to a setup does not improve it. If a trader feels
more confident on a "confluence" setup and sizes up accordingly, confluence is
**negative expectancy through position sizing alone**, even though the raw
difference is zero.
