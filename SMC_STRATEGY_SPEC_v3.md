# SMC Strategy Spec v3 — Frozen Rulebook for Backtesting

This is playbook v2 with the six review drawbacks fixed and every parameter
marked **FROZEN** (do not optimize) or **TUNABLE** (the small set we're
allowed to search, on in-sample data only). It targets **BTCUSDT** on a
single execution timeframe. Gold gets its own repo later.

Nothing here is claimed to be profitable. This is the exact, causal
definition we backtest so the numbers mean something.

---

## 0. What changed from v2 (the six fixes)

1. **No look-ahead when reading the labeler.** The backtest consumes
   `smc_luxalgo.py` output *as-of each bar*: an order block is only usable
   from its `created_index` (the bar its structure break confirmed it),
   never before; a swing level is only usable from its confirmation bar
   (already `swing_length` bars after the extreme). We never read a value
   the finished full-history labeling reveals early.
2. **Trailing uses a FAST structure.** Trail on **Internal-5** confirmed
   swing lows/highs (≈5-bar lag), not Swing-50 (≈50-bar lag, which barely
   moves and protects nothing).
3. **Entry timeframe decided: 15-minute, single-timeframe.** Swing-50 (≈
   12.5h of structure) IS the "big-picture trend"; Internal-5 is the fast
   structure. This matches the validated BTC `smc_engine`. The old "1H
   trend filter" is deliberately replaced by the Swing-50 trend, not left
   dangling.
4. **Parameter budget enforced.** ~12 parameters are FROZEN at sensible
   defaults; only **3 are TUNABLE** (swing length, ATR break multiple,
   min reward:risk). A strategy that needs all 15 tuned is a curve, not an
   edge.
5. **Scenarios 2/3/5 defined to the same rigor as A/B** (below).
6. **Volume filter made meaningful** (≥ 60th percentile, not the median)
   and marked FROZEN/off for the v1 BTC run.

---

## 1. Primary hypothesis (what we test first)

**Scenario 2 — pullback into an unmitigated order block, in the trend
direction.** Chosen as the primary because it's the highest-quality setup
and is closest to the already-validated BTC engine. The other five
scenarios are **exploratory**, reported separately, and never allowed to
be the headline result (multiple-comparisons discipline).

---

## 2. Fixed definitions (the eyeball words)

| Term | Exact rule | Status |
|---|---|---|
| Trend | `swing_trend` from Swing-50 structure (bullish / bearish / none) | FROZEN |
| Order block | From the labeler; usable only when `created_index ≤ i` and not yet mitigated as of `i` | FROZEN |
| Rejection candle (bull) | `(close-low)/(high-low) ≥ 0.66` **and** `close > open` | FROZEN |
| Rejection candle (bear) | `(high-close)/(high-low) ≥ 0.66` **and** `close < open` | FROZEN |
| "Price reached the zone" | bar's `low ≤ ob.top` (long) / `high ≥ ob.bottom` (short) | FROZEN |
| "Closes clearly beyond" | `close − level ≥ ATR_break_mult × ATR(14)` | TUNABLE (mult) |
| Target | nearest **unbroken** opposing Swing-50 level in trade direction, known as-of entry; must clear min R:R or the trade is skipped | FROZEN |
| ATR (stops/breaks) | `ATR(14)` on the 15m series | FROZEN |

---

## 3. Scenario 2 — the primary setup (long; short mirrors)

Precondition: `swing_trend == bullish` and no open position.

1. A **bullish order block** exists that is known (`created_index ≤ i`) and
   **not yet mitigated** as of bar `i`.
2. The current bar **trades into** the block: `low ≤ ob.top`.
3. The current bar is a **bullish rejection candle** (Section 2).
4. **Entry** = close of that candle (market), plus slippage.
5. **Stop** = `ob.bottom − 0.25 × ATR(14)`.  (FROZEN buffer)
6. **Target** = nearest unbroken Swing-50 high above entry, known as-of
   entry. If `(target − entry) / (entry − stop) < min_RR`, **skip**.
