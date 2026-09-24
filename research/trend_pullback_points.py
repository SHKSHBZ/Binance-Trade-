"""
Pre-registered simple test (rules fixed before running):
 gold 15m, trade WITH the 4H trend only.
 4H uptrend: last CLOSED 4H bar close > EMA50(4H) > EMA200(4H)   (downtrend mirror)
 15m trigger (long): bar low <= EMA20(15m) and close > EMA20(15m), 07-17 UTC
 entry at trigger close, stop = entry - STOP$, target = entry + TGT$, max hold 96 bars (1 day)
 cost 0.25 per trade. One trade at a time.
 Control: same trend filter, same hours, same stop/target, but RANDOM entry bars
 -> separates 'pullback timing' from 'just gold drifting up'.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def ema(x,n): return pd.Series(x).ewm(span=n,adjust=False).mean().values

def trend_on_15m(d15, d4):
    c4=d4.close.values; e50=ema(c4,50); e200=ema(c4,200)
    t=np.where((c4>e50)&(e50>e200),1,np.where((c4<e50)&(e50<e200),-1,0))
    # value of a 4H bar is known only after it closes: shift timestamps by 4h
    s=pd.Series(t,index=d4.index+pd.Timedelta(hours=4))
    return s.reindex(d15.index,method="ffill").fillna(0).values

def sim(d15, tr, stop=5.0, tgt=8.0, cost=0.25, mode="rule", seed=0, hours=(7,17), maxhold=96, sides=(1,-1)):
    h,l,c=d15.high.values,d15.low.values,d15.close.values; n=len(c)
    e20=ema(c,20); hr=d15.index.hour
    rng=np.random.default_rng(seed); out=[]; i=1
    ok=(hr>=hours[0])&(hr<hours[1])
    while i<n-1:
        d=tr[i]
        if d==0 or d not in sides or not ok[i]: i+=1; continue
        if mode=="rule":
            sig=(l[i]<=e20[i]<c[i]) if d==1 else (h[i]>=e20[i]>c[i])
        else:
            sig=rng.random()<0.02
        if not sig: i+=1; continue
        e=c[i]; s=e-d*stop; g=e+d*tgt; R=None
        for j in range(i+1,min(i+1+maxhold,n)):
            if (d==1 and l[j]<=s) or (d==-1 and h[j]>=s): R=-1.0; break
            if (d==1 and h[j]>=g) or (d==-1 and l[j]<=g): R=tgt/stop; break
        if R is None: j=min(i+maxhold,n-1); R=d*(c[j]-e)/stop
        out.append(dict(time=d15.index[i],dir=d,R=R-cost/stop)); i=j+1
    return pd.DataFrame(out)

def boot(R,n=4000):
    ix=np.random.default_rng(0).integers(0,len(R),(n,len(R))); return (R[ix].mean(1)<=0).mean()

def report(name,d):
    R=d.R.values; D=d.dir.values; y=pd.DatetimeIndex(d.time).year
    yrs=" ".join(f"{yy}:{R[y==yy].mean():+.2f}" for yy in sorted(set(y)))
    print(f"{name:<34} n={len(R):4d} win={100*(R>0).mean():4.1f}% expR={R.mean():+.3f} P={100*boot(R):4.1f}% "
          f"long={R[D==1].mean() if (D==1).any() else np.nan:+.3f}({(D==1).sum()}) short={R[D==-1].mean() if (D==-1).any() else np.nan:+.3f}({(D==-1).sum()})")
    print(f"{'':<34} by year {yrs}")

if __name__=="__main__":
    d15=load_ohlcv("XAUUSD_15m.csv"); d4=load_ohlcv("XAUUSD_4h.csv")
    tr=trend_on_15m(d15,d4)
    for st,tg in ((5,8),(4,8),(5,5),(8,8)):
        report(f"RULE  stop${st} tgt${tg}", sim(d15,tr,st,tg))
        rs=[sim(d15,tr,st,tg,mode="rand",seed=s).R.mean() for s in range(20)]
        print(f"{'  random entries, same filter':<34} expR mean={np.mean(rs):+.3f} (range {min(rs):+.3f}..{max(rs):+.3f})")
