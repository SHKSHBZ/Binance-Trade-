# SMC Bot — Stop-Loss & Entry Investigation (findings)

A plain-language record of what we tested after noticing the stop-losses
looked wrong, and what we concluded. Written so someone who wasn't in the
process can follow it. All tests are on **BTCUSDT, 15-minute candles**, in
a **backtest** (simulated on historical data — no real money), risking
**1% of a $1,000 account per trade**.

---

## 1. The strategy in one paragraph

The bot waits for price to **sweep a 4-hour high or low** (grab the
liquidity where stop-losses sit), then for the 15-minute structure to
**break the other way** (a "change of character"), then drops a **limit
order at an order block** and targets the next opposing liquidity, needing
at least a **2:1 reward-to-risk**. It's patient — roughly 1–2 trades a
week.

## 2. What started this: the stop-losses looked "mental"

Looking at the actual April–July 2026 trades, several stops made no sense —
some were **$5 away** from a $72,000 entry, and a few were on the **wrong
side of the entry entirely** (a short with its stop *below* the entry).
Those trades opened and closed almost instantly.

**The cause (a real bug):** the entry and the stop were measured from two
different places.
- **Entry** = the middle of the order block.
- **Stop** = the sweep wick (a *different* candle), ± 0.3%.

When those two points collided, the stop ended up microscopic or inverted.
6 of 16 trades in that window had this problem.

**Why it mattered more than it looked:** those broken trades were
*accidentally profitable* in the backtest (a wrong-side stop acts like a
tiny take-profit), so they inflated the results. Stripping them out:

| Year | All trades | "Real" trades only |
|---|---|---|
| 2025 | 79 trades, +$1,054 | 30 trades, 33% win, **+$307** |
| 2026 | 30 trades, +$663 | 15 trades, 13% win, **−$24 (loss)** |

So the headline win rate (~40%) was largely the bug. The real win rate is
much lower, and 2026 was actually a small loss once the junk was removed.

## 3. Every stop-loss rule we tested

We rebuilt the stop as a configurable setting (the old behaviour stays the
default, so the validation check still passes) and tried seven rules, with
a proper minimum distance so no more $5 stops:

| Stop rule | 2025 net | 2026 net |
|---|---|---|
| Original (sweep ±0.3%, buggy) | +$1,054 | +$663 |
| **Fixed 200 points** | **+$1,536** | **−$76** |
| Fixed 300 points | +$1,037 | +$44 |
| Fixed 500 points | +$604 | +$42 |
| Previous-candle low + 200pt floor (a manual rule) | +$1,265 | −$75 |
| **ATR × 0.5 (volatility-based)** | +$1,069 | **+$113** |
| Previous S/R level | +$680 | −$96 |

**What we learned:**
- A **tighter** stop (fixed 200) makes the *most* in 2025 but **loses** in
  2026. A tight stop isn't a smarter edge — with fixed 1% risk it just buys
  a *bigger* position, magnifying both wins and losses. It's a variance
  dial, not an edge.
- The **volatility (ATR) stop was the most consistent** — positive in both
  years.
- But the real win rate stays ~15–25% whatever stop we use, and no stop
  fixes 2026. **Changing the stop just moves the money between years.**

## 4. "What stop would have saved the losing trades?"

For every losing trade we checked: did price *eventually* reach the target
if we'd used a wider stop, or did it just keep going against us?

| Year | Losers that would've won with a wider stop | Losers that never reached target |
|---|---|---|
| 2025 | 64% (needed a ~1.45% stop) | 36% (entry just wrong) |
| 2026 | 67% (needed a ~2.26% stop) | 33% (entry just wrong) |

**The insight:** ~2/3 of losers *do* eventually go the predicted way — but
only after moving 1.5–2% **against** us first. That's the "we hunt
liquidity, so we become the liquidity" effect: the **entry is too early**,
so price takes our stop before running to target. This pointed us away from
the stop and toward the **entry**.

## 5. Every entry we tested

**Entry depth** (how deep into the zone the limit sits), stop held constant:

| Entry depth | 2025 net | 2026 net |
|---|---|---|
| Midpoint (original) | +$1,069 | +$113 |
| Deeper (0.25) | +$249 | +$4 |
| Far edge (0.0) | +$157 | −$75 |
| Beyond the block | −$49 to −$312 | +$65 to +$255 |

Deeper entries were **worse** in 2025 and better in 2026 — the years
contradict each other. Reason: a deeper limit only fills when price pushes
*further* through the zone, which selects for the setups that were
**failing**. You can't dodge the hunt by entering deeper, because in real
time a dip that reverses and a dip that keeps going look identical.

**FVG entry** (enter inside the fair-value-gap instead of the order block —
a classic SMC entry we'd been using only as a filter). Tested across four
separate years:

| Year | Order-block entry | FVG entry |
|---|---|---|
| 2023 | −$135 | −$155 |
| 2024 | +$148 | −$153 |
| 2025 | +$1,069 | +$275 |
| 2026 | +$113 | **+$614** |
| **Total** | **+$1,195** | +$582 |

FVG entry looked great in 2026 but **lost in 2023 and 2024** and made less
overall. Its 2026 win didn't repeat — adopting it would've been fitting to
one lucky year.

## 6. Other cuts we checked for a hidden edge

- **Long vs short:** over 3 years, nearly identical (39% vs 36% win). No
  edge in one direction.
- **Market regime (bull/bear/sideways):** no direction/regime combination
  cleanly separates winners from losers.
- **2026 shorts specifically:** 21 taken, but only **3** hit target; **two
  trades (+$126 and +$332) made the entire year's profit.**

## 7. The bottom line

Look at the base strategy across **four separate years**:

| 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|
| **−$135** | +$148 | **+$1,069** | +$113 |

**The strategy's entire profit is 2025** — a strong, clean bull year for
Bitcoin. Three of the four years are flat-to-losing.

We tested **7 stop rules, 5 entry depths, FVG entry, long/short, market
regime, and 4 separate years.** Every change we made only shifted *which*
year looked good. Nothing produced a consistent edge across years. That is
the definition of a strategy **without a robust edge** — it rode one good
market, it didn't beat the market.

**Conclusion:** this specific SMC sequence should **not** be traded live
expecting the 2025 numbers. Those were one year, not a repeatable edge.

## 8. What this exercise was actually worth

This is the backtesting process **working**. We discovered — on historical
data and fake money — that the edge isn't real, *before* risking anything
live. What remains genuinely valuable:
- a verified SMC labeler that correctly finds BOS / CHoCH / order blocks /
  FVGs / liquidity on any data;
- an honest, rigorous backtest harness with configurable stops and entries;
- and clear, documented proof of what does **not** work — which saves the
  next attempt from repeating it.
