# Trend + Order Block — edge was a one-bar look-ahead

Synthesis test: trend filter (price vs 1H SMA200) for direction, order block (from
the verified SMC labeler) for entry timing, chandelier trail to let winners run.
Compared to a trend-only (SMA50 pullback) baseline. `research/trend_ob_system.py`.

## The trap (and how it was caught)

First result looked excellent: trend+OB pooled +82%, Sharpe 1.00, edge 97%,
positive in all 4 years -- while trend-only lost -188%. It looked like the OB was
the missing entry.

Robustness check: the OB-creation itself is causal (verified by a truncation
test -- OBs created before bar K are identical whether the labeler sees the future
or not). BUT the backtest let a trade FILL on the SAME bar the OB was confirmed,
using that bar's intrabar low -- acting ~1 bar before the OB was actually known.

Forbidding same-bar entry (fill only from the bar AFTER confirmation) collapses it:

| Version | Pooled | +years |
|---|---|---|
| same-bar entry (leaky) | +82% | 4/4 (FALSE) |
| strict next-bar entry, 0.03% slip | -38% | 0/4 |
| strict next-bar entry, 0.05% slip | -51% | 0/4 |
| strict next-bar entry, 0.10% slip | -80% | 0/4 |

## Verdict

The order block adds NO real edge once entries are strictly causal (it is only
less-bad than an SMA50 pullback: -38% vs -188%). The +82% was a one-bar fill
illusion -- the same failure mode as the prior-day-level fades: a level-limit
backtest looks great until you require the fill to be genuinely reachable in time.

Lesson locked in: any level/OB entry MUST be tested with strictly-after-confirmation
fills, or it will lie. Trend direction + let-winners-run remains the only robust
piece; the entry-location signals (OB, Fib, prior-day) do not add a real edge on BTC.
