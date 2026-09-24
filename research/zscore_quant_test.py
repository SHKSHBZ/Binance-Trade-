"""
Trader-supplied 'quant' strategies, implemented exactly as written:
 GOLD mean reversion: atr_slope < 0.5*ATR; BUY z<-2.2 & close>SMA200; SELL z>2.2 & close<SMA200;
                      SL = 3 ATR; exit when z crosses 0.
 BTC momentum:        atr_slope > 0; BUY z>2.2 & close>SMA200; SELL z<-2.2 & close<SMA200;
                      SL = 4 ATR; exit when z crosses 0.
 z = (close - SMA50)/STD50, ATR14 (simple mean of TR), atr_slope = ATR - ATR[5].
Entry at signal-bar close; stop checked intrabar from the next bar; z-exit at bar close.
No take-profit exists in the spec. One position at a time.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def ind(df, window=50):
    df=df.copy()
    df["m"]=df.close.rolling(window).mean(); df["s"]=df.close.rolling(window).std()
    df["z"]=(df.close-df.m)/df.s
    tr=pd.concat([df.high-df.low,(df.high-df.close.shift()).abs(),(df.low-df.close.shift()).abs()],axis=1).max(axis=1)
    df["atr"]=tr.rolling(14).mean(); df["sma200"]=df.close.rolling(200).mean()
    df["slope"]=df.atr-df.atr.shift(5)
    return df.dropna()

def run(df, kind, cost=0.25, cost_frac=None):
    h,l,c=df.high.values,df.low.values,df.close.values
    z=df.z.values; a=df.atr.values; sm=df.sma200.values; sl=df.slope.values; n=len(c)
    out=[]; i=0
    while i<n-1:
        d=0
        if kind=="gold" and sl[i]<0.5*a[i]:
            if z[i]>2.2 and c[i]<sm[i]: d=-1; k=3.0
            elif z[i]<-2.2 and c[i]>sm[i]: d=1; k=3.0
        if kind=="btc" and sl[i]>0:
            if z[i]>2.2 and c[i]>sm[i]: d=1; k=4.0
            elif z[i]<-2.2 and c[i]<sm[i]: d=-1; k=4.0
        if d==0: i+=1; continue
        e=c[i]; sd=k*a[i]; stop=e-d*sd; R=None
        for j in range(i+1,n):
            if (d==1 and l[j]<=stop) or (d==-1 and h[j]>=stop): R=-1.0; break
            if (d==1 and ((kind=="gold" and z[j]>=0) or (kind=="btc" and z[j]<=0))) or \
               (d==-1 and ((kind=="gold" and z[j]<=0) or (kind=="btc" and z[j]>=0))):
                R=d*(c[j]-e)/sd; break
        if R is None: j=n-1; R=d*(c[j]-e)/sd
        sp=cost if cost_frac is None else e*cost_frac
        out.append(dict(time=df.index[i],dir=d,R=R-sp/sd,bars=j-i,risk=sd)); i=j+1
    return pd.DataFrame(out)

def report(name,t,yrs):
    R=t.R.values; D=t.dir.values; y=pd.DatetimeIndex(t.time).year
    ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
    eq=5000.0
    for r in R: eq*=1+0.02*r
    print(f"{name:<34} n={len(R):4d} ({len(R)/yrs:.0f}/yr) win={100*(R>0).mean():4.1f}% avgR={R.mean():+.3f} P={100*(R[ix].mean(1)<=0).mean():5.1f}% "
          f"long={R[D==1].mean():+.3f}({(D==1).sum()}) short={R[D==-1].mean() if (D==-1).any() else np.nan:+.3f}({(D==-1).sum()}) "
          f"hold~{np.median(t.bars):.0f} bars  $5k@2% -> ${eq:,.0f}")
    print(f"{'':<34} by year: "+" ".join(f"{yy}:{R[y==yy].mean():+.2f}({(y==yy).sum()})" for yy in sorted(set(y))))

if __name__=="__main__":
    g15=load_ohlcv("XAUUSD_15m.csv"); g1=load_ohlcv("XAUUSD_1h.csv"); g4=load_ohlcv("XAUUSD_4h.csv")
    cat=lambda a,b:(lambda x:x[~x.index.duplicated()].sort_index())(pd.concat([load_ohlcv(a),load_ohlcv(b)]))
    b15=cat("BTCUSDT_15m_2023_to_2025.csv","BTCUSDT_15m_Jan_to_Jul2026.csv")
    b1=cat("BTCUSDT_1h_2023_to_2025.csv","BTCUSDT_1h_Jan_to_Jul2026.csv")
    yrs=lambda d:(d.index[-1]-d.index[0]).days/365.25
    print("=== GOLD mean reversion (as written) ===")
    for nm,dd in (("gold 15m",g15),("gold 1h",g1),("gold 4h",g4)):
        x=ind(dd); report(nm,run(x,"gold",cost=0.25),yrs(x))
    print("=== BTC momentum (as written) ===")
    for nm,dd in (("btc 15m",b15),("btc 1h",b1)):
        x=ind(dd); report(nm,run(x,"btc",cost_frac=0.0006),yrs(x))
    print("=== cross-check: each logic on the OTHER market ===")
    for nm,dd in (("gold 1h, BTC momentum logic",g1),):
        x=ind(dd); report(nm,run(x,"btc",cost=0.25),yrs(x))
    for nm,dd in (("btc 1h, gold mean-rev logic",b1),):
        x=ind(dd); report(nm,run(x,"gold",cost_frac=0.0006),yrs(x))
    x=ind(g1); print("gold 1h: share of bars passing 'volatility contracting' filter:", f"{100*(x.slope<0.5*x.atr).mean():.0f}%")
