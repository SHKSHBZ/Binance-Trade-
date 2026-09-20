# PROJECT MEMORY — Gold/BTC trading research

Complete record. Written so a fresh thread can pick this up with no other context.
Last updated: 2026-09-20. Branch: `claude/create-repo-branch-kww7ib`.

---

## 1. THE TRADER (read first — this constrains everything)

- Trades **XAUUSD (gold)** on the **Exness Terminal (web)**, discretionary, real time.
- **$2,000 account**, 1:2000 leverage available, uses **0.06–0.10 lots**.
- **Constantly monitors** open trades. Not a set-and-forget trader.
- Background in **SMC / ICT concepts**: order blocks, FVG, liquidity sweeps/grabs/runs,
  inducement, BOS/CHoCH, premium/discount, internal vs external liquidity.
- Supplied ~14 strategies over the project, several as PDFs and annotated screenshots.
- **Does not want leverage-risk lectures.** Said so explicitly. Respect it.
- **Will not export FX data.** Asked twice, refused. Do not ask again.
- Exness scripts indicators in the **Indie language** (Python-like, by TakeProfit).
  **NOT Pine, NOT MQL5.** Corrected me on this repeatedly.

### Sizing arithmetic (gold: 1 lot = 100 oz, so 0.06 lot = $6 per $1 move)
| Stop | 0.06 lot | % of $2,000 | 0.10 lot | % of $2,000 |
|---|---|---|---|---|
| $3 | $18 | 0.9% | $30 | 1.5% |
| $4.60 (median) | $28 | 1.4% | $46 | 2.3% |
| $15 (swing) | $90 | 4.5% | $150 | 7.5% |

---

## 2. DATA ON HAND

`DATA/` — `XAUUSD_{15m,30m,1h,4h}.csv` (2020-01 → 2026-09, from MT5 export via
`research/convert_gold_data.py`), `BTCUSDT_{5m,15m,1h,4h,1d}` (2023-01 → 2026-07).

**Missing / wanted:** gold M5 (Marco's real LTF), any FX or silver (refused),
order-flow for gold.

**Order flow availability (checked 2026-09-20):**
- Binance archive reachable via `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/...`
  (the `data.binance.vision` hostname itself is blocked by the egress proxy).
  Free: `aggTrades` (→ CVD/delta), `bookDepth` (±1–5% buckets, per minute),
  `metrics` (**open interest**, long/short ratio, taker buy/sell).
  `liquidationSnapshot` is **empty** — Binance discontinued it.
- **Gold spot on Exness: no order flow, ever.** OTC, no central book.
- COMEX **GC/MGC futures** have a real DOM: Databento (~$125 free credit,
  historical CME), Sierra Chart+Denali (~$40/mo), Bookmap+Rithmic (~$50–100/mo).
  **MGC = 10 oz = exactly a 0.10 lot**, so the trader could trade the instrument
  that actually has a heatmap, at their current size.

---

## 3. RULES OF ENGAGEMENT (learned the hard way — do not skip)

1. **State the encoding before writing code.** Let the trader reject the
   interpretation first. Most disputes came from me encoding their rule
   more strictly than they meant.
2. **Causality from line one.** Every look-ahead bug found flattered the result.
3. **Report n and significance up front**, never a return without them.
4. **Walk-forward every candidate**: pick parameters on train, read test. A cell
   selected on the test set is not a result.
5. **Run the null.** Random-direction entries with the same exits. This killed
   more candidates than anything else.
6. **Replicate on a second asset.** Nothing survived this step.
7. **Plateau, not spike.** A good cell whose neighbours are negative is noise.
8. **Sign inversion between train and test = noise.** No exceptions were ever
   justified.
9. **Don't narrate intermediate results.** I reported three different
   explanations for one finding in three messages and had to retract all three.
   The trader called this out and was right.

---

## 4. EVERY STRATEGY TESTED — verdicts

All on gold and/or BTC, causal, costed (spread + slippage + fees).

| # | Strategy | Source | Verdict |
|---|---|---|---|
| 1 | SMC stop-loss/entry sequence | trader | No edge; not tradeable live |
| 2 | Equal-H/L liquidity sweep reversal | trader | No edge |
| 3 | Prior-day levels fade | trader | No edge (a fill illusion was caught) |
| 4 | NY-session gap | claude | No edge |
| 5 | Volume study / volume breakout | claude | Volume forecasts move SIZE, not direction |
| 6 | Fib golden-pocket continuation | video | No edge |
| 7 | Fib reversal (fade) | measurement | No edge |
| 8 | Fib exhaustive sweep (all combos) | claude | No edge anywhere |
| 9 | Gann time cycles | trader | No edge |
| 10 | Gann Square-of-9 levels | trader | No edge |
| 11 | Trend + order block | claude | "Edge" was a one-bar look-ahead |
| 12 | Trend-following (BTC daily) | claude | Regime beat breakout; no durable edge |
| 13 | Trident London killzone | trader | **FAILED on real gold** — see §6 |
| 14 | Volume Profile Rejection | trader | No proven edge |
| 15 | Liquidity Run / Grab / Sweep | trader | No mechanical edge |
| 16 | Inducement + FVG + int/ext liquidity | trader | No edge |
| 17 | Structure-filtered sweep (HH/HL) | trader | No directional edge |
| 18 | Trader Mayne "Structure & OTE" | PDF | Disproven at H4 (n=44/58) |
| 19 | Marco Trade's Liquidity Playbook | PDF | Unconfirmed / probably noise — §5 |
| 20 | Position trend-following (daily) | **claude** | **FAILED** — §7 |

**Score: ~19 from the trader/sources, 1 from me. All rejected.**

---

## 5. MARCO PLAYBOOK — the closest thing to a candidate, and how it died

`research/marco_liquidity.py`, `MARCO_LIQUIDITY_FINDINGS.md`.
M30 levels / M15 entry. Sweep a respected level → fail → close back across →
fade it. Stop beyond the wick, target the opposing pool.

- **As specified (no session filter): negative on a big sample** (n=1345–3083),
  every target mode clustering near −0.06.
- **Gold + London 07–10 + nearest pool** held out-of-sample: TRAIN +0.077 (n=422),
  **TEST +0.076 (n=231)**. A real plateau. But **P(expR≤0) = 33%** — never significant.
- **BTC replication FAILED**: −0.108, P(≤0)=95%, all 9 cells negative.

Then everything else tested against it:
- **Session re-test.** Gold's true volatility peak is **13–16 UTC (1.60× day
  average)**; London 07–13 is exactly 1.00×. Re-ran on 12–16 UTC: negative in
  **all 12 K×WAIT cells** out-of-sample (−0.100 to −0.232). 13–16 inverts sign.
