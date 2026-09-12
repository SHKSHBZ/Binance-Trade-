# Fibonacci Level Study — what the measurement says

Measurement only (no trades). We drew a Fib on every **real 1H leg** (a swing of
at least 2%), waited for price to pull back into the **0.5 zone** (the entry),
then raced each target against **invalidation** (price breaking the 1.0 level,
i.e. the leg's origin). Causal throughout — a leg is only used once its swing
pivot is confirmed. `research/fib_level_study.py`.

## The raw reaction (very consistent across 2023–25 and 2026)

| From a 0.5-zone entry… | 2023–25 | 2026 |
|---|---|---|
| price enters the 0.5 zone at all | 92% | 91% |
| reaches TP1 (0.3) before failing | 57% | 59% |
| reaches TP2 (0.0, prior extreme) | **36%** | 35% |
| reaches TP3 (1.272 extension) | 30% | 27% |
| **breaks 1.0 first (move fails)** | **60%** | 61% |

## What this means (the honest read)

1. **The 0.5 pullback is not selective.** ~92% of real legs pull back into the
   0.5 zone — so "wait for a 0.5 retrace" filters out almost nothing.

2. **Naive Fib continuation is a LOSER on its own.** Enter at 0.5, stop at 1.0:
   risk and the TP2 reward are equal (1:1), so you need a 50% hit rate to break
   even. Actual is **36%**. Every target, checked against its required break-even
   win rate, comes up short:
   - TP1 0.3 → needs 71%, gets 57%
   - TP2 0.0 → needs 50%, gets 36%
   - TP3 1.272 → needs 39%, gets 30%
   So a plain "buy the 0.5 pullback, expect continuation" edge is **not there.**

3. **The more common outcome is failure, not continuation.** Once price reaches
   the mid-leg (0.5), it breaks the origin (1.0) **~60%** of the time vs
   returning to the extreme ~36%. On BTC 1H, a half-retraced leg more often
   keeps going against the leg than resumes with it. That points at the
   **opposite trade** (fading the leg / reversal) as the more promising side —
   worth testing next.

4. **The daily-trend filter helps — but only in 2026.** With-trend vs
   against-trend: 2026 separates cleanly (TP2 44% vs 27%, failure 51% vs 72%),
   but 2023–25 barely moves (37% vs 36%). So the filter is promising, not proven.

## Where this leaves us

The measurement did its job: it killed the naive continuation version cheaply,
and it surfaced two real leads to design and backtest properly (with the
expectancy/Sharpe/"edge-is-real" scoreboard):
- **the reversal/fade** (bet the 0.5-retraced leg breaks its origin), and
- **the trend-filtered continuation** (only the with-trend legs, tighter stop).
