"""
The trader's own method, made mechanical (rules fixed before testing older data):
  LEVELS  : 4H swing highs (resistance) / swing lows (support), 2 bars each side, from the last 30 days,
            usable only after confirmed, and only while unbroken (price never traded >0.1 dATR beyond).
  TOUCH   : a 15m candle reaches the level (within 0.1 daily ATR) WITHOUT poking more than 0.02 dATR through,
            and closes back away from it (bearish candle at resistance / bullish at support).
  ENTRY   : that candle's close. SELL at resistance, BUY at support.
  STOP    : beyond the level: max(level, candle extreme) + 0.05 dATR ; skip if <0.1 or >0.5 dATR.
  TARGET  : 2R.  (variant: trail 1.5R once +1.5R)
  FILTER  : volatile day (15m ATR >1.2x 5-day avg or a >3x spike earlier today). 02:00-16:00 New York.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
from my_pattern_strategy import prep, rep

def levels_4h(g):
    b=g.resample("4h").agg(dict(high="max",low="min")).dropna(); H,Lw=b.high.values,b.low.values; out=[]
    for i in range(2,len(b)-2):
        known=b.index[i+2]+pd.Timedelta(hours=4)
        if H[i]==H[i-2:i+3].max(): out.append((known,b.index[i],H[i],-1))
        if Lw[i]==Lw[i-2:i+3].min(): out.append((known,b.index[i],Lw[i],1))
    return pd.DataFrame(out,columns=["known","t","price","side"]).sort_values("known").reset_index(drop=True)

def run(g, cost, use_vol=True, allow_poke=False, exitm="2R", tf_levels=None, trend=None):
    lv=tf_levels if tf_levels is not None else levels_4h(g)
    h,l,c,o=g.high.values,g.low.values,g.close.values,g.open.values; n=len(c)
    datr=g.datr.values; hr=g.hr.values; idx=g.index
    vol=(g.atr15.values>1.2*g.atr5d.values)|(g.spike_today.values==1)
    TR=np.sign(g.ema80.values-g.ema800.values) if trend=='ema' else (np.sign(g.close.values-g.close.shift(96*5).values) if trend=='5day' else None)
    kn=lv.known.values; lt=lv.t.values; lp=lv.price.values; ls=lv.side.values
    broken=np.zeros(len(lv),bool); nxt=0; active=[]
    out=[]; i=1; busy=-1
    while i<n-1:
        while nxt<len(lv) and kn[nxt]<=idx[i]: active.append(nxt); nxt+=1
        # drop levels older than 30 days or broken
        cut=idx[i]-pd.Timedelta(days=30); keep=[]
        for k in active:
            if broken[k] or lt[k]<cut: continue
            if (ls[k]==-1 and h[i-1]>lp[k]+0.1*datr[i]) or (ls[k]==1 and l[i-1]<lp[k]-0.1*datr[i]): broken[k]=True; continue
            keep.append(k)
        active=keep
        if i<=busy or not (2<=hr[i]<16) or (use_vol and not vol[i]): i+=1; continue
        tol=0.1*datr[i]; poke=(10 if allow_poke else 0.02)*datr[i]; took=False
        for k in active:
            lvl=lp[k]
            if ls[k]==-1:   # resistance -> SELL
                if lvl-tol<=h[i]<=lvl+poke and c[i]<o[i] and c[i]<lvl:
                    d=-1; stop=max(lvl,h[i])+0.05*datr[i]
                else: continue
            else:           # support -> BUY
                if lvl-poke<=l[i]<=lvl+tol and c[i]>o[i] and c[i]>lvl:
                    d=1; stop=min(lvl,l[i])-0.05*datr[i]
                else: continue
            if TR is not None and TR[i]!=d: continue
            e=c[i]; risk=d*(e-stop)
            if not (0.1*datr[i]<=risk<=0.5*datr[i]): continue
            best=e; st=stop; R=None
            for j in range(i+1,min(i+501,n)):
                if (d==1 and l[j]<=st) or (d==-1 and h[j]>=st): R=d*(st-e)/risk; break
                best=max(best,h[j]) if d==1 else min(best,l[j]); gain=d*(best-e)/risk
                if exitm=="2R" and gain>=2: R=2.0; break
                if exitm=="trail" and gain>=1.5:
                    ts=best-d*1.5*risk; st=max(st,ts) if d==1 else min(st,ts)
            if R is None: j=min(i+500,n-1); R=d*(c[j]-e)/risk
            out.append(dict(time=idx[i],dir=d,R=R-cost/risk,risk=risk)); busy=j; took=True; break
        i+=1
    return pd.DataFrame(out)

if __name__=="__main__":
    g=prep(load_ohlcv("XAUUSD_15m.csv")); lv=levels_4h(g)
    PRE=("2022-06-24","2025-05-07"); USER=("2025-05-08","2026-09-16")
    T={"S/R bounce, no trend rule":run(g,0.25,tf_levels=lv),
       "S/R bounce WITH TREND (EMA80/800), volatile day":run(g,0.25,tf_levels=lv,trend="ema"),
       "S/R bounce WITH TREND, any day":run(g,0.25,tf_levels=lv,trend="ema",use_vol=False),
       "S/R bounce WITH TREND, trailing 1.5R":run(g,0.25,tf_levels=lv,trend="ema",exitm="trail"),
       "S/R bounce with 5-day price direction as trend":run(g,0.25,tf_levels=lv,trend="5day")}
    for per,(a,b) in (("CLEAN TEST: before your first trade (2022-06 .. 2025-05)",PRE),("YOUR TRADING PERIOD (2025-05 .. 2026-09)",USER)):
        print(f"\n=== {per} ===")
        for k,t in T.items(): rep(k,t,a,b)
