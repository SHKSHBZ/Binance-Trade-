"""Same pullback-in-trend entries (07:00-21:00 London), different exits / entry looseness.
Goal: higher win rate AND more profit. Checked in 3 periods."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
import my_pattern_strategy as S

g=S.prep(load_ohlcv("XAUUSD_15m.csv"))
lon=g.index.tz_localize("UTC").tz_convert("Europe/London").tz_localize(None); LH=(lon.hour+lon.minute/60).values
h,l,c=g.high.values,g.low.values,g.close.values; n=len(c)
TR=np.sign(g.ema80.values-g.ema800.values); DATR=g.datr.values
VOL=(g.atr15.values>1.2*g.atr5d.values)|(g.spike_today.values==1)

def entries(pb=0.15, use_vol=True, turn=True):
    E=[]
    for i in range(820,n-1):
        d=TR[i]
        if d==0 or not (7<=LH[i]<21): continue
        if d*(c[i]-c[i-16]) > -pb*DATR[i]: continue
        if turn and d*(c[i]-c[i-4])<=0: continue
        if use_vol and not VOL[i]: continue
        ext=l[i-15:i+1].min() if d==1 else h[i-15:i+1].max()
        stop=ext-d*0.05*DATR[i]; risk=d*(c[i]-stop)
        if not (0.15*DATR[i]<=risk<=0.6*DATR[i]): continue
        E.append((i,int(d),stop,risk))
    return E

def simulate(E, tp=2.0, partial=None, part_frac=0.5, be_after_partial=True, trail=None, cost=0.25):
    out=[]; busy=-1
    for i,d,stop,risk in E:
        if i<=busy: continue
        e=c[i]; st=stop; best=e; done=0.0; bank=0.0; R=None
        for j in range(i+1,min(i+501,n)):
            if (d==1 and l[j]<=st) or (d==-1 and h[j]>=st):
                R=bank+(1-done)*d*(st-e)/risk; break
            best=max(best,h[j]) if d==1 else min(best,l[j]); gain=d*(best-e)/risk
            if partial and done==0 and gain>=partial:
                bank+=part_frac*partial; done=part_frac
                if be_after_partial: st=max(st,e) if d==1 else min(st,e)
            if tp and gain>=tp: R=bank+(1-done)*tp; break
            if trail and gain>=trail:
                ts=best-d*trail*risk; st=max(st,ts) if d==1 else min(st,ts)
        if R is None: j=min(i+500,n-1); R=bank+(1-done)*d*(c[j]-e)/risk
        out.append((g.index[i],d,R-cost/risk)); busy=j
    return pd.DataFrame(out,columns=["time","dir","R"])

P={"22-06..24-06":("2022-06-24","2024-06-30"),"24-07..25-05":("2024-07-01","2025-05-07"),"25-05..26-09":("2025-05-08","2026-09-16")}
def show(lab,t):
    cells=[]
    for a,b in P.values():
        x=t[(t.time>=a)&(t.time<=b+" 23:59")].R.values
        cells.append(f"{100*(x>0).mean():3.0f}% {x.mean():+.2f}")
    R=t.R.values; eq=5000*np.cumprod(1+0.02*R); dd=(eq/np.maximum.accumulate(eq)-1).min()
    print(f"{lab:<44} {len(R):4d} {100*(R>0).mean():4.0f}% {R.mean():+.3f} {R.sum():+6.1f}R | "+" | ".join(cells)+f" | $5k->${eq[-1]:>8,.0f} DD {100*dd:4.0f}%")

base=entries()
print(f"{'EXIT (same entries)':<44} {'n':>4} {'win':>5} {'avgR':>6} {'total':>7} | win/avgR per period: "+" | ".join(P)+" | 2% risk")
show("CURRENT: target 2R",simulate(base,tp=2.0))
for tp in (1.0,1.25,1.5,3.0): show(f"target {tp}R",simulate(base,tp=tp))
show("half off at 1R + BE, rest to 2R",simulate(base,tp=2.0,partial=1.0))
show("half off at 1R + BE, rest to 3R",simulate(base,tp=3.0,partial=1.0))
show("half off at 1R, NO BE, rest to 2R",simulate(base,tp=2.0,partial=1.0,be_after_partial=False))
show("half off at 1R + BE, rest trails 1.5R",simulate(base,tp=None,partial=1.0,trail=1.5))
show("no target, trail 1.5R",simulate(base,tp=None,trail=1.5))
show("70% off at 1R + BE, rest to 3R",simulate(base,tp=3.0,partial=1.0,part_frac=0.7))
print()
print("MORE TRADES (looser entries), target 2R:")
show("pullback >= 0.10 dATR",simulate(entries(pb=0.10)))
show("no moving-day filter",simulate(entries(use_vol=False)))
show("pullback >= 0.10, no moving-day filter",simulate(entries(pb=0.10,use_vol=False)))
