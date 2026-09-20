# Trader Kane "SMT Divergence + PO3" — component isolation on gold

The playbook is built for **NQ/ES futures**. Its defining confirmation is SMT
divergence between two correlated index futures, which **cannot be substituted
with XAU or BTC** without becoming a different strategy. KANE-01 (stop entry)
and KANE-02 (retest entry) are therefore **untestable here**: Yahoo Finance,
Stooq and Databento are all blocked by this environment's egress proxy, so no
NQ/ES data can be obtained. Those two remain blocked pending a user export.

Rather than rebuild the whole machine for KANE-03 — whose core
(sweep -> rejection -> reversal) has already failed ~10x in this project — the
two genuinely **novel** components were isolated and tested on their own.
Code: `kane_components.py`.

Timezone note: the playbook's "10:00 AM EST" is New York *local* time.
10:00 EDT = 14:00 UTC = 18:00 Dubai; 10:00 EST = 15:00 UTC = 19:00 Dubai.
Worth noting 14:00 UTC is the highest-volatility hour measured on gold in this
project (1.60x day average) — the playbook picked the right hour.

---

## A) INVERSION ZONES — no effect beyond a random level

An FVG that price closes fully through flips polarity (a bull FVG closed
downward becomes resistance). Claim: it rejects on the retest. Measured MFE/MAE
over 24 bars from the zone CE, against a control of random bars/random side
with the same count and window.

| | n | held | MFE/MAE ratio | fwd 24 |
|---|---|---|---|---|
| **H1** inverted-zone retests | 6,576 | **51.2%** | 1.028 | +0.030 |
| H1 CONTROL random levels | 6,576 | 50.0% | 0.997 | −0.007 |
| **M15** inverted-zone retests | 17,768 | **49.5%** | 0.983 | −0.048 |
| M15 CONTROL random levels | 17,768 | **50.8%** | 1.012 | +0.032 |

**+1.2pp over control on H1, −1.3pp on M15.** The sign flips between
timeframes on samples of 6.5k and 17.8k. That is noise.

The split shows where even the H1 number comes from:

| | H1 held | M15 held |
|---|---|---|
| bull-FVG inverted (-> short signal) | 48.9% | 48.4% |
| bear-FVG inverted (-> long signal) | **53.8%** | 50.7% |

Only the **long** side is above 50, on an instrument that rose 179% over the
sample. That is drift, not the zone. **Rejected.**

---

## B) MIDPOINT TARGET — reached at exactly its geometric rate, not once more

Dealing range from confirmed H1/M15 pivots (strength 3, stamped at the
**confirmation** bar, not the pivot bar). Range >= 1.5x ATR. On a sweep of an
extreme that closes back inside: does price reach the 50% midpoint before it
reaches the sweep extreme?

| | base rate midpoint first | median RR | **breakeven win rate needed** |
|---|---|---|---|
| **H1** (n=3,512) | **44.1%** | 1.27 | **44.0%** |
| **M15** (n=8,392) | **50.4%** | 0.98 | **50.4%** |

**The hit rate equals the geometric breakeven to within 0.1pp on H1 and 0.0pp
on M15.** The race between the midpoint and the sweep extreme resolves exactly
as the distance between them predicts — there is no draw toward the midpoint
beyond geometry. Add costs and it is negative:

| | n | win | expR | totR | P(<=0) |
|---|---|---|---|---|---|
| H1 as a trade | 2,431 | 45.0% | **−0.093** | −225.3 | **100.0%** |
| M15 as a trade | 5,974 | 51.0% | **−0.092** | −552.3 | **100.0%** |

This confirms a prediction stated *before* the run: gold does not mean-revert
intraday (measured earlier in this project), so a midpoint-reversion target
should fail on gold. It did. The sharper version of the finding is not "mean
reversion does not happen" but **"it happens exactly as often as random
distance implies, and no more."**

---

## Verdict

Both novel components rejected on gold, on large samples, against controls.
KANE-03 is not worth building: its two distinguishing ideas carry no
information, leaving only the sweep/rejection core that has already failed
repeatedly here.

KANE-01 and KANE-02 stay **untested, not rejected** — they need synchronized
NQ/ES data this environment cannot reach.

A separate caution for KANE-01/02 whenever that data arrives: the playbook's
step 8 moves the stop to breakeven after the 11:00 H1 candle. On the trader's
own 82-trade log, breakeven at +0.5R took a 2:1 system from **+0.122R to
−0.074R**. Breakeven must be an on/off variant from day one, never a default.
