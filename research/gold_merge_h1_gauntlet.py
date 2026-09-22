import sys; sys.path.insert(0,'.')
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
import gold_merge as gm

h1=load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16")
h4=load_ohlcv("XAUUSD_4h.csv","2020-01-01","2026-09-16")
agg=dict(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"))
d1=h1.resample("1D").agg(**agg).dropna()

def gauntlet(label,ltf,htf,rr,spread=None):
    d=gm.run("internal",sess=None,tgt="fixed",rr=rr,ltf=ltf,htf=htf,maxhold=100,spread=spread)
    R=d.R.values; D=d["dir"].values; T=pd.DatetimeIndex(d.time)
    print(f"\n{'='*84}\n{label}   n={len(R)}  win={100*(R>0).mean():.1f}%  expR={R.mean():+.3f}  P(<=0)={100*gm.boot(R):.1f}%")
    print(f"  1 LONG n={(D==1).sum():<4} {R[D==1].mean():+.3f}    SHORT n={(D==-1).sum():<4} {R[D==-1].mean():+.3f}")
    s=np.sort(R)[::-1]; tot=R.sum()
    print(f"  2 top1={100*s[0]/tot:.0f}%  top5={100*s[:5].sum()/tot:.0f}%  top10={100*s[:10].sum()/tot:.0f}%   without top10: {np.sort(R)[:-10].mean():+.3f}")
    mid=T[len(T)//2]; a=R[T<=mid]; b=R[T>mid]
    print(f"  3 TRAIN to {mid.date()} n={len(a):<4} {a.mean():+.3f} P={100*gm.boot(a):.1f}%   TEST n={len(b):<4} {b.mean():+.3f} P={100*gm.boot(b):.1f}%")
    yr=pd.Series(R,index=T).groupby(T.year).agg(['size','mean'])
    print("  4 by year: "+"  ".join(f"{y}:{r['mean']:+.2f}(n={int(r['size'])})" for y,r in yr.iterrows()))
    nl=[gm.run("internal",sess=None,tgt="fixed",rr=rr,ltf=ltf,htf=htf,maxhold=100,spread=spread,rand=k).R.mean() for k in range(6)]
    z=(R.mean()-np.mean(nl))/np.std(nl) if np.std(nl)>0 else 0
    print(f"  5 NULL mean={np.mean(nl):+.3f} sd={np.std(nl):.3f}  edge over null={R.mean()-np.mean(nl):+.3f}  z={z:+.2f}")
    print(f"    median stop ${d.risk.median():.2f}")

gauntlet("GOLD 1H entry, H4 trend, 3R, all hours", h1,h4,3.0)
gauntlet("GOLD 1H entry, Daily trend, 3R, all hours", h1,d1,3.0)
gauntlet("GOLD 1H entry, H4 trend, 2R, all hours", h1,h4,2.0)

# BTC replication, same engine, cost-matched
b1=pd.concat([load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"),load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")])
b1=b1[~b1.index.duplicated()].sort_index()
b4=b1.resample("4h").agg(**agg).dropna(); bd=b1.resample("1D").agg(**agg).dropna()
sp=b1.close.median()*0.0001
print(f"\n\n######## BTC REPLICATION (1H entry, spread ${sp:.2f}) ########")
for nm,htf in (("H4",b4),("Daily",bd)):
    for rr in (2.0,3.0):
        for mode in ("internal","external"):
            d=gm.run(mode,sess=None,tgt="fixed",rr=rr,ltf=b1,htf=htf,maxhold=100,spread=sp)
            R=d.R.values; D=d["dir"].values
            print(f"  BTC {nm:<5} {rr:.0f}R {mode:<9} n={len(R):<5} expR={R.mean():+.3f}  P(<=0)={100*gm.boot(R):5.1f}%"
                  f"  LONG {R[D==1].mean():+.3f}  SHORT {R[D==-1].mean():+.3f}")
