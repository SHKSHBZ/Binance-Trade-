"""
Institutional / academic strategy #1: Time-series momentum with volatility targeting
(Moskowitz, Ooi & Pedersen 2012; the core of CTA trend funds: AQR, Man AHL, Winton).
 signal_L = sign(close_t / close_{t-L} - 1)  for L in {21, 63, 126, 252} trading days
 combo   = average of the four signs (how CTAs blend lookbacks)
 position for day t+1 = signal * 15% annual vol target / realised vol (60d), capped at 3x
 cost charged on every change in position. Benchmark: vol-targeted LONG-ONLY (pure drift).
Daily closes built from 1h data at 21:00 UTC (the gold daily break).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def daily(df):
    return df.close.resample("1D").last().dropna()

def backtest(c, L, cost_frac, target=0.15, cap=3.0, long_only=False, ann=252):
    r=c.pct_change()
    vol=r.rolling(60).std()*np.sqrt(ann)
    if long_only: sig=pd.Series(1.0,index=c.index)
    elif L=="combo": sig=sum(np.sign(c/c.shift(l)-1) for l in (21,63,126,252))/4
    else: sig=np.sign(c/c.shift(L)-1)
    pos=(sig*target/vol).clip(-cap,cap).shift(1)          # decided at close t, held on t+1
    pnl=(pos*r - pos.diff().abs()*cost_frac).dropna()
    return pnl, pos

def stats(p, ann):
    if len(p)<20: return "n/a"
    eq=(1+p).cumprod(); dd=(eq/eq.cummax()-1).min()
    return f"ann.ret {100*p.mean()*ann:+6.1f}%  sharpe {p.mean()/p.std()*np.sqrt(ann):+5.2f}  maxDD {100*dd:5.0f}%"

if __name__=="__main__":
    g=daily(load_ohlcv("XAUUSD_1h.csv")); g=g[g.index.dayofweek<5]
    cat=lambda a,b:(lambda x:x[~x.index.duplicated()].sort_index())(pd.concat([load_ohlcv(a),load_ohlcv(b)]))
    b=daily(cat("BTCUSDT_1h_2023_to_2025.csv","BTCUSDT_1h_Jan_to_Jul2026.csv"))
    for name,c,cf,ann in (("GOLD",g,0.25/2500,252),("BTC",b,0.0006,365)):
        print(f"\n===== {name} ({c.index[0].date()} -> {c.index[-1].date()}) =====")
        for L in (21,63,126,252,"combo","LONG-ONLY"):
            p,pos=backtest(c,L if L!="LONG-ONLY" else 21,cf,long_only=(L=="LONG-ONLY"),ann=ann)
            ins=p[:"2024-12-31"]; oos=p["2025-01-01":]
            short_share=(pos<0).mean()
            yr=" ".join(f"{y}:{100*v:+.0f}%" for y,v in p.groupby(p.index.year).apply(lambda x:(1+x).prod()-1).items())
            print(f"{str(L):>9} | to 2024: {stats(ins,ann)} | 2025-26: {stats(oos,ann)} | short {100*short_share:.0f}% of days | {yr}")
