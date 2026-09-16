"""
Entry-signal scan: which entry actually has a DIRECTIONAL edge on BTC?

For each candidate entry signal, at every bar it fires we run the same
target-independent test: with a symmetric 1-ATR stop and 1-ATR target, does price
reach +1 ATR in our favor BEFORE -1 ATR against, within a forward horizon?

  fav-first > 50%  -> real directional edge (the higher the better)
  fav-first ~ 50%  -> coin flip (no edge)

This separates ENTRY quality from any take-profit choice. 1H BTC, causal
(signals use only closed bars; ATR is trailing).

Run:  python3 entry_scan.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv

HORIZON = 48      # bars to resolve the 1:1 race (48h on 1H)


def load_all():
    a = load_ohlcv("BTCUSDT_1h_2023_to_2025.csv")
    b = load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")
    df = pd.concat([a, b])
    return df[~df.index.duplicated(keep="first")].sort_index()


def indicators(df):
    c = df["close"]; h = df["high"]; l = df["low"]
    out = {}
    out["sma50"] = c.rolling(50).mean()
    out["sma200"] = c.rolling(200).mean()
    d = c.diff()
    up = d.clip(lower=0).rolling(14).mean(); dn = (-d.clip(upper=0)).rolling(14).mean()
    out["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14).mean()
    out["hh"] = h.rolling(48).max().shift(1)     # prior 48-bar high
    out["ll"] = l.rolling(48).min().shift(1)
    out["ret24"] = c / c.shift(24) - 1
    return out


def fav_first_rate(df, sig_long, sig_short, atr):
    """For every fired bar, does +1ATR favor hit before -1ATR against within HORIZON?"""
    h = df["high"].values; l = df["low"].values; c = df["close"].values
    a = atr.values
    n = len(c)
    wins = 0; total = 0
    idx = np.where(sig_long | sig_short)[0]
    for i in idx:
        if i + 1 >= n or np.isnan(a[i]) or a[i] <= 0:
            continue
        long = sig_long[i]
        tgt = c[i] + a[i] if long else c[i] - a[i]
        stp = c[i] - a[i] if long else c[i] + a[i]
        end = min(i + 1 + HORIZON, n)
        res = None
        for j in range(i + 1, end):
            if long:
                if l[j] <= stp: res = 0; break
                if h[j] >= tgt: res = 1; break
            else:
                if h[j] >= stp: res = 0; break
                if l[j] <= tgt: res = 1; break
        if res is None:
            res = 1 if ((c[end-1]-c[i] > 0) == long) else 0
        wins += res; total += 1
    return (wins / total * 100 if total else 0), total


if __name__ == "__main__":
    df = load_all()
    I = indicators(df)
    atr = I["atr"]
    c = df["close"]; F = pd.Series(False, index=df.index).values

    def arr(cond): return cond.reindex(df.index).fillna(False).values

    print("ENTRY-SIGNAL SCAN -- 1H BTC, 1:1 ATR race, higher fav-first = real edge\n")
    print(f"{'signal':<34}{'fav-first':>10}{'fires':>8}")
    print("-" * 52)

    tests = [
        ("MEAN-REVERSION at prior-day level (baseline)", None, None),  # placeholder
        ("Momentum: up>24h -> long / else short",
         arr(I["ret24"] > 0), arr(I["ret24"] < 0)),
        ("Trend regime: above/below SMA200",
         arr(c > I["sma200"]), arr(c < I["sma200"]),),
        ("Trend regime: above/below SMA50",
         arr(c > I["sma50"]), arr(c < I["sma50"])),
        ("Breakout: new 48h high->long / low->short",
         arr(c > I["hh"]), arr(c < I["ll"])),
        ("RSI mean-revert: <30 long / >70 short",
         arr(I["rsi"] < 30), arr(I["rsi"] > 70)),
        ("RSI momentum: >55 long / <45 short",
         arr(I["rsi"] > 55), arr(I["rsi"] < 45)),
        ("Momentum WITH trend (ret24>0 AND >SMA200)",
         arr((I["ret24"] > 0) & (c > I["sma200"])),
         arr((I["ret24"] < 0) & (c < I["sma200"]))),
        ("Breakout WITH trend (48h high AND >SMA200)",
         arr((c > I["hh"]) & (c > I["sma200"])),
         arr((c < I["ll"]) & (c < I["sma200"]))),
    ]
    for name, sl, ss in tests:
        if sl is None:
            continue
        rate, n = fav_first_rate(df, sl, ss, atr)
        flag = "  <-- edge" if rate >= 54 else ("  (coin flip)" if 47 <= rate <= 53 else "")
        print(f"{name:<34}{rate:>9.1f}%{n:>8}{flag}")
    print("\n(>54% = worth building on; ~50% = no edge; <46% = fade it instead)")
