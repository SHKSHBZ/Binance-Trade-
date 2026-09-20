# Trader Mayne "Structure & OTE" Playbook — backtested, INCONCLUSIVE (too few setups)

Faithful causal mechanization: HTF Daily BOS → Order-Block POI in premium/
discount → LTF sweep+reclaim entry inside the POI → external-liquidity target,
min 2:1. Code: `mayne_playbook.py`. Tested on gold and BTC.

## Results

| Instrument | Target | Trades | Win | avgRR | Return | expR | Edge |
|---|---|---|---|---|---|---|---|
| GOLD | external liq | 13 | 8% | 19.7 | +28.8% | +2.25 | 74% |
| GOLD | fixed 3R | 13 | 23% | 3.0 | −6.9% | −0.52 | 16% |
| GOLD | fixed 2R | 13 | 23% | 2.0 | −9.8% | −0.75 | 1% |
| BTC | external liq | 10 | 20% | 17.6 | +7.9% | +0.84 | 72% |
| BTC | fixed 3R | 10 | 30% | 3.0 | −0.1% | +0.00 | 52% |
| BTC | fixed 2R | 10 | 30% | 2.0 | −3.0% | −0.30 | 28% |

(Lower execution timeframes 30m/15m did not add trades — the bottleneck is the
DAILY BOS+OB setup, which is inherently rare: ~10-13 in years.)

## Honest verdict — inconclusive, not proven, not disproven

1. **Sample far too small to judge.** 10-13 setups over multiple years on ONE
   instrument cannot separate skill from luck (edge ~72-74%, below the 95% bar).
   This is a DAILY-HTF SWING model by design — it produces few, large trades. To
   test it properly you need a **basket of instruments** (crypto + FX + indices +
   commodities) to accumulate a few hundred setups. On gold+BTC alone it is
   effectively untestable.

2. **The apparent gains are outlier-driven.** The positive "external liquidity"
   returns (+28.8% gold, +7.9% BTC) come almost entirely from 1-2 trades with
   huge RR (win rate 8-20%). Same fragile profile as the Trident test.

3. **At realistic fixed targets (2R/3R) it is breakeven-to-negative** — i.e. the
   ENTRY itself carries no directional edge (consistent with every other setup
   tested). Any profit is purely the asymmetric "let it run to external
   liquidity" target paying off on the rare winner.

4. **The author agrees it's discretionary.** The playbook's own Pros/Cons: entries
   "need some discretion," it "requires backtesting and live practice," and "must
   be personalized." So it was never a mechanical system — the edge, if any, is in
   the trader's POI/confirmation judgment, which a backtest cannot capture.

## DECISIVE UPDATE — H4 HTF (bigger sample) → clearly NEGATIVE

The Daily-HTF result above was only 10-13 trades (untestable). Switching HTF to
**4H → M15 execution** produces a real sample and settles it:

| Instrument | Trades | Exit modes tried | Return | Edge |
|---|---|---|---|---|
| GOLD (H4→M15) | 44 | trail 4/2.5 ATR, fixed 3R/2R | −48% to −56% | 0% |
| BTC (H4→M15) | 58 | same | −29% to −54% | 0% |

Every exit mode, both instruments, clearly negative, edge 0%, win rates below
breakeven. **The Daily version's apparent +28%/+7.9% was 1-2 outliers on a tiny
sample; with 44-58 trades the edge evaporates — the signature of a false
positive.** Also tested: lenient entry (gold 13→22 trades) made it *worse* (the
extra setups were coin flips, not hidden winners); a wide ATR trailing stop was
the only lever that helped marginally but could not create an edge.

**Verdict upgraded: mechanically DISPROVEN on gold and BTC, not merely
inconclusive.** Quality entries + let-winners-run remain the only sound
principles; the strategy's structure does not predict direction.

## Bottom line

The Mayne playbook is a legitimate, well-structured SMC swing framework — and
its low-win-rate / big-runner / few-trades profile is by design. But on a single
instrument it produces too few setups to validate, and mechanically its entry is
a coin flip (breakeven at fixed RR); its returns depend on rare outsized winners.
Same conclusion as the whole research program: the structure is sound, the edge
lives in discretion + asymmetric payoff, not in a mechanical rule.

## Run
```
python3 mayne_playbook.py
# run(ltf_file, start, end, target_mode="ext"|"fixed", rr_fixed=3.0)
```

## Stop-out analysis — the stops were too tight (valuable insight)

Of the stop-outs on the H4→M15 version: **GOLD 65% and BTC 73% would have
reached the full target** after being stopped; 90-97% came back to at least
breakeven within ~2-3 days. So the stops were being noise-hit ("stop hunted")
and price then went the intended way.

Fixing it (wider stop + trailing exit) improves results dramatically but does
NOT reach profit:
- Wider stop alone: win rate 16% -> 45%, but proportionally worse RR -> still negative.
- Wider stop (3x) + ATR trailing: GOLD -48% -> -4.5% (edge 39%), BTC -43% -> ~-8%.

**Conclusion: good risk management (wide stop + let winners run) takes a
coin-flip entry from deeply negative up to ~breakeven, but cannot cross into
profit. The final step (breakeven -> profit) requires a >50% entry, which is
not mechanically available -- it must come from discretionary entry selection.**

## Correction + walk-forward on stop-width x trail

The first wider-stop test was constructed wrong: holding the target at a fixed
PRICE while widening the stop forces RR to collapse, so the "no free lunch"
conclusion drawn from it was not valid. Re-ran properly as a joint grid
(stop_mult x trail_atr, 36 cells) where the trail sets the reward.

Full-sample best: GOLD stop12x/trail16ATR +11.0% (expR +0.27, edge 83%, n=29);
BTC stop12x/trail16ATR +7.5% (expR +0.15, edge 73%, n=44). Both at the grid
corner = effectively "no structure stop, loose trail does all exits".

Walk-forward (pick params on early years, test on unseen later years):
- GOLD pick stop6x/trail12 -> IS expR +0.081, OOS expR +0.079 (+2.3%, edge 63%, n=19). Held, but trivial / inside noise.
- BTC pick stop3x/trail16 -> IS expR +0.302, OOS expR -0.905 (-20.3%, edge 0%). Collapsed = pure fit.
- OOS across all 36 cells: GOLD mean expR -0.202 (10/36 positive); BTC mean -0.381 (2/36 positive).

**Conclusion: widening the stop paired with a trail is the correct construction
and removes the noise-stop bleed (-48% -> ~0), but it does not produce an edge
that survives out-of-sample.**
