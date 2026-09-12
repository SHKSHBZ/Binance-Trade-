# Volume-Confirmed Breakout — backtest findings

Built on the one real property we found: volume forecasts move SIZE, not
direction. So direction comes from a range-break, volume only confirms the
expansion is real. Squeeze (box narrowest in W bars) → break the box → require
elevated volume → stop at far side, target/trail. 1H, causal, slippage 0.05%.
Code: `research/volume_breakout_backtest.py`.

## Fixed-target version (target = R × risk)

Swept 54 combos (box L, window W, volume threshold, target R), ranked by
positive years:

- **1 of 54 combos positive in all 4 years** (L48/W120/vol2.5/R2.0): +3%, +0.5%,
  +3%, +3.5% — positive every year but tiny, on only 101 trades. Pooled +0.111R,
  edge 80%.
- **But the median combo is ~0R** (−0.011R), 24/54 positive pooled. Under pure
  chance you'd expect ~3 combos to hit 4/4; we found 1. That is *not* evidence
  of a real edge — it's what noise looks like.

## Trailing-stop version (let winners run — the proper breakout exit)

Breakout edges are supposed to live in a fat right tail, which a fixed target
caps. So we trailed the stop instead. Swept 24 combos:

- **0 combos positive in all 4 years.** Best are 3/4 with a bigger pooled number
  (+0.35R) but always one losing year (usually 2025).
- Median still ~0R (−0.03). Positive pooled in 11/24.

The trailing stop makes the *pooled* number look better by catching 1–2 big
trends, but does **not** make it dependable year-to-year — the signature of a
fat-tailed lottery, not a steady edge.

## Honest verdict

The volume *insight* is real and valuable (volume = volatility forecast). But
turning it into a mechanical directional breakout does **not** produce a
dependable cross-year edge on BTC — the median setting is break-even and the
good-looking combos come from searching, not from a robust signal.

This now matches every mechanical price/volume strategy we have tested (SMC,
Fib continuation, Fib reversal, volume breakout): simple mechanical rules do not
reliably beat BTC. That is itself the finding — liquid-market TA is close to
efficient. The remaining honest edges are not more patterns but: selectivity /
judgment on top (the LLM layer), genuinely new information (news/events), or a
different market/instrument. And a thin, real tilt (the Fib fade) we can still
forward-test.
