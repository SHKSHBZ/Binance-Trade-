# Archive

Everything here is superseded by the production system at the repo
root (`smc_engine.py` + `binance_live_bot_v2.py`). Kept for reference,
not deleted, because some of the negative results below are exactly
what ruled out weaker approaches in favor of the current strategy.

Nothing in this folder is imported by the root-level code. It's safe
to ignore entirely unless you want the research history.

## `legacy_v1_bot/`

The original bot: a single-symbol EMA20 + Fair Value Gap strategy,
plus its FastAPI dashboard (`server.py`, `web/`). Backtested on real
data, it lost money in every period tested (-5% to -60.6%). Superseded
entirely by the SMC V2 sweep→CHoCH→order-block strategy at the root.

Also here: `fetch_btc.py` (superseded by `fetch_data.py`, which
supports any symbol, not just BTC), and `check_order.py`/`test_order.py`
(one-off Binance API smoke tests), and an MQL5 port of the old
EMA20+FVG strategy for MetaTrader/Exness (`EMA20_FVG_Sniper_EA.mq5`) —
also superseded, never adapted to the current strategy.

## `exploratory_backtests/`

Roughly two dozen strategy variants tested against BTC data while
arriving at the current approach. Grouped by what they tested:

- **`simulate_gann_*.py`, `backtest_gann.py`, `simulate_fib*.py`,
  `fib_optimizer.py`** — Gann angle and Fibonacci-based strategies.
  Earliest exploration; not carried forward.
- **`simulate_smc*.py`, `simulate_and_log*.py`** — early FVG-only SMC
  variants, before liquidity sweeps or structure confirmation were added.
- **`simulate_ema_crossover.py`, `simulate_ema_rsi_vol.py`,
  `simulate_ema20_fvg_sniper.py`** — EMA-stack and RSI/volume filters on
  top of FVG entries. Controlled signal testing later showed FVG itself
  carries no directional information (lift ≈ 1.00 against a random
  control) — these predate that finding.
- **`simulate_liquidity_sweep*.py`** — the direct ancestors of the
  current strategy: liquidity sweep + FVG, then + structure break, then
  weekly/daily-only pools. The best of these is what became `smc_engine.py`
  after fixing look-ahead bias and formalizing the CHoCH + order-block
  + displacement sequence.
- **`simulate_daily_sr_bounce.py`, `simulate_2day_sr_bounce.py`** —
  pure support/resistance range-bounce, no SMC structure. High
  reward:risk but very low win rate (11–23%); not pursued further.
- **`simulate_live_bot_exact.py`** — exact replica of the legacy v1
  bot's logic, used to confirm its real-data losses before rebuilding.
- **`simulate_momentum_system.py`** — a symmetric multi-timeframe
  momentum system, the one significant non-SMC direction tested. Real
  edge in signal analysis (`roc48 > 2%` scored lift 1.20–1.34,
  consistent pre- and post- look-ahead-bug-fix), but the trading system
  built on it lost money in every period once realistic execution was
  modeled — the edge didn't survive contact with stops and costs. Left
  here as a candidate worth revisiting with a regime filter, not a dead
  end.

None of these were run through `validate_engine.py`'s look-ahead and
equivalence checks as rigorously as the current strategy was — treat
their reported returns as indicative, not trustworthy, even where they
look good.
