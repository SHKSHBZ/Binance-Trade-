# Gold Structured Strategy: Pullback into a Level, with the Trend

Built from the trader's own 82 trades, then tested on 3 years of data from **before** the first trade.
TradingView strategy to test it yourself: `tools/pullback_trend_strategy.pine`.

## Chart: XAUUSD 15-minute

### 1. Direction (the bigger picture)
EMA 80 above EMA 800 means **buys only**. Below means **sells only**. (73 of the trader's 82 trades already did this.)

### 2. Session: London time (on a UTC chart such as Exness: same hours in winter, 1 hour earlier in UK summer, e.g. 06:00–20:00 UTC)
| session | trade? | result in all 3 test periods |
|---|---|---|
| Asia 00:00–07:00 | **NO** | lost in all 3 (−0.16 / −0.33 / −0.28R) |
| London 07:00–12:00 | yes | +0.02 / +0.41 / +0.39R |
| NY–London overlap 12:00–16:30 | yes, the most volatile | +0.17 / +0.27 / +0.09R |
| NY afternoon 16:30–21:00 | yes | +0.07 / +0.06 / +0.08R |

### 3. Setup: a fast move into your level
- Over the last **4 hours** price moved **against** the trend by at least **0.15 × daily ATR** (about $10–15 at 2026 prices).
  This is price coming fast into your support (in an uptrend) or resistance (in a downtrend).
- **Slow crawls into a level: skip.** In the trader's log, fast approaches made +16.6R and slow ones lost −6.6R.

### 4. Only on a moving day
15m candles are bigger than usual (1.2× their 5-day average), **or** a news-sized candle (3× normal) already printed today.
In the trader's log: moving days +17.6R, quiet days −7.7R.

### 5. Confirmation
The **last hour** has already turned back in the trend direction. Enter on the 15m close.

### 6. Stop and target
- **Stop:** just beyond the pullback's extreme (lowest low of the last 4h for buys) plus 0.05 × daily ATR.
  Skip the trade if the stop is under 0.15 or over 0.6 × daily ATR.
- **Target:** 2R. Do **not** move the stop to breakeven early (in the trader's log that turned +10R into 0R).
- One trade at a time.

### 7. Size
Risk **2% of the account** per trade. Lot size = (account × 2%) ÷ (stop distance in $ × 100).
On $5,000 with a $25 stop that's $100 ÷ $2,500 = **0.04 lots**.

## Results (costs included, rules fixed before each check)
| period | trades | win % | avg per trade | total |
|---|---|---|---|---|
| Jun 2022 – Jun 2024 (session rule chosen here) | 329 | 38% | +0.11R | +34.8R |
| Jul 2024 – May 2025 (check) | 131 | 41% | +0.21R | +27.2R |
| May 2025 – Sep 2026 (trader's own period) | 174 | 39% | +0.14R | +24.6R |
| **all** | **634** | **39%** | **+0.14R** | **+86.7R** (P(luck) 0.8%) |

$5,000 at 2% risk from June 2022 would have ended at **about $21,600**. Year ends: 2022 $5,026, 2023 $11,019,
2024 $10,695, 2025 $15,595, 2026 $21,602. About 3 trades a week.

## Be ready for
- Worst drawdown **−31%**; longest losing streak **13 trades**. 2024 was a slightly losing year.
- Win rate is under 40%: most trades lose, and the 2R winners pay for them.
- Random entries in the trend with the same stops also made money (+0.08R). A good part of the edge is simply
  **trend + stop behind the pullback**; the pullback/turn/moving-day rules add the rest.
