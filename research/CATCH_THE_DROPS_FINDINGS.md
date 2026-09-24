# The drops were there. Why can't we catch them? (`catch_the_drops.py`)

## There were plenty of drops
| market | swing size | # drops | avg drop | biggest | avg length |
|---|---|---|---|---|---|
| Gold 2020–26 | ≥1% | 480 | 2.4% | 11.0% | 36h |
| Gold | ≥2% | 157 | 4.4% | 12.5% | 105h |
| Gold | ≥5% | 37 | 8.9% | 22.3% | 402h |
| BTC 2023–26 | ≥3% | 226 | 6.5% | 23.8% | 62h |
| BTC | ≥5% | 92 | 10.3% | 35.6% | 151h |

## Part you can actually catch
A drop only looks like a drop after price has already fallen X from the top, and it only
looks finished after price has bounced X from the bottom. A trader following the swings
loses the first X and the last X of every drop. Measured with real candle-close fills and costs:

| gold swing size | avg drop | sell caught per drop | buy caught per rally |
|---|---|---|---|
| 0.5% | 1.3% | −0.03% | +0.06% |
| 1% | 2.4% | −0.03% | +0.20% |
| 2% | 4.4% | −0.04% | +0.68% |
| 5% | 8.9% | −1.27% | +1.81% |

BTC is the same: −0.25% to −2.25% caught per drop at every swing size.

## At the moment you'd sell, it's a coin flip
When gold is X% below its 5-day top, sell with the stop at the top and the target another X lower (1R):

| X | reaches target first | avg R | mirror BUY off bottom |
|---|---|---|---|
| 0.5% | 47% | −0.08 | 51%, +0.00 |
| 1% | 46% | −0.10 | 54%, +0.07 |
| 2% | 49% | −0.01 | 54%, +0.08 |
| 3% | 46% | −0.08 | 58%, +0.20 |

BTC: sells hit the target first 44–50% of the time, buys 54–57%.

**Conclusion:** at the moment you'd sell, a drop that keeps going looks the same as a dip that gets
bought back. Historically it kept falling slightly less than half the time. The drops were real,
but they can't be picked out early enough to profit.
