# Gann Time-Cycle Test — findings

Gann's testable core claim: market turns cluster at specific time distances from
a prior turn (the "Gann numbers": 30/45/60/90/120/144/180/225/270/360 days).
We tested it on BTC daily pivots. `research/gann_time_study.py`.

## Method note (a bias we caught and fixed)

A first version compared the Gann hit-rate to random numbers spread over the
whole 0-400 day range and showed a "signal." That was an ARTIFACT: Gann numbers
are mostly small, and pivot-to-pivot gaps are also mostly small (turns cluster
in time), so Gann numbers scored well just by sitting where gaps are dense.

The correct test JITTERS each Gann number by a small random offset (same size,
wrong exact value). If the exact Gann numbers matter, they beat their own
jittered versions.

## Result: no edge

| Period | Gann hit rate | Jittered (fake) cycles | Jittered beats Gann |
|---|---|---|---|
| 2023–25 | 18.6% | 17.7% | 26% of the time |
| 2026 | 26.3% | 24.3% | 28% of the time |

The exact Gann day-numbers are **no better than nearby non-Gann numbers**. Market
turns do not cluster on 90/144/180/360 specifically. No time-cycle edge.

## On the rest of Gann

- **Gann angles (1x1 etc.)** depend on a price/time chart scaling Gann kept
  secret — there is no objective way to draw them, so any "result" just reflects
  the scale you chose. Unfalsifiable = not testable = not an edge you can rely on.
- **"P x T = K, the future is already in the past"** is not a physical law; it is
  marketing. Same genre as the video's fake 70% win rate.

We tested the one objective, falsifiable Gann claim (time cycles) and it failed.
The rest cannot be tested because it has no fixed definition — which is itself
the tell.
