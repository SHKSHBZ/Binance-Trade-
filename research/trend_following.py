"""
Trend-following on BTC -- the one edge with real, decades-long evidence
(time-series momentum: Moskowitz/Ooi/Pedersen 2012, and every CTA/managed-
futures fund). We never actually tested this; we only tested intraday
mean-reversion patterns. This is different: hold for weeks, ride trends, step
aside in downtrends.

Rules tested (all causal -- position decided at yesterday's close):
  * Buy & hold                        (the benchmark to beat)
  * MA filter: long when close > MA(N), else FLAT (in cash)
  * MA long/short: long above MA(N), short below
  * Momentum: long if past-N-day return > 0, else flat

Metrics: total return, annualized Sharpe, max drawdown, % time in market.
The honest question is not "biggest return" but "better RISK-ADJUSTED return
than just holding" -- i.e. similar/better gains with smaller drawdowns.

Run:  python3 trend_following.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd

from data_loader import load_ohlcv

FEE = 0.0004   # per switch, one side


def daily_close():
    a = load_ohlcv("BTCUSDT_1h_2023_to_2025.csv")["close"].resample("1D").last()
    b = load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")["close"].resample("1D").last()
    s = pd.concat([a, b])
    s = s[~s.index.duplicated(keep="first")].sort_index().dropna()
    return s


def metrics(name, strat_ret, pos):
    eq = (1 + strat_ret).cumprod()
    total = (eq.iloc[-1] - 1) * 100
    yrs = len(strat_ret) / 365.25
    cagr = (eq.iloc[-1] ** (1 / yrs) - 1) * 100 if yrs > 0 else 0
    sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(365) if strat_ret.std() > 0 else 0
    peak = eq.cummax()
    mdd = ((eq - peak) / peak).min() * 100
    exposure = (pos != 0).mean() * 100
    switches = int((pos.diff().fillna(0) != 0).sum())
    print(f"  {name:<22} return {total:+8.0f}%  CAGR {cagr:+6.1f}%  "
          f"Sharpe {sharpe:5.2f}  maxDD {mdd:6.1f}%  inMkt {exposure:3.0f}%  "
          f"switches {switches}")
    return sharpe, total, mdd


def run():
    px = daily_close()
    ret = px.pct_change().fillna(0)
    print(f"BTC daily, {px.index[0].date()} -> {px.index[-1].date()}  "
          f"({len(px)} days)\n")

    # benchmark
    print("BENCHMARK:")
    metrics("Buy & hold", ret, pd.Series(1.0, index=px.index))

    print("\nMA FILTER (long when above MA, else cash):")
    for N in (50, 100, 200):
        ma = px.rolling(N).mean()
        pos = (px > ma).shift(1).fillna(0).astype(float)   # causal
        sr = ret * pos
        # subtract fees on switches
        sw = pos.diff().abs().fillna(0)
        sr = sr - sw * FEE
        metrics(f"MA({N}) long/flat", sr, pos)

    print("\nMA LONG/SHORT (long above, short below):")
    for N in (50, 100, 200):
        ma = px.rolling(N).mean()
        pos = np.where(px > ma, 1.0, -1.0)
        pos = pd.Series(pos, index=px.index).shift(1).fillna(0)
        sr = ret * pos
        sw = pos.diff().abs().fillna(0)
        sr = sr - sw * FEE
        metrics(f"MA({N}) long/short", sr, pos)

    print("\nMOMENTUM (long if past-N-day return > 0, else cash):")
    for N in (30, 60, 90):
        mom = px / px.shift(N) - 1
        pos = (mom > 0).shift(1).fillna(0).astype(float)
        sr = ret * pos
        sw = pos.diff().abs().fillna(0)
        sr = sr - sw * FEE
        metrics(f"Mom({N}) long/flat", sr, pos)

    print("\nRead: look for HIGHER Sharpe and SMALLER maxDD than buy & hold --")
    print("that is trend-following's real, documented benefit (not bigger raw return).")


if __name__ == "__main__":
    print("TREND-FOLLOWING TEST -- the one edge with real evidence\n")
    run()
