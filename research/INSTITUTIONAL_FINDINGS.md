# Published institutional / quant strategies on gold and BTC

The actual strategies of firms like Citadel and Renaissance are secret and need data we don't have:
thousands of instruments, order-book and tick data, fast execution. What *is* public is the
strategy families such funds and CTAs run, with academic papers behind them. Parameters below
come from the papers; nothing was tuned. Out-of-sample = 2025–26.

## 1. Time-series momentum + volatility targeting (Moskowitz, Ooi & Pedersen 2012; CTA core)
`institutional_tsmom.py`: daily, sign of the past 21/63/126/252-day return, 15% vol target, cap 3x, costs.

| | to 2024 | 2025–26 | long-only benchmark (to 2024 / 2025–26) |
|---|---|---|---|
| Gold, combo | +1.9%/yr, Sharpe 0.16 | +28.6%/yr, Sharpe 1.86 | +12.8% / +34.2% |
| Gold, 126d | +5.3%/yr | +32.6%/yr | same |
| BTC, combo | +26.8%/yr, Sharpe 2.04 | +3.2%/yr | +30.1% / **−9.9%** |
| BTC, 126d | +30.6%/yr | **+9.0%/yr** | same |

- **Gold:** it never beat simply holding gold, so it adds nothing there.
- **BTC:** in 2025–26, when BTC fell, holding lost 10% a year and 126-day momentum **made about 9% a year**.
  That protection in falling markets is what funds run it for. It is a swing/position strategy, held for weeks.

## 2. Intraday momentum (Gao, Han, Li & Zhou 2018, JFE)
`institutional_intraday_mom.py`: the return from the previous 17:00 ET to 10:00 ET sets the direction of the last half hour.

- **Gold:** trading the last half hour as the paper does is about 0 (−0.6bp build, +1.3bp test).
  The only consistent variant is **holding in the morning's direction from 10:00 to 16:00 ET**:
  +3.4bp build, +5.2bp test, positive in all 5 years, but weak (t≈1.3). At $4,000 gold that is about $2 per ounce per day.
- **BTC:** the last-half-hour effect is momentum in 2023–24 (+3.1bp gross) but reversal in 2025–26
  (+3.6bp gross). It flips sign, and both sizes are below the 6bp round-trip cost.
