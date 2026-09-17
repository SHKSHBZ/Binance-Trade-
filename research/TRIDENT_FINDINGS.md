# Trident London-Killzone — tested on real gold, DOES NOT hold

**Status: FAILED on the real instrument.** Was parked as promising on a BTC
proxy; real XAUUSD 2020-2026 disproved it. Code: `trident_killzone.py`.

## Gold verdict (the decisive test) — added after real XAUUSD data arrived

Ran the exact code on real Exness XAUUSD 30m, 2020-2026 (66 setups, causal):

- **20R target: −82%** pooled (hit 20R just 3 times in 66 trades).
- **No target (ride to stop/bail): +48%** — BUT it is a mirage:
  - **6 of 7 years lose money**; only 2023 is positive (+122%).
  - **Top 3 trades = 139% of all profit**; without them, −70R.
  - The top trade had a **$0.10 stop** (entry 1948.1, doji-low 1948.0) — a
    stop *inside the spread*. With 1% risk sizing that near-zero risk
    manufactures a fake +229R. Several such sub-spread-stop trades carry it.
  - Filter to executable stops (≥0.05% of price ≈ $1): **+180R → −26R.**
    At ≥0.10%: +6R (breakeven). The "edge" was unexecutable trades.
  - **Buy-and-hold gold returned +180%** over the same span; the strategy
    made +48% while losing in 6 of 7 years. It underperforms doing nothing.

**Conclusion: no real edge on gold.** The BTC-proxy promise (+41%) and the
gold +48% were both driven by a few outlier trades, several with sub-spread
stops. Same false-positive pattern as every other setup this session. A
minimum-stop-distance filter (reject risk < ~0.1% of price) should be
standard in the harness to prevent this class of artifact.

---

## Original BTC-proxy notes (kept for the record — now known to be a mirage)

## What it is (the user's gold strategy, mechanized)

A long-only continuation setup, built for **XAUUSD** but tested on BTC as a
proxy (no gold data yet).

- **BIAS (daily):** `close > 200 EMA` AND a strong bullish daily candle
  (body/range > 0.5). Uses **yesterday's** finished daily candle (causal).
- **WINDOW:** 30m bars in the London Killzone **03:00–06:30 New York**.
- **STACK:** 30m EMAs fanning up `5 > 9 > 13 > 21` (momentum on).
- **FVG:** bullish 3-candle gap in the window (`low[i] > high[i-2]`); CE = 50%.
- **DOJI:** a doji taps the CE (small body ≤ 35% of range, lower wick ≥ body).
- **ENTRY:** the candle **after** the doji closes **below** the doji high → buy.
  (Closes above → invalid, skip.)
- **STOP:** soft — exit when a 30m candle **closes below the doji low**.
- **BAIL:** EMA5 < EMA21 bearish cross exits early. **(load-bearing — see below)**
- **TARGET:** the strategy's own design uses min 1:20 R:R.

## Results on BTC proxy (causal, honest fees + slippage)

| Cut | Trades | 20R hit | Return | expR |
|---|---|---|---|---|
| 2023 | 11 | 2 | +32.8% | +2.92 |
| 2024 | 8 | 2 | −5.7% | −0.38 |
| 2025 | 6 | 1 | +13.5% | +2.42 |
| 2026 | 1 | 0 | +0.1% | +0.10 |
| **Pooled** | **26** | **5** | **+41%** | **+1.68**, edge 85% |

### Real-winner profile (target removed, ride to soft-stop / bail)

- **25 trades → 11 real winners (44%), 14 losers (56%).**
- Avg winner **+20.6R**, avg loser **−2.4R**.
- **3 trades carried +194R of the +195R total** (Jul-2024 +142R, Dec-2023 +30R,
  Jan-2023 +22R). Remove them and it's flat.
- This is a **low-win-rate, big-runner** strategy, not a high-accuracy one.

## What we learned tuning it (see `stop_buf`, `use_bail`, `bail_span` params)

The user's instinct — "losers are small, maybe stops are too tight" — was
tested three ways. All three refinements make it **worse**:

- **Widen the stop** → win rate unchanged (44%); just trades smaller, earns less.
  The doji-low stop is almost never what exits a loser — the EMA bail is.
- **Remove the bail** → win rate collapses to 20%, −$3,274.
- **Slow the bail** (EMA5 vs 34/50/89) → avg loss balloons −2.4R → −33R, blows up.

**Conclusion: the tight loss control is the edge. The 44% win rate is an
ENTRY property (BTC direction ≈ coin flip), not an exit problem, and cannot
be fixed by adjusting exits.** Original parameters are the sweet spot.

## Open questions / next steps to develop performance

1. **Run on real XAUUSD 30m + daily.** This is #1. Gold's London-session
   behavior is what the strategy was designed for; BTC is only a proxy.
   Same code — just point `run()` at gold data.
2. **Entry filtering** could raise the 44% — but on 26 trades any filter is
   almost certainly curve-fitting. Needs the larger gold sample first.
3. **Discretionary vs mechanical gap:** the real trader reads the "bright
   green momentum" indicator and liquidity by eye; the mechanical proxy
   (200 EMA + strong candle) is a floor, not a ceiling.

## How to run

```
python3 trident_killzone.py                 # BTC proxy, 20R target
python3 trident_killzone.py --rr 1000        # no target: ride to stop/bail
# run(file, start, end, rr=, stop_buf=, use_bail=, bail_span=)  <- tunables
```
