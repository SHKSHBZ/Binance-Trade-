# Marco Trade's Liquidity Playbook — the first candidate to survive walk-forward

Code: `marco_liquidity.py`. Gold, M30 levels / M15 entry (M5 pending).
Causal by construction: an M30 swing is confirmed pivot+P bars later AND only
usable by the LTF after that M30 bar has closed; "respected" displacement is
measured only with bars up to confirmation. Cost = 0.25pt round-trip spread.

## Rules (from the PDF, verbatim intent)
- Mark a high/low that was **respected and caused price to move away** -> resting liquidity.
- Wait for price to **trade beyond** it (run stops), fail, and **close back across** = the trap.
- Swept **high -> SHORT**, swept **low -> LONG** ("buy below lows, sell above highs").
- Stop **beyond the sweep wick** ("always cover the last high/low").
- Target the **opposing respected liquidity pool** — not a fixed R.
- One trade per level; a level is consumed the moment price sweeps it.
- Strict **session window**; ignore price action outside it.

## Headline: as specified (no session filter) it LOSES, on a big sample

| Target mode | n | win | expR | P(<=0) |
|---|---|---|---|---|
| nearest opposing pool | 2698 | 31.3% | −0.052 | 90.1% |
| furthest opposing pool | 396 | 8.6% | −0.253 | 82.4% |
| fixed 1.5R | 2868 | 40.2% | −0.062 | 99.6% |
| fixed 2R | 2476 | 33.3% | −0.066 | 99.1% |
| fixed 3R | 1915 | 24.8% | −0.075 | 96.6% |
| fixed 5R | 1345 | 16.6% | −0.072 | 87.8% |

Unlike the Mayne test, the **target definition does not rescue it** — every mode
clusters near −0.06. Well-powered negative.

## The exception: London session + nearest opposing target

| | n | win | expR | P(<=0) |
|---|---|---|---|---|
| TRAIN 2022-06→2024-12 | 422 | 34.4% | **+0.077** | 23.1% |
| **TEST 2025-01→2026-09 (unseen)** | 231 | 30.7% | **+0.076** | **33.5%** |

**expR held out-of-sample (+0.077 -> +0.076).** Every earlier candidate inverted
at this step; this one did not.

It is a **plateau, not a spike** — in the unseen period K=0.5 and K=1.0 are
positive across all WAIT values (6 cells: +0.039 to +0.076), with a clean
boundary at K=2.0 (negative).

Session contrast, unseen period: London 07-10 **+0.076**, NY 13-16 +0.043,
Asia 00-04 **−0.270**, no filter −0.107. The session filter carries real
information — an interpretable mechanism, not a fit.

## Honest status
**NOT statistically significant: P(expR<=0) = 33.5%.** ~1 in 3 chance it is
still noise. Magnitude is modest: ~139 trades/yr x 0.076R ~ +10%/yr at 1% risk.

This is the strongest result in the whole research program — the only candidate
with (a) a real sample, (b) an out-of-sample hold, (c) a parameter plateau, and
(d) an interpretable mechanism. It is a *lead*, not a proven edge.

