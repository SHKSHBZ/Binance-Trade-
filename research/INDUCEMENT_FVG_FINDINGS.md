# Inducement + FVG + Internal/External Liquidity — tested, NO edge

The trader's confluence setup: macro uptrend (HH/HL) + a bullish FVG left by
an impulse + an inducement (minor swing low above the FVG, the trap) + entry
on the sweep of internal sell-side into the FVG with a reaction out; target
the major swing high (external buy-side). Code: `inducement_fvg.py`.

## Result — negative in every configuration

15m BTC, long-only, causal, honest fees. Swept reaction strength × target:

| Reaction | Target | Trades | Win | avgRR | Return | expR | Edge |
|---|---|---|---|---|---|---|---|
| weak (>gap_lo) | major high | 763 | 20% | 6.2 | −189% | −0.345 | 0% |
| weak | 2R | 861 | 32% | 2.0 | −229% | −0.392 | 0% |
| weak | 3R | 820 | 25% | 3.0 | −223% | −0.386 | 0% |
| strong (>gap_hi) | major high | 675 | 23% | 5.0 | −124% | −0.205 | 2% |
| strong | 2R | 767 | 34% | 2.0 | −162% | −0.273 | 0% |
| strong | 3R | 723 | 27% | 3.0 | −145% | −0.240 | 0% |

The stronger reaction filter helps a little, but everything is deeply
negative. **The diagnostic tell: at every fixed target the win rate sits right
on the geometric breakeven** (34% at 2R vs 33% breakeven; 18% at 5R vs 17%).
That is the signature of **random entry direction** — the confluence does not
pick the winning side, so costs make it a net loser.

## Why stacking confluence didn't help

The hypothesis was "direction is 50/50, add OB/FVG/inducement to fix it."
But each ingredient is itself a coin flip on BTC direction (proven separately:
FVGs get filled/continued ~70%; sweeps don't predict direction; structure
doesn't predict post-sweep direction). **Stacking coin-flips yields a coin
flip — with more conditions you take fewer trades and *feel* more selective,
but you add no directional information, only more fees.** Confluence narrows
count, it does not manufacture an edge the parts lack.

## The consolidated BTC finding (across ~9 setups now)

fib, gann, volume profile, prior-day, liquidity sweep, volume breakout,
structure-filtered sweep, and now inducement+FVG: **every mechanical ICT/price
setup lands at ~random direction on BTC intraday, net-negative after costs.**
The one robust edge was trend-regime on the DAILY timeframe with long holds;
the one promising discretionary setup (Trident) needs its real instrument.

Direction on BTC intraday is not mechanically predictable by any known
pattern. The edge, if it exists, is discretionary (live context) or lives on
a different instrument/timeframe.

## Verdict

Not an edge on BTC. Merging it into structure_sweep would only stack another
coin flip — NOT done. Worth one clean re-run on real gold when XAUUSD arrives.

## Run
```
python3 inducement_fvg.py
# run(file, start, end, react_strong=True|False, fixed_rr=None|2|3|5)
```
