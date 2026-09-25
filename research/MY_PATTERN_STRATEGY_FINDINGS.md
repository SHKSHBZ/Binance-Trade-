# Strategy extracted from the trader's own 82 trades

Scripts: `my_trades_anatomy.py` (context of every trade), `my_trades_patterns.py` (what separates
wins from losses), `my_trades_report.py` (per-trade explanation → `MY_82_TRADES_EXPLAINED.md`),
`my_pattern_strategy.py` (mechanical test).

## What separated the trader's wins from losses (true in both halves of the log)
| setup score | trades | win % | total R |
|---|---|---|---|
| **3/3: pullback + with trend + volatile day** | **26** | **62%** | **+21.7R** |
| 2/3 | 36 | 31% | −3.5R |
| 1/3 | 19 | 16% | −10.2R |

- **Pullback:** the last 4h moved against the trade: 60 trades, +17.2R. Chasing (last 4h already moved the trade's way): 18 trades, −6.2R.
- **Trend:** with EMA80/800 on 15m: 73 trades, +13.0R. Against: 9 trades, −3.1R.
- **Volatile/news day:** 36 trades, +17.6R. Quiet days: 46 trades, −7.7R.
- **Things that did not matter:** a liquidity sweep just before entry (+1.6R vs +8.4R without one) and RSI.
- **Losses:** 11 of 51 were stop hunts (price went on to the 2R target within 24h). 12 were +1R in profit
  before reversing. Only 2 were stopped out within the first hour.

## Mechanical version (rules fixed before testing older data)
15m gold. Direction = EMA80 vs EMA800. Last 4h moved ≥0.15 daily ATR against the trend, and the
last 1h moved with it. Volatile day. 02:00–16:00 New York time. Stop beyond the last-4h extreme
+0.05 daily ATR (skip if <0.15 or >0.6 daily ATR). 2R target, or trail 1.5R once +1.5R.

| period | trades | avg R | total | P(luck) | random in-trend entries, same stops |
|---|---|---|---|---|---|
| **2022-06 → 2025-05 (before the trader's first trade)** | 474 | **+0.113** | +53.5R | 4% | +0.084 |
| 2025-05 → 2026-09, 2R | 186 | +0.131 | +24.4R | 10% | +0.061 |
| 2025-05 → 2026-09, trailing | 183 | +0.282 | +51.6R | 1.6% | — |

About 3 trades a week. $5,000 at 2% risk: **$18,000** with the 2R target (worst drawdown −31%, 12 losses in a row
at worst, 2024 a losing year) or $26,600 with the trailing stop (worst drawdown −50%).

**Caveat:** random entries in the trend with the same stops were also positive (+0.08R in the clean
period). Most of the edge is trend plus a stop behind the pullback; the trader's timing adds about +0.03R.
In 2022–25 the buys carried it (+0.22R) and the sells lost (−0.08R). In 2025–26 the sells made +0.27R.

## The trader's own description: "I trade support/resistance on 1H/4H/15m/5m, inside the range"
`my_trades_levels.py`: 81 of 82 entries were at a swing level (62 at 4H levels). There is no 5m gold data, so 5m levels were not checked.

| at the level... | trades | win % | total |
|---|---|---|---|
| **level held** (price did not poke through before entry) | 54 | 48% | **+23.3R** (both halves +) |
| price poked through first | 27 | 19% | **−12.3R** (both halves −) |
| at a level on a volatile day | 35 | 51% | +18.7R |
| at a level on a quiet day | 46 | 28% | −7.7R |

`my_sr_strategy.py`: plain mechanical 4H swing-level bounce (touch without poke, rejection candle,
stop beyond the level, 2R): **−0.11R** before 2025-05, **−0.21R** in the trader's own period.
With the trend added: −0.11R / −0.07R. **The mechanical level bounce does not reproduce the trader's result.**
The trader picks levels and timing in a way a pivot rule doesn't capture. The measurable version that does
work on older data is the pullback-in-trend rule above: the end of the pullback is where the trader sees the level.

## The trader's stated method: yesterday's high/low as S/R, fast approach, wait for confirmation
`my_pdhl_check.py` (the trader's 82 trades): a fast approach into the level (last 4h ≥0.14 dATR toward it)
gave 32 trades, 53% win, **+18.6R** (both halves positive). Slow/medium approaches: 50 trades, −8.6R.
Only 32 of 82 entries were within 0.25 dATR of yesterday's high/low, so other levels were used too.

`my_pdhl_strategy.py` (mechanical, UTC days, rules fixed first):
| version | 2022-06 → 2025-05 (clean) | 2025-05 → 2026-09 |
|---|---|---|
| **PDH/PDL + fast approach + confirmation candle, 2R** | **+0.114R, 395 trades, P=6%** (buys +0.25, sells −0.02) | **−0.111R**, 153 trades (buys −0.31, sells +0.09) |
| without the speed check | +0.008R | −0.036R |
| slow approach only | −0.129R | +0.114R (49 trades) |
| without the confirmation candle | +0.059R | −0.157R |
| + volatile day | −0.011R | +0.162R |

In the clean period the speed check and the confirmation candle both help, and the method made +45R there,
mostly from buys during the gold bull run. In the trader's own period the code lost −17R while the trader made +10R.
Over the whole period it is about +0.05R per trade. The trader's live choice of which touches to take does
better than the rule; the code alone is not reliable.

## Where the 2025–26 trades really were, and why they don't match the stated rules (`my_trades_vs_rules.py`)
Only **5 of 82** trades met every stated rule (at yesterday's H/L, fast approach, 15m confirmation candle, level not already closed through).

| level actually used | trades | win % | total |
|---|---|---|---|
| **yesterday's high (sells)** | 22 | 50% | **+10.7R** |
| yesterday's low (buys) | 24 | 25% | −6.3R |
| **4H swing low (buys)** | 14 | 57% | **+9.8R** |
| 4H swing high (sells) | 15 | 33% | −0.2R |
| today's earlier high/low (set more than 4h before) | 7 | 14% | −4.1R |

- **Most common reason for not matching: slow approach.** 51 trades came in slowly (−6.6R); 31 came in fast (+16.6R).
- **36 trades were not at yesterday's H/L at all**, mostly at 4H swing levels.
- The 15m "confirmation candle" did not help (with: +3.2R, without: +6.8R). The trader probably confirms on
  the 5m chart, and there is no 5m gold data to check that.

**Code vs trader in 2025–26:** of the code's 153 trades, the 16 the trader also took made **+4.8R**. The 137 the
trader skipped made **−21.7R**, and the skipped *buys* alone lost −26.8R. The trader's edge in this period came
from *not* buying most of the touches of yesterday's low.
