"""
The trader's stated method, mechanical (rules fixed before testing older data):
  LEVELS : yesterday's high (resistance) and low (support), wicks included, UTC days (Exness server time).
  NEAR   : a 15m candle comes within 0.25 daily ATR of the level from inside the range.
  HOLDS  : no 15m CLOSE beyond the level today so far (wicks through are allowed).
  SPEED  : price came into the level fast: last 4h moved >= 0.14 daily ATR toward it.
  CONFIRM: that candle closes back away from the level (bullish at support / bearish at resistance).
  ENTRY  : at the confirmation close. BUY at support, SELL at resistance.
  STOP   : beyond the level and the recent extreme + 0.05 dATR; skip if <0.1 or >0.6 dATR.
  TARGET : 2R (variants: trail 1.5R; opposite side of yesterday's range).
  One trade at a time, max one trade per level per day, 02:00-16:00 New York.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
from my_pattern_strategy import rep

def prep(df):
    g=df.copy()
    et=g.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None); g["hr"]=et.hour+et.minute/60
    g["uday"]=g.index.normalize()
    dd=g.groupby("uday").agg(H=("high","max"),L=("low","min"),C=("close","last"))
    dd=dd[pd.DatetimeIndex(dd.index).dayofweek<5]
    tr=np.maximum(dd.H-dd.L,np.maximum((dd.H-dd.C.shift()).abs(),(dd.L-dd.C.shift()).abs()))
    dd["datr"]=tr.rolling(14).mean().shift(1); dd["PDH"]=dd.H.shift(1); dd["PDL"]=dd.L.shift(1)
    g=g.join(dd[["datr","PDH","PDL"]],on="uday")
    c=g.close
    tr15=np.maximum(g.high-g.low,np.maximum((g.high-c.shift()).abs(),(g.low-c.shift()).abs()))
    g["atr15"]=tr15.rolling(14).mean(); g["atr5d"]=tr15.rolling(480).mean()
    g["spike_today"]=(tr15>3*g.atr5d).astype(int).groupby(g.uday).cummax()
    g["ema80"]=c.ewm(span=80,adjust=False).mean(); g["ema800"]=c.ewm(span=800,adjust=False).mean()
    g["closed_above_pdh"]=(c>g.PDH).astype(int).groupby(g.uday).cummax()
    g["closed_below_pdl"]=(c<g.PDL).astype(int).groupby(g.uday).cummax()
    return g.dropna(subset=["datr","PDH","atr5d"])

def run(g, cost, speed=0.14, confirm=True, near=0.25, exitm="2R", vol=False, trend=False, hold=True):
    h,l,c,o=g.high.values,g.low.values,g.close.values,g.open.values; n=len(c)
    datr=g.datr.values; hr=g.hr.values; PDH=g.PDH.values; PDL=g.PDL.values; day=g.uday.values
    ca=g.closed_above_pdh.values; cb=g.closed_below_pdl.values
    V=(g.atr15.values>1.2*g.atr5d.values)|(g.spike_today.values==1); TR=np.sign(g.ema80.values-g.ema800.values)
    out=[]; used=set(); busy=-1
    for i in range(17,n-1):
        if i<=busy or not (2<=hr[i]<16): continue
        if vol and not V[i]: continue
        for d,lvl,broken in ((1,PDL[i],cb[i-1]),(-1,PDH[i],ca[i-1])):
            if (day[i],d) in used: continue
            if hold and broken: continue
            ext=l[i] if d==1 else h[i]
            if not (-d*(ext-lvl) >= -near*datr[i]): continue          # came within `near` of the level (or through it)
            if -d*(c[i]-lvl)>0: continue                               # this candle closed beyond the level -> not holding
            if speed is not None and -d*(c[i-1]-c[i-17]) < speed*datr[i] and -d*(ext-c[i-16]) < speed*datr[i]: continue
            if confirm and not (d*(c[i]-o[i])>0): continue
            if trend and TR[i]!=d: continue
            used.add((day[i],d))
            recent=l[i-3:i+1].min() if d==1 else h[i-3:i+1].max()
            stop=(min(recent,lvl) if d==1 else max(recent,lvl))-d*0.05*datr[i]
            e=c[i]; risk=d*(e-stop)
            if not (0.1*datr[i]<=risk<=0.6*datr[i]): continue
            tgt=None
            if exitm=="range": tgt=PDH[i] if d==1 else PDL[i]
            best=e; st=stop; R=None
            for j in range(i+1,min(i+501,n)):
                if (d==1 and l[j]<=st) or (d==-1 and h[j]>=st): R=d*(st-e)/risk; break
                best=max(best,h[j]) if d==1 else min(best,l[j]); gain=d*(best-e)/risk
                if exitm=="2R" and gain>=2: R=2.0; break
                if exitm=="range" and ((d==1 and h[j]>=tgt) or (d==-1 and l[j]<=tgt)): R=d*(tgt-e)/risk; break
                if exitm=="trail" and gain>=1.5:
                    ts=best-d*1.5*risk; st=max(st,ts) if d==1 else min(st,ts)
            if R is None: j=min(i+500,n-1); R=d*(c[j]-e)/risk
            out.append(dict(time=g.index[i],dir=d,R=R-cost/risk,risk=risk)); busy=j; break
    return pd.DataFrame(out)

if __name__=="__main__":
    g=prep(load_ohlcv("XAUUSD_15m.csv"))
    PRE=("2022-06-24","2025-05-07"); USER=("2025-05-08","2026-09-16")
    T={"YOUR METHOD: PDH/PDL + fast approach + confirm, 2R":run(g,0.25),
       "  same, trailing 1.5R":run(g,0.25,exitm="trail"),
       "  same, target = other side of yesterday's range":run(g,0.25,exitm="range"),
       "  same + volatile day":run(g,0.25,vol=True),
       "  same + with trend":run(g,0.25,trend=True),
       "  WITHOUT speed check":run(g,0.25,speed=None),
       "  WITHOUT confirmation candle":run(g,0.25,confirm=False),
       "  SLOW approach only (speed < 0.14)":None}
    # slow-approach contrast
    full=run(g,0.25,speed=None); fast=T["YOUR METHOD: PDH/PDL + fast approach + confirm, 2R"]
    T["  SLOW approach only (speed < 0.14)"]=full[~full.time.isin(fast.time)]
    for per,(a,b) in (("CLEAN TEST: before your first trade (2022-06 .. 2025-05)",PRE),("YOUR TRADING PERIOD (2025-05 .. 2026-09)",USER)):
        print(f"\n=== {per} ===")
        for k,t in T.items(): rep(k,t,a,b)
