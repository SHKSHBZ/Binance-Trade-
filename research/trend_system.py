"""
Clean trend-following system -- the only approach that survived honest testing.

No level entries, no order blocks. Just the two things that held up:
  1) trade WITH the trend, 2) let winners run (asymmetric exit).

Rules (daily BTC, causal):
  Filter : price above SMA200 (uptrend) for longs; below for shorts.
  Entry  : Donchian breakout -- close breaks the highest high of the last ENTRY_N
           days (long) / lowest low (short).
  Stop   : entry -/+ STOP_ATR * ATR(14).
  Exit   : chandelier trail (best price since entry -/+ TRAIL_ATR * ATR), i.e.
           ride the trend and let winners run.
  Sizing : 1% risk per trade via the initial stop (leverage-capped).

Reports the honest scoreboard AND buy & hold for the same period.
Run:  python3 trend_system.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from trade_stats import summarize_trades

CAP = 1000.0
TAKER, SLIP = 0.0004, 0.0005
ENTRY_N = 20        # Donchian breakout lookback (days)
STOP_ATR = 2.0
TRAIL_ATR = 3.0


def daily():
    a = load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"); b = load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")
    df = pd.concat([a, b]); df = df[~df.index.duplicated(keep="first")].sort_index()
    d = df.resample("1D").agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last")).dropna()
    return d


def atr(d, n=14):
    h, l, c = d["high"], d["low"], d["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def run(d, allow_short=False):
    o = d["open"].values; h = d["high"].values; l = d["low"].values; c = d["close"].values
    t = d.index; n = len(c)
    sma200 = d["close"].rolling(200).mean().values
    a = atr(d).values
    don_hi = d["high"].rolling(ENTRY_N).max().shift(1).values   # prior N-day high (causal)
    don_lo = d["low"].rolling(ENTRY_N).min().shift(1).values
    params = SMCParams(risk_per_trade_pct=0.01, leverage=5)

    capital = CAP; trades = []; i = 205
    while i < n - 1:
        if np.isnan(sma200[i]) or np.isnan(a[i]) or np.isnan(don_hi[i]) or a[i] <= 0:
            i += 1; continue
        long_sig = c[i] > don_hi[i] and c[i] > sma200[i]
        short_sig = allow_short and c[i] < don_lo[i] and c[i] < sma200[i]
        if not (long_sig or short_sig):
            i += 1; continue
        direction = "LONG" if long_sig else "SHORT"
        entry = c[i]
        stop = entry - STOP_ATR * a[i] if direction == "LONG" else entry + STOP_ATR * a[i]
        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            i += 1; continue

        peak = entry; exit_px = exit_r = None; j = i + 1
        while j < n:
            if direction == "LONG":
                peak = max(peak, h[j]); stp = max(stop, peak - TRAIL_ATR * a[i])
                if l[j] <= stp:
                    exit_px, exit_r = stp, ("STOP" if stp == stop else "TRAIL"); break
            else:
                peak = min(peak, l[j]); stp = min(stop, peak + TRAIL_ATR * a[i])
                if h[j] >= stp:
                    exit_px, exit_r = stp, ("STOP" if stp == stop else "TRAIL"); break
            j += 1
        if exit_px is None:
            j = n - 1; exit_px, exit_r = c[j], "END"
        exit_px *= (1 - SLIP) if direction == "LONG" else (1 + SLIP)
        gross = qty * (exit_px - entry) if direction == "LONG" else qty * (entry - exit_px)
        fee = qty * entry * TAKER + qty * exit_px * TAKER
        capital = max(capital + gross - fee, 0.0)
        trades.append({"dir": direction, "time": t[i], "exit_time": t[j], "entry": entry,
                       "stop": stop, "target": None, "qty": qty, "notional": notional,
                       "pnl": gross - fee, "exit_r": exit_r})
        i = j + 1
        if capital <= 0:
            break
    return trades


def buyhold(d):
    c = d["close"]; ret = (c.iloc[-1] / c.iloc[0] - 1) * 100
    eq = c / c.iloc[0]; mdd = ((eq - eq.cummax()) / eq.cummax()).min() * 100
    dr = c.pct_change().dropna(); sharpe = dr.mean() / dr.std() * np.sqrt(365)
    return ret, mdd, sharpe


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--short", action="store_true")
    args = ap.parse_args()
    d = daily()
    print(f"CLEAN TREND SYSTEM -- daily BTC {d.index[0].date()}..{d.index[-1].date()}, "
          f"Donchian({ENTRY_N}) + SMA200, ATR trail, {'long+short' if args.short else 'long-only'}\n")

    yr_bounds = [("2023", "2023-01-01", "2023-12-31"), ("2024", "2024-01-01", "2024-12-31"),
                 ("2025", "2025-01-01", "2025-12-31"), ("2026", "2026-01-01", None)]
    allt = run(d, allow_short=args.short)
    for label, s, e in yr_bounds:
        seg = [x for x in allt if (str(x["time"].date()) >= s and (e is None or str(x["time"].date()) <= e))]
        st = summarize_trades(seg, CAP, label=label)
        ds = d.loc[s:e]; bh = buyhold(ds) if len(ds) > 1 else (0, 0, 0)
        print(f"  {label}: trades={st.n:<3} win={st.win_rate:4.0f}%  sysRet={st.ret_pct:+7.1f}%  "
              f"expR={st.expectancy_r:+.2f}   | buy&hold {bh[0]:+7.1f}% (maxDD {bh[1]:.0f}%)")
    ps = summarize_trades(allt, CAP)
    bh = buyhold(d)
    print(f"\n  SYSTEM  pooled: trades={ps.n} win={ps.win_rate:.0f}% ret={ps.ret_pct:+.0f}% "
          f"expR={ps.expectancy_r:+.2f} Sharpe={ps.sharpe_annual or 0:.2f} maxDD={ps.max_dd_pct:.0f}% edge={ps.edge_confidence:.0f}%")
    print(f"  BUY&HOLD      : ret={bh[0]:+.0f}%  Sharpe={bh[2]:.2f}  maxDD={bh[1]:.0f}%")
