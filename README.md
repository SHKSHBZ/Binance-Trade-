# Binance SMC Trading Bot

An automated crypto trading bot for Binance USD-M Futures, built on a
Smart Money Concepts (SMC) strategy: liquidity sweep → change of
character → order block with displacement → limit fill at the order
block's mean threshold.

Trades BTC, ETH, SOL, BNB, and XRP on 15-minute candles with a 4-hour
liquidity bias. Runs on Binance Testnet by default.

## Status

**Backtested and validated on BTCUSDT.** Not yet validated on the other
four symbols — they run the identical strategy code but need their own
historical data before the numbers below can be trusted for them. Not
yet run on testnet at all. Read [Honest limitations](#honest-limitations)
before risking anything.

| Period | Trades | Win rate | Return | Max drawdown |
|---|---|---|---|---|
| 2025 (full year) | 79 | 43.0% | +105.4% | 9.5% |
| Jan–Jul 2026 | 30 | 40.0% | +66.3% | 4.8% |
| 2025, with 0.1% stop slippage + funding | 79 | 41.8% | +65.4% | 15.0% |
| Jan–Jul 2026, same costs | 30 | 36.7% | +52.5% | 5.8% |

Checked against 40 random-entry runs sharing the identical risk
framework: zero matched this result in either period. The entry
sequence — not the risk sizing — is what's producing the edge.

## How it works

1. **Sweep** — price wicks through a 4H swing high/low (a liquidity pool).
2. **CHoCH** — within 8 hours, 15M market structure breaks the opposite way.
3. **Order block** — the last opposite-colour candle immediately followed
   by a fair value gap (the displacement requirement).
4. **Fill** — a limit order rests at the 50% midpoint of that block,
   valid for 24 hours, taken only if the nearest opposing liquidity pool
   offers at least 2:1 reward:risk.

Stop sits just past the sweep wick (0.3% buffer). Target is the nearest
unswept opposing liquidity pool, not a fixed R-multiple. Risk is 1% of
account balance per trade, capped at 10x leverage / 80% margin. A
portfolio-wide 3% daily loss circuit breaker halts new entries across
every symbol, and no more than 2 of the 5 symbols can be open at once —
these coins move together, so uncapped concurrent risk is closer to one
correlated bet than five independent ones.

## Repository layout

```
smc_engine.py            The strategy. Single source of truth -- every
                          backtest and the live bot drive this same code.
smc_luxalgo.py            Faithful bar-by-bar port of the LuxAlgo "Smart
                          Money Concepts" TradingView indicator. Labels
                          OHLCV with dual (internal-5 / swing-50)
                          structure, BOS/CHoCH, volatility-filtered order
                          blocks with mitigation, FVGs with the auto
                          significance threshold, EQH/EQL, and premium/
                          discount zones -- a testable accuracy anchor for
                          the concepts the strategy trades on. Standalone:
                          `python3 smc_luxalgo.py <csv>` prints event counts.
backtest_engine.py        Single-symbol backtest, driven by smc_engine.
backtest_portfolio.py     Multi-symbol backtest with a shared balance
                          and portfolio-wide correlation cap.
binance_live_bot_v2.py    The live bot (testnet by default), driven by
                          smc_engine per symbol.
validate_engine.py        Regression test -- proves the live bot's engine
                          reproduces the validated backtest exactly.
                          Run this after ANY change to the strategy.
data_loader.py            Format-detecting CSV loader. The files in
                          DATA/ mix ISO and DD/MM timestamps; this is
                          the only safe way to read them (see below).
fetch_data.py              Downloads historical klines from Binance for
                          any symbol. Run this locally to get ETH/SOL/
                          BNB/XRP data -- ship-supplied data only covers
                          BTCUSDT.
simulate_live_bot_params.py  The original strategy implementation.
                          validate_engine.py checks the engine against
                          this on every run -- it's a dependency of the
                          test suite, not legacy code.
DATA/                     Historical BTCUSDT OHLCV, several timeframes.
archive/                  Superseded code, kept for reference. See
                          archive/README.md.
```

## Getting started

```bash
pip install -r requirements.txt

# 1. Get real data for the other four symbols (this needs to run on your
#    own machine -- Binance's API isn't reachable from every sandbox)
python3 fetch_data.py --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT --days 730

# 2. See whether the strategy actually holds up on them before risking anything
python3 backtest_portfolio.py --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT

# 3. Confirm the live bot's engine still matches the validated backtest
python3 validate_engine.py

# 4. Testnet. Needs BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_SECRET_KEY in .env
python3 binance_live_bot_v2.py
```

## Honest limitations

- **Only BTCUSDT has real backtested history in this repo.** The other
  four symbols are architecturally identical but empirically untested.
- **109 BTC trades across two periods on one symbol** is a modest
  sample. A meaningful share of the profit sits in a handful of trades.
- **Three data/logic bugs were found and fixed while building this** —
  a timestamp-parsing fault that silently scrambled 36% of rows in the
  older CSVs, two look-ahead errors, plus two more in the portfolio
  driver during multi-symbol testing (a one-bar exit-timing divergence
  and an ambiguous file resolver). Each inflated results until caught.
  There may be another. This is exactly why `validate_engine.py` exists
  — run it after any change, not just once.
- **The backtest assumes a resting limit order fills whenever price
  touches its level.** Real queue position may not cooperate. This is
  the single largest thing testnet actually measures that the backtest
  cannot.
- **Funding fees, real fill quality, and exchange downtime are absent
  from the backtest.** A cost-sensitivity run is included above; treat
  it as illustrative, not precise.

Run on testnet for 30–40 trades per symbol before drawing any
conclusion, and compare the actual win rate against the ~40% backtested
figure. Below roughly 33% (breakeven at the strategy's 2:1 minimum
reward:risk), the edge is not there.
