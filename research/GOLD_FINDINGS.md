# Gold (XAUUSD) — real data results & the session's meta-conclusion

Real Exness XAUUSD 2020-2026 (15m/30m/1h/4h), added via `convert_gold_data.py`.
This is the instrument the user actually trades, so it's the decisive test bed.

## 1. Trident London-Killzone — FAILS on gold
See `TRIDENT_FINDINGS.md`. 6 of 7 years negative; the +48% no-target result
was carried by 3 trades, one with a $0.10 (sub-spread) stop faking +229R.
Executable-stop filter turns +180R into −26R. Buy-and-hold gold was +180%.

## 2. Gold does NOT mean-revert intraday (unlike BTC) — but sweeps still coin-flip
`sweep_direction_test.py` logic on gold 30m/1h:

| | BTC | Gold |
|---|---|---|
| baseline continuation (all bars) | ~47% (reverts) | **~50-51%** (neutral/slight trend) |
| post-sweep + trend continuation | ~45-47% | ~49-51.6% |

Gold has a healthier (non-reverting) character — the reason BTC killed every
trend/continuation idea doesn't apply. BUT the liquidity SWEEP still adds no
directional edge (swept ≈ all bars, both ~coin flip). The faint >50% trend
tilt is too small to trade mechanically after spread/costs.

## 3. Trend-regime filter — does NOT beat buy-and-hold on gold
Gold daily, long-while-close>MA vs hold:

| Strategy | Return | maxDD | Sharpe |
|---|---|---|---|
| buy & hold | +179% | −28% | 0.99 |
| long>MA50 | +111% | −22% | 0.88 |
| long>MA200 | +81% | −25% | 0.71 |

The regime filter helped on BTC (dodges crashes, Sharpe 1.13 vs 1.05) but not
on gold — gold's uptrend was too smooth to improve on by sitting out. Best
action for gold 2020-2026 was simply to hold.

## Meta-conclusion (after ~10 strategies on BTC + gold)

No mechanical strategy tested this session beats buy-and-hold or random
entry, on either instrument, after realistic costs. Consistent findings that
DID hold up (the durable principles):

- **Direction is not mechanically predictable** from fib, gann, volume
  profile, prior-day, liquidity sweeps, structure, inducement/FVG, or their
  confluence — on BTC or gold. Every "edge" was a fill illusion, look-ahead,
  small-sample luck, or a sub-spread-stop sizing artifact.
- **Liquidity/volume predict MAGNITUDE, not direction** (measured directly).
- **Asymmetry is the only positive shape**: tiny losers + rare big winners.
- **Trade with the higher-timeframe trend; never fight it.**
- **Costs are decisive**: a stop tighter than the spread is fantasy; a
  minimum-stop filter (risk ≥ ~0.1% of price) belongs in the harness.

Implication for a real-time discretionary trader: the edge, if any, is in the
LIVE READ (which a backtest cannot validate or create), not a mechanical
rule. The productive next steps are (a) real-time marking TOOLS to support
that read, and (b) disciplined forward demo testing where the trader's
discretion — not a fixed rule — is the variable under test.
