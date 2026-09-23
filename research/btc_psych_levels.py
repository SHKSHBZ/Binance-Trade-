"""
Do BTC 1H moves respect "psychological" levels -- found from the data, not
assumed round numbers?

1. DISCOVER: a level = a price zone (0.3% wide) where BTC made >=3 confirmed
   swing turns in the trailing 90 days. Only past data is used at each point.
2. TEST: when price comes back to a level (from >=0.2% away), race +1.5 ATR in
   the bounce direction vs 1.5 ATR through the level, over the next 24 hours.
   Compare with CONTROL prices 0.6-1.5% away from any level.
3. DIGITS: distribution of swing-turn prices by their last 3 digits (mod $1000).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

P=5; WIDTH=0.003; LOOKBACK=90*24; MINCNT=3; APPROACH=0.002; RACE=1.5; HORIZON=24

def load():
    b=pd.concat([load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"),load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")])
    return b[~b.index.duplicated()].sort_index()

def atr(h,l,c,n=24):
    pc=np.concatenate([[c[0]],c[:-1]])
    return pd.Series(np.maximum(h-l,np.maximum(abs(h-pc),abs(l-pc)))).rolling(n).mean().bfill().values

def swings(h,l):
    out=[]
    for i in range(P,len(h)-P):
        if h[i]==h[i-P:i+P+1].max(): out.append((i+P,h[i]))   # usable from confirmation bar
        if l[i]==l[i-P:i+P+1].min(): out.append((i+P,l[i]))
    return out

def cluster(prices):
    prices=sorted(prices); groups=[]; cur=[prices[0]] if prices else []
    for p in prices[1:]:
        if (p-cur[0])/cur[0] <= WIDTH: cur.append(p)
        else: groups.append(cur); cur=[p]
    if cur: groups.append(cur)
    return [(float(np.mean(g)),len(g)) for g in groups if len(g)>=MINCNT]

def run(df, seed=0):
    h,l,c=df.high.values,df.low.values,df.close.values; n=len(c); A=atr(h,l,c)
    sw=swings(h,l); rng=np.random.default_rng(seed); events=[]
    for day0 in range(LOOKBACK, n-HORIZON, 24):            # rebuild levels once a day
        past=[p for (i,p) in sw if day0-LOOKBACK<=i<day0]
        if len(past)<10: continue
        real=cluster(past)
        ctrl=[]
        for lv,cnt in real:
            for _ in range(20):
                x=lv*(1+rng.choice([-1,1])*rng.uniform(0.006,0.015))
                if all(abs(x-r)/r>WIDTH for r,_ in real): ctrl.append((x,cnt)); break
        for kind,lvls in (("LEVEL",real),("CONTROL",ctrl)):
            for lv,cnt in lvls:
                for i in range(day0, min(day0+24,n-HORIZON)):
                    if not (l[i]<=lv<=h[i]): continue
                    if c[i-1]>lv*(1+APPROACH): side=1        # came from above -> support test
                    elif c[i-1]<lv*(1-APPROACH): side=-1     # from below -> resistance test
                    else: continue
                    up=lv+side*RACE*A[i]; dn=lv-side*RACE*A[i]; res=0
                    for j in range(i+1,i+1+HORIZON):
                        hb=(h[j]>=up) if side==1 else (l[j]<=up)
                        br=(l[j]<=dn) if side==1 else (h[j]>=dn)
                        if br: res=-1; break
                        if hb: res=1; break
                    events.append(dict(time=df.index[i],kind=kind,level=lv,count=cnt,side=side,res=res,
                                       cost=2*0.0001*lv/(RACE*A[i])))
                    break                                  # one event per level per day
    return pd.DataFrame(events), sw

def summarize(e,tag):
    held=(e.res==1).mean(); brk=(e.res==-1).mean(); R=(e.res-e.cost).mean()
    return f"{tag:<30} n={len(e):<5} bounce={100*held:5.1f}%  break={100*brk:5.1f}%  undecided={100*(e.res==0).mean():4.1f}%  trade expR={R:+.3f}"

if __name__=="__main__":
    df=load()
    e,sw=run(df)
    print(f"BTC 1H {df.index[0].date()} -> {df.index[-1].date()}\n")
    print("=== 1. Do discovered levels hold better than ordinary prices? ===")
    for k in ("LEVEL","CONTROL"): print("  "+summarize(e[e.kind==k],k))
    print("\n  by how many times price turned there (LEVEL only):")
    for lo,hi,lab in ((3,3,"3 turns"),(4,5,"4-5 turns"),(6,99,"6+ turns")):
        s=e[(e.kind=="LEVEL")&(e["count"]>=lo)&(e["count"]<=hi)]
        if len(s): print("    "+summarize(s,lab))
    print("\n  split by period (walk-forward check):")
    for lab,m in (("2023-2024",e.time<"2025-01-01"),("2025-2026",e.time>="2025-01-01")):
        for k in ("LEVEL","CONTROL"): print("    "+summarize(e[m&(e.kind==k)],f"{lab} {k}"))
    print("\n=== 2. Do BTC turns cluster at particular price endings? (last 3 digits, $50 buckets) ===")
    ends=np.array([p%1000 for _,p in sw]); cnt,_=np.histogram(ends,bins=20,range=(0,1000))
    exp=len(ends)/20; chi=((cnt-exp)**2/exp).sum()
    for k,v in enumerate(cnt):
        bar="#"*int(round(40*v/cnt.max()))
        print(f"   ...{k*50:03d}-{k*50+49:03d}  {v:>4}  {100*(v/exp-1):+6.1f}%  {bar}")
    print(f"   chi-square={chi:.1f} with 19 dof (p<0.05 needs >30.1)")
    print("\n=== 3. Strongest levels right now (last 90 days of data) ===")
    last=len(df); past=[p for (i,p) in sw if last-LOOKBACK<=i<last]
    for lv,k in sorted(cluster(past),key=lambda x:-x[1])[:12]:
        print(f"   ${lv:>10,.0f}   turned {k} times")
    e.to_csv("/home/user/Binance-Trade-/DATA/btc_psych_level_events.csv",index=False)
