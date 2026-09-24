import _paths, numpy as np, pandas as pd
from own_search_nyet import d, run
T=lambda hh,mm=0: hh*60+mm
t=run(d,T(9),T(10),T(10),T(15),rr=2.0,flat=T(16)).reset_index(drop=True)
# R already net of $0.25 cost; risk = stop distance in $
def equity(tr, start=5000, risk_pct=0.02):
    eq=start; rows=[]
    for _,r in tr.iterrows():
        lots=np.floor(eq*risk_pct/(r.risk*100)*100)/100      # 1 lot = 100 oz
        lots=max(lots,0.01)
        pnl=lots*100*r.risk*r.R; eq+=pnl
        rows.append((r.time,lots,pnl,eq))
    return pd.DataFrame(rows,columns=["time","lots","pnl","equity"])

for rp in (0.01,0.02,0.03):
    e=equity(t,5000,rp); e["yr"]=e.time.dt.year
    peak=e["equity"].cummax(); dd=((e["equity"]-peak)/peak).min()
    by=e.groupby("yr")["equity"].last()
    print(f"risk {int(rp*100)}%: $5,000 (Jun 2022) -> ${e['equity'].iloc[-1]:,.0f} (Sep 2026)  worst drop {100*dd:.0f}%  "
          + " ".join(f"{y}:${v:,.0f}" for y,v in by.items()))
# one year forward, from reshuffled real trades (~125 trades/yr)
R=t.R.values; rng=np.random.default_rng(1)
for rp in (0.01,0.02,0.03):
    fin=[]
    for _ in range(5000):
        eq=5000
        for r in rng.choice(R,125): eq*=1+rp*r
        fin.append(eq)
    fin=np.array(fin)
    print(f"1-year outlook at {int(rp*100)}% risk: bad 10%: ${np.percentile(fin,10):,.0f}  typical: ${np.median(fin):,.0f}  good 10%: ${np.percentile(fin,90):,.0f}  chance of loss: {100*(fin<5000).mean():.0f}%")
e=equity(t[t.time>="2026"],5000,0.02); print(f"2026 only, 2% risk: $5,000 -> ${e['equity'].iloc[-1]:,.0f}, typical lots {e.lots.median()}")
