# Gold Merge — how to read it (1 page)

**Chart:** XAUUSD, **1-hour** candles only. Load at least ~4 months of history
(scroll the chart back) so the orange level is calculated properly.

## The 6 lines

| Line | Meaning |
|---|---|
| **Trend line GREEN** | Only look for **BUY** trades |
| **Trend line RED** | Only look for **SELL** trades |
| **Trend line GRAY** | **SKIP. No trades.** |
| **ORANGE** | The major level to watch |
| **GRAY (flat)** | Line in the sand |
| **AQUA / RED / GREEN (flat)** | **ENTRY / STOP / TARGET — a trade is ON** |

## TAKE the trade when
1. The ENTRY (aqua), STOP (red) and TARGET (green) lines **appear**, and
2. the candle that made them has **CLOSED** (the lines can flicker while a
   candle is still forming — wait for the close), and
3. price is still near the entry line (not already 1/3 of the way to target).

Then: place the trade at market, stop on the red line, take-profit on the green line.

## SKIP when
- Trend line is **gray**.
- No aqua/red/green lines on the chart — there is no trade.
- You're late: price has already moved more than 1/3 of the way to the target.
- Stop is wider than **$60** (lot would be below 0.01 at $2,000).

## Lot size — 3% risk on $2,000 ($60)
**lot = 0.6 ÷ stop distance in $**  (stop distance = entry line − stop line). Always round **down**.

| Stop distance | Lot |
|---|---|
| $3 | 0.20 |
| $5 | 0.12 |
| $6 | 0.10 |
| $8 | 0.07 |
| $10 | 0.06 |
| $15 | 0.04 |
| $20 | 0.03 |
| $30 | 0.02 |
| $60 | 0.01 |

Typical stop is about **$5.60**. When the account grows, redo it: lot = (balance × 0.03) ÷ (stop × 100).

## While the trade is open — do NOTHING
- Don't move the stop. Don't move to breakeven (measured: it hurts).
- Don't take half profit early (measured: worst rule tested).
- If neither stop nor target is hit after ~100 hourly candles (~4 trading
  days), close it. The lines disappear when the trade is over.

## What to expect
- About **40 trades a year**. You **lose 2 out of 3**. The 3× target pays for it.
- Losing streaks of **10–11 in a row** happened in the backtest. At 3% risk
  that is about a **28% drop**. It is normal. Don't change the rules during it.
- Backtest 2020–2026: +0.25 to +0.28R per trade. Real trading will be worse.
- Works on **gold only**. Tested on Bitcoin: does not work there.

**Paper-trade it for 2–3 months before using real money.**
