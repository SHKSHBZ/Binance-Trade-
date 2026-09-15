"""
Option-SELLING backtest -- sell puts (then calls) at swing lows, harvest premium.

!!! WARNING -- NOT A VALID EDGE TEST. SCAFFOLDING ONLY. !!!
The option premium here is MODELLED with Black-Scholes from a GUESSED implied
volatility, not the real price an exchange quoted. Since the entire edge in
selling options IS the premium (implied vs realized vol), modelling the premium
means partly deciding the answer -- the results shift with the assumed IV markup.
A faithful test needs REAL historical BTC option data (actual strikes, expiries,
bid/ask/IV from Deribit or a vendor), or a forward test on Deribit/Binance
options testnet with live quotes. Deribit is blocked from this sandbox, so this
file exists only to plug real premium data into later. Do not trust its numbers.


We don't have historical option prices, so we PRICE the options ourselves with
Black-Scholes using BTC's own realized volatility, and test a range of implied-
vol markups. This matters: the whole edge in selling options is the VOLATILITY
RISK PREMIUM -- how much implied vol (what you collect) exceeds realized vol
(what actually happens). If implied == realized (markup x1.0), selling is
break-even before costs by construction. Any profit must come from the markup.

Strategy (puts):
  * entry  : a swing low (confirmed pivot, causal)
  * sell   : an at-the-money put, expiry T days
  * premium: BlackScholes(put, S, K=S, T, sigma = realized_vol * iv_mult)
  * manage : walk hourly to expiry; STOP (buy back at mark) if price falls
             stop_pct below entry; else hold to expiry and pay max(K-S,0)
  * pnl    : premium_collected - buyback/payoff   (in % of underlying)

Run:  python3 option_selling_backtest.py
"""
import _paths  # noqa: F401
import math
import numpy as np
import pandas as pd

from data_loader import load_ohlcv

PIVOT_HALF = 12
RF = 0.0           # risk-free ~0
FEE_PCT = 0.0003   # taker fee proxy on notional per side


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(S, K, T_years, sigma, kind):
    if T_years <= 0 or sigma <= 0:
        intrinsic = max(0.0, (K - S) if kind == "put" else (S - K))
        return intrinsic
    d1 = (math.log(S / K) + (RF + 0.5 * sigma ** 2) * T_years) / (sigma * math.sqrt(T_years))
    d2 = d1 - sigma * math.sqrt(T_years)
    if kind == "put":
        return K * math.exp(-RF * T_years) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return S * norm_cdf(d1) - K * math.exp(-RF * T_years) * norm_cdf(d2)


def confirmed_low_pivots(h, l, half):
    n = len(h)
    piv = []
    for i in range(half, n - half):
        wl = l[i - half:i + half + 1]
        if l[i] == wl.min() and wl.argmin() == half:
            piv.append(i + half)   # confirmed 'half' bars later (causal)
    return piv


def realized_vol(returns_hourly):
    # annualized from hourly log returns (24*365 hours)
    if len(returns_hourly) < 24:
        return 0.6
    return float(np.std(returns_hourly) * math.sqrt(24 * 365))


def run(fname, kind="put", expiry_days=7, iv_mult=1.1, stop_pct=0.05,
        start=None, end=None):
    df = load_ohlcv(fname, start, end)
    o, h, l, c = (df[x].values for x in ["open", "high", "low", "close"])
    n = len(c)
    logret = np.diff(np.log(c), prepend=np.log(c[0]))
    T = expiry_days / 365.0
    hold_bars = expiry_days * 24

    pivots = confirmed_low_pivots(h, l, PIVOT_HALF)
    trades = []
    busy_until = -1
    for entry_i in pivots:
        if entry_i <= busy_until or entry_i + hold_bars >= n:
            continue
        S0 = c[entry_i]
        K = S0                                   # at-the-money
        sigma = realized_vol(logret[max(0, entry_i - 24 * 30):entry_i]) * iv_mult
        premium = bs_price(S0, K, T, sigma, kind)   # collected, in $ of 1 unit
        stop_level = S0 * (1 - stop_pct) if kind == "put" else S0 * (1 + stop_pct)

        exit_reason = "EXPIRY"
        pnl = None
        for j in range(entry_i + 1, entry_i + hold_bars + 1):
            hit = (l[j] <= stop_level) if kind == "put" else (h[j] >= stop_level)
            if hit:
                # buy back at mark (BS with remaining time), approximate at stop level
                rem = (entry_i + hold_bars - j) / 24 / 365.0
                sig_now = realized_vol(logret[max(0, j - 24 * 30):j]) * iv_mult
                buyback = bs_price(stop_level, K, rem, sig_now, kind)
                pnl = premium - buyback
                exit_reason = "STOP"
                busy_until = j
                break
        if pnl is None:
            S_exp = c[entry_i + hold_bars]
            payoff = max(0.0, (K - S_exp) if kind == "put" else (S_exp - K))
            pnl = premium - payoff
            busy_until = entry_i + hold_bars
        pnl -= FEE_PCT * S0 * 2
        trades.append({"pnl_usd": pnl, "premium": premium, "S0": S0,
                       "pnl_pct": pnl / S0 * 100, "prem_pct": premium / S0 * 100,
                       "reason": exit_reason})
    return trades


def report(label, trades):
    if not trades:
        print(f"  {label:<34} no trades"); return
    p = np.array([t["pnl_pct"] for t in trades])
    prem = np.mean([t["prem_pct"] for t in trades])
    wins = (p > 0).mean() * 100
    stops = np.mean([t["reason"] == "STOP" for t in trades]) * 100
    print(f"  {label:<34} n={len(trades):>3}  win={wins:4.0f}%  "
          f"avg prem={prem:4.2f}%  net/trade={p.mean():+5.2f}%  "
          f"total={p.sum():+6.1f}%  stopped={stops:3.0f}%")


if __name__ == "__main__":
    print("OPTION-SELLING BACKTEST -- Black-Scholes priced, BTC 1H\n")
    print("Key: at IV markup x1.0 (implied=realized) selling is ~break-even by")
    print("construction. Profit only appears if a real premium (x1.1, x1.25) exists")
    print("AND the timing/stops don't give it back.\n")

    files = [("2023-25", "BTCUSDT_1h_2023_to_2025.csv"),
             ("2026", "BTCUSDT_1h_Jan_to_Jul2026.csv")]
    for kind in ("put", "call"):
        print(f"===== SELLING {kind.upper()}S at swing {'lows' if kind=='put' else 'lows'}, "
              f"weekly, ATM, 5% stop =====")
        for iv in (1.0, 1.1, 1.25):
            print(f"  --- IV markup x{iv} ---")
            for lbl, f in files:
                report(f"{lbl}", run(f, kind=kind, iv_mult=iv))
        print()
