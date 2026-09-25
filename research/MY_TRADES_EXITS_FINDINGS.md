# The trader's own 82 trades replayed with different exits (`my_trades_exits.py`)

Same entries and same stops, only the exit changes. The replay reproduces all 82 recorded
wins and losses (trade times are UTC). Cost is $0.25 per trade.

## How far the trades ran before the stop (max 5 days)
| reached | 1R | 2R | 3R | 4R | 5R | 6R | 8R |
|---|---|---|---|---|---|---|---|
| trades | 52% | 38% | 26% | 23% | 17% | 15% | 10% |

## Exit rules
| exit | total R | 2025 | 2026 | worst losing streak |
|---|---|---|---|---|
| **Actual: target 2R** | **+10.0** | +6.3 | +3.7 | 6 |
| target 1R | +3.0 | +4.3 | −1.3 | 6 |
| target 3R | +4.1 | +2.3 | +1.9 | 12 |
| target 4R | +21.1 | +13.3 | +7.8 | 12 |
| **trail 1.5R once +1.5R, no target** | **+15.1** | +6.1 | +8.9 | 6 |
| 2R + stop to breakeven at +1R | 0.0 | +1.3 | −1.3 | 12 |
| 3R + breakeven at +1R | −10.0 | −0.7 | −9.3 | 23 |
| half off at 1R, rest to 3R | −3.5 | +1.8 | −5.3 | 6 |
| 2R but closed by 16:45 NY | +1.6 | +4.6 | −3.0 | 6 |

## Reading
- **Moving the stop to breakeven early destroys the edge** (+10R → 0R, and down to −10R with a 3R target).
- **Forcing trades to close by the end of the NY day** cuts +10R to +1.6R. The winners need time.
- **A trailing stop that starts at +1.5R** beat the fixed 2R in both 2025 and 2026 (+15.1R vs +10.0R),
  with the same worst streak.
- The 4R result is lumpy: only 2 trades ended between 3R and 4R, so it depends on a few trades.
  Treat it as "winners can run", not as a precise rule.
- With 82 trades, differences of a few R can be luck. Only the breakeven and intraday-close
  results are large enough to be confident about.
