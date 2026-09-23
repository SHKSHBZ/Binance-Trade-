"""Follow-up: the digit test showed BTC swing turns AVOID prices ending ...950-...049
(the round thousands). If round thousands are not where BTC turns, does price
tend to push THROUGH them? Same race as btc_psych_levels.py, vs control prices."""
import _paths, numpy as np, pandas as pd
from btc_psych_levels import load, atr, RACE, HORIZON, APPROACH
df=load(); h,l,c=df.high.values,df.low.values,df.close.values; n=len(c); A=atr(h,l,c)
rng=np.random.default_rng(1)
def race(lv,i,side):
    up=lv+side*RACE*A[i]; dn=lv-side*RACE*A[i]
    for j in range(i+1,i+1+HORIZON):
        if (l[j]<=dn if side==1 else h[j]>=dn): return -1
        if (h[j]>=up if side==1 else l[j]<=up): return 1
    return 0
ev=[]
for i in range(30,n-HORIZON):
    for kind,lv in (("ROUND $1000",round(c[i-1]/1000)*1000),
                    ("HALF $500",round((c[i-1]-500)/1000)*1000+500),
                    ("CONTROL",round(c[i-1]/1000)*1000+rng.choice([-1,1])*rng.uniform(200,350))):
        if not (l[i]<=lv<=h[i]): continue
        if c[i-1]>lv*(1+APPROACH): side=1
        elif c[i-1]<lv*(1-APPROACH): side=-1
        else: continue
        r=race(lv,i,side)
        ev.append(dict(time=df.index[i],kind=kind,res=r,cost=2*0.0001*lv/(RACE*A[i])))
e=pd.DataFrame(ev)
# one event per level-kind per 24h to avoid counting the same touch repeatedly
e["day"]=e.time.dt.floor("24h"); e=e.drop_duplicates(["kind","day"])
print("When BTC 1H reaches a level: does it BOUNCE (1.5 ATR back) or BREAK (1.5 ATR through) first?\n")
for lab,m in (("ALL 2023-2026",e.time>="2000"),("2023-2024",e.time<"2025-01-01"),("2025-2026",e.time>="2025-01-01")):
    print(lab)
    for k in ("ROUND $1000","HALF $500","CONTROL"):
        s=e[m&(e.kind==k)]
        brk=(s.res==-1).mean(); bnc=(s.res==1).mean()
        print(f"   {k:<12} n={len(s):<4} BREAK {100*brk:5.1f}%   BOUNCE {100*bnc:5.1f}%"
              f"   'trade the break' expR={(-s.res-s.cost).mean():+.3f}")