## What would settle it
1. **M5 entry data** (the playbook's actual LTF) — more setups, finer traps.
2. **Other instruments** — the playbook claims it is fractal/asset-agnostic, so
   it should hold on BTC/FX. That is a genuine independent test.
3. **More out-of-sample time.**

## Run
```
python3 -c "import marco_liquidity as m; print(m.run(K=1.0, sess=(7,10), tgt_mode='near')[0].mean())"
# run(ltf_file, start, end, P, K, WAIT, sess, eq_only, spread, tgt_mode, fixed_rr)
```

---

# INDEPENDENT TEST ON BTC — did NOT replicate

The playbook claims the model is "Fractal... Fits Any Asset." Ran the exact
gold-winning config on BTC 15m (2023-2026), cost 0.02% round trip.

| BTC session | n | win | expR | P(<=0) |
|---|---|---|---|---|
| **London 07-10 (the gold config)** | 731 | 30.2% | **−0.108** | **95.0%** |
| NY 13-16 | 1076 | 36.4% | −0.040 | 79.4% |
| Asia 00-04 | 848 | 33.8% | −0.009 | 55.8% |
| no session filter | 3083 | 32.8% | −0.060 | 97.3% |

The whole London plateau is negative on BTC — all 9 K x WAIT cells between
−0.070 and −0.121. Zero-cost reference also negative (−0.035). No trace of the
gold pattern.

## Verdict on the candidate
**Most likely noise.** The gold London result was never significant
(P(expR<=0) = 33.5%) and was one favourable cell out of ~20 searched; it then
failed the first independent asset test, on a decent sample, significantly.

*Fair caveat:* BTC has no institutional London session (no LBMA fix, no metals
desks, 24/7 market), so it is not a perfect analogue for a gold/London
mechanism. Weight this lightly — 1-in-3 noise odds plus a failed replication is
mostly just noise.

## The discriminating test
An instrument that DOES have a real London session: **EURUSD, GBPUSD or silver
(XAGUSD)**, M15/M30 from MT5. If the London edge appears there, the
gold-specific mechanism story becomes credible. If not, the candidate is dead.

## Running scoreboard for this playbook
- As specified, no session filter: **negative**, large sample (n=1345-3083, both assets).
- Gold + London + nearest target: +0.076 OOS but not significant.
- BTC + same config: **−0.108**, significant.
- Status: **unconfirmed / probably noise**, pending an FX or silver test.

---

# SESSION RE-TEST — the "active window" hypothesis, tested and REJECTED

Measuring gold M30 volatility/volume by hour (2024-2026 UTC) showed the real
activity peak is the **London+NY overlap 13:00-16:00** (1.60x the day-average
range, ~2x the volume), while **London 07-13 is exactly 1.00x** — dead average.
The originally-tested `London 07-10` window is one of the QUIETEST parts of the
day. Hypothesis: the session filter was mis-specified and the true active
window (12:00-16:00) should do better.

**It does not. It is decisively worse.**

## Gold, K=1.0 WAIT=12, nearest-pool target

| Session | TRAIN 22-06..24-12 | TEST 25-01..26-09 (unseen) |
|---|---|---|
| Asia 00-04 | −0.141 (n=434) | −0.270 (n=315) |
| **London 07-10** | **+0.077** (n=422) | **+0.076** (n=231) |
| London 07-13 | +0.044 (n=808) | −0.089 (n=459) |
| **ACTIVE 12-16** | +0.036 (n=643) | **−0.109** (n=409), P(≤0)=90.8% |
| Overlap 13-16 | −0.064 (n=466) | +0.043 (n=329) |
| NY 16-21 | −0.112 (n=281) | −0.185 (n=226) |
| no filter | −0.026 (n=1614) | −0.107 (n=1078) |

## Grid, unseen period — the active window fails everywhere

`ACTIVE 12-16` is negative in **all 12 K x WAIT cells** out-of-sample
(−0.100 to −0.232). There is no plateau, no corner, nothing. `Overlap 13-16`
inverts sign between the two periods (−0.03..−0.09 train, +0.04 test) — the
classic noise signature. `London 07-10` remains the only window positive in
BOTH periods across the K=0.5/1.0 plateau (6/6 cells).

## Why the quiet window beats the loud one — mechanism check

A trap/reclaim model needs a sweep to FAIL. Measured directly: fraction of
swept levels reclaimed within 3h, gold 2022-2026 (n=8,547 sweeps):

| Session | sweeps | reverts | continues |
|---|---|---|---|
| London 07-10 | 1,166 | **86.7%** | 13.3% |
| London 07-13 | 2,641 | 86.0% | 14.0% |
| Asia 00-07 | 2,435 | 84.6% | 15.4% |
| ACTIVE 12-16 | 2,769 | 82.6% | 17.4% |
| Overlap 13-16 | 2,011 | **82.5%** | 17.5% |
| NY 16-21 | 1,049 | 81.7% | 18.3% |
| Late 21-24 | 411 | 79.8% | 20.2% |

The gradient runs in the predicted direction — sweeps in high-volatility hours
are ~30% more likely to become real breakouts (17.5% vs 13.3% continuation) —
so "quiet hours favour reversal models" is a genuine effect. **But the gap is
only 4.2 percentage points, nowhere near enough to explain a +0.076 vs −0.109
expR swing.** The mechanism is real and small; the performance gap is large.
That difference is unexplained, and unexplained gaps are usually noise.

## Net effect on the candidate's status

**Weaker, not stronger.** The correction removed the one explanation that could
have made London 07-10 look like a mis-specification worth fixing; instead it
confirms 07-10 is an isolated favourable window whose advantage over the
genuinely active hours has no proportionate mechanism behind it. Combined with
P(expR≤0)=33% and the failed BTC replication, the candidate stays
**unconfirmed / probably noise**. An FX or silver test is still the only thing
that would settle it.

---

# EXIT RE-TEST — "maybe the target is reached 1-2 days later"

Trader's hypothesis: the trades are being cut short. Tested three ways.

## 1. No — winners resolve within hours, not days

`_sim` already allows unlimited time to target, so nothing was truncated.
Measured durations (M15 bars; 96 bars = 1 day):

| Session | winners median | p90 | losers median |
|---|---|---|---|
| London 07-10 | 11 bars (2.7h) | 0.3d | 7 bars (1.8h) |
| ACTIVE 12-16 | 10 bars (2.5h) | 0.9d | 4 bars (1.0h) |
| Overlap 13-16 | 17 bars (4.3h) | 0.9d | 6 bars (1.5h) |

When the opposing pool is reached, it is reached the same session.

## 2. But the stops ARE too tight — hypothesis right, mechanism different

**Stop-outs that later reached the target within 5 days: 69.6% (London 07-10),
61.9% (12-16), 65.2% (no filter).** Direction correct, stop hit first. Third
appearance of this pattern (Mayne: 65% gold / 73% BTC).

## 3. CORRECTION to the earlier mechanism number

The 4.2pp continuation gap reported above used a 3h horizon — the wrong lens.
At 12-24h the gap is ~2.6x, not 1.3x:

| continuation (never reclaimed) | 3h | 12h | 1d | 2d | 5d |
|---|---|---|---|---|---|
| London 07-10 | 13.3% | 5.1% | 4.0% | 3.5% | 2.4% |
| ACTIVE 12-16 | 17.4% | 13.4% | 10.7% | 7.9% | 5.5% |

Sweeps in high-volatility hours are ~2.6x more likely to genuinely run away.
The session mechanism is real and larger than first reported.

## 4. Widening the stop does not pay (fixed target)

| stop x | London 07-10 TEST expR | win rate |
|---|---|---|
| 1.0 (as specified) | **+0.076** | 30.7% |
| 2.0 | −0.004 | 43.4% |
| 4.0 | −0.051 | 56.4% |
| 6.0 | −0.048 | 64.5% |

Win rate doubles, expectancy flat-to-worse — against a FIXED target price a
wider stop shrinks R one-for-one. Same in all four sessions.

## 5. Stop x trail grid (reward set by the trail, not a fixed target)

Walk-forward, pick the best cell on TRAIN then read TEST:
- London 07-10: best train stop x1/trail 8ATR **+0.238** -> TEST **−0.097**. Collapsed.
- ACTIVE 12-16: best train stop x1/trail 4ATR **+0.090** -> TEST **−0.080**. Collapsed.

## 6. The trail=8ATR column is gold's trend, proven by a null

trail 8ATR was positive OOS nearly everywhere INCLUDING with no session filter
(+0.092) — the signature of a trending market, not an entry edge. Null test:
identical entry timing and risk, **random direction**, same trail, 12 seeds.

| Session | stop | REAL | NULL mean | NULL sd | z |
|---|---|---|---|---|---|
| London 07-10 | x1 | −0.097 | −0.078 | 0.119 | −0.16 |
| London 07-10 | x3 | +0.126 | +0.130 | 0.076 | −0.05 |
| ACTIVE 12-16 | x1 | +0.108 | +0.045 | 0.110 | +0.57 |
| ACTIVE 12-16 | x3 | +0.175 | +0.144 | 0.070 | +0.45 |
| **no filter** | **x1** | **+0.092** | **+0.092** | 0.079 | **+0.00** |
| no filter | x2 | −0.018 | +0.110 | 0.055 | **−2.34** |

**Coin-flip entries with the same trail earn the same money.** No cell clears
z=+0.6; at no-filter x2 the real signal is significantly WORSE than random.
Gold buy-and-hold over the same unseen period: **+64.8%**. An 8 ATR trail in
that market is trend-following with extra steps.

## Net

The trader's premise was factually right (stops too tight; 60-70% of losers
were directionally correct) and forced a 2x upward correction to the session
mechanism — but no exit fix produces an edge. Widening against a fixed target
trades win rate for R one-for-one; replacing the target with a trail either
collapses under walk-forward selection or is indistinguishable from random.

