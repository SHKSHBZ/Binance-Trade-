# TJR NY-open sweep + MSS (SMC) — tested, negative on both assets

Claim supplied with the strategy: ~70% return, 45% win rate.
Code: `tjr_ny_open.py`. Levels = Asia (19:00-02:00 ET), London (02:00-08:00 ET),
PDH/PDL; sweep 09:30-11:30 ET (DST-aware) with a close back inside within 3 bars;
MSS = close beyond the last confirmed swing that led into the sweep, by 12:00 ET;
stop beyond the sweep wick (the rules' conservative stop); target = nearest
opposing session level, or fixed 2R / 2.5R; one trade/day, flat by 16:00 ET.

**Approximation:** entry is the MSS candle close. The rules refine the entry on
the 1-minute chart (BOS or inversion FVG), and no 1m data exists here (gold has
15m minimum, BTC 5m minimum).

| | trades/yr | win | expR | P(<=0) | 1% risk / yr |
|---|---|---|---|---|---|
| BTC 5m, target = session level | 169 | 39.2% | −0.019 | 63.6% | −4.7% |
| BTC 5m, 2R | 223 | 38.1% | −0.065 | 93.5% | −14.8% |
| BTC 5m, 2.5R | 223 | 36.0% | −0.074 | 94.8% | −16.7% |
| Gold 15m, session level | 33 | 40.4% | −0.100 | 85.1% | −3.5% |
| Gold 15m, 2R | 87 | 40.9% | −0.095 | 97.9% | −8.3% |
| Gold 15m, 2.5R | 87 | 40.7% | −0.083 | 95.3% | −7.4% |

Random-direction null: BTC +0.002, gold −0.130.

The **win rate (~40%) is close to the claimed 45%**, but the strategy still
loses: a win rate says nothing about profit without the payout and costs.
Not rejected on the 1-minute entry specifically — that needs XAUUSD M1/M5 data.
