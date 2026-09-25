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
