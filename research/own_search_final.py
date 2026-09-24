import _paths, numpy as np, pandas as pd
from own_search import BUILD, CHECK, HOLD, COST
from own_search_nyet import d, run
T=lambda hh,mm=0: hh*60+mm

def timed(d, at, stop_k=0.5, rr=2.0, mode="trend", maxhold=48):
    h,l,c=d.high.values,d.low.values,d.close.values; em=d.etmin.values; n=len(c)
    ef=d.ema_fast.values; es=d.ema_slow.values; da=d.datr.values
    starts=np.where((em>=at)&(np.roll(em,1)<at))[0]; out=[]; busy=-1
    for i in starts:
        if i<=busy: continue
        dr=1 if mode=="long" else (1 if ef[i]>es[i] else -1)
        sd=stop_k*da[i]; e=c[i]; s=e-dr*sd; g=e+dr*rr*sd; R=None
        for j in range(i+1,min(i+1+maxhold,n)):
            if (dr==1 and l[j]<=s) or (dr==-1 and h[j]>=s): R=-1.0; break
            if (dr==1 and h[j]>=g) or (dr==-1 and l[j]<=g): R=rr; break
        if R is None: j=min(i+maxhold,n-1); R=dr*(c[j]-e)/sd
        out.append(dict(time=d.index[i],dir=dr,R=R-COST/sd,risk=sd)); busy=j
    return pd.DataFrame(out)

def show(lab,t,a,b):
    x=t[(t.time>=a)&(t.time<=b+" 23:59")]; R=x.R.values; D=x.dir.values
    if not len(R): print(f"{lab:<46} n=0"); return
    ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
    f=lambda m: f"{R[m].mean():+.3f}({m.sum()})" if m.any() else "   n/a"
    print(f"{lab:<46} n={len(R):4d} win={100*(R>0).mean():4.1f}% exp={R.mean():+.3f} P={100*(R[ix].mean(1)<=0).mean():5.1f}% "
          f"long={f(D==1)} short={f(D==-1)} total={R.sum():+.1f}R medrisk=${x.risk.median():.1f}")

C={"C1 NY breakout 9-10ET trend rr2":run(d,T(9),T(10),T(10),T(15),rr=2.0),
   "C2 trend entry 10:00ET stop.5ATR rr2":timed(d,T(10)),
   "C3 LONG-only 10:00ET stop.5ATR rr2 (beta)":timed(d,T(10),mode="long")}
if "C1 NY breakout 9-10ET trend rr2" in C: C["C1 NY breakout 9-10ET trend rr2"]["risk"]=C["C1 NY breakout 9-10ET trend rr2"]["risk"]
for per,(a,b) in {"BUILD":BUILD,"CHECK":CHECK,"HOLDOUT 2026":HOLD}.items():
    print(f"=== {per} ===")
    for k,t in C.items(): show(k,t,a,b)
g=d.close
print("gold price: start build %.0f, end check %.0f, holdout %s -> %.0f" % (g[:BUILD[1]].iloc[0], g[:CHECK[1]].iloc[-1], g["2026"].index[-1].date(), g.iloc[-1]))
m=g["2026"].resample("ME").last(); print("2026 month-end:", " ".join(f"{i.month}:{v:.0f}" for i,v in m.items()))
