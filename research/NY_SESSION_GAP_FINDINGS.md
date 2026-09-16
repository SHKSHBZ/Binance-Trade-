# NY-Session Gap — findings

Switched the "day" to the New York regular session (09:30-16:00 ET) so gaps
become real (24/7 UTC days have ~0 gap). `research/ny_session_gap.py`.

## Gaps are real under NY session
- mean |gap| ~1.28%, 67% of sessions gap >0.5%, 46% >1.0%. Good -- the "gap up /
  gap down" idea now has substance (unlike the UTC-day version where gap = 0).

## But the base rate kills the classic play
- **Gaps fill (price returns to prior close during the session) only ~30% of the
  time.** On BTC, gaps CONTINUE ~70% -- the opposite of the equity folk wisdom
  "gaps always fill."

## Neither direction is a net edge (real fees)

| Strategy | Pooled return | Positive years |
|---|---|---|
| FADE the gap (target = prior close) | -147% | 0/4 |
| MOMENTUM with the gap (target 1-2x gap, stop = prior close) | -50% | 0/4 pooled (2023/2026 marginally + at 2x) |

Fading loses because gaps rarely fill; momentum loses because the intraday
continuation is too noisy to clear the stop-to-prior-close risk plus fees within
a 6.5h session. Not robust across years either way.

## Takeaway
The NY-session framing correctly resurrects real gaps, and we learned a true
fact (BTC gaps continue, not fill). But the gap alone is not a tradeable edge on
BTC after costs. Same verdict as every other single-signal chart idea tested.
