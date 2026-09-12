# Fib Golden-Pocket Continuation — findings (the video method)

Faithful build of the 5-step "golden pocket" method: 1H swing leg, trade only
the 0.5–0.618 pocket, **drop to 15M for a rejection confirmation (no blind
limit)**, HTF-trend filter, high-RR extension targets.
Code: `research/fib_continuation_backtest.py`. Scored with `trade_stats`.

## The video's claims vs reality

| Video says | We measured |
|---|---|
| ~3 of 10 trades hit stops (≈70% win) | **~30–42% win** (7 of 10 hit stops) |
| Tight stop inside the pocket is fine | **Tight (0.786) stop LOSES**; needs the wide (origin) stop |
| Edge from high-RR targets | True *direction*, but win rate is far lower than claimed |

The 70% win rate is not real on BTC. The method's *process* ideas hold up; its
*numbers* are marketing.

## What is genuinely robust (keep these)

- **Confirmation helps for continuation.** `confirm on` beat `confirm off` in
  all 6 stop/target pairs. Unlike the fade (where we enter with the move),
  here we buy into a falling pullback, so a 15M rejection candle is real
  information. Your "wait for confirmation" instinct is right — *for this trade
  type.*
- **The HTF trend filter is essential.** Best config with the daily-trend
  filter = +0.148R pooled; turn it OFF and it collapses to −0.133R. Only taking
  continuations in the direction of the daily trend is load-bearing.
- **Wide stop + far target.** Tight pocket stop (0.786) is negative everywhere;
  the wide stop (origin) with a 1.618 extension target is the only positive zone.

## But it is NOT a dependable edge (the honest killer)

Best config (stop = origin, target = 1.618 ext, trend on, confirm on):

| Year | Win rate | Return | Edge-is-real |
|---|---|---|---|
| 2023 | 35% | **−5.7%** | 31% |
| 2024 | 50% | **+26.8%** | 98% |
| 2025 | 37% | **−2.7%** | 40% |
| 2026 (Jan–Jul) | 52% | +10.0% (only 23 trades) | 90% |
| **Pooled** | **42%** | **+28.4% (+0.148R)** | 91% |

Pooled it survives 0.05% slippage (+0.137R). **But it is carried by 2024**, with
2023 and 2025 both losing — the exact one-good-year trap the SMC strategy fell
into (which rode 2025). A strategy that needs the right year is not an edge.

## Verdict

Three strategies tested on the same honest scoreboard now:

| Strategy | Pooled expectancy | Cross-year? |
|---|---|---|
| SMC sequence (earlier) | varies | no — 2025 only |
| Fib fade (reversal) | +0.070R | **closest** — positive 3 of 4 years, but thin |
| Fib golden-pocket continuation | +0.148R | no — 2024 only |

The **fade is still the most consistent** across years, even though its pooled
number is smaller. The continuation's bigger number is less trustworthy because
it leans on one year. Net: we keep two real process lessons (confirmation +
HTF-trend help continuation), but no version clears the bar of a *dependable*
cross-year edge.
