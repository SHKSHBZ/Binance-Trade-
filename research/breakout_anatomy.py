"""
Anatomy of gold breakouts / breakdowns (15m). What is different about real ones vs fake-outs?
Levels: previous-day high/low (PDH/PDL), Asia range high/low (18:00-02:00 ET), 24h high/low.
Event: FIRST 15m close beyond the level. Unit u = 0.25 x yesterday's daily ATR.
Outcome: REAL if price travels +2u in the break direction before -1u against (from the break close),
within 8 hours. Breakeven for a 2:1 trade = 33.3% real. All features are known at the break close.
BUILD 2022-06..2024-12 / TEST 2025-01..2026-09.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

d=load_ohlcv("XAUUSD_15m.csv")
et=d.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
d["et"]=et; d["hr"]=et.hour+et.minute/60
d["sday"]=(et+pd.Timedelta(hours=6)).normalize()          # gold session day starts 18:00 ET
h,l,c,o,v=d.high.values,d.low.values,d.close.values,d.open.values,d.volume.values; n=len(d)

# daily ATR per session day, known from yesterday
sd=d.groupby("sday").agg(H=("high","max"),L=("low","min"),C=("close","last"))
tr=np.maximum(sd.H-sd.L,np.maximum((sd.H-sd.C.shift()).abs(),(sd.L-sd.C.shift()).abs()))
sd["datr"]=tr.rolling(14).mean().shift(1); sd["PDH"]=sd.H.shift(1); sd["PDL"]=sd.L.shift(1)
sd["pd_dir"]=np.sign(sd.C.shift(1)-sd.C.shift(2))
d=d.join(sd[["datr","PDH","PDL","pd_dir"]],on="sday")
tr15=np.maximum(h-l,np.maximum(abs(h-np.roll(c,1)),abs(l-np.roll(c,1))))
d["atr15"]=pd.Series(tr15).rolling(14).mean().values
d["sqz"]=(pd.Series(tr15).rolling(16).mean()/pd.Series(tr15).rolling(480).mean()).values   # last 4h vs last 5 days
d["volr"]=(pd.Series(v).shift(0)/pd.Series(v).rolling(96).mean().shift(1)).values
d["ema80"]=d.close.ewm(span=80,adjust=False).mean(); d["ema800"]=d.close.ewm(span=800,adjust=False).mean()
dlt=d.close.diff(); up=dlt.clip(lower=0).ewm(alpha=1/14).mean(); dn=(-dlt.clip(upper=0)).ewm(alpha=1/14).mean()
d["rsi"]=100-100/(1+up/dn)
d["don_hi"]=d.high.rolling(96).max().shift(1); d["don_lo"]=d.low.rolling(96).min().shift(1)
# asia range per session day (18:00-02:00 ET)
asia=d[(d.hr>=18)|(d.hr<2)].groupby("sday").agg(AH=("high","max"),AL=("low","min"))
d=d.join(asia,on="sday")
d["day_hi"]=d.groupby("sday").high.cummax().shift(1); d["day_lo"]=d.groupby("sday").low.cummin().shift(1)
d["day_open"]=d.groupby("sday").open.transform("first")
d=d.dropna(subset=["datr","atr15","sqz","volr","ema800"])
h,l,c,o=d.high.values,d.low.values,d.close.values,d.open.values; n=len(d)

def outcome(i,dr,u):
    """returns R: +2 target, -1 stop, else marked at 8h."""
    e=c[i]; tp=e+dr*2*u; sl=e-dr*u
    for j in range(i+1,min(i+33,n)):
        if (dr==1 and l[j]<=sl) or (dr==-1 and h[j]>=sl): return -1.0
        if (dr==1 and h[j]>=tp) or (dr==-1 and l[j]<=tp): return 2.0
    j=min(i+32,n-1); return dr*(c[j]-e)/u

def touches(i,lvl,dr,u,look=192):
    a=max(0,i-look); x=h[a:i] if dr==1 else l[a:i]
    return int(np.sum(np.abs(x-lvl)<=0.3*u))

ev=[]; used=set(); last_don={1:-99,-1:-99}
cols=d.columns
for i in range(1,n):
    r=d.iloc[i] if False else None
for i in range(1,n):
    sday=d.sday.iat[i]; hr=d.hr.iat[i]; u=0.25*d.datr.iat[i]
    cand=[("PDH",d.PDH.iat[i],1),("PDL",d.PDL.iat[i],-1)]
    if 2<=hr<17: cand+=[("AsiaH",d.AH.iat[i],1),("AsiaL",d.AL.iat[i],-1)]
    cand+=[("24hH",d.don_hi.iat[i],1),("24hL",d.don_lo.iat[i],-1)]
    for typ,lvl,dr in cand:
        if np.isnan(lvl): continue
        crossed=(c[i]>lvl and c[i-1]<=lvl) if dr==1 else (c[i]<lvl and c[i-1]>=lvl)
        if not crossed: continue
        key=(sday,typ)
        if typ.startswith("24h"):
            if i-last_don[dr]<16: continue
            last_don[dr]=i
        elif key in used: continue
        used.add(key)
        body=abs(c[i]-o[i]); rng=h[i]-l[i]
        ev.append(dict(time=d.index[i],typ=typ,dir=dr,Rg=outcome(i,dr,u),
            hr=hr, dow=d.et.iat[i].dayofweek,
            trend_with=int(np.sign(d.ema80.iat[i]-d.ema800.iat[i])==dr),
            body_atr=body/d.atr15.iat[i], close_loc=((c[i]-l[i])/rng if dr==1 else (h[i]-c[i])/rng) if rng>0 else 0.5,
            volr=d.volr.iat[i], sqz=d.sqz.iat[i], rsi=d.rsi.iat[i],
            beyond_u=dr*(c[i]-lvl)/u, touches=touches(i,lvl,dr,u),
            day_used=(max(d.day_hi.iat[i],h[i])-min(d.day_lo.iat[i],l[i]))/d.datr.iat[i] if not np.isnan(d.day_hi.iat[i]) else np.nan,
            vs_open=dr*np.sign(c[i]-d.day_open.iat[i]), pd_with=int(d.pd_dir.iat[i]==dr), cost_R=0.25/u))
E=pd.DataFrame(ev); E.to_csv("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/breakouts.csv",index=False)
E["period"]=np.where(E.time<"2025-01-01","BUILD","TEST")
E["R"]=E.Rg-E.cost_R; E["real"]=(E.Rg>=2).astype(int)
print(f"events: {len(E)}  BUILD {len((E.period=='BUILD').nonzero()[0]) if False else (E.period=='BUILD').sum()}  TEST {(E.period=='TEST').sum()}")
rng=np.random.default_rng(0); base=[]
for i in rng.choice(np.arange(100,n-40),6000,replace=False):
    u=0.25*d.datr.iat[i]; dr=rng.choice([1,-1]); base.append((d.index[i],outcome(i,dr,u)-0.25/u))
B=pd.DataFrame(base,columns=["time","R"])
print(f"RANDOM entry baseline: BUILD avg R {B[B.time<'2025'].R.mean():+.3f}  TEST {B[B.time>='2025'].R.mean():+.3f}  (target hit {100*(B.R>1.5).mean():.1f}%)")
print(f"ALL BREAKOUTS: BUILD target hit {100*E[E.period=='BUILD'].real.mean():.1f}% avg R {E[E.period=='BUILD'].R.mean():+.3f} | TEST {100*E[E.period=='TEST'].real.mean():.1f}% avg R {E[E.period=='TEST'].R.mean():+.3f}\n")

def table(name, key, order=None):
    g=E.groupby([key,"period"]).agg(n=("real","size"),real=("real","mean"),R=("R","mean")).unstack("period")
    if order is not None: g=g.reindex(order)
    print(f"--- {name} ---")
    for k,row in g.iterrows():
        try:
            print(f"  {str(k):<26} BUILD n={int(row[('n','BUILD')]):4d} real {100*row[('real','BUILD')]:4.1f}% R {row[('R','BUILD')]:+.2f} | TEST n={int(row[('n','TEST')]):4d} real {100*row[('real','TEST')]:4.1f}% R {row[('R','TEST')]:+.2f}")
        except Exception: pass

E["session"]=pd.cut(E.hr,[-0.1,2,8,8.5,9.5,11,13,17,18,24.1],labels=["Asia late 00-02","London 02-08","pre-news 08-08:30","NEWS 08:30-09:30","NY open 09:30-11","NY midday 11-13","NY pm 13-17","break 17-18","Asia 18-24"])
table("level type","typ")
table("direction (+1 breakout / -1 breakdown)","dir")
table("time of day (ET)","session")
table("with the EMA80/800 trend?","trend_with")
E["body_b"]=pd.qcut(E.body_atr,4,labels=["small candle","medium","big","very big candle"]); table("breakout candle size vs normal","body_b")
E["close_b"]=pd.cut(E.close_loc,[-0.01,0.5,0.8,1.01],labels=["closes weak (<50%)","mid","closes at the extreme"]); table("where the candle closes","close_b")
E["vol_b"]=pd.qcut(E.volr,4,labels=["low volume","normal","high","very high volume"]); table("volume vs last 24h","vol_b")
E["sq_b"]=pd.qcut(E.sqz,4,labels=["tight (squeezed) before","fairly tight","fairly wide","wide/volatile before"]); table("squeeze before the break","sq_b")
E["t_b"]=pd.cut(E.touches,[-1,0,2,5,999],labels=["0 prior touches","1-2 touches","3-5 touches","6+ touches"]); table("prior touches of the level (48h)","t_b")
E["used_b"]=pd.cut(E.day_used,[-1,0.5,0.8,1.2,99],labels=["day range <50% ATR","50-80%","80-120%","day already >120% ATR"]); table("how much of daily ATR already used","used_b")
E["rsi_b"]=pd.cut(E.rsi*np.where(E.dir==1,1,-1)+np.where(E.dir==1,0,100),[0,50,60,70,101],labels=["RSI weak","RSI 50-60","RSI 60-70","RSI >70 (stretched)"]); table("RSI in break direction","rsi_b")
table("with the day's direction (vs day open)","vs_open")
table("with yesterday's direction","pd_with")
E["dow_n"]=E.dow.map({0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",6:"Sun"}); table("day of week","dow_n",["Mon","Tue","Wed","Thu","Fri","Sun"])
E.to_pickle("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/breakouts.pkl")
