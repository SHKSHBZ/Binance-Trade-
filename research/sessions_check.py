"""Gold session behaviour: Asia / London / NY-London overlap / NY afternoon (London local time, DST-aware)."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
g=load_ohlcv("XAUUSD_15m.csv")
lon=g.index.tz_localize("UTC").tz_convert("Europe/London").tz_localize(None)
g["lh"]=lon.hour+lon.minute/60; g["lday"]=lon.normalize()
def sess(h):
    if h<7: return "1 Asia 00-07"
    if h<12: return "2 London 07-12"
    if h<16.5: return "3 NY/London overlap 12-16:30"
    if h<21: return "4 NY afternoon 16:30-21"
    return None
g["sess"]=[sess(h) for h in g.lh]
g=g.dropna(subset=["sess"])
S=g.groupby(["lday","sess"]).agg(o=("open","first"),c=("close","last"),h=("high","max"),l=("low","min"),n=("close","size"))
S=S[S.n>=8]
S["ret"]=(S.c/S.o-1)*1e4; S["rng"]=(S.h/S.l-1)*1e4; S["yr"]=pd.DatetimeIndex(S.index.get_level_values(0)).year
S=S.reset_index()
print(f"{'session':<30}{'avg move':>9}{'up days':>8}{'avg range':>10}  (bp = 0.01%; at $4,000 gold, 10bp = $4)")
for s,x in S.groupby("sess"):
    print(f"{s:<30}{x.ret.mean():>+8.1f}bp{100*(x.ret>0).mean():>7.0f}%{x.rng.mean():>8.0f}bp")
print("\nby year: avg session move in bp (up-days %)")
tab=S.groupby(["yr","sess"]).apply(lambda x:f"{x.ret.mean():+5.1f} ({100*(x.ret>0).mean():.0f}%)").unstack()
print(tab.to_string())
print("\nby year: avg session RANGE in bp")
print(S.groupby(["yr","sess"]).rng.mean().round(0).unstack().to_string())
# does London reverse Asia?
P=S.pivot(index="lday",columns="sess",values="ret").dropna()
a,lo,ov,ny=P.columns
for lab,m in (("Asia UP",P[a]>0),("Asia DOWN",P[a]<0)):
    x=P[m]
    print(f"\nafter {lab:<9} ({m.sum()} days): London avg {x[lo].mean():+.1f}bp, London moves opposite {100*(np.sign(x[lo])!=np.sign(x[a])).mean():.0f}% | overlap avg {x[ov].mean():+.1f}bp")
for lab,m in (("London UP",P[lo]>0),("London DOWN",P[lo]<0)):
    x=P[m]
    print(f"after {lab:<11} ({m.sum()} days): overlap avg {x[ov].mean():+.1f}bp, overlap moves opposite {100*(np.sign(x[ov])!=np.sign(x[lo])).mean():.0f}%")
S.to_pickle("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/sessions.pkl")
