"""
Trend-following + Order-Block entry -- the honest synthesis.

The edge we proved: go WITH the trend, small stop, let winners run (asymmetric).
The user's addition: time the entry with liquidity / order blocks.

  Direction: only trade WITH the higher-timeframe trend (price vs SMA200 on 1H).
  Entry:     buy a pullback into a fresh BULLISH order block (uptrend), or sell a
             pullback into a BEARISH order block (downtrend). OB from the verified
             SMC labeler (causal: only OBs created before this bar).
  Stop:      the far side of the order block (its low for longs), min-floored.
  Exit:      CHANDELIER TRAIL -- ride the trend, let winners run (the real edge).

Measured against a TREND-ONLY baseline (same trend + trail, entry = any pullback
to SMA50) so we can SEE whether the order block actually adds value.

1H BTC, causal, honest fees. Run:  python3 trend_ob_system.py
"""
import _paths  # noqa: F401
import argparse
import numpy as np
import pandas as pd

from data_loader import load_ohlcv
from smc_engine import SMCParams, position_size
from smc_luxalgo import label_smc_luxalgo
from trade_stats import summarize_trades

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
ATR_N = 14
TRAIL_ATR = 3.0          # chandelier: exit if price retraces 3 ATR from the peak
STOP_ATR = 1.5           # initial stop
BULLISH, BEARISH = 1, -1


def atr(df, n=ATR_N):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def build_obs(df):
    """Return list of (created_idx, top, bottom, bias) for causal OB entries."""
    _, res = label_smc_luxalgo(df)
    obs = []
    for o in res.order_blocks:
        ci = o.get("created_index", -1)
        if ci is None or ci < 0:
            continue
        obs.append((ci, o["top"], o["bottom"], 1 if o["bias"] == "bullish" else -1))
    return sorted(obs)


def run(fname, mode="trend_ob", start=None, end=None):
    """mode: 'trend_ob' (order-block entry) or 'trend_only' (SMA50 pullback)."""
    df = load_ohlcv(fname, start, end)
    c = df["close"].values; h = df["high"].values; l = df["low"].values
    t = df.index
    n = len(c)
    sma200 = df["close"].rolling(200).mean().values
    sma50 = df["close"].rolling(50).mean().values
    a = atr(df).values
    params = SMCParams(risk_per_trade_pct=0.01, leverage=10)

    # per-bar list of OBs that are known and not yet used
    ob_by_bar = {}
    if mode == "trend_ob":
        for ci, top, bot, bias in build_obs(df):
            ob_by_bar.setdefault(ci + 1, []).append((top, bot, bias))
    active_obs = []   # (top, bottom, bias) known so far

    capital = CAP
    trades = []
    i = 205
    while i < n - 1:
        if mode == "trend_ob" and i in ob_by_bar:
            active_obs.extend(ob_by_bar[i])
        if np.isnan(sma200[i]) or np.isnan(a[i]) or a[i] <= 0:
            i += 1; continue

        up = c[i] > sma200[i]
        down = c[i] < sma200[i]
        direction = entry = None

        if mode == "trend_ob":
            # pullback into a fresh OB aligned with the trend
            for (top, bot, bias) in active_obs:
                if up and bias == BULLISH and l[i] <= top and c[i] >= bot:
                    direction, entry = "LONG", min(c[i], top); break
                if down and bias == BEARISH and h[i] >= bot and c[i] <= top:
                    direction, entry = "SHORT", max(c[i], bot); break
        else:  # trend_only: pullback to SMA50 in the trend
            if up and l[i] <= sma50[i] and c[i] > sma200[i]:
                direction, entry = "LONG", c[i]
            elif down and h[i] >= sma50[i] and c[i] < sma200[i]:
                direction, entry = "SHORT", c[i]

        if direction is None:
            i += 1; continue

        stop = entry - STOP_ATR * a[i] if direction == "LONG" else entry + STOP_ATR * a[i]
        qty, notional = position_size(capital, entry, stop, params)
        if qty <= 0:
            i += 1; continue

        # manage with a chandelier trail; ride until stop/trail
        peak = entry
        exit_px = exit_r = None; j = i + 1
        while j < n:
            if direction == "LONG":
                peak = max(peak, h[j])
                trail = peak - TRAIL_ATR * a[i]
                stp = max(stop, trail)
                if l[j] <= stp:
                    exit_px, exit_r = stp, ("STOP" if stp == stop else "TRAIL"); break
            else:
                peak = min(peak, l[j])
                trail = peak + TRAIL_ATR * a[i]
                stp = min(stop, trail)
                if h[j] >= stp:
                    exit_px, exit_r = stp, ("STOP" if stp == stop else "TRAIL"); break
            j += 1
        if exit_px is None:
            j = n - 1; exit_px, exit_r = c[j], "END"
        exit_px *= (1 - SLIP) if direction == "LONG" else (1 + SLIP)

        gross = qty * (exit_px - entry) if direction == "LONG" else qty * (entry - exit_px)
        fee = qty * entry * TAKER + qty * exit_px * TAKER
        capital = max(capital + gross - fee, 0.0)
        trades.append({"dir": direction, "time": t[i], "entry": entry, "stop": stop,
                       "target": None, "qty": qty, "notional": notional,
                       "pnl": gross - fee, "exit_r": exit_r})
        # remove used OBs near the fill; cooldown to avoid stacking
        active_obs = [o for o in active_obs
                      if not (o[1] <= entry <= o[0])]
        i = j + 1
        if capital <= 0:
            break
    return trades


YEARS = [("2023", "BTCUSDT_1h_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
         ("2024", "BTCUSDT_1h_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
         ("2025", "BTCUSDT_1h_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
         ("2026", "BTCUSDT_1h_Jan_to_Jul2026.csv", None, None)]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="both", choices=["trend_ob", "trend_only", "both"])
    args = ap.parse_args()
    modes = ["trend_only", "trend_ob"] if args.mode == "both" else [args.mode]
    print("TREND-FOLLOWING + ORDER-BLOCK -- 1H BTC, chandelier trail, honest fees\n")
    for mode in modes:
        print(f"===== {mode} =====")
        pooled = []
        for label, f, s, e in YEARS:
            tr = run(f, mode=mode, start=s, end=e)
            pooled += tr
            st = summarize_trades(tr, CAP, label=label)
            print(f"  {label}: n={st.n:<4} win={st.win_rate:4.1f}%  ret={st.ret_pct:+7.1f}%  "
                  f"expR={st.expectancy_r:+.3f}  edge={st.edge_confidence:.0f}%")
        ps = summarize_trades(pooled, CAP)
        print(f"  POOLED: n={ps.n:<4} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  "
              f"expR={ps.expectancy_r:+.3f}  Sharpe={ps.sharpe_annual or 0:.2f}  edge={ps.edge_confidence:.0f}%\n")
