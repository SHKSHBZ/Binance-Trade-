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