7. **Regime gate**: take only if `ADX(14) ≥ 25`. `20–25` allowed but
   flagged in stats; `< 20` blocked. (Reported both on and off.)

---

## 4. The other scenarios (exploratory, defined for later)

- **Scenario 1 / Strategy A (breakout-continuation):** enter at close of a
  break candle when `close beyond Swing level ≥ ATR_break_mult × ATR(14)`,
  volume ≥ 60th pct of last 20, `RSI(14) < 85`. Stop = pre-break swing ±
  0.25 ATR. Same target/R:R rule.
- **Scenario 3 (CHoCH reversal):** on a confirmed Swing CHoCH, wait for a
  pullback to the broken level and a rejection candle *against* the old
  trend; entry on that candle's close. Highest precedence.
- **Strategy B (grab-reversal):** wick beyond a level that fails Strategy
  A's close test; if price closes back on the original side by bar N+2
  (N=2 FROZEN), enter on N+2 close. Mutually exclusive with A.
- **Scenario 5 (range):** only when regime = chop (`ADX < 20`). Range
  top/bottom = current `trailing_top`/`trailing_bottom` from the labeler.
  Buy within the bottom third, sell within the top third, stop just
  outside the range.
- **Scenario 6 (premium/discount):** filter only, never a trigger. Prefer
  longs in discount, shorts in premium (from labeler zone columns).

Precedence when several fire on one bar: 3 → B → A → 2 → (6 filter). Same
priority + same bar ⇒ **skip and log a conflict.**

---

## 5. Risk & trade management (FROZEN unless noted)

- **Risk per trade:** 1% of equity, fixed. No martingale.
- **Min reward:risk:** 2:1. **TUNABLE** (test 1.5 / 2 / 2.5).
- **Max concurrent:** 1 position.
- **Breakeven:** at +1R, move stop to entry.
- **Trailing (after BE):** to each new **Internal-5** confirmed swing low
  (long) / high (short). Never backward.
- **Time-stop:** if +1R not reached within **20 bars**, close at market.
- **Partial (Variant A):** 50% off at +2R, remainder trails. **Variant B**
  takes no partial (full exit at target). Both reported; neither assumed
  better.
- **RSI partial (separate variant):** if `RSI(14) ≥ 80` while past BE, take
  25% more off. Tested in isolation, not folded into the default.

---

## 6. The 3 tunable parameters (everything else is frozen)

| Parameter | Default | Search grid (in-sample only) |
|---|---|---|
| `swing_length` | 50 | 30 / 50 / 70 |
| `ATR_break_mult` | 0.5 | 0.4 / 0.5 / 0.6 |
| `min_RR` | 2.0 | 1.5 / 2.0 / 2.5 |

If a small change in any of these swings the result wildly, that parameter
is fragile → treat the "edge" as suspect, not real.

---

## 7. Costs (BTCUSDT, USD-M futures)

- **Taker fee:** 0.04% per side.
- **Slippage:** 0.02% on entry and on stop fills (gold-style wick risk is
  worse; BTC is tighter).
- Every result reported **gross and net**.
- Fills: a resting level fills when the bar's range touches it. If a bar
  could hit both stop and target, assume **stop first** (conservative).

---

## 8. Validation protocol (non-negotiable)

- **In-sample:** 2023–2024. **Out-of-sample:** 2025 + Jan–Jul 2026. Tune
  ONLY on in-sample; OOS is a one-shot exam.
- **Benchmark:** same risk framework with random entries (like the BTC
  engine's 40-run check). The entry must beat random, or there's no edge.
- **Report:** trades, win rate, expectancy (R), profit factor, max
  drawdown, and the equity curve — per scenario, gross and net.
- **Reminder:** "tweak until it matches the chart" = curve-fitting. We tune
  on in-sample and let OOS judge. Matching the visible market is not the
  goal; surviving the unseen market is.
