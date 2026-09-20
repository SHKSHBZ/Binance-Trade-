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