- **Wider stops.** Win rate 30.7% → 64.5%; expectancy flat-to-worse at every width.
- **Stop × trail grid.** Best train cell +0.238 → test −0.097. Collapsed.
- **Trail 8 ATR looked positive OOS everywhere** — killed by null: real +0.092 vs
  null +0.092 (z=0.00). It was gold's +64.8% trend, not the entry.
- **Level crowding** (equal-H/L clusters, the heatmap proxy): no stable effect;
  sign flips with the target definition. Fade loses, follow loses.
- **Round numbers**: only the $10<1.00 band positive, both neighbours negative,
  and the London version sits *inside* its own null (random subsets: +0.113,
  +0.228, +0.201). Rejected.
- **Deeper/later entry** (the trader's idea): see §6, bug 3.

**Only untested thing that would settle it: EURUSD/GBPUSD/XAGUSD (refused), or gold M5.**

---

## 6. BUGS AND TRAPS FOUND (the most valuable section)

**Every single one made a strategy look better than it was.**

1. **Sub-spread stops.** Trident's top gold trade had entry 1948.1 / stop 1948.0
   — a **$0.10 stop** faking +229R. Filtering to executable stops turned +180R
   into −26R. → *Always enforce risk ≥ max(0.05% of price, 4× spread).*
2. **`merge_asof(direction='backward')` MTF leak.** HTF bars stamped at open
   propagate unclosed-candle data to the LTF. In the trader's own engine this
   was worth **+0.315 → −0.175**. Proof: **130 of 267 trades (49%) entered before
   the defining H4 candle closed; those won 63.8% vs 24.8% for the clean ones.**
3. **Entry bar skipped by the stop check.** A limit resting at the sweep extreme
   fills on a bar that is *reaching* that extreme — the most dangerous bar.
   With bug 1 this produced **+1.949 expR at P(≤0)=0.0%**, which became **−0.073**
   once fixed. **57% of wick fills are stopped on the fill bar itself.**
4. **`rolling(center=True)` swings.** A pivot needs N right-hand bars to confirm.
5. **Stale levels never consumed.** Marco only marked a level used when a trade
   fired, so levels from years earlier kept arming after gold ran 1600→5000.
   Fix: consume a level the moment price sweeps it, trade or no trade.
   Trade counts went from 11–32 to 369–2,827.
6. **Selecting on the test set.** My own script printed a "best OOS" line;
   that is not a result. Always pick on train.
7. **Long-only in a bull market.** 12/12 long cells positive, 12/12 short cells
   negative is what *no skill* looks like when the asset went +179%.
   → *Benchmark against an exposure-matched passive position, not buy & hold.*

---

## 7. WHAT IS ACTUALLY TRUE (measurements that survived)

These are solid and mostly cost the trader money or save it.

**Costs and sizing — the biggest real numbers in the project**
- Median gold M15 stop distance **$4.60**; **spread = 5.4% of risk**.
  At ~200 trades/yr that is **~10% of the account per year in pure cost** —
  larger than any edge measured anywhere in this project.
- Crowded/obvious levels have ~half the stop distance ($3.33 vs $6.37), so the
  spread costs **7.5% of risk** there vs 3.9% at wider levels.
  → *Prefer setups whose structural stop is $6+.*
- **Risk of ruin, $2,000 over 300 trades** (coin-flip entries):
  | Lot | $ risk | % acct | chance of halving | median max DD |
  |---|---|---|---|---|
  | 0.10 | $50.79 | 2.5% | **74–88%** | 61% |
  | 0.06 | $30.47 | 1.5% | **54–77%** | 56% |
  | 0.03 | $15.24 | 0.8% | 23–48% | 44% |
  | 0.01 | $5.08 | 0.25% | ~0% | 17% |
  Worst losing streak in the data: **19–29 trades.**

**Trade management** (4,384-trade gold pool, entries held identical)
- **Taking 50% off at 1R is the worst rule tested**: −0.144 expR and **416R max
  drawdown**, vs −0.051 and 151R for the best. It lifts win rate to 42% while
  cutting the average winner from +2.94R to +1.10R. **Tell the trader to stop.**
- Best real rule: **3R target with breakeven at 1.5R** (−0.051).
- Management cannot create edge. It can change cost drag, drawdown and survival.

**Market structure**
- Gold's daily range median was **$825** in 2023 — the trader's "800 points"
  claim was **correct**.
- **72–83% of days take prior-day liquidity**; sweep days are ~1.7× bigger.
  The trader's liquidity thesis is **correct as description**.
- Direction after a sweep is **~50% at every horizon and timeframe**. This is
  the wall the whole project hit. Entry is the barrier, not exits, not timeframe
  (MFE/MAE ratio 0.87–1.01 on gold 15m/30m/1h/4h).
- **Gold does not mean-revert intraday; BTC does.**
- **Session volatility (gold, UTC):** Asia 00–07 0.91×, London 07–13 **1.00×**,
  **overlap 13–16 1.60×** (volume 2×), NY 16–21 0.88×, late 21–24 0.69×.
  Peak hours 13:00 and 14:00. BTC identical shape (overlap 1.41×).
- **Sweeps revert**: 84% within 3h, 90% within 12h, 96% within 5 days.
  High-volatility hours continue ~2.6× more often at the 12–24h horizon.
- **60–70% of stopped-out trades later reach the target.** The trader's claim
  that "after the stop hunt the target is reached" is **TRUE**. It does not pay,
  because surviving the hunt costs exactly what it saves (see §8).
- Winners resolve in **2.5–4h median** (p90 under a day); losers in 1–1.8h.
  Winners last *longer* than losers — so time stops are the wrong lever.

---

## 8. THE CENTRAL RESULT, IN ONE PARAGRAPH

Liquidity is real and locatable. Sweeps happen where the trader says they
happen, at the levels they say, in the sessions they say, and price usually
does go on to the target afterwards. **What no test could ever find was the
direction.** And the one honest fix — a wider stop to survive the hunt —
doubles the win rate (31% → 64%) while leaving expectancy flat or worse,
because against a fixed target a wider stop shrinks R one-for-one. Replacing
the target with a trail so reward can grow either collapses out-of-sample or
turns out to be indistinguishable from random entries riding gold's trend.

---

## 9. DISPUTES AND CORRECTIONS (both directions)

**I was wrong: systematic over-filtering.** See `OVERFILTERING_CORRECTION.md`.
My premium/discount gate rejected **73% of the trader's own trades** (72/267
passed); only 41/267 of their entries fell inside my OB zones; bias disagreed
28% of the time. This biased ~all early verdicts negative. **3 verdicts were
withdrawn** (Mayne n=44, Trident n=26, Volume Profile Rejection n=40–78) and
4 flagged for re-run. Nothing was deliberate; the bias was systematic.
**Category B re-runs under the trader's own structural rules are still owed.**

