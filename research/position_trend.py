import sys; sys.path.insert(0,'/home/user/Binance-Trade-/research')
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def daily(f,start=None,end=None):
    d=load_ohlcv(f,start,end)
    return d.resample("1D").agg(open=("open","first"),high=("high","max"),
                                low=("low","min"),close=("close","last")).dropna()

def atr(h,l,c,n=20):
    pc=np.concatenate([[c[0]],c[:-1]])
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    return pd.Series(tr).rolling(n).mean().bfill().values

def run(d,N=40,trailA=4.0,allow=("L","S"),cost_frac=0.0001,risk=0.01,
        cap0=1000.0,rand=None):
    """Donchian N-day breakout, chandelier ATR trailing exit. Causal: the
    channel uses bars up to i-1; entry is at the close of the breakout bar."""
    o,h,l,c=d["open"].values,d["high"].values,d["low"].values,d["close"].values
    n=len(c);A=atr(h,l,c,20)
    hh=pd.Series(h).rolling(N).max().shift(1).values
    ll=pd.Series(l).rolling(N).min().shift(1).values
    rng=np.random.default_rng(rand) if rand is not None else None
    cap=cap0;pos=0;entry=stop=qty=0.0;best=0.0
    eq=[];trades=[];bars_in=0
    for i in range(n):
        if pos!=0:
            bars_in+=1
            if pos>0:
                best=max(best,h[i]); ts=best-trailA*A[i]
                if ts>stop: stop=ts
                if l[i]<=stop:
                    px=stop*(1-cost_frac)
                    cap+=qty*(px-entry); trades.append((px-entry)/ (entry-stop0) if False else (px-entry))
                    pos=0
            else:
                best=min(best,l[i]); ts=best+trailA*A[i]
                if ts<stop: stop=ts
                if h[i]>=stop:
                    px=stop*(1+cost_frac)
                    cap+=qty*(entry-px); trades.append((entry-px))
                    pos=0
        if pos==0 and not np.isnan(hh[i]) and A[i]>0:
            sig=0
            if c[i]>hh[i]: sig=1
            elif c[i]<ll[i]: sig=-1
            if rng is not None and sig!=0: sig=1 if rng.random()<0.5 else -1
            if sig==1 and "L" in allow:
                entry=c[i]*(1+cost_frac); stop=entry-trailA*A[i]; stop0=stop
                qty=(cap*risk)/(entry-stop); pos=1; best=entry
            elif sig==-1 and "S" in allow:
                entry=c[i]*(1-cost_frac); stop=entry+trailA*A[i]; stop0=stop
                qty=(cap*risk)/(stop-entry); pos=-1; best=entry
        # mark to market
        m=cap+(qty*(c[i]-entry) if pos>0 else (qty*(entry-c[i]) if pos<0 else 0))
        eq.append(m)
    eq=np.array(eq); peak=np.maximum.accumulate(eq)
    dd=100*((peak-eq)/peak).max()
    yrs=(d.index[-1]-d.index[0]).days/365.25
    ret=100*(eq[-1]/cap0-1)
    cagr=100*((eq[-1]/cap0)**(1/yrs)-1) if eq[-1]>0 else -100
    bh=100*(c[-1]/c[0]-1)
    bhe=cap0*c/c[0]; bhpk=np.maximum.accumulate(bhe); bhdd=100*((bhpk-bhe)/bhpk).max()
    return dict(n=len(trades),ret=ret,cagr=cagr,dd=dd,bh=bh,bhdd=bhdd,
                expo=100*bars_in/n,eq=eq)

G=daily("XAUUSD_4h.csv")
print(f"GOLD daily {G.index[0].date()} -> {G.index[-1].date()}  ({len(G)} days)")
print(f"buy&hold: {100*(G['close'].values[-1]/G['close'].values[0]-1):+.0f}%\n")
print(f"{'N':>4}{'trail':>7}{'side':>6}{'n':>5}{'return%':>10}{'CAGR%':>8}{'maxDD%':>8}{'B&H ret':>9}{'B&H DD':>8}{'expo%':>7}")
for N in (20,40,60,100):
    for tA in (3.0,5.0,8.0):
        for allow,lab in ((("L","S"),"L+S"),(("L",),"L"),(("S",),"S")):
            r=run(G,N,tA,allow)
            print(f"{N:>4}{tA:>7.1f}{lab:>6}{r['n']:>5}{r['ret']:>+10.1f}{r['cagr']:>+8.1f}{r['dd']:>8.1f}{r['bh']:>+9.0f}{r['bhdd']:>8.1f}{r['expo']:>7.1f}")
