"""
BIG-DAY BREAKOUT (rules fixed from the gold study; BTC/ETH never used to find them):
  - Session day starts 18:00 ET. Day range so far > 1.2 x daily ATR(14, known from yesterday).
  - First 15m CLOSE beyond: previous-day high/low, Asia range (18:00-02:00 ET) high/low, or 24h high/low.
  - Only WITH the trend (EMA80 vs EMA800 on 15m). Skip NY lunch 11:00-13:00 ET.
  - Entry at the close, stop = 0.25 daily ATR, target = 2x stop. Exit after 8h if neither hit.
  - Variant 'intraday': also close everything at 16:45 ET.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def prepare(df):
    d=df.copy()
    et=d.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    d["et"]=et; d["hr"]=et.hour+et.minute/60; d["sday"]=(et+pd.Timedelta(hours=6)).normalize()
    sd=d.groupby("sday").agg(H=("high","max"),L=("low","min"),C=("close","last"))
    tr=np.maximum(sd.H-sd.L,np.maximum((sd.H-sd.C.shift()).abs(),(sd.L-sd.C.shift()).abs()))
    sd["datr"]=tr.rolling(14).mean().shift(1); sd["PDH"]=sd.H.shift(1); sd["PDL"]=sd.L.shift(1)
    d=d.join(sd[["datr","PDH","PDL"]],on="sday")
    asia=d[(d.hr>=18)|(d.hr<2)].groupby("sday").agg(AH=("high","max"),AL=("low","min"))
    d=d.join(asia,on="sday")
    d["don_hi"]=d.high.rolling(96).max().shift(1); d["don_lo"]=d.low.rolling(96).min().shift(1)
    d["ema80"]=d.close.ewm(span=80,adjust=False).mean(); d["ema800"]=d.close.ewm(span=800,adjust=False).mean()
    d["day_hi"]=d.groupby("sday").high.cummax(); d["day_lo"]=d.groupby("sday").low.cummin()
    return d.dropna(subset=["datr","ema800"])

def run(d, cost, bigday=1.2, trend=True, skip_lunch=True, intraday=False):
    h,l,c=d.high.values,d.low.values,d.close.values; hr=d.hr.values; n=len(d)
    out=[]; used=set(); last_don={1:-99,-1:-99}; busy=-1
    for i in range(1,n):
        if i<=busy: continue
        if skip_lunch and 11<=hr[i]<13: continue
        datr=d.datr.iat[i]; u=0.25*datr
        if bigday and (d.day_hi.iat[i]-d.day_lo.iat[i])<bigday*datr: continue
        cand=[("PDH",d.PDH.iat[i],1),("PDL",d.PDL.iat[i],-1),("24hH",d.don_hi.iat[i],1),("24hL",d.don_lo.iat[i],-1)]
        if 2<=hr[i]<17: cand+=[("AsiaH",d.AH.iat[i],1),("AsiaL",d.AL.iat[i],-1)]
        for typ,lvl,dr in cand:
            if np.isnan(lvl): continue
            if not ((c[i]>lvl and c[i-1]<=lvl) if dr==1 else (c[i]<lvl and c[i-1]>=lvl)): continue
            key=(d.sday.iat[i],typ)
            if typ.startswith("24h"):
                if i-last_don[dr]<16: continue
                last_don[dr]=i
            elif key in used: continue
            used.add(key)
            if trend and np.sign(d.ema80.iat[i]-d.ema800.iat[i])!=dr: continue
            e=c[i]; tp=e+dr*2*u; sl=e-dr*u; R=None
            for j in range(i+1,min(i+33,n)):
                if (dr==1 and l[j]<=sl) or (dr==-1 and h[j]>=sl): R=-1.0; break
                if (dr==1 and h[j]>=tp) or (dr==-1 and l[j]<=tp): R=2.0; break
                if intraday and 16.75<=hr[j]<18: R=dr*(c[j]-e)/u; break
            if R is None: j=min(i+32,n-1); R=dr*(c[j]-e)/u
            out.append(dict(time=d.index[i],dir=dr,typ=typ,R=R-cost(e)/u,risk=u)); busy=j; break
    return pd.DataFrame(out)

def report(lab,t,split="2025-01-01"):
    def seg(x):
        if len(x)<5: return f"n={len(x)}"
        R=x.R.values; ix=np.random.default_rng(0).integers(0,len(R),(3000,len(R)))
        yrs=max((x.time.iloc[-1]-x.time.iloc[0]).days/365.25,0.1)
        return f"n={len(R):4d} ({len(R)/yrs:3.0f}/yr) win {100*(R>0).mean():4.1f}% avgR {R.mean():+.3f} P {100*(R[ix].mean(1)<=0).mean():4.1f}%"
    y=pd.DatetimeIndex(t.time).year
    print(f"{lab:<44} ALL {seg(t)}")
    print(f"{'':<44} long {t[t.dir==1].R.mean():+.3f} short {t[t.dir==-1].R.mean():+.3f} | by year "+" ".join(f"{yy}:{t.R[y==yy].mean():+.2f}({(y==yy).sum()})" for yy in sorted(set(y))))

if __name__=="__main__":
    cat=lambda a,b:(lambda x:x[~x.index.duplicated()].sort_index())(pd.concat([load_ohlcv(a),load_ohlcv(b)]))
    mk={"GOLD (where pattern was found)":(load_ohlcv("XAUUSD_15m.csv"),lambda p:0.25),
        "BTC  (never looked at)":(cat("BTCUSDT_15m_2023_to_2025.csv","BTCUSDT_15m_Jan_to_Jul2026.csv"),lambda p:p*0.0006),
        "ETH  (never looked at)":(load_ohlcv("ETHUSDT_15m.csv"),lambda p:p*0.0006)}
    for name,(df,cost) in mk.items():
        d=prepare(df); print(f"\n===== {name}  {d.index[0].date()} -> {d.index[-1].date()} =====")
        report("BIG-DAY BREAKOUT (all rules)", run(d,cost))
        report("  same, intraday (flat 16:45 ET)", run(d,cost,intraday=True))
        report("  control: ALL days (no big-day rule)", run(d,cost,bigday=None))
