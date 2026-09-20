# Position trend-following on gold — MY hypothesis, tested, FAILED

Origin: this was not the trader's idea. It came from two observations in our
own data that I had been misreading:

1. Every time something "worked" (trail 4 ATR, trail 8 ATR) I called it a gold
   trend artifact and discarded it. The null proved the ENTRY added nothing —
   it did not prove the TRAIL added nothing. So: delete the entry, keep the trail.
2. Spread is 5.4% of median risk on M15. Every test had been run inside the
   regime where cost dominates the effect being measured. Held for days with a
   $40 stop, cost drops to ~0.6%.

Prediction: Donchian breakout + chandelier ATR trail, daily bars, few trades,
should show a real edge where the M15 work could not.

## Raw grid looked excellent — and that was the trap

Gold daily 2020-01 -> 2026-09, 36 cells (N x trail x side):
- **12/12 long-only cells positive** (+9.0% to +21.3%, maxDD 2.1-5.7%)
- **12/12 short-only cells negative** (−1.3% to −7.2%)

A perfect split. It is also exactly what a bull market produces with no skill
whatsoever — gold was +179% over the sample. Raw returns cannot separate the
two, so the grid is uninformative on its own.

## The decisive test: alpha vs an exposure-matched passive position

1% risk sizing with wide ATR stops means average notional exposure is only
~7.6%. The fair benchmark is therefore a 7.6% passive allocation, not
buy & hold. Regressing strategy returns on gold returns separates beta
(the market) from alpha (the strategy).

| GOLD | CAGR | maxDD | avg exposure | matched passive | beta | ALPHA |
|---|---|---|---|---|---|---|
| N=40 trail=3 LONG | +2.93% | 3.04% | 7.6% | +1.93% | 0.07 | **+1.44%/yr** |
| N=60 trail=3 LONG | +2.48% | 2.36% | 6.7% | +1.70% | 0.06 | +1.21%/yr |
| N=40 trail=5 LONG | +1.83% | 2.09% | 6.9% | +1.75% | 0.07 | +0.52%/yr |
| N=60 trail=8 LONG | +2.00% | 3.73% | 7.1% | +1.80% | 0.08 | +0.56%/yr |

**Null (random direction, same trail, 8 seeds): mean +0.26%/yr, sd 1.07,
range [−1.37, +2.28].**

Best cell is +1.44 against a null of +0.26 ± 1.07 → **z = 1.1, and +1.44 sits
inside the null's own range.** Not significant.

## Independent replication on BTC — FAILED, alpha negative

| BTC (2023-01 -> 2026-01, b&h +429%) | CAGR | matched passive | ALPHA |
|---|---|---|---|
| N=40 trail=3 LONG | +0.01% | +3.45% | **−0.96%/yr** |
| N=60 trail=3 LONG | +0.31% | +2.60% | −0.62%/yr |
| N=40 trail=5 LONG | +1.07% | +4.62% | −0.79%/yr |
| N=60 trail=8 LONG | +1.48% | +4.09% | −0.31%/yr |

Every cell negative, and a passive allocation of the same size beat the
strategy 3-4x in every case. Trend-following is supposed to be the most
asset-agnostic method there is; it did not survive one asset change.

## Walk-forward on gold — SIGN INVERSION

| | CAGR | ALPHA |
|---|---|---|
| TRAIN 2020-2023 (n=18) | +0.24% | **−0.20%/yr** |
| TEST 2024-2026 (n=12) | +7.03% | **+3.82%/yr** |

Negative in training, positive out-of-sample. Under honest walk-forward
selection this system would have been rejected before the test period ever
ran. Identical noise signature to every previous candidate.

## Verdict

**Rejected on all three counts: inside its own null, negative on the second
asset, sign-inverted across the walk-forward split.**

The reasoning that produced it was sound — the cost regime argument is still
correct, and "the trail did the work, not the entry" is still the right reading
of the earlier null. But the conclusion drawn from it does not survive testing.
The trail was not capturing a tradeable trend edge on gold; at 1% risk it was
capturing a 7.6% passive position and roughly nothing else.

Score so far: ~14 strategies from the trader, 1 from me. All rejected.