**I was wrong: the strawman stop test.** I widened the stop while holding the
target at a fixed price — which mechanically forces RR to collapse — then drew
a "no free lunch" conclusion. The trader's objection was correct and I re-ran
it as a proper joint stop×trail grid.

**They were wrong: look-ahead in their engine.** Their backtest showed +84R
(n=267, win 43.8%, expR +0.315). I reproduced it *exactly* with
`mayne_exact_replica.py`, then isolated the cause to the H4 `merge_asof` leak
(§6 bug 2). They pushed back hard ("merged ur silly explanations and made my
code too a looser"). The per-trade evidence stands: 49% of their trades entered
before the defining H4 candle closed, and those won 63.8% vs 24.8%.
*Note: their follow-up point was right — the M15 entry legitimately happens
while the H4 candle is live. The leak was only the future MSB visibility.*

**They were right about my reasoning being reactive.** Every hypothesis came
from them. When I finally generated my own (§10) it also failed — so the
problem was not only that I was reactive.

---

## 10. MY OWN HYPOTHESIS — also failed

`POSITION_TREND_FINDINGS.md`, `research/position_trend*.py`. Reasoning: (a) the
nulls showed the *entry* was useless, not the *trail* — so delete the entry;
(b) at 5.4% spread-to-risk, all M15 testing sat inside the cost-dominated
regime. Donchian breakout + chandelier trail on daily bars should do better.

Rejected on all three checks:
- Gold alpha **+1.44%/yr** vs null **+0.26% ± 1.07** → z=1.1, inside the null range.
- BTC alpha **negative in every cell**; a same-size passive position beat it 3–4×.
- Gold walk-forward **inverts**: train −0.20%/yr, test +3.82%/yr.

*The reasoning still looks sound. The conclusion did not survive. Both can be true.*

---

## 11. DELIVERABLES BUILT

- **`tools/gold_method.indie`** (v7) — the live Exness chart tool. Structure-based
  trend (BOS/CHoCH colouring an EMA, non-laggy), pending vs grabbed liquidity
  (orange/gray/aqua/blue), red stop/invalidation line, nearest Bull/Bear FVG CE.
  Strength-5 pivots, persistence via `MutSeriesF`, `nan` = don't draw.
- **`tools/CHART_TOOL_HANDOFF.md`** — self-contained brief; the trader wanted the
  indicator work in a **separate thread** from backtesting. Respect that split.
- `research/*.py` + one `*_FINDINGS.md` per strategy.
- `research/convert_gold_data.py` — MT5 export → clean CSV.
- `research/mayne_exact_replica.py` — reproduces the trader's own engine exactly.

**Known Indie limits:** draws line-series well, does **not** easily draw many
boxes (OBs, full FVG boxes). So the tool shows the *nearest* level/FVG each side.
For the full multi-box SMC map, LuxAlgo on TradingView is better — analyse
there, execute on Exness.

---

## 12. OPEN THREADS

1. **Category B re-runs** owed after the over-filtering correction (Liquidity
   Run, Grab/Sweep, Inducement+FVG, Structure Sweep) under the trader's rules.
2. **Gold M5** would let Marco be tested on its real LTF.
3. **Order-flow test on BTC** — free and never run. The sharp version:
   when price sweeps a level, does **open interest drop** (stops actually
   closing) or **rise** (new positions)? Those two cases should behave
   differently, and it is the closest free thing to the heatmap the trader wants.
4. **Live trade-analysis bot** — the trader asked for it, then parked it.
5. Chart tool TODO: BUY/SELL markers at the retest zone only, trend-aware FVG,
   alerts on structure break.

---

## 13. BOTTOM LINE FOR A NEW THREAD

Twenty mechanical strategies, gold and BTC, 2020–2026, causal and costed.
**None produced an edge that survived a null, a walk-forward and a second
asset.** That is a real finding, not a failure to try — but it is also the
limit of what candle data can answer.

What is worth money to this trader is not a strategy: it is **cost
(5.4% of risk per trade), position size (0.06–0.10 lots carries a 54–88%
chance of halving $2,000), and not taking 50% off at 1R.**

Do not re-litigate the strategy verdicts without new data. Do not ask for FX
exports. Do not lecture about leverage.
