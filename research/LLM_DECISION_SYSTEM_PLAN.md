# LLM-Assisted SMC Decision System — Plan

A plan for adding an LLM "brain" on top of the mechanical SMC engine. The
engine finds candidate setups deterministically; the LLM adds judgment,
context, and a news/event filter that the rule engine is blind to. Every
decision is logged and — critically — validated with the same discipline
that showed the pure rule strategy had no edge.

## The honest premise (read this first)

An LLM **cannot predict price**. It has no crystal ball, and feeding it a
chart won't create an edge the rules couldn't find. So we are NOT betting
on the LLM to "know" where the market goes. We are using it for three
things it can genuinely do:

1. **Judgment on a mechanical setup** — weigh context (higher-timeframe
   trend, where price sits in the range, quality of the structure) and say
   *take / skip / size-down* with written reasoning. This can only help if
   it removes bad setups more often than good ones — and that must be
   proven, not assumed.
2. **News / event awareness** — read headlines and the economic calendar
   and flag high-impact events (FOMC, CPI, major crypto news). This is
   *new information the rule engine never sees*, and is the most likely
   place real value comes from.
3. **A full "LLM decides" mode** — for comparison only. Weakest evidence,
   highest cost; we test it to *measure* it, not because we expect it to
   win.

The bar is unchanged: **any LLM mode must beat the baseline** (the engine
taking every setup, and random) on validation before it touches money.

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
   live/hist 15m →  │ 1. MARKET-STATE BUILDER (deterministic)  │
   candles          │    reuse smc_luxalgo + smc_engine:       │
                    │    4H pools, 15m trend, armed setup,      │
                    │    premium/discount, ATR/RSI → text brief │
                    └───────────────┬─────────────────────────┘
                                    │  compact "market brief"
   news/calendar →  ┌───────────────▼─────────────────────────┐
   (API / web       │ 2. NEWS & EVENT FILTER (LLM)             │
   search)          │    summarize: high-impact events soon?   │
                    │    directional bias? → event note        │
                    └───────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────┐
                    │ 3. LLM ANALYST (structured output)       │
                    │    input: market brief + event note      │
                    │    output (JSON): action, confidence,    │
                    │    reason, entry/stop/target or "engine"  │
                    └───────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────┐
                    │ 4. DECISION COMBINER (rules)             │
                    │    Mode A: engine setup AND analyst=take │
                    │            AND no imminent hi-impact news │
                    │    Mode B: engine + news filter only      │
                    │    Mode C: LLM decides alone (compare)    │
                    └───────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────┐
                    │ 5. RISK + EXECUTION (existing bot)       │
                    │    1% risk, sizing, Binance testnet       │
                    └───────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────┐
                    │ 6. JOURNAL (existing, extended)          │
                    │    plan + LLM reasoning + news + outcome  │
                    └─────────────────────────────────────────┘
```

**What we reuse (already built):** the SMC labeler (`smc_luxalgo.py`), the
engine (`smc_engine.py`), the causal backtest harness, the risk sizing,
the live bot, and the trade journal. The LLM layer is *added on top* — it
does not replace the mechanical setup detection.

---

## The three modes (so we can compare)

| Mode | What decides the trade | Tests which LLM role |
|---|---|---|
| **A — Analyst filter** | Engine finds setup → LLM says take/skip → news gate | Judgment (role 1) + news (role 2) |
| **B — News filter only** | Engine finds setup → only news gate, no analyst | News (role 2) in isolation |
| **C — LLM decides** | LLM given market brief, decides long/short/skip | Full decision maker (role 3) |

We backtest all three against the **baseline** (engine takes every setup)
and against **random**. The winner — if any beats baseline — is the one
that goes to a forward test.

---

## What the LLM actually sees (the "market brief")

A compact, **anonymised** text/JSON snapshot built from the engine, e.g.:

```
Trend (4H structure): bearish
Price vs range: upper third (premium)
Setup: SHORT — swept a 4H high 3 bars ago, 15m CHoCH down confirmed,
       order block + FVG present
