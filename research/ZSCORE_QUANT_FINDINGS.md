# Z-score "quant" strategies (trader-supplied), tested exactly as written

Script: `zscore_quant_test.py`. Rules unchanged; entry at signal close, stop intrabar,
exit when z crosses 0, costs $0.25 (gold) / 0.06% (BTC). Nothing was tuned.

| strategy | n (/yr) | win | avg R | P(luck) | long / short | $5k @2% |
|---|---|---|---|---|---|---|
| Gold mean-rev 15m | 436 (103) | 57% | +0.04 | 19% | +0.06 / +0.02 | $6,586 |
| Gold mean-rev 1h | 166 (25) | 60% | +0.10 | 10% | +0.19 / −0.05 | $6,691 |
| BTC momentum 15m | 1728 (486) | 31% | +0.00 | 46% | +0.05 / −0.04 | **$2,824** |
| BTC momentum 1h | 433 (122) | 32% | +0.12 | 6% | +0.20 / +0.02 | $11,189 |
| (cross) momentum logic on gold 1h | 497 (74) | 39% | +0.11 | 2% | +0.24 / −0.03 | $12,770 |
| (cross) mean-rev logic on BTC 1h | 146 (41) | 56% | −0.08 | 87% | −0.15 / −0.02 | $3,816 |

- Gold 15m (the intraday version) was positive in 2022–23 and **negative in 2024, 2025 and 2026**.
- The gold "volatility contracting" filter (`atr_slope < 0.5*ATR`) passes **99%** of bars, so it filters nothing.
- Every positive cell is carried by **long** trades, while shorts are about 0. That is the gold/BTC bull
  markets (long beta), the same pattern as every earlier test in this repo.
- BTC 15m momentum breaks even on average but loses 44% of the account at 2% risk, because its
  31% win rate produces long losing streaks.
- The 1h versions hold ~17–34 hours, so they are not intraday.
