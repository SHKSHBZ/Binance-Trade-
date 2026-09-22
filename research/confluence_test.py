"""
Which strategies fire the SAME trade, and does confluence perform better?

A trade is "the same" if another strategy opened in the SAME DIRECTION within
a time window and at a similar price. Then the question that matters:
do trades confirmed by 2+ strategies beat solo trades?

That is the mechanical version of what a discretionary trader means by
"confluence", and it has never been tested in this project.
"""
import _paths, numpy as np, pandas as pd
from itertools import combinations

d=pd.read_csv("/home/user/Binance-Trade-/DATA/all_strategy_trades.csv",parse_dates=["time"])
d=d.sort_values("time").reset_index(drop=True)

def find_overlaps(d, hours=4, price_tol=0.003):
    """Tag each trade with how many OTHER strategies fired the same way nearby."""
    t=d.time.values.astype("datetime64[s]").astype(np.int64)
    px=d.entry.values; dr=d["dir"].values; st=d.strategy.values
    win=hours*3600
    partners=[set() for _ in range(len(d))]
    j0=0
    for i in range(len(d)):
        while t[j0] < t[i]-win: j0+=1
        j=j0
        while j<len(d) and t[j]<=t[i]+win:
            if j!=i and st[j]!=st[i] and dr[j]==dr[i] \
               and abs(px[j]-px[i])/px[i] <= price_tol:
                partners[i].add(st[j])
            j+=1
    d=d.copy()
    d["n_confirm"]=[len(p) for p in partners]
    d["partners"]=[",".join(sorted(p)) for p in partners]
    return d

for hrs,tol in ((4,0.003),(12,0.005)):
    dd=find_overlaps(d,hrs,tol)
    print(f"\n{'='*80}\nMATCH WINDOW: +/-{hrs}h, price within {100*tol:.1f}%\n{'='*80}")
    print("=== 1. DOES CONFLUENCE PAY? ===")
    print(f"{'confirmations':>14}{'n':>7}{'win%':>8}{'expR':>9}{'totR':>9}")
    for k in sorted(dd.n_confirm.unique()):
        g=dd[dd.n_confirm==k]
        lab=f"{k} other" + ("" if k==1 else "s")
        if k==0: lab="SOLO (none)"
        print(f"{lab:>14}{len(g):>7}{100*(g.outcome=='WIN').mean():>8.1f}{g.R.mean():>+9.3f}{g.R.sum():>+9.1f}")
    solo=dd[dd.n_confirm==0].R; conf=dd[dd.n_confirm>=1].R
    print(f"  SOLO {solo.mean():+.3f} (n={len(solo)})   vs   CONFIRMED {conf.mean():+.3f} (n={len(conf)})"
          f"   difference {conf.mean()-solo.mean():+.3f}")
    if hrs==4:
        print("\n=== 2. WHICH PAIRS OVERLAP MOST? ===")
        cnt={}
        for _,r in dd[dd.n_confirm>0].iterrows():
            for p in r.partners.split(","):
                key=tuple(sorted([r.strategy,p])); cnt[key]=cnt.get(key,0)+1
        rows=sorted(cnt.items(),key=lambda x:-x[1])[:12]
        print(f"{'pair':<44}{'shared trades':>14}")
        for (a,b),c in rows: print(f"{a+' + '+b:<44}{c//2:>14}")
        print("\n=== 3. HOW OFTEN IS A TRADE SHARED AT ALL? ===")
        print(dd.n_confirm.value_counts().sort_index().to_string())
        print(f"\n  shared by >=1 other strategy: {100*(dd.n_confirm>0).mean():.1f}% of all trades")
        dd.to_csv("/home/user/Binance-Trade-/DATA/trades_with_confluence.csv",index=False)
