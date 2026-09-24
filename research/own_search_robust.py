import _paths, numpy as np, pandas as pd
from own_search import load, s_range_break, s_overnight, simulate, stats, BUILD, CHECK
d=load()
def show(lab,t,a=BUILD[0],b=CHECK[1]):
    x=t[(t.time>=a)&(t.time<=b+" 23:59")]; R=x.R.values; D=x.dir.values; y=pd.DatetimeIndex(x.time).year
    ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
    top=np.sort(R)[::-1]; conc=top[:10].sum()/R.sum() if R.sum()>0 else np.nan
    print(f"{lab:<48} n={len(R):4d} win={100*(R>0).mean():4.1f}% exp={R.mean():+.3f} P={100*(R[ix].mean(1)<=0).mean():4.1f}% "
          f"L={R[D==1].mean():+.3f}({(D==1).sum()}) S={R[D==-1].mean() if (D==-1).any() else np.nan:+.3f}({(D==-1).sum()}) top10={100*conc:.0f}% "
          + " ".join(f"{yy}:{R[y==yy].mean():+.2f}" for yy in sorted(set(y))))

print("=== NY first-hour breakout, trend, stop=other side, variants (BUILD+CHECK) ===")
for (r0,r1,t0,t1) in ((13,14,14,19),(13,14,14,17),(13,14,14,21),(12,14,14,19),(13,15,15,19),(14,15,15,19)):
    for rr in (1.5,2.0,2.5):
        show(f"range {r0}-{r1} trade {t0}-{t1} rr{rr}", s_range_break(d,r0,r1,t0,t1,stop="other",rr=rr,trend=True))
print("--- same, NO trend filter / random side null ---")
base=s_range_break(d,13,14,14,19,stop="other",rr=2.0,trend=False); show("no trend filter rr2",base)
