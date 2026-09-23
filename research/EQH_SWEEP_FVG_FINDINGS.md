# Equal-highs/lows sweep -> FVG re-entry -> range target (trader's formal spec)

Code: `eqh_sweep_fvg.py`. Pivots k=5 (confirmed), equal extremes 5-100 bars apart,
eps 0.05/0.10/0.15%, acceptance cancel delta 0.10%, trigger high>EQH & close<=EQH,
entry A = trigger close / B = limit at the CE of the first post-sweep FVG,
stop = sweep extreme + 1 ATR(14), target = internal range extreme, R >= 2.
Gold ($0.25 spread) and BTC (0.06% round trip), 15m and 1h. 24 cells.

Result: **23 of 24 cells negative.** Win rates 20-27% against a median R of
~2.6-2.8, which needs ~27% just to break even.

| | best eps | n | win | expR | P(<=0) |
|---|---|---|---|---|---|
| Gold 15m, entry A | 0.15% | 689 | 23.1% | −0.169 | 99.3% |
| Gold 15m, entry B (FVG) | 0.05% | 74 | 29.7% | +0.028 | 43.8% |
| Gold 1h, entry A | 0.10% | 95 | 21.1% | −0.204 | 88.5% |
| BTC 15m, entry A | 0.10% | 233 | 26.2% | −0.236 | 97.2% |
| BTC 1h | all | <=28 | — | −0.25 to −1.05 | — |

The single positive cell (gold 15m, FVG entry, eps 0.05%, n=74) is noise:
P(<=0)=44%, train +0.129 -> test −0.078, and its neighbours at eps 0.10/0.15%
are negative. Consistent with earlier findings: obvious equal highs/lows are
run through more often than they are defended.
