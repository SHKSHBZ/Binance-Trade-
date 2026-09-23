# BTC 1H "psychological levels" — found from the data, then tested

Code: `btc_psych_levels.py`, `btc_round_race.py`. BTC 1H, 2023-01 -> 2026-07.

## 1. Levels where BTC kept turning do NOT hold better than ordinary prices
Level = 0.3%-wide zone with >=3 swing turns in the trailing 90 days (past data
only). On the next touch: race 1.5 ATR bounce vs 1.5 ATR break, 24h.

| | n | bounce | break | trade expR |
|---|---|---|---|---|
| discovered LEVELS | 5,623 | 49.5% | 47.1% | +0.001 |
| CONTROL prices | 2,870 | 51.7% | 44.6% | +0.051 |
| levels with 6+ turns | 2,314 | 46.6% | 49.8% | −0.056 |

The most-tested levels break slightly MORE often (same as the earlier finding
that crowded levels continue rather than reverse). Walk-forward: no effect in
either 2023-24 or 2025-26.

## 2. One real pattern in the digits — but not a tradeable one
Swing-turn prices by last 3 digits: chi-square 74.1 (19 dof, 5% cut-off 30.1).
BTC turns **35% less often at ...000-049** and 25% less at ...950-999, and
**23% more often at ...450-499** (+18% at ...250-299). Swing points are not
independent, so this overstates significance, but the shape is clear: BTC does
not tend to turn right at round thousands.

Tested as a trade (bounce vs break when price reaches a round $1000 / $500):

| | 2023-24 break | 2025-26 break | control 2023-24 / 2025-26 |
|---|---|---|---|
| round $1000 | 51.0% | 44.4% | 46.0% / 51.5% |
| half $500 | 50.8% | 48.5% | |

The sign flips between periods (break-trade +0.050 then −0.089) — noise.

## Verdict
Levels can be identified (list in the script output), but on BTC 1H they do not
predict bounces or breaks better than arbitrary prices. The only structural
finding is that turns avoid exact round thousands; it does not survive as a trade.
