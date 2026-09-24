import _paths, numpy as np, pandas as pd
from own_search import load, BUILD, CHECK, COST

d=load()
et=d.index.tz_localize("UTC").tz_convert("America/New_York")
d["etmin"]=et.hour*60+et.minute; d["etday"]=et.tz_localize(None).normalize()

def run(d, r0, r1, t0, t1, rr=2.0, trend=True, maxhold=48, flat=None, rand=None, stop_frac=1.0):
    """times in ET minutes. range r0..r1, trade window t0..t1. stop = other side of range."""
    h,l,c=d.high.values,d.low.values,d.close.values; em=d.etmin.values; n=len(c)
    ef=d.ema_fast.values; es=d.ema_slow.values; da=d.datr.values
    rng=np.random.default_rng(rand) if rand is not None else None
    out=[]; busy=-1
    for day,ix in pd.Series(np.arange(n),index=d.etday.values).groupby(level=0):
        ix=ix.values; m=em[ix]
        R_=ix[(m>=r0)&(m<r1)]; W=ix[(m>=t0)&(m<t1)]
        if len(R_)<(r1-r0)//15-1 or not len(W): continue
        H=h[R_].max(); L=l[R_].min()
        for i in W:
            dr=1 if c[i]>H else -1 if c[i]<L else 0
            if dr==0: continue
            if trend and np.sign(ef[i]-es[i])!=dr: break
            if i<=busy: break
            sd=max((c[i]-(L if dr==1 else H))*dr*stop_frac,0.1*da[i])
            if rng is not None: dr=1 if rng.random()<.5 else -1
            e=c[i]; s=e-dr*sd; g=e+dr*rr*sd; R=None; kind="time"
            for j in range(i+1,min(i+1+maxhold,n)):
                if (dr==1 and l[j]<=s) or (dr==-1 and h[j]>=s): R=-1.0; kind="stop"; break
                if (dr==1 and h[j]>=g) or (dr==-1 and l[j]<=g): R=rr; kind="tgt"; break
                if flat is not None and em[j]>=flat and d.etday.values[j]==day: R=dr*(c[j]-e)/sd; kind="flat"; break
            if R is None: j=min(i+maxhold,n-1); R=dr*(c[j]-e)/sd
            out.append(dict(time=d.index[i],dir=dr,R=R-COST/sd,kind=kind,risk=sd,price=e)); busy=j; break
    return pd.DataFrame(out)

def show(lab,t,a=BUILD[0],b=CHECK[1]):
    x=t[(t.time>=a)&(t.time<=b+" 23:59")]; R=x.R.values; D=x.dir.values; y=pd.DatetimeIndex(x.time).year
    ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
    k=x.kind.value_counts(normalize=True).round(2).to_dict()
    print(f"{lab:<44} n={len(R):4d} win={100*(R>0).mean():4.1f}% exp={R.mean():+.3f} P={100*(R[ix].mean(1)<=0).mean():4.1f}% "
          f"L={R[D==1].mean():+.3f} S={R[D==-1].mean():+.3f} {k} risk$ med={x.risk.median():.1f} "
          + " ".join(f"{yy}:{R[y==yy].mean():+.2f}" for yy in sorted(set(y))))

if __name__=="__main__":
    T=lambda hh,mm=0: hh*60+mm
    print("=== ET-aligned opening-range breakout, trend filter, stop=other side (BUILD+CHECK) ===")
    for lab,(r0,r1) in {"8:00-9:00 ET":(T(8),T(9)),"8:30-9:30 ET":(T(8,30),T(9,30)),"9:00-10:00 ET":(T(9),T(10)),
                        "9:30-10:30 ET":(T(9,30),T(10,30)),"9:30-10:00 ET":(T(9,30),T(10))}.items():
        for rr in (1.5,2.0):
            show(f"range {lab} rr{rr}", run(d,r0,r1,r1,T(15),rr=rr))
    print("--- main variant, exit rules ---")
    show("9:00-10:00 rr2 flat 16:00 ET", run(d,T(9),T(10),T(10),T(15),rr=2.0,flat=T(16)))
    show("9:00-10:00 rr2 hold max 12h", run(d,T(9),T(10),T(10),T(15),rr=2.0))
    show("9:00-10:00 rr2 half-range stop", run(d,T(9),T(10),T(10),T(15),rr=2.0,stop_frac=0.5))
    print("--- random-direction null (same entries/stops), 20 seeds ---")
    for lab,(r0,r1) in {"8:30-9:30":(T(8,30),T(9,30)),"9:00-10:00":(T(9),T(10))}.items():
        v=[]
        for s in range(20):
            t=run(d,r0,r1,r1,T(15),rr=2.0,rand=s); x=t[t.time<=CHECK[1]+" 23:59"]; v.append(x.R.mean())
        print(f"{lab} null mean={np.mean(v):+.3f} max={max(v):+.3f}")
