import _paths, numpy as np, pandas as pd
from own_search import BUILD, CHECK, COST
from own_search_nyet import d, run
T=lambda hh,mm=0: hh*60+mm

def control(d, ref, seed, rr=2.0, maxhold=48, t0=T(10), t1=T(15)):
    """For each real breakout trade (same day), enter at a RANDOM bar in the trade window,
    in the TREND direction, with the same stop distance. Tests breakout timing vs trend beta."""
    h,l,c=d.high.values,d.low.values,d.close.values; em=d.etmin.values; n=len(c)
    ef=d.ema_fast.values; es=d.ema_slow.values
    rng=np.random.default_rng(seed); days=d.etday.values
    pos={t:i for i,t in enumerate(d.index)}
    out=[]; busy=-1
    for _,r in ref.iterrows():
        i0=pos[r.time]; day=days[i0]
        cand=np.where((days==day)&(em>=t0)&(em<t1))[0] if False else None
        lo=i0
        while lo>0 and days[lo-1]==day: lo-=1
        hi=i0
        while hi<n-1 and days[hi+1]==day: hi+=1
        win=[k for k in range(lo,hi+1) if t0<=em[k]<t1 and k>busy]
        if not win: continue
        i=rng.choice(win); dr=1 if ef[i]>es[i] else -1; sd=r.risk
        e=c[i]; s=e-dr*sd; g=e+dr*rr*sd; R=None
        for j in range(i+1,min(i+1+maxhold,n)):
            if (dr==1 and l[j]<=s) or (dr==-1 and h[j]>=s): R=-1.0; break
            if (dr==1 and h[j]>=g) or (dr==-1 and l[j]<=g): R=rr; break
        if R is None: j=min(i+maxhold,n-1); R=dr*(c[j]-e)/sd
        out.append(R-COST/sd); busy=j
    return np.array(out)

for lab,(r0,r1) in {"8:00-9:00":(T(8),T(9)),"8:30-9:30":(T(8,30),T(9,30)),"9:00-10:00":(T(9),T(10)),"9:30-10:30":(T(9,30),T(10,30))}.items():
    t=run(d,r0,r1,r1,T(15),rr=2.0); t=t[t.time<=CHECK[1]+" 23:59"]
    cs=[control(d,t,s,t0=r1).mean() for s in range(20)]
    print(f"{lab}: breakout exp={t.R.mean():+.3f} (n={len(t)})  random-time trend entry exp={np.mean(cs):+.3f} range {min(cs):+.3f}..{max(cs):+.3f}  -> breakout beats {sum(t.R.mean()>np.array(cs))}/20")
