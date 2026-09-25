"""
Strategy extracted from the trader's own 82 trades (rules fixed BEFORE testing on older data):
  P2 trend    : direction = sign(EMA80 - EMA800) on 15m
  P1 pullback : last 4h (16 bars) moved AGAINST the trend by >= 0.15 daily ATR
  turn        : last 1h (4 bars) moved WITH the trend
  P3 volatile : 15m ATR14 > 1.2x its 5-day average, OR a news-like spike (bar range > 3x) earlier today
  hours       : 02:00-16:00 New York (London + NY, where the trader trades)
  stop        : beyond the pullback extreme (last 16 bars) + 0.05 daily ATR; skip if stop <0.15 or >0.6 daily ATR
  exit        : 2R target (trader's actual) / variant: trail 1.5R once +1.5R
Clean test = 2022-06 .. 2025-05-07 (before the trader's first trade).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def prep(df):
    g=df.copy()
    et=g.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    g["hr"]=et.hour+et.minute/60; g["sday"]=(et+pd.Timedelta(hours=6)).normalize()
    sd=g.groupby("sday").agg(H=("high","max"),L=("low","min"),C=("close","last"))
    tr=np.maximum(sd.H-sd.L,np.maximum((sd.H-sd.C.shift()).abs(),(sd.L-sd.C.shift()).abs()))
    g=g.join(tr.rolling(14).mean().shift(1).rename("datr"),on="sday")
    c=g.close
    g["ema80"]=c.ewm(span=80,adjust=False).mean(); g["ema800"]=c.ewm(span=800,adjust=False).mean()
    tr15=np.maximum(g.high-g.low,np.maximum((g.high-c.shift()).abs(),(g.low-c.shift()).abs()))
    g["atr15"]=tr15.rolling(14).mean(); g["atr5d"]=tr15.rolling(480).mean()
    g["spike_today"]=(tr15>3*g.atr5d).astype(int).groupby(g.sday).cummax()
    return g.dropna(subset=["datr","atr5d"])

def run(g, cost, use_vol=True, use_pullback=True, use_turn=True, exitm="2R", rand=None, pb=0.15):
    h,l,c=g.high.values,g.low.values,g.close.values; n=len(c)
    tr_=np.sign(g.ema80.values-g.ema800.values); datr=g.datr.values; hr=g.hr.values
    vol=(g.atr15.values>1.2*g.atr5d.values)|(g.spike_today.values==1)
    rng=np.random.default_rng(rand) if rand is not None else None
    out=[]; i=820
    while i<n-1:
        d=tr_[i]
        ok = d!=0 and 2<=hr[i]<16
        if ok and use_pullback: ok = d*(c[i]-c[i-16]) <= -pb*datr[i]
        if ok and use_turn: ok = d*(c[i]-c[i-4]) > 0
        if ok and use_vol: ok = vol[i]
        if ok and rng is not None: ok = rng.random()<0.5
        if not ok: i+=1; continue
        ext=l[i-15:i+1].min() if d==1 else h[i-15:i+1].max()
        e=c[i]; stop=ext-d*0.05*datr[i]; risk=d*(e-stop)
        if not (0.15*datr[i]<=risk<=0.6*datr[i]): i+=1; continue
        best=e; st=stop; R=None
        for j in range(i+1,min(i+501,n)):
            if (d==1 and l[j]<=st) or (d==-1 and h[j]>=st): R=d*(st-e)/risk; break
            best=max(best,h[j]) if d==1 else min(best,l[j]); gain=d*(best-e)/risk
            if exitm=="2R" and gain>=2: R=2.0; break
            if exitm=="trail" and gain>=1.5:
                ts=best-d*1.5*risk; st=max(st,ts) if d==1 else min(st,ts)
        if R is None: j=min(i+500,n-1); R=d*(c[j]-e)/risk
        out.append(dict(time=g.index[i],dir=int(d),R=R-cost/risk,risk=risk)); i=j+1
    return pd.DataFrame(out)

def rep(lab,t,a,b):
    x=t[(t.time>=a)&(t.time<=b)]
    if len(x)<5: print(f"{lab:<52} n={len(x)}"); return
    R=x.R.values; ix=np.random.default_rng(0).integers(0,len(R),(4000,len(R)))
    yrs=(pd.Timestamp(b)-pd.Timestamp(a)).days/365.25
    y=pd.DatetimeIndex(x.time).year; D=x.dir.values
    print(f"{lab:<52} n={len(R):4d} ({len(R)/yrs:3.0f}/yr) win {100*(R>0).mean():4.1f}% avgR {R.mean():+.3f} total {R.sum():+6.1f}R P {100*(R[ix].mean(1)<=0).mean():4.1f}% "
          f"buy {R[D==1].mean():+.2f} sell {R[D==-1].mean() if (D==-1).any() else np.nan:+.2f} | "+" ".join(f"{yy}:{R[y==yy].mean():+.2f}" for yy in sorted(set(y))))

if __name__=="__main__":
    g=prep(load_ohlcv("XAUUSD_15m.csv")); cost=0.25
    PRE=("2022-06-24","2025-05-07"); USER=("2025-05-08","2026-09-16")
    for per,(a,b) in (("CLEAN TEST: before your first trade (2022-06 .. 2025-05)",PRE),("YOUR TRADING PERIOD (2025-05 .. 2026-09)",USER)):
        print(f"\n=== {per} ===")
        rep("YOUR PATTERN, 2R target",run(g,cost),a,b)
        rep("YOUR PATTERN, trail 1.5R",run(g,cost,exitm="trail"),a,b)
        rep("  without volatile-day filter",run(g,cost,use_vol=False),a,b)
        rep("  without pullback (chasing trend)",run(g,cost,use_pullback=False),a,b)
        rep("  without the 1h turn",run(g,cost,use_turn=False),a,b)
        rs=[run(g,cost,use_vol=False,use_pullback=False,use_turn=False,rand=s) for s in range(5)]
        v=[x[(x.time>=a)&(x.time<=b)].R.mean() for x in rs]
        print(f"{'  control: random entries in trend, same stops/exits':<52} avgR {np.mean(v):+.3f} (range {min(v):+.3f}..{max(v):+.3f})")
