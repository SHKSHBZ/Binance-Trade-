import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
from zscore_quant_test import ind, run

g1=load_ohlcv("XAUUSD_1h.csv")
cat=lambda a,b:(lambda x:x[~x.index.duplicated()].sort_index())(pd.concat([load_ohlcv(a),load_ohlcv(b)]))
b1=cat("BTCUSDT_1h_2023_to_2025.csv","BTCUSDT_1h_Jan_to_Jul2026.csv")

def price_path(name,df):
    c=df.close; y=c.resample("YE").last(); f=c.iloc[0]
    print(f"{name}: {f:,.0f} -> {c.iloc[-1]:,.0f} ({100*(c.iloc[-1]/f-1):+.0f}%).  year ends: "+" ".join(f"{i.year}:{v:,.0f}" for i,v in y.items()))
    r=np.log(c).diff().dropna()
    up=(r>0).mean(); print(f"   hours up {100*up:.1f}%  |  avg hour {1e4*r.mean():+.2f} bp")

print("### 1. The market itself")
price_path("GOLD",g1); price_path("BTC ",b1)

def random_side(df, trades, seed):
    """same entry bars, same stop, same holding time -> random-looking trades, split by side."""
    c=df.close.values; h=df.high.values; l=df.low.values; pos={t:i for i,t in enumerate(df.index)}
    out=[]
    for _,t in trades.iterrows():
        i=pos[t.time]; sd=t.risk; n=int(t.bars)
        for d in (1,-1):
            R=None
            for j in range(i+1,min(i+1+n,len(c))):
                if (d==1 and l[j]<=c[i]-sd) or (d==-1 and h[j]>=c[i]+sd): R=-1.0; break
            if R is None: j=min(i+n,len(c)-1); R=d*(c[j]-c[i])/sd
            out.append((d,R))
    o=np.array(out); return o[o[:,0]==1,1].mean(), o[o[:,0]==-1,1].mean()

def by_regime(name, df, t):
    c=df.close; idx=df.index
    back=(c/c.shift(24*60)-1).reindex(t.time).values     # past ~60 days (tradable)
    fwd =(c.shift(-24*30)/c-1).reindex(t.time).values   # next ~30 days (hindsight, diagnosis only)
    t=t.assign(back=back,fwd=fwd)
    S=t[t.dir==-1]; L=t[t.dir==1]
    print(f"\n### {name}   longs {L.R.mean():+.3f} (n={len(L)})   shorts {S.R.mean():+.3f} (n={len(S)})")
    rl,rs=random_side(df,t,0)
    print(f"   2. same entries/stops/hold but direction forced: ALL-LONG {rl:+.3f}   ALL-SHORT {rs:+.3f}")
    print("   3. shorts split by what the market did NEXT 30 days (hindsight):")
    for lab,m in (("market fell next month",S.fwd<0),("market rose next month",S.fwd>=0)):
        print(f"        {lab:<26} n={m.sum():3d} avgR={S.R[m].mean():+.3f} win={100*(S.R[m]>0).mean():.0f}%")
    print(f"        share of shorts taken right before the market ROSE: {100*(S.fwd>=0).mean():.0f}%")
    print("   4. shorts split by past 60 days (known at entry):")
    for lab,m in (("past 60d falling",S.back<0),("past 60d rising",S.back>=0)):
        print(f"        {lab:<26} n={m.sum():3d} avgR={S.R[m].mean():+.3f}")
    print("   5. shorts by year:  "+"  ".join(f"{y}:{S.R[S.time.dt.year==y].mean():+.2f}({(S.time.dt.year==y).sum()})" for y in sorted(S.time.dt.year.unique())))
    print("      longs  by year:  "+"  ".join(f"{y}:{L.R[L.time.dt.year==y].mean():+.2f}({(L.time.dt.year==y).sum()})" for y in sorted(L.time.dt.year.unique())))
    ex=S.assign(stopped=S.R<=-0.99)
    print(f"   6. shorts stopped out: {100*ex.stopped.mean():.0f}%   longs stopped out: {100*(L.R<=-0.99).mean():.0f}%")

x=ind(g1); by_regime("GOLD 1h mean-reversion", x, run(x,"gold",cost=0.25))
x=ind(g1); by_regime("GOLD 1h momentum logic", x, run(x,"btc",cost=0.25))
x=ind(b1); by_regime("BTC 1h momentum", x, run(x,"btc",cost_frac=0.0006))

print("\n### 7. How falls behave vs rallies (gold 1h): after a sharp 4h move of >2x normal, what happens next 24h?")
c=g1.close; r4=np.log(c).diff(4); sd=r4.rolling(24*20).std(); nxt=np.log(c).shift(-24)-np.log(c)
for lab,m in (("after a sharp DROP",r4<-2*sd),("after a sharp RALLY",r4>2*sd)):
    v=nxt[m].dropna()
    print(f"   {lab:<20} n={len(v):4d}  next 24h: avg {1e4*v.mean():+.1f} bp, price higher {100*(v>0).mean():.0f}% of the time")
print("   by year (next 24h avg bp after DROP / after RALLY):")
for y in sorted(set(c.index.year)):
    yy=c.index.year==y
    print(f"     {y}: drop {1e4*nxt[(r4<-2*sd)&yy].mean():+6.1f}   rally {1e4*nxt[(r4>2*sd)&yy].mean():+6.1f}")
