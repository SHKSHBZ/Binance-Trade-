"""
"Trident Pattern" London-Killzone model (the user's gold strategy).

Faithful mechanical version. Built instrument-agnostic: test on BTC now (proxy),
run on GOLD when data arrives (same code, just point it at gold 30m + daily).

Rules implemented:
  BIAS (daily): close > 200 EMA AND a strong bullish daily candle
                (proxy for the "Bull trading" bright-green momentum indicator).
  WINDOW: 30m bars in the London Killzone 03:00-06:30 New York time only.
  STACK : 30m EMAs 5>9>13>21 fanning up (momentum).
  FVG   : bullish 3-candle gap in the window (low[i] > high[i-2]); CE = 50%.
  DOJI  : price pulls back and a DOJI taps the CE (small body, lower wick).
  ENTRY : the candle AFTER the doji closes BELOW the doji high -> market buy.
          (closes above doji high -> invalid, skip.)
  STOP  : soft -- exit only when a 30m candle CLOSES below the doji low.
  TARGET: min 1:20 R:R (entry + 20 * risk). Reports how often it's reached.
  BAIL  : 30m EMA bearish cross (ema5 < ema21 close) exits early.

python3 trident_killzone.py   (BTC proxy)
"""
import _paths  # noqa: F401
import argparse
import datetime as dt
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades

CAP = 1000.0
TAKER, SLIP = 0.0004, 0.0005
RR_MIN = 20.0
DOJI_BODY = 0.35      # body <= 35% of range to count as a doji
MAX_HOLD = 300        # 30m bars to resolve (~6 days)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def run(m5_file, start=None, end=None, rr=RR_MIN):
    df5 = load_ohlcv(m5_file, start, end)
    df = df5.resample("30min").agg(open=("open","first"), high=("high","max"),
                                   low=("low","min"), close=("close","last")).dropna()
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    mins = ny.hour * 60 + ny.minute
    inKZ = (mins >= 180) & (mins <= 390)          # 03:00 - 06:30 NY

    # daily bias
    d = df5.resample("1D").agg(open=("open","first"), high=("high","max"),
                               low=("low","min"), close=("close","last")).dropna()
    d_ema200 = ema(d["close"], 200)
    body = (d["close"] - d["open"])
    rng = (d["high"] - d["low"]).replace(0, np.nan)
    bull_day = (d["close"] > d_ema200) & (d["close"] > d["open"]) & (body / rng > 0.5)
    bull_day = bull_day.shift(1)     # CAUSAL: today uses YESTERDAY's finished daily candle
    # map each 30m bar to its day's bias
    day_key = pd.Series(df.index.normalize(), index=df.index)
    biasArr = day_key.map(bull_day.to_dict()).fillna(False).values

    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    e5 = ema(df["close"],5).values; e9 = ema(df["close"],9).values
    e13 = ema(df["close"],13).values; e21 = ema(df["close"],21).values
    t = df.index; n = len(c)
    kz = np.asarray(inKZ)

    capital = CAP; trades = []; busy = -1
    hit20 = 0

    for i in range(25, n - 2):
        if i <= busy:
            continue
        # need: bias long, in killzone, EMA stack fanning up, a bullish FVG at i
        if not (biasArr[i] and kz[i]):
            continue
        if not (e5[i] > e9[i] > e13[i] > e21[i]):
            continue
        # bullish 3-candle FVG ending at i: low[i] > high[i-2]
        if not (l[i] > h[i-2]):
            continue
        ce = (h[i-2] + l[i]) / 2.0            # consequent encroachment (50%)
        gap_lo, gap_hi = h[i-2], l[i]

        # wait for a DOJI that taps the CE (within a reasonable window)
        entry = doji_hi = doji_lo = None
        for j in range(i+1, min(i+20, n-1)):
            tapped = l[j] <= ce <= h[j]
            rj = h[j]-l[j]
            bodyj = abs(c[j]-o[j])
            lower_wick = min(o[j], c[j]) - l[j]
            is_doji = rj > 0 and bodyj <= DOJI_BODY*rj and lower_wick >= bodyj
            if tapped and is_doji:
                # invalidation check on the NEXT candle
                k = j+1
                if k >= n: break
                if c[k] < h[j]:               # valid: closes below doji high
                    entry = c[k]; doji_hi = h[j]; doji_lo = l[j]; start_i = k
                break                          # only the first tap matters
        if entry is None or doji_lo >= entry:
            continue

        risk = entry - doji_lo
        target = entry + rr * risk
        # manage: soft stop (close below doji low), target, or EMA bail
        exit_px = exit_r = None
        reached20 = False
        for m in range(start_i+1, min(start_i+MAX_HOLD, n)):
            if h[m] >= target:
                reached20 = True
                exit_px, exit_r = target, "TARGET"; busy = m; break
            if c[m] < doji_lo:                 # soft stop
                exit_px, exit_r = c[m], "STOP"; busy = m; break
            if e5[m] < e21[m]:                 # EMA bail
                exit_px, exit_r = c[m], "BAIL"; busy = m; break
        if exit_px is None:
            m = min(start_i+MAX_HOLD, n)-1; exit_px, exit_r = c[m], "TIME"; busy = m
        if exit_r in ("STOP","TIME","BAIL"):
            exit_px *= (1 - SLIP)
        if reached20: hit20 += 1

        qty = (capital*0.01)/risk if risk>0 else 0     # 1% risk
        gross = qty*(exit_px-entry)
        fee = qty*entry*TAKER + qty*exit_px*TAKER
        capital = max(capital+gross-fee, 0.0)
        trades.append({"dir":"LONG","time":t[start_i],"entry":entry,"stop":doji_lo,
                       "target":target,"qty":qty,"notional":qty*entry,
                       "pnl":gross-fee,"exit_r":exit_r})
        if capital<=0: break
    return trades, hit20


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rr", type=float, default=20.0)
    args = ap.parse_args()
    print(f"TRIDENT LONDON-KILLZONE -- BTC proxy (no gold data yet), target {args.rr:.0f}R\n")
    YEARS = [("2023","BTCUSDT_5m_2023_to_2025.csv","2023-01-01","2023-12-31"),
             ("2024","BTCUSDT_5m_2023_to_2025.csv","2024-01-01","2024-12-31"),
             ("2025","BTCUSDT_5m_2023_to_2025.csv","2025-01-01","2025-12-31"),
             ("2026","BTCUSDT_5m_Jan_to_Jul2026.csv",None,None)]
    pooled=[]; tot20=0
    for label,f,s,e in YEARS:
        tr,h20 = run(f, s, e, rr=args.rr); pooled+=tr; tot20+=h20
        st = summarize_trades(tr, CAP, label=label)
        wr = 100*sum(1 for x in tr if x["exit_r"]=="TARGET")/len(tr) if tr else 0
        print(f"  {label}: trades={st.n:<3} hit-{args.rr:.0f}R={h20}  ret={st.ret_pct:+7.1f}%  expR={st.expectancy_r:+.3f}")
    ps = summarize_trades(pooled, CAP)
    print(f"\n  POOLED: trades={ps.n}  reached {args.rr:.0f}R: {tot20} times  "
          f"ret={ps.ret_pct:+.0f}%  expR={ps.expectancy_r:+.3f}  edge={ps.edge_confidence:.0f}%")
