# My own strategy search (gold 15m) — with a locked 2026 holdout

**Method:** Build on Jun 2022–Jun 2025, check on Jul–Dec 2025, then run the
final candidates **once** on the untouched 2026 data (Jan–Sep). Stops are scaled
by the daily ATR, so they mean the same thing at $1,800 and $4,300 gold.
Cost is $0.25 per trade.

## Search (108 variants: `own_search.py`)
The families tested were overnight drift, Asia/London/NY opening-range breakouts,
daily-open bias, 1h impulse follow/fade and trend entries at fixed hours.
The fades (bias fade, Asia-range fade) lost in every year. Two families survived
the build and check periods: the **NY opening-range breakout in the trend direction**
and **long positions held overnight**.

## What the stress tests showed
- **Overnight / long-only is mostly gold's bull market.** Buying during the day
  (03–11 ET) also made money over 2022–25. Longs were positive and shorts
  negative almost everywhere, so this is beta (gold going up), not timing.
  (An earlier overnight window test had a bug that held trades for about 32 hours.)
- **The NY breakout timing adds nothing.** Entering at a *random* time in the same
  window, in the trend direction, with the same stop, did as well or better
  (the breakout beat random in 0–2 of 20 runs).
- **Closing every trade by 16:00 ET** cuts the breakout to +0.05R (P=10%). The
  profit comes from holding up to 12h, into the evening and overnight.
- **The real ingredient is the trend filter:** 20h EMA vs 200h EMA on 15m
  (EMA 80 vs EMA 800), a wide stop (about the NY first-hour range or 0.5 daily ATR),
  a 2R target, and up to 12h of holding.

## Locked 2026 holdout (run once)
Gold in 2026: 4,891 (Jan) → 5,279 (Feb) → 4,006 (Jun) → 4,259 (Sep).

| strategy | build | check | **2026** | 2026 long / short |
|---|---|---|---|---|
| C1 NY 9–10 ET range breakout, trend dir, stop other side, 2R | +0.093 (n370) | +0.180 (n72) | **+0.064 (n89, P=30%)** | +0.051 / +0.078 |
| C2 trend-direction entry 10:00 ET, stop 0.5 dATR, 2R | +0.066 (n766) | +0.162 (n131) | **+0.034 (n183, P=33%)** | −0.013 / +0.079 |
| C3 long-only, same (pure beta benchmark) | +0.046 | +0.169 | **−0.029** | — |

## Verdict
- Following the trend beat blind buying in 2026. When gold turned down, the short
  trades made money and long-only lost.
- In 2026 it stayed **slightly positive, around breakeven** (+0.03 to +0.06R), but
  2026 alone is too short to prove it. All periods combined: C1 ≈ +0.10R/trade over 531
  trades; C2 ≈ +0.07R over 1,080.
- The stop in 2026 has to be wide: a median of $33 (C1) to $46 (C2). Stops of
  $5–8 (500–800 points) sit inside normal gold noise (see TREND_PULLBACK_POINTS_FINDINGS.md).
