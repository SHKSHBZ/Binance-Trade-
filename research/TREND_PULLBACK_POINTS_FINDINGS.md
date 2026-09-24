# Trend pullback, fixed $ stop/target (gold 15m, with 4H trend)

Rules fixed before running: 4H trend = close > EMA50 > EMA200 (mirror for down),
15m bar touches EMA20 and closes back on the trend side, 07-17 UTC, fixed $ stop/target.
Control = random entries under the same trend filter/hours/stop/target.

| stop/target | n | win | expR | P(luck) | random control |
|---|---|---|---|---|---|
| $5 / $8 | 1914 | 40.2% | -0.008 | 61% | -0.029 |
| $4 / $8 | 2075 | 34.1% | -0.040 | 90% | -0.034 |
| $5 / $5 | 2154 | 49.9% | -0.052 | 99% | -0.070 |
| $8 / $8 | 1612 | 52.1% | +0.010 | 36% | -0.001 |

Breakeven, the same as random entries in the trend direction. 2026 is the worst year:
at a gold price of about $4,000, a $5 stop is only 0.12% of price, which sits inside normal noise.
