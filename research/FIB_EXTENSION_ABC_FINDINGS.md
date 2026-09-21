# Fibonacci Extension (trend-based A-B-C) — tested, NOT an edge

The PDF's strategy: 3-candle swing rule, A-B-C structure, enter on the break of
the Point-C candle, targets at C + k*(B-A), TP at 1.000 and 1.618.
Code: `fib_extension_abc.py`. Distinct from the earlier Fib work here, which
entered *inside* the 0.5 retracement; this enters on the resumption.

## Is the document accurate?

The mechanics are stated correctly (1.272 = sqrt(1.618), trend-based 3-point
extension, etc.). But its central claim — "market moves often relate to previous
moves by specific ratios" — is an assertion, not a fact, and is exactly what the
control test below refutes.

Two of its three management rules are ones already measured as HARMFUL here:
- "Move to break-even at 0.618": on the trader's own 82-trade log, BE at +0.5R
  took a 2:1 system from **+0.122R to −0.074R**.
- "Close 50% at 1.000": on 4,384 gold trades, the **worst rule tested** —
  −0.144R vs −0.051R for the best, max drawdown 416R vs 151R.
Its third rule (higher-timeframe trend alignment) IS supported by our data
(+0.148R with the daily filter, −0.133R without).
Section 7's "avoid choppy markets" is an unfalsifiable escape hatch; ignored.

## 1. FIBONACCI RATIOS ARE NOT SPECIAL — the decisive test

1.000 and 1.618 were raced against deliberately NON-Fibonacci levels. Same
pipeline, so any bug hits both equally.

| Fib level | vs null | | Non-Fib control | vs null |
|---|---|---|---|---|
| 1.272 | +0.018 | | 1.350 | +0.002 |
| **1.618** | **+0.023** | | **1.500** | +0.016 |
| 2.618 | +0.030 | | **2.200** | **+0.038** |

Non-Fib **2.200 beats Fib 1.618** on gold; on BTC non-Fib **1.350 (+0.094)** and
**2.200 (+0.098)** beat Fib **1.618 (+0.084)**. Across four panels the Fib levels
never lead. **Only distance matters; the ratios are decoration.**

## 2. The A-B-C structure — passed three checks, failed the fourth

Non-overlapping (one trade at a time), honest fills, costs charged:

| | n | expR | LONG | SHORT | vs null | P(<=0) |
|---|---|---|---|---|---|---|
| GOLD 1.618 | 344 | +0.252 | +0.468 | +0.061 | +0.254 | 3.9% |
| BTC 1.618 | 276 | +0.096 | +0.119 | +0.073 | +0.176 | 23.7% |

Walk-forward held: TRAIN +0.274 (n=173) -> TEST **+0.229** (n=171).
Year by year, **6 of 7 positive** — and the one losing year (2025, −0.122) was
gold's *strongest* bull year (+64.6%), while 2022 (gold flat) made +0.209 with
the shorts doing the work. So it is **not** a simple drift artifact.

**But the concentration test kills it:**

| | |
|---|---|
| n / win rate | 344 / 29.9% |
| top 1 trade | **22% of all profit** |
| top 3 | **59%** |
| top 10 | **138%** |
| **excluding top 10** | **expR = −0.097** |

Ten trades out of 344 carry everything, and without them it is negative. Median
win +2.13R against a single +18.6R max. Same profile that killed the Mayne
Daily test and the deeper-entry variant.

Also: median stop distance is only **$5.67**, so spread eats **4.4% of risk** —
the expensive regime, and the opposite of the trader's own log ($23 stop, 1.1%).

## Verdict

**Not an edge.** A lottery-ticket payout distribution, not a repeatable one.
The walk-forward and year-by-year results are real but they measure a handful
of large winners, not a process. BTC does not confirm at significance.

## Three bugs found while building this — all inflated the result

1. Scored a mean hit rate against a breakeven from the **median** RR. High-RR
   trades hit less often, so the mix inflated every level by ~12pp.
2. **No holding limit** — in a market that went 1600->5000 a long waited years
   for any upside target while the loss stayed capped at −1R. The tell was
   expectancy rising monotonically all the way out to 2.618.
3. **Stale-price fill** — Point C is a swing low confirmed P bars later, so by
   the first actionable bar price has usually already rallied past C's candle
   high. Filling there buys at a price the market left behind. This was worth
   roughly +0.7R and affected longs and shorts equally.

Running tally for the project: nine bugs found, **nine of them flattering**.
