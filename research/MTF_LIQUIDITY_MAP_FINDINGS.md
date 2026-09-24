# MTF S&R / Liquidity-Pool Mapping — Findings

## Spec tested
HTF swing highs/lows = S&R levels; two same-side swings within eps of each
other = a liquidity pool. Pairing table as given: 1W->1D, 1D->4H, 12H->1H,
4H->1H/15M. Rule made concrete: HTF level swept (LTF wick trades through it)
-> wait for LTF confirmation (price breaks its own recent LTF swing back in
the fade direction, within W bars) -> enter at confirmation close, stop =
sweep extreme + small ATR buffer, target = nearest opposing HTF level (or a
fixed-R floor if none), fade the sweep. Causal: an HTF level is only usable
after the HTF candle that confirms it has actually closed.

**Not tested:** the 15M->1M scalping sub-system. No 1-minute gold/BTC data
exists in this repo, so the 1M trigger step cannot be tested honestly.

## Headline scan (`research/mtf_liquidity_map.py`)
All pairs, both markets, raw S&R levels vs. pool-only levels:

| mkt | pair | pools | n | /yr | expR | P(luck) | train | test |
|---|---|---|---|---|---|---|---|---|
| GOLD | 1D->4H | True | 11 | 2 | +0.226 | 34.9% | +1.185 | -0.924 |
| GOLD | **12H->1H** | **True** | **26** | **4** | **+0.659** | **2.1%** | +1.095 | +0.150 |
| GOLD | 4H->1H | True | 9 | 1 | -0.347 | 78.5% | -0.454 | -0.212 |
| GOLD | 4H->15M | True | 41 | 10 | +0.207 | 21.9% | -0.354 | +0.796 |
| BTC | 4H->1H | True | 10 | 3 | +0.794 | 10.8% | -0.062 | +2.079 |
| BTC | 4H->15M | True | 38 | 11 | +0.242 | 17.9% | -0.063 | +0.580 |

Every cell not shown was clearly negative or n too small to matter.
Only one cell looked real at first glance: **GOLD 12H levels -> 1H
execution, pools only**, so that's the one I stress-tested.

## Stress test on GOLD 12H->1H (pools)

- **Parameter sensitivity** (eps, confirmation window, stop buffer, min R):
  stayed positive across most reasonable settings — this ruled out "my
  interpretation choice happened to cause it."
- **Independent replication on BTC, same pairing:** n=18, expR=**-0.114**,
  P(luck)=64%. Fails completely on the second asset.
- **Random-direction null** (same entries/stops, coin-flip side): expR=-0.162,
  i.e. a fair fight would lose money — the market isn't just drifting in a
  way that flatters any trade here.
- **Concentration** — this is the real problem: top 1 of 26 trades =
  **27% of all profit**, top 5 = **81% of all profit**. Remove five lucky
  trades out of twenty-six and the whole result is close to breakeven.

## Verdict

This is the same failure pattern as every other lucky-looking cell in this
project: small sample (26-41 trades), the win concentrated in a handful of
outsized trades, and it doesn't survive being run on a second asset. It is
not a real, repeatable edge — it's noise that happened to land on the
positive side this time.

**No pairing in the HTF/LTF table produced a strategy that (a) had enough
trades to trust, (b) wasn't dominated by 1-5 trades, and (c) replicated on
both gold and BTC.** The MTF S&R/liquidity-pool framework, tested exactly as
specified, does not show an edge on the data available here.
