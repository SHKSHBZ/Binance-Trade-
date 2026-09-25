# What makes a gold breakout real vs a fake-out? (`breakout_anatomy.py`, `breakout_anatomy2.py`)

**Events:** 3,850 first 15m closes beyond the previous-day high/low, the Asia-range high/low and
the 24h high/low (Jun 2022 – Sep 2026). A break counts as REAL if it runs +2u before coming back
−1u (u = ¼ daily ATR) within 8h. Timed-out trades are marked at the 8h price, and cost is included.
Build = 2022–24, Test = 2025–26.

**Baseline:** all breakouts: build −0.04R, test +0.08R. Random entries: build −0.03R, test +0.05R.
**Breaking a level on its own is no better than a random entry.**

## Conditions that differed in BOTH periods
| condition | target hit (build / test) | avg R (build / test) |
|---|---|---|
| **Day already moved >1.2× its daily ATR** (trend/news day) | **33.8% / 33.3%** | **+0.28 / +0.15** |
| — >1.5× daily ATR | 29.5% / 41.7% | −0.03 / +0.32 |
| **Level touched only 1–2 times in 48h** (fresh) | 31.7% / 27.2% | +0.18 / +0.10 |
| Level touched 6+ times (tired) | 18.4% / 19.8% | −0.05 / +0.07 |
| **Break during NY lunch 11:00–13:00 ET** | **9.4% / 13.1%** | **−0.09 / −0.16** |
| Break with the EMA80/800 trend | 20.2% / 26.1% | −0.03 / +0.22 |
| Break against the trend | 17.5% / 14.0% | −0.05 / −0.12 |
| (all breakouts, reference) | 19.1% / 21.3% | −0.04 / +0.08 |

## Conditions that did NOT help (no consistent difference)
Big breakout candle, candle closing at its extreme, high volume, a squeeze beforehand,
RSI level, day of week, level type. The 8:30–9:30 ET news hour was +0.09R in build and −0.09R in test.

## Reading
- Breakouts follow through when the **day is already a big-range day**, which usually means a
  news or event day. On quiet days most breaks fail.
- **Fresh levels** break better than levels that have been hit many times.
- **Avoid the NY lunch hour.**
- The test period was used to check which conditions held up in both periods, so any
  *combination* of these rules is not yet independently validated.
