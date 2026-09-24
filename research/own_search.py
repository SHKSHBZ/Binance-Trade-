"""
Own strategy search, gold 15m. Splits: BUILD 2022-06..2025-06, CHECK 2025-07..2025-12,
HOLDOUT 2026 (touched once, at the end). Stops/targets scaled by daily ATR so they
mean the same thing at $1,800 and $4,200 gold. Cost $0.25/trade.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

COST=0.25
BUILD=("2022-06-24","2025-06-30"); CHECK=("2025-07-01","2025-12-31"); HOLD=("2026-01-01","2026-12-31")

def load():
    d=load_ohlcv("XAUUSD_15m.csv")
    dd=d.resample("1D").agg(dict(high="max",low="min",close="last")).dropna()
    pc=dd.close.shift(); tr=np.maximum(dd.high-dd.low,np.maximum(abs(dd.high-pc),abs(dd.low-pc)))
    datr=tr.rolling(14).mean().shift(1)            # yesterday's known daily ATR
    d["datr"]=datr.reindex(d.index.normalize()).values
    d["ema_fast"]=d.close.ewm(span=20*4,adjust=False).mean()   # ~20h
    d["ema_slow"]=d.close.ewm(span=200*4,adjust=False).mean()  # ~200h
    return d.dropna()

def simulate(d, sigs, maxhold=96, exit_time=None):
    """sigs: list of (i, dir, stop_dist, tgt_dist or None). Entry at close of bar i.
    exit_time: UTC hour to flatten (optional). One trade at a time."""
    h,l,c=d.high.values,d.low.values,d.close.values; hr=d.index.hour; n=len(c)
    out=[]; busy=-1
    for i,dr,sd,td in sigs:
        if i<=busy or i>=n-1 or not sd>0: continue
        e=c[i]; s=e-dr*sd; g=None if td is None else e+dr*td; R=None
        for j in range(i+1,min(i+1+maxhold,n)):
            if (dr==1 and l[j]<=s) or (dr==-1 and h[j]>=s): R=-1.0; break
            if g is not None and ((dr==1 and h[j]>=g) or (dr==-1 and l[j]<=g)): R=td/sd; break
            if exit_time is not None and hr[j]==exit_time and d.index[j].minute==0: R=dr*(c[j]-e)/sd; break
        if R is None: j=min(i+maxhold,n-1); R=dr*(c[j]-e)/sd
        out.append((d.index[i],dr,R-COST/sd)); busy=j
    return pd.DataFrame(out,columns=["time","dir","R"])

# ---------- strategy families ----------
def s_overnight(d, entry_h=20, exit_h=3, stop_k=0.5):
    idx=np.where((d.index.hour==entry_h)&(d.index.minute==0))[0]
    return simulate(d,[(i-1,1,stop_k*d.datr.iat[i],None) for i in idx if i>0],maxhold=60,exit_time=exit_h)

def s_range_break(d, r0, r1, t0, t1, stop="mid", rr=1.5, trend=False, flat_h=None):
    """range built r0..r1 UTC hours; trade first close outside it during t0..t1."""
    sigs=[]; days=d.index.normalize()
    hr=d.index.hour.values; c=d.close.values; h=d.high.values; l=d.low.values
    for day,ix in pd.Series(np.arange(len(d)),index=days).groupby(level=0):
        ix=ix.values; hh=hr[ix]
        rng=ix[(hh>=r0)&(hh<r1)]; win=ix[(hh>=t0)&(hh<t1)]
        if len(rng)<(r1-r0)*3 or not len(win): continue
        H=h[rng].max(); L=l[rng].min()
        for i in win:
            dr=1 if c[i]>H else -1 if c[i]<L else 0
            if dr==0: continue
            if trend and np.sign(d.ema_fast.iat[i]-d.ema_slow.iat[i])!=dr: break
            sd=(c[i]-(H+L)/2)*dr if stop=="mid" else (c[i]-(L if dr==1 else H))*dr
            sd=max(sd,0.1*d.datr.iat[i])
            sigs.append((i,dr,sd,rr*sd)); break
    return simulate(d,sigs,maxhold=48,exit_time=flat_h)

def s_bias_open(d, at_h=7, ref_h=0, rr=1.5, stop_k=0.3, follow=True):
    """at at_h, trade in direction of price vs the ref_h open (daily bias)."""
    sigs=[]; o=d.open.values; c=d.close.values
    ref=pd.Series(np.where((d.index.hour==ref_h)&(d.index.minute==0),o,np.nan),index=d.index).ffill().values
    for i in np.where((d.index.hour==at_h)&(d.index.minute==0))[0]:
        i-=1
        dr=int(np.sign(c[i]-ref[i]))*(1 if follow else -1)
        if dr==0 or np.isnan(ref[i]): continue
        sd=stop_k*d.datr.iat[i]; sigs.append((i,dr,sd,rr*sd))
    return simulate(d,sigs,maxhold=40)

def s_impulse(d, k=1.0, follow=True, rr=1.5, stop_k=0.3, hours=None):
    """after a 1h move (4 bars) larger than k*dailyATR*0.25, follow or fade."""
    c=d.close.values; mv=c-np.roll(c,4); th=k*0.25*d.datr.values; sigs=[]
    last=-10
    for i in np.where(np.abs(mv)>th)[0]:
        if i<4 or i-last<8: continue
        if hours and d.index[i].hour not in hours: continue
        dr=int(np.sign(mv[i]))*(1 if follow else -1); sd=stop_k*d.datr.iat[i]
        sigs.append((i,dr,sd,rr*sd)); last=i
    return simulate(d,sigs,maxhold=48)

def s_trend_hour(d, hours, rr=1.5, stop_k=0.3):
    """enter at the start of given hours in direction of the ~200h trend."""
    sigs=[]
    for i in np.where(np.isin(d.index.hour,hours)&(d.index.minute==0))[0]:
        i-=1; dr=1 if d.ema_fast.iat[i]>d.ema_slow.iat[i] else -1
        sd=stop_k*d.datr.iat[i]; sigs.append((i,dr,sd,rr*sd))
    return simulate(d,sigs,maxhold=48)

def catalog():
    C={}
    for eh,xh in ((20,3),(21,3),(20,2),(22,3),(13,20)):
        for sk in (0.3,0.5,1.0):
            C[f"overnight long {eh}->{xh} stop{sk}"]=lambda d,eh=eh,xh=xh,sk=sk: s_overnight(d,eh,xh,sk)
    for name,(r0,r1,t0,t1) in {"Asia range->London":(0,7,7,12),"London 7-9->London/NY":(7,9,9,16),
                               "NY first hr->NY":(13,14,14,19),"Asia range->NY":(0,12,12,17)}.items():
        for st in ("mid","other"):
            for rr in (1.0,1.5,2.0):
                for tf in (False,True):
                    C[f"{name} stop={st} rr{rr} trend={tf}"]=lambda d,a=(r0,r1,t0,t1),st=st,rr=rr,tf=tf: s_range_break(d,*a,stop=st,rr=rr,trend=tf)
    for at in (7,13):
        for fol in (True,False):
            for rr in (1.0,1.5,2.0):
                C[f"bias vs 00 open at {at}h {'follow' if fol else 'fade'} rr{rr}"]=lambda d,at=at,fol=fol,rr=rr: s_bias_open(d,at,0,rr,0.3,fol)
    for k in (1.0,1.5,2.0):
        for fol in (True,False):
            for rr in (1.0,1.5,2.0):
                C[f"1h impulse>{k} {'follow' if fol else 'fade'} rr{rr}"]=lambda d,k=k,fol=fol,rr=rr: s_impulse(d,k,fol,rr)
    for hs,lab in (([7],"7h"),([13],"13h"),([7,13],"7+13h"),([1],"1h"),([20],"20h")):
        for rr in (1.0,1.5,2.0):
            C[f"trend-dir entry at {lab} rr{rr}"]=lambda d,hs=hs,rr=rr: s_trend_hour(d,hs,rr)
    return C

def stats(t, a, b):
    x=t[(t.time>=a)&(t.time<=b+" 23:59")]
    if not len(x): return None
    R=x.R.values; yrs=(pd.Timestamp(b)-pd.Timestamp(a)).days/365.25
    ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
    y=pd.DatetimeIndex(x.time).year
    return dict(n=len(R),py=len(R)/yrs,win=(R>0).mean(),exp=R.mean(),P=(R[ix].mean(1)<=0).mean(),
                yrs_pos=sum(R[y==yy].mean()>0 for yy in set(y)),yrs=len(set(y)))

if __name__=="__main__":
    d=load(); rows=[]
    for name,f in catalog().items():
        t=f(d); b=stats(t,*BUILD); c=stats(t,*CHECK)
        if b is None: continue
        rows.append(dict(name=name,n=b["n"],per_yr=round(b["py"]),win=round(100*b["win"],1),expR=round(b["exp"],3),
                         P=round(100*b["P"],1),yrs_pos=f'{b["yrs_pos"]}/{b["yrs"]}',
                         chk_n=c["n"] if c else 0,chk_expR=round(c["exp"],3) if c else np.nan))
    df=pd.DataFrame(rows).sort_values("expR",ascending=False)
    df.to_csv("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/own_search_build.csv",index=False)
    pd.set_option("display.width",250); pd.set_option("display.max_colwidth",60)
    print(f"{len(df)} strategies tested on BUILD")
    print(df.head(30).to_string(index=False))
    print("...\nworst 5:"); print(df.tail(5).to_string(index=False))
