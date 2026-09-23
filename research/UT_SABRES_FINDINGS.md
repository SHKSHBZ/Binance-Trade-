# UT Bot (key 2, ATR 1) + MA Sabres (TEMA-50) — the trader's strategy, tested

Scripts: `ut_sabres_backtest.py`, `ut_sabres_fixed_tp.py` (trader's own, run
unchanged) and `research/ut_sabres_diagnose.py` (same run(), costs/TF/asset varied).
Code review: signals are causal (TEMA and UT stop computed forward only, entry at
the signal close, exits checked from the next bar). No look-ahead found.

## As written — both versions lose
- Swing stop + baseline-cross exit, BTC 15m: 25-27% win, −0.14 to −0.18R/trade,
  −91% (2025), −81% (2026 out-of-sample).
- Fixed $1,000 TP / $250 SL: account to zero at 5x, 10x and 20x. A $250 stop is
  10% of a $2,500 account per trade; at a 25% win rate, 10 losses in a row is routine.

## Why — the signal is ~zero, and trading it often makes it negative
| | trades/yr | avgR with costs | avgR zero costs | cost per trade |
|---|---|---|---|---|
| BTC 15m | 1,601 | −0.162 | −0.015 | 0.12R |
| BTC 1h 2023-25 | 377 | −0.094 | −0.029 | 0.05R |
| BTC 1h 2026 | 362 | +0.006 | +0.064 | 0.05R |
| Gold 15m | 1,054 | −0.046 | −0.024 | 0.02R |
| Gold 1h | 250 | +0.039 | +0.050 | 0.01R |

Even with zero costs the signal is about zero. On 15m it trades ~1,600 times a
year, so costs turn nothing into a big loss.

Gold 1h is the only positive cell (+0.039, P(luck) 7%), but longs carry it
(P 1%) while shorts are nothing (P 57%) — gold's uptrend, not the signal — and
its top-10 trades are 110% of the profit (negative without them).

## Verdict
No edge. Not a bug; the entry does not predict direction.
