# CORRECTION — several earlier verdicts were biased negative by over-filtering

**Read this before trusting any strategy verdict in the other FINDINGS docs.**

## What happened

The trader independently backtested the same Mayne playbook and produced
267 trades, 43.8% win at a strict 2:1, expR **+0.315**. Their log was verified
here against raw 15m data: **266/267 outcomes matched**, zero look-ahead (all
267 OB zones existed in price history before entry), every entry price inside
its bar, no overlapping trades. **Their backtest is clean.**

My encoding of the same playbook returned 44 trades and a negative result, and
I wrote "mechanically DISPROVEN". That was an overclaim: I had shown only that
*my particular encoding, at n=44, was negative*.

## Root cause (diagnosed, not guessed)

Comparing my model against their 267 entries:
- OB zone widths were nearly identical (theirs 10.7 pts median, mine 10.0) — the
  order-block detection itself was comparable.
- My HTF bias **disagreed with theirs on 28%** of entries.
- Only **41/267** of their entries fell inside my OB zones.
- Only **72/267** of their entries passed my premium/discount gate — i.e. **my
  extra filter alone rejected 73% of the trades that made their system work.**

My encoding choices were **systematically restrictive** (one-trade-per-setup
locks, strict entry triggers, distant targets, a hard premium/discount gate).
Not deliberate, but it leaned one direction and pushed results negative.

## Re-run under the trader's rules (2:1 target, zone reuse, permissive sweep+MSB)

`user_rules_harness.py`. Gold 15m 2022-2026. Cost = 0.25pt round-trip spread.

| Strategy family | n | expR (no cost) | expR (w/ cost) | original verdict |
|---|---|---|---|---|
| Mayne OB, my p/d gate ON | 82 | −0.195 | −0.334 | (the biased version) |
| Mayne OB, gate REMOVED | 351 | **+0.103** | −0.031 | **original was wrong** |
| FVG zones (all) | 267 | **+0.112** | −0.005 | **was over-filtered** |
| FVG + trend filter | 110 | **+0.118** | **+0.014** | **was over-filtered** |
| Swing levels — reversal | 1285 | −0.045 | −0.219 | **confirmed negative** |
| Swing levels — continuation | 622 | +0.051 | −0.103 | mostly confirmed |
| **trader's own Mayne** | 267 | **+0.315** | ~+0.284 | — |

## Status of the earlier verdicts

- **WITHDRAWN** (same failure mode: restrictive lock + my target choice + small n):
  Mayne playbook (n=44), Trident killzone (n=26), Volume Profile Rejection (n=40-78).
- **NEEDS RE-RUN under the trader's rules** (had the locks, but large samples and
  fixed 2R/3R targets were tested): Liquidity Run, Grab/Sweep, Inducement+FVG,
  Structure Sweep.
- **STANDS** — the measurement studies, which barely depend on rule encoding:
  gold volatility (6.7pt 15m ATR / 61pt daily range), ~80% of days tapping
  prior-day liquidity, sweep days ~1.7x larger, post-sweep direction test,
  MFE/MAE entry diagnostic, the 65-73% stop-out reversal finding, and the
  lot-size vs stop-distance arithmetic.
- **STANDS** — pure reversal setups are negative: 1285 trades, −0.219 with costs,
  P(expR<=0) = 100%.

## The open question (where the real edge is)

The trader's +0.315 vs my best de-filtered +0.112, on the same strategy, same
data, same management rules. The difference is **setup identification** — their
OB selection and bias detection, which this repo could not reproduce. That gap,
not trade management, is where their alpha lives.

Also note their own decay: 2022-23 expR +0.691 → 2024-26 expR +0.111 with a
95% CI of [−0.098, +0.318] (P(expR<=0) = 14.9%). The recent period is marginal
even in their clean test.

## Method changes going forward

1. Report a **range across structural variants**, never a single encoding.
2. State **n** and confidence up front; no "disproven" language under a few
   hundred trades.
3. Surface encoding decisions explicitly **before** running, so they can be overruled.

---

# PART 2 — the trader's engine also had look-ahead (resolved)

The trader shared their source (`data_loader.py`, `explain_trade.py`, `main.py`).
Their engine was replicated here in `mayne_lookahead_test.py`: it reproduced
n=403, win 45.4%, expR **+0.362** against their reported n=267 / 43.8% / +0.315 —
close enough to confirm faithful replication. Then the two timing issues were
isolated one at a time:

| Version | n | win | expR | P(expR<=0) |
|---|---|---|---|---|
| A — as written | 403 | 45.4% | **+0.362** | 0.0% |
| B — H4 waits for its bar to close | 322 | 39.1% | +0.174 | 1.5% |
| C — swings wait for 5-candle confirm | 593 | 38.6% | +0.159 | 0.4% |
| D — **both fixed, fully causal** | 525 | 35.6% | **+0.069** | **14.7%** |

**The edge falls 81% (+0.362 -> +0.069) and stops being significant.** With a
0.25pt round-trip spread on ~11pt stops it is roughly +0.046.

## The two leaks

1. **`pd.merge_asof(..., direction='backward')` mapping H4 context onto M15.**
   MetaTrader stamps an H4 bar at its OPEN, so an M15 bar at 09:00 inherits the
   OB/bias computed from the 08:00 H4 candle — which does not finish until 12:00.
   Up to **4 hours of future data** in the OB zone and the MSB flag.
2. **Swing marks used at their own bar.** A swing needs 5 candles to its RIGHT,
   so it is not knowable until 5 bars later — **20h on H4**, 75min on M15.

Fix (small):
```python
ctx.index = ctx.index + pd.Timedelta(hours=4)   # H4 known only after it closes
sh[i + length] = h[i]                           # swing known only after confirmation
```

*Caveat: `smc_utils.py` was not shared, so the swing-marking convention was
inferred. If `find_swings` already shifts by `length`, only leak #1 applies —
still +0.174, about half the reported figure.*

## Reconciliation — neither implementation was right

- Claude's original verdict: **wrong** (over-filtering, Part 1).
- The trader's +0.315: **inflated** by look-ahead in setup construction. Their
  trade *resolution* was genuinely clean — verified 266/267 against raw data.
- **The causal answer sits between them:** Claude's de-filtered build +0.112,
  the trader's engine fixed +0.069. Both land in the same marginal,
  not-statistically-significant zone.

This is the best current estimate for the Mayne playbook on gold: a small
positive expectancy that does not clear significance and is largely consumed
by spread.