**Status unchanged: no demonstrated edge on gold.** Only the original
tight-stop / fixed-pool London 07-10 cell still stands, at P(expR<=0)=33%,
already failed on BTC. An FX or silver test remains the only thing that settles it.

---

# ENTRY-TIMING RE-TEST — "enter after the stops are hunted" (trader's idea)

Trader's argument: widening the stop is the wrong lever (it shrinks RR).
Instead move the ENTRY deeper into the hunt — a better fill shrinks risk AND
extends reward. Correct reasoning, and a genuinely different lever. Tested as:
- wait for a deeper hunt (>= 0.5 / 1.0 ATR past the level before entering)
- delay 4-8 bars after the reclaim
- rest a LIMIT back at the level / 50% / 100% into the hunt zone

## A 2.0R BUG, caught before reporting

First run showed "LIMIT at the wick" = **+1.949 expR, P(<=0)=0.0%**. Not real:

1. **Sub-spread stop.** Entry at the wick with the stop 0.02% beyond it = a
   **$0.80 stop on $4,000 gold** (spread alone is $0.25). Every R is measured
   against that, so one winner reaching a $30 target books **+37R**. This is the
   same artifact that faked Trident's +229R trade.
2. **Entry bar skipped.** The sim checked the stop from the bar AFTER the fill.
   But a limit at the sweep extreme fills on a bar that is reaching that
   extreme, with the stop $0.80 away — that bar is the most dangerous one and
   it was being hidden.

