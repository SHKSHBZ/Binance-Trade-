import _paths, numpy as np, pandas as pd
from own_search import load, BUILD, CHECK, COST
d=load()
et=d.index.tz_localize("UTC").tz_convert("America/New_York")
d["etmin"]=et.hour*60+et.minute

def overnight(d, entry_et, exit_et, stop_k=0.5, trend=None, rand=None, rr=None):
    """enter at bar close of first bar >= entry_et (ET minutes), exit at first bar >= exit_et next session."""
    h,l,c=d.high.values,d.low.values,d.close.values; em=d.etmin.values; n=len(c)
    ef=d.ema_fast.values; es=d.ema_slow.values; da=d.datr.values
    rng=np.random.default_rng(rand) if rand is not None else None
    starts=np.where((em>=entry_et)&(np.roll(em,1)<entry_et))[0]
    out=[]; busy=-1
    for i in starts:
        if i<=busy or i<1: continue
        dr=1
        if trend=="filter" and ef[i]<es[i]: continue
        if trend=="both": dr=1 if ef[i]>es[i] else -1
        if rng is not None: dr=1 if rng.random()<.5 else -1
        sd=stop_k*da[i]; e=c[i]; s=e-dr*sd; g=None if rr is None else e+dr*rr*sd; R=None
        crossed=False
        for j in range(i+1,min(i+200,n)):
            if (dr==1 and l[j]<=s) or (dr==-1 and h[j]>=s): R=-1.0; break
            if g is not None and ((dr==1 and h[j]>=g) or (dr==-1 and l[j]<=g)): R=rr; break
            if em[j]<entry_et and not crossed: crossed=True   # past midnight ET
            if crossed and em[j]>=exit_et: R=dr*(c[j]-e)/sd; break
        if R is None: continue
        out.append(dict(time=d.index[i],dir=dr,R=R-COST/sd)); busy=j
    return pd.DataFrame(out)

def show(lab,t,a=BUILD[0],b=CHECK[1]):
    x=t[(t.time>=a)&(t.time<=b+" 23:59")]; R=x.R.values; D=x.dir.values; y=pd.DatetimeIndex(x.time).year
    ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
    print(f"{lab:<44} n={len(R):4d} win={100*(R>0).mean():4.1f}% exp={R.mean():+.3f} P={100*(R[ix].mean(1)<=0).mean():4.1f}% "
          f"L={R[D==1].mean():+.3f}({(D==1).sum()}) S={R[D==-1].mean() if (D==-1).any() else np.nan:+.3f}({(D==-1).sum()}) "
          + " ".join(f"{yy}:{R[y==yy].mean():+.2f}" for yy in sorted(set(y))))

if __name__=="__main__":
    T=lambda hh,mm=0: hh*60+mm
    for ent,ex in ((T(15),T(23)),(T(16),T(23)),(T(18),T(23)),(T(18),T(3)),(T(15),T(3)),(T(12),T(3))):
        lab=f"{ent//60:02d}:{ent%60:02d}->{ex//60:02d}:00 ET"
        for sk in (0.5,1.0):
            show(f"long only  {lab} stop{sk}", overnight(d,ent,ex,sk))
            show(f"trend dir  {lab} stop{sk}", overnight(d,ent,ex,sk,trend="both"))
    print("--- control: same length window during the DAY (03->11 ET) ---")
    show("long only 03:00->11:00 ET stop0.5", overnight(d,T(3),T(11),0.5))
    show("trend dir 03:00->11:00 ET stop0.5", overnight(d,T(3),T(11),0.5,trend="both"))
