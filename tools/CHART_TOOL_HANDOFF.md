# Gold Method Assistant — Chart Indicator (handoff for a fresh thread)

**This folder is the complete, self-contained chart-indicator project.** Start a
new thread with these files attached; it needs nothing from the backtesting
research (which lives in `../research/` and stays in its own thread).

---

## Platform reality (read first — this decides everything)

- The trader executes on the **Exness Terminal (web)**, which scripts custom
  indicators in the **Indie language** (Python-like, by TakeProfit).
  **NOT Pine, NOT MQL5.** The live tool must be `.indie`.
- Instrument: **XAUUSD (gold)**, execution timeframe **15m**.
- The tool is **marking + alerts only** — it does NOT place trades. The trader
  reads it and executes manually (discretionary).

## Files here
| File | Language | Use |
|---|---|---|
| **`gold_method.indie`** | Indie | **THE live tool for Exness Terminal (current, v7).** |
| `gold_method.pine` | Pine v5 | Same idea for TradingView (superseded for Exness; keep for reference). |
| `prior_day_levels.pine` | Pine v5 | Prior-day levels + sweep alerts (TradingView). |
| `PriorDayLevels.mq5` | MQL5 | Same, for the MetaTrader 5 app (only if the trader ever uses MT5). |

## The method the tool supports (evidence-based)
Direction is ~a coin flip mechanically (proven in backtests), so the edge is
**payoff + discipline**, not prediction:
1. Trade **with the higher-timeframe / structure trend** only.
2. **Wait for a pullback (retest)** to a level — never enter at the breakout/flip.
3. Enter only if **reward ≥ 3× risk**.
4. Risk **1%** per trade, real stop beyond structure (never sub-spread).
5. Small losers, let winners run (breakeven at +1R).

## `gold_method.indie` (v7) — current legend
Lines drawn on the chart:
- **Structure Trend** — green = bullish structure (BUY side / longs only),
  red = bearish (SELL side / shorts only). Flips **at the BOS/CHoCH break**
  (close breaks last swing high/low) — non-laggy. (An EMA is the visual anchor;
  its COLOUR is driven by structure.)
- **Pending High** (orange) / **Pending Low** (aqua) — untapped liquidity = targets.
- **Grabbed High** (gray) / **Grabbed Low** (blue) — already-swept liquidity = spent.
- **Stop / Invalidation** (red) — structure low (for longs) / high (for shorts);
  if price closes beyond it the setup is dead. Use it to avoid chasing.
- **Bull FVG (buy dip)** (green) / **Bear FVG (sell rally)** (red) — nearest
  unfilled FVG 50%/CE entry for the smaller in-range trades; cleared once tapped.

Swing detection = strength-5 pivots (constant-index comparison over highs/lows).
All persistence via `MutSeriesF`; `nan` = "no value / don't draw".

## Version history (so the new thread knows what was tried)
- v1: trend EMA (green/red) — confirmed Indie compiles (plots + dynamic colour via `plot.Line`).
- v2: nearest swing liquidity, pending vs grabbed colour (single carried level — had a bug).
- v3: FIX — separate persistent pending (bright) + grabbed (gray) levels that stay put.
- v4: grabbed low = blue (distinct from grabbed high gray).
- v5: trend switched from price-vs-EMA to **structure (BOS/CHoCH)** — non-laggy.
- v6: **Stop/Invalidation** line (anti-chase; always see your risk boundary).
- v7: nearest **Bull/Bear FVG** entry levels (in-range trades).

## Known Indie constraints (important for planning next features)
- Indie draws **line-series well** but does **NOT** easily draw many discrete
  **boxes** (order blocks, full FVG boxes) or multiple stacked levels like Pine.
  So the tool shows the **nearest** level/FVG each side, not all of them.
- For the **full multi-box SMC map** (all FVGs, order blocks, EQH/EQL, premium/
  discount), **LuxAlgo SMC on TradingView is the better, free tool.** Recommended
  workflow: analyse with LuxAlgo on TradingView, execute on Exness with this tool.
- Confirmed-working Indie constructs: `@indicator`, `@param.int`, `@plot.line`,
  `Ema.new`, `self.high/low/close[k]`, `MutSeriesF.new`, `plot.Line(value,color=...)`,
  colours GREEN/RED/GRAY/ORANGE/AQUA (BLUE/RED newer — verify on compile).
- Uncertain / to verify in Indie: markers/shapes (`@plot.marker`?), boxes, fills,
  `bgcolor`, multi-timeframe (`sec_context`), alerts syntax.

## Next steps / TODO for the new thread
1. **▲BUY / ▼SELL arrow markers** that fire ONLY at the valid retest zone
   (not at the breakout) — needs Indie marker syntax confirmed.
2. **Trend-aware FVG**: only show the Bull FVG when trend is green, Bear FVG when
   red, so the chart only ever offers the valid in-range entry.
3. Optional: alerts on structure break / FVG tap (confirm Indie alert API).
4. Optional: order blocks — only if Indie box drawing turns out to be supported.

## One-line context on WHY this tool (not a bot)
~12 mechanical strategies were backtested on BTC and gold; none beat a coin flip
after costs (see `../research/`). Conclusion: the edge is the trader's live
discretion + risk discipline, so the deliverable is a **marking tool** that
supports that, not an automated system.

---
## NEW: `gold_merge.indie` (the tested strategy indicator)
Signals the GOLD-MERGE major-level reclaim on XAUUSD 1H. Reading guide:
`GOLD_MERGE_HOW_TO_READ.md`. Its logic is verified trade-for-trade against a
backtest by `research/indie_transliteration_check.py`. Only uses Indie
constructs already proven in gold_method.indie (MutSeriesF, plot.Line, Ema,
constant-index comparisons). Do not change the tested numbers (16, 3, 500, 3.0, 100).
