# Volume Profile Rejection — tested, NO proven edge

The user's "absorption won" reversal: push into a low-volume void beyond a
swing → reject → re-cross the POC → target the opposite-side HVN.
Code: `volume_profile_rejection.py`. Causal profile, honest fees + slippage.

## Why it looked promising at first

On **15m BTC, ~2.5-day profile** (LOOKBACK=240), far-side target:

| Cut | Trades | Win | Return | expR |
|---|---|---|---|---|
| 2023 | 21 | 52% | +2.9% | +0.144 |
| 2024 | 24 | 63% | +7.7% | +0.319 |
| 2025 | 27 | 52% | +5.9% | +0.225 |
| **Pooled** | **78** | **56%** | **+15.8%** | **+0.206**, edge 91% |

- Positive in **every full year** — the only reversal this session to do that.
- **Robust** to NBINS (40–100), ARM_WIN (4–16), HVN_FRAC (0.25–0.65): all positive.
- Robust to **timeframe** once the profile range is held at ~60 hours:
  15m/LB240 +15.8%, 1h/LB60 +9.9% (121 trades), 5m/LB720 +4.9%. The real
  parameter is a ~2.5-DAY profile, not a bar count (short ranges fail: 15m/LB120 = −25%).

## Why it FAILS the decisive test

The null test — **random entries with the SAME risk/reward geometry**, random
direction — asks whether the volume-profile logic actually locates
better-than-random entries, or whether the profit just comes from the
asymmetric geometry (a reachable far-side target vs a wide stop).

| Sample | Real expR | Null mean | p-value | Verdict |
|---|---|---|---|---|
| 15m, 78 trades | +0.206 | +0.015 | **0.09** | marginal |
| 1h, 121 trades | +0.082 | −0.006 | **0.15** | not distinguishable |

**The edge SHRINKS as the sample grows (+0.206 → +0.082), and never clears
the 95% bar.** That is the signature of a small-sample false positive. Most
of the headline return is the favorable RR geometry, not directional skill —
the same wall every other entry hit this session: **the entry does not beat
random; on BTC, short-term direction after the setup is ~a coin flip.**

## Verdict

Not a proven edge. Do not trade it on this evidence. Filed with the other
chart/volume patterns (fib, gann, prior-day, liquidity sweep, volume
breakout) that looked plausible and dissolved under a proper null test.

Open door (small): it was *closest* to significant of the reversals, and was
never tested on the instrument the user actually trades. If real gold data
arrives, worth a single honest re-run — but expectations low.

## Run

```
python3 volume_profile_rejection.py          # 15m, far target
# run(file, start, end, target_mode="far"|"near")
# tunables: LOOKBACK, NBINS, ARM_WIN, HVN_FRAC, STOP_BUF (module globals)
```
