# Why do the sell trades lose? (`short_side_analysis.py`)

1. **The market rose:** gold went from 1,519 to 4,267 (+181%) and BTC from 16.5k to 64k (+290%).
2. **Same entries, same stops, same holding time, direction forced:** gold mean-rev all-long +0.15R and
   all-short −0.13R. Selling at those exact moments loses whatever the signal says, so the problem is the market.
3. **Shorts work when the market falls:** they average +0.09 to +0.34R when the next month fell, and −0.14
   to −0.25R when it rose. 55–61% of shorts came just before a rising month, because most months rose.
4. **A simple filter doesn't fix it:** splitting shorts by whether the past 60 days were falling or rising
   changes nothing (about −0.03R either way). The coming month can't be read from the last two.
5. **It flips when the market turns:** BTC shorts made +0.05R in 2025 and +0.29R in 2026 (BTC 93k→64k),
   while BTC longs lost both years. Gold momentum shorts made +0.17R in 2026.
6. **Gold dips got bought quickly:** 51% of gold mean-rev shorts hit their stop, against 30% of longs.
   In 2025 a sharp drop was followed by +11bp on average over the next 24h. In 2026 that reversed:
   −55bp, so drops kept falling.

**Conclusion:** the sell rules are not broken. They lose because the market mostly went up. In the
years it fell, the sells made money and the buys lost. Dropping sells for good would have hurt in 2026:
the NY breakout's short trades are what kept it positive that year.
