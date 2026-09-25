import numpy as np, pandas as pd
E=pd.read_pickle("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/breakouts.pkl")
E["mid"]=(E.hr>=11)&(E.hr<13)
def show(lab,m):
    out=[]
    for p in ("BUILD","TEST"):
        x=E[m&(E.period==p)]
        if len(x)<5: out.append(f"{p} n={len(x)}"); continue
        R=x.R.values; ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
        out.append(f"{p} n={len(x):4d} hit {100*x.real.mean():4.1f}% avgR {R.mean():+.2f} P {100*(R[ix].mean(1)<=0).mean():4.1f}%")
    print(f"{lab:<52} "+" | ".join(out))
print("### 'day already moved a lot' — threshold robustness")
for t in (0.8,1.0,1.2,1.5,2.0): show(f"day range > {t:.1f}x daily ATR", E.day_used>t)
print("### split by direction / level / trend (day range > 1.0x ATR)")
big=E.day_used>1.0
show("  breakouts up", big&(E.dir==1)); show("  breakdowns", big&(E.dir==-1))
for t in ["PDH","PDL","AsiaH","AsiaL","24hH","24hL"]: show(f"  level {t}", big&(E.typ==t))
show("  with EMA trend", big&(E.trend_with==1)); show("  against EMA trend", big&(E.trend_with==0))
show("  not midday 11-13", big&~E.mid)
print("### prior touches")
for lo,hi in ((1,2),(1,5),(0,5),(6,999)): show(f"touches {lo}-{hi}", E.touches.between(lo,hi))
print("### combinations")
show("A  day>1.0 ATR, not midday", big&~E.mid)
show("B  day>1.0 ATR, with trend, not midday", big&(E.trend_with==1)&~E.mid)
show("C  touches<=5, with trend, not midday", (E.touches<=5)&(E.trend_with==1)&~E.mid)
show("D  day>1.0 ATR or touches<=2, not midday", (big|(E.touches<=2))&~E.mid)
show("ALL breakouts (reference)", E.day_used>-1)
