"""
Equal-highs / equal-lows liquidity sweep -> FVG re-entry -> internal range target.
Implements the trader's formal specification:

  pivot high (k):     H_i = max H[i-k .. i+k]      (usable only at i+k)
  equal highs:        consecutive pivot highs i1<i2, Tmin <= i2-i1 <= Tmax,
                      |H1-H2| / min(H1,H2) <= eps     -> EQH = max(H1,H2)
  range low:          L_range = min L[i1 .. i2]
  acceptance cancel:  close > EQH*(1+delta)
  trigger (short):    high > EQH and close <= EQH
  entry A:            close of the trigger bar
  entry B:            first bearish FVG after the sweep (L[t-2] > H[t]),
                      limit short at its midpoint (CE)
  stop:               max high since the sweep + 1 ATR(14)
  target:             L_range ;  trade only if R >= 2
Mirror image for equal lows / longs.
Causal: levels active only after the second pivot is confirmed; the stop for a
limit fill uses highs up to the bar BEFORE the fill, and the fill bar itself is
checked for the stop (the bug that once faked +1.9R in this project).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

K=5; TMIN=5; TMAX=100; DELTA=0.001; RMIN=2.0; EXPIRE=200; W_FVG=12; W_FILL=24; MAXHOLD=300

def atr(h,l,c,n=14):
    pc=np.concatenate([[c[0]],c[:-1]])
    return pd.Series(np.maximum(h-l,np.maximum(abs(h-pc),abs(l-pc)))).rolling(n).mean().bfill().values

def pivots(x, k, hi=True):
    n=len(x); out=[]
    for i in range(k,n-k):
        w=x[i-k:i+k+1]
        if (x[i]==w.max()) if hi else (x[i]==w.min()): out.append(i)
    return out

def setups(h,l,eps):
    out=[]
    ph=pivots(h,K,True); pl=pivots(l,K,False)
    for a,b in zip(ph[:-1],ph[1:]):
        if TMIN<=b-a<=TMAX and abs(h[a]-h[b])/min(h[a],h[b])<=eps:
            out.append(dict(side=-1,level=max(h[a],h[b]),target=l[a:b+1].min(),active=b+K))
    for a,b in zip(pl[:-1],pl[1:]):
        if TMIN<=b-a<=TMAX and abs(l[a]-l[b])/min(l[a],l[b])<=eps:
            out.append(dict(side=1,level=min(l[a],l[b]),target=h[a:b+1].max(),active=b+K))
    return out

def run(df, eps=0.001, entry="A", cost=0.25, cost_frac=None, rand=None, atr_mult=1.0, fvg_at="ce"):
    h,l,c=df.high.values,df.low.values,df.close.values; n=len(c); A=atr(h,l,c)
    rng=np.random.default_rng(rand) if rand is not None else None
    cands=[]
    for s in setups(h,l,eps):
        sd=s["side"]; lv=s["level"]; t_sweep=None; trig=None
        for t in range(s["active"]+1, min(s["active"]+1+EXPIRE, n)):
            if sd==-1:
                if c[t]>lv*(1+DELTA): break                       # accepted -> cancel
                if h[t]>lv and t_sweep is None: t_sweep=t
                if h[t]>lv and c[t]<=lv: trig=t; break
            else:
                if c[t]<lv*(1-DELTA): break
                if l[t]<lv and t_sweep is None: t_sweep=t
                if l[t]<lv and c[t]>=lv: trig=t; break
        if trig is not None: cands.append((trig,t_sweep,s))
    cands.sort(key=lambda x:x[0])
    trades=[]; busy=-1
    for trig,t_sweep,s in cands:
        if trig<=busy: continue
        sd=s["side"]; d=-sd if False else (-1 if sd==-1 else 1)   # short after EQH sweep, long after EQL
        d = -1 if sd==-1 else 1
        tgt=s["target"]
        if entry=="A":
            fill=trig; e=c[trig]
            ext=h[t_sweep:trig+1].max() if d<0 else l[t_sweep:trig+1].min()
            stop=ext+atr_mult*A[trig] if d<0 else ext-atr_mult*A[trig]
            check_fill_bar=False
        else:
            fvg=None
            for t in range(max(trig,t_sweep+2), min(trig+W_FVG,n)):
                if d<0 and l[t-2]>h[t]: fvg=(t,(l[t-2]+h[t])/2 if fvg_at=="ce" else h[t]); break
                if d>0 and h[t-2]<l[t]: fvg=(t,(h[t-2]+l[t])/2 if fvg_at=="ce" else l[t]); break
            if fvg is None: continue
            tf,ce=fvg; fill=None
            for j in range(tf+1, min(tf+1+W_FILL,n)):
                ext=h[t_sweep:j].max() if d<0 else l[t_sweep:j].min()
                stp=ext+atr_mult*A[j-1] if d<0 else ext-atr_mult*A[j-1]
                if (d<0 and l[j]<=tgt) or (d>0 and h[j]>=tgt): break        # ran to target without us
                if (d<0 and h[j]>=ce) or (d>0 and l[j]<=ce): fill=j; e=ce; stop=stp; break
            if fill is None: continue
            check_fill_bar=True
        risk=abs(e-stop)
        if risk<=0 or (d<0 and not (tgt<e<stop)) or (d>0 and not (stop<e<tgt)): continue
        rr=abs(tgt-e)/risk
        if rr<RMIN: continue
        if rng is not None:                                           # NULL: random side, same distances
            d=1 if rng.random()<0.5 else -1
            stop=e-d*risk; tgt=e+d*rr*risk
        sp=cost if cost_frac is None else e*cost_frac
        R=None; start=fill if check_fill_bar else fill+1
        for j in range(start, min(fill+1+MAXHOLD,n)):
            if (d<0 and h[j]>=stop) or (d>0 and l[j]<=stop): R=-1.0; break
            if j==fill: continue                                      # no target credit on the fill bar
            if (d<0 and l[j]<=tgt) or (d>0 and h[j]>=tgt): R=rr; break
        if R is None:
            j=min(fill+MAXHOLD,n-1); R=max(-1.0,min(rr,((c[j]-e) if d>0 else (e-c[j]))/risk))
        trades.append(dict(time=df.index[fill],dir=d,entry=e,stop=stop,target=tgt,rr=rr,risk=risk,R=R-sp/risk))
        busy=j
    return pd.DataFrame(trades)

def boot(R,n=4000,seed=0):
    R=np.asarray(R,float)
    if not len(R): return 1.0
    ix=np.random.default_rng(seed).integers(0,len(R),(n,len(R))); return float((R[ix].mean(1)<=0).mean())

if __name__=="__main__":
    b15=pd.concat([load_ohlcv("BTCUSDT_15m_2023_to_2025.csv"),load_ohlcv("BTCUSDT_15m_Jan_to_Jul2026.csv")])
    b15=b15[~b15.index.duplicated()].sort_index()
    b1=pd.concat([load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"),load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")])
    b1=b1[~b1.index.duplicated()].sort_index()
    data=[("GOLD 15m",load_ohlcv("XAUUSD_15m.csv","2022-06-24","2026-09-16"),dict(cost=0.25)),
          ("GOLD 1h", load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16"),dict(cost=0.25)),
          ("BTC 15m", b15, dict(cost_frac=0.0006)),
          ("BTC 1h",  b1,  dict(cost_frac=0.0006))]
    print(f"{'market':<9}{'entry':<7}{'eps':>6}{'n':>6}{'/yr':>5}{'win%':>7}{'medRR':>7}{'expR':>8}{'P':>7}{'LONG':>8}{'SHORT':>8}{'train':>8}{'test':>8}")
    for name,df,kw in data:
        yrs=(df.index[-1]-df.index[0]).days/365.25
        for ent in ("A","B"):
            for eps in (0.0005,0.001,0.0015):
                d=run(df,eps=eps,entry=ent,**kw)
                if not len(d): print(f"{name:<9}{ent:<7}{eps:>6.4f}  n=0"); continue
                R=d.R.values; D=d["dir"].values; T=pd.DatetimeIndex(d.time); mid=T[len(T)//2]
                f=lambda x: f"{x.mean():+8.3f}" if len(x) else "     nan"
                print(f"{name:<9}{ent:<7}{eps:>6.4f}{len(R):>6}{len(R)/yrs:>5.0f}{100*(R>0).mean():>7.1f}{d.rr.median():>7.1f}"
                      f"{R.mean():>+8.3f}{100*boot(R):>6.1f}%{f(R[D==1])}{f(R[D==-1])}{f(R[T<=mid])}{f(R[T>mid])}")
        print()