Nearest opposing liquidity (target): ~2.8R away
Recent 15m swings: lower highs, lower lows
ATR(14): 0.9% | RSI(14): 61
Event note: high-impact USD CPI in 40 min → CAUTION
```

Note: **no absolute dates, no absolute price levels** in the historical
backtest (see contamination below) — only relative structure.

---

## Model & cost (open-ended, your call)

Decisions are rare (~1–2/week live; ~200 setups over 3 years of history),
so cost is small. Per-decision ≈ 2k input + ~2.5k output tokens:

| Model | Per decision | Backtest all ~200 setups | Live (per week) |
|---|---|---|---|
| Haiku 4.5 (cheapest) | ~$0.015 | ~$3 | ~$0.03 |
| Sonnet 5 (balanced) | ~$0.03 | ~$6 | ~$0.06 |
| Opus 5 (strongest) | ~$0.07 | ~$15 | ~$0.15 |

**Recommendation:** backtest with **Sonnet 5** (good judgment, cheap in
bulk); run **live** on **Opus 5** (pennies per week, best judgment). Code
uses the Anthropic SDK; the model is a one-line config, so you can dial
cost vs quality any time, or swap providers later. **Cost is not a
blocker** — the engine's selectivity keeps call volume tiny.

---

## The hard part: how do we validate this honestly?

This is where most "AI trading bot" projects fool themselves. Three real
problems and how we handle them:

1. **Training contamination (look-ahead).** An LLM may *remember* what BTC
   did on a historical date. If we show it "2025-03-15, BTC $84,000," its
   "analysis" could be hindsight, not skill.
   → **Fix:** the historical brief is *anonymised* — no dates, no absolute
   prices, only relative structure and percentages. Imperfect, but removes
   the obvious leak. We also spot-check by asking it to date/price a brief;
   if it can, the anonymisation failed.

2. **Historical news is contaminated too.** Getting true point-in-time
   news for a past date without leaking the outcome is hard.
   → **Fix:** the **news filter is validated forward-only** (live/paper),
   not on history. History tests judgment (mode A-without-news and C); news
   value is measured in the forward test.

3. **Non-determinism.** Same input → different output.
   → **Fix:** run each historical setup a few times, use the majority
   decision, and report the variance. A decision that flips run-to-run is
   not a decision.

**Because of all this, the real proof is the FORWARD test** (paper/testnet,
going forward, zero contamination possible) — exactly like we always said
the live fill question could only be answered forward. History gives a
cheap first read; forward gives the verdict.

---

## Phased build plan

**Phase 1 — Market-brief builder (deterministic).** Turn the engine's
state at any bar into the anonymised text brief. No LLM yet. Reuses
existing code. *Safe, cheap, testable on its own.*

**Phase 2 — LLM analyst call.** Anthropic SDK, structured output (JSON:
`action`, `confidence`, `reason`, optional levels). One function:
brief → decision. Deterministic-as-possible settings, logged.

**Phase 3 — News/event filter.** Pull calendar/headlines (web-search tool
or a calendar API), LLM summarises into the event note. Live-only for
validation.

**Phase 4 — Decision combiner + 3 modes.** Wire modes A/B/C; each produces
a take/skip that feeds the existing risk/execution/journal path.

**Phase 5 — Contamination-controlled historical eval (~$3–15).** Run modes
A and C on the ~200 historical setups, compare vs baseline and random.
Report win rate, expectancy, and decision variance. *Go/no-go gate.*

**Phase 6 — Forward paper/testnet test.** The honest proof: LLM decides on
live setups going forward (all three roles, including news), logged in the
journal, 30–40 trades. Compare to the engine-only baseline running beside
it.

**Phase 7 — Live, only if it beats baseline forward.** Same as before:
1–2% risk, small, eyes open.

---

## Honest expectations

- The **news filter (role 2)** is where I'd bet real value lives — it adds
  information the rules can't see.
- The **analyst (role 1)** *might* help by pruning bad setups; it must be
  proven to prune losers more than winners.
- The **full-LLM mode (role 3)** is the least likely to beat the rules; we
  test it to know, not because we expect it.
- An LLM layer is **not** a fix for "the underlying setup has no edge." If
  the setups are coin-flips, judgment on coin-flips is still coin-flips.
  The one exception is the news filter, which can add genuinely new signal.

The whole thing is built so we **measure** each role rather than believe
it — the same discipline that just saved us from funding a dead strategy.
