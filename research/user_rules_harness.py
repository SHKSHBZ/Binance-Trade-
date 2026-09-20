"""Re-run strategies under the TRADER'S encoding rules (not Claude's):
   - fixed 2:1 target (bank it)
   - setup/zone REUSE allowed (multiple trades per zone)
   - permissive entry: sweep a recent minor swing inside the zone, close back = MSB
   - stop just beyond the sweep wick
   - no overlapping positions
Zones are pluggable so every strategy family can be run identically."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def minor_pivots(h,l,half=3):
    n=len(h); kh=np.full(n,np.nan); kl=np.full(n,np.nan)
    for i in range(half,n-half):
        if h[i]==h[i-half:i+half+1].max() and i+half<n: kh[i+half]=h[i]
        if l[i]==l[i-half:i+half+1].min() and i+half<n: kl[i+half]=l[i]
    return kh,kl

def simulate(df, zones, rr=2.0, spread=0.25, half=3):
    """zones: array per bar of (dir, lo, hi) ; dir 0 = none"""
    o=df["open"].values;h=df["high"].values;l=df["low"].values;c=df["close"].values
    t=df.index; n=len(c)
    kh,kl=minor_pivots(h,l,half)
    mlo=np.nan; mhi=np.nan
    busy=-1; trades=[]
    zdir,zlo,zhi = zones
    for i in range(half+1,n-1):
        if not np.isnan(kl[i]): mlo=kl[i]
        if not np.isnan(kh[i]): mhi=kh[i]
        if i<=busy: continue
        d=zdir[i]
        if d==0 or np.isnan(zlo[i]) or np.isnan(zhi[i]): continue
        inzone = (l[i]<=zhi[i]) and (h[i]>=zlo[i])
        if not inzone: continue
        direction=entry=stop=None
        if d>0 and not np.isnan(mlo):
            if l[i]<mlo and c[i]>mlo:            # swept low + reclaimed = bullish MSB
                direction=1; entry=c[i]; stop=l[i]
        elif d<0 and not np.isnan(mhi):
            if h[i]>mhi and c[i]<mhi:            # swept high + rejected = bearish MSB
                direction=-1; entry=c[i]; stop=h[i]
        if direction is None: continue
        risk=abs(entry-stop)
        if risk<=0 or risk/entry<0.0002: continue
        tgt = entry+rr*risk if direction>0 else entry-rr*risk
        j=i+1; res=None
        while j<n:
            if direction>0:
                if l[j]<=stop: res=-1.0; break
                if h[j]>=tgt:  res=rr;   break
            else:
                if h[j]>=stop: res=-1.0; break
                if l[j]<=tgt:  res=rr;   break
            j+=1
        if res is None: j=n-1; res=((c[j]-entry) if direction>0 else (entry-c[j]))/risk
        res -= spread/risk                      # round-trip cost in R
        trades.append({"time":t[i],"dir":direction,"R":res,"risk_pts":risk})
        busy=j
    return trades

def report(name, trades):
    if not trades:
        print(f"  {name:28} n=0"); return
    R=np.array([x["R"] for x in trades]); n=len(R)
    win=100*np.mean(R>0)
    rng=np.random.default_rng(1)
    bs=rng.choice(R,(5000,n),replace=True).mean(axis=1)
    p=(bs<=0).mean()
    print(f"  {name:28} n={n:<5} win={win:4.1f}%  expR={R.mean():+.3f}  totalR={R.sum():+7.1f}  P(expR<=0)={p*100:4.1f}%")
    return R