Both bugs flatter the hypothesis. Fixed: stop forced to an executable distance
(>= max(0.05% of price, 4x spread) ~ $2 on gold) and the entry bar is checked.

## Corrected result — the idea fails

| Variant (no session filter) | TRAIN | TEST | n | P(<=0) | missed | stopped on fill bar |
|---|---|---|---|---|---|---|
| BASELINE enter at reclaim | −0.024 | −0.106 | 1078 | 96.1% | | |
| wait deeper hunt 0.5 ATR | −0.003 | −0.036 | 656 | 71.0% | | |
| wait deeper hunt 1.0 ATR | +0.044 | −0.084 | 383 | 90.1% | | |
| delay 4 bars | −0.070 | +0.001 | 947 | 52.9% | | |
| LIMIT back at the level | −0.161 | −0.177 | 918 | 93.3% | 331 | 211 |
| LIMIT 50% into hunt zone | −0.223 | −0.123 | 878 | 82.7% | 614 | 335 |
| **LIMIT 100% (at the wick)** | **−0.389** | **−0.073** | 761 | 66.0% | **809** | **434** |

+1.949 became −0.073 on the same data with the same rules — the entire result
was the two bugs.

## Why it fails: adverse selection, now measured

- **Miss rate rises with patience**: 26% -> 41% -> 52% of setups never fill.
  The ones that never come back are disproportionately the trades that worked.
- **57% of wick fills are stopped on the entry bar itself** (434 of 761). Price
  returns to the sweep extreme, and more often than not it is on its way
  through, not bouncing off it.

The better fill is real. It is paid for twice over — once in the winners you
never enter, once in the fills that are simply the move continuing.

London panel shows TRAIN negative (−0.004 / −0.152 / −0.288) and TEST positive
(+0.431 / +0.400 / +0.187) — sign inversion, and under walk-forward selection
you would never pick a cell that was negative in training.

**No variant beats the baseline. Nothing here rescues the strategy.**

---

# ROUND NUMBERS — tested with a null, REJECTED

| $10-round tolerance | TEST expR | | random subset, same n |
|---|---|---|---|
| <0.25 | −0.101 | | seed0 −0.061 |
| <0.50 | −0.087 | | seed1 −0.019 |
| **<1.00** | **+0.030** | | seed2 −0.159 |
| <2.00 | −0.093 | | seed3 −0.169 |

Only the <1.00 band is positive and both neighbouring bands are negative — a
spike in noise, not a plateau (a real magnet effect strengthens monotonically
as tolerance tightens). In the London panel the apparent +0.333 sits INSIDE its
own null: random level subsets of the same size scored +0.113, +0.228, +0.201.
Rejected.
