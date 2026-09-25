"""Each of the trader's 82 trades checked against the trader's own stated rules, and which level was really used."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
L=pd.read_csv("../DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
g=load_ohlcv("XAUUSD_15m.csv")
dd=g.resample("1D").agg(dict(open="first",high="max",low="min",close="last")).dropna(); dd=dd[dd.index.dayofweek<5]
tr=np.maximum(dd.high-dd.low,np.maximum((dd.high-dd.close.shift()).abs(),(dd.low-dd.close.shift()).abs())); dd["atr"]=tr.rolling(14).mean()
wk=g.resample("W-FRI").agg(dict(high="max",low="min")).dropna()
h4=g.resample("4h").agg(dict(high="max",low="min")).dropna()
rows=[]
for _,t in L.iterrows():
    d=1 if t.dir=="LONG" else -1; e=t.entry; day=t.date.normalize()
    prevs=dd[dd.index<day]; p1=prevs.iloc[-1]; p2=prevs.iloc[-2]; datr=p1.atr
    pw=wk[wk.index<day-pd.Timedelta(days=day.dayofweek)].iloc[-1] if True else None
    today=g.loc[day:t.date-pd.Timedelta(minutes=15)]
    last4=g.loc[t.date-pd.Timedelta(hours=4):t.date-pd.Timedelta(minutes=15)]
    probe=(last4.low.min() if d==1 else last4.high.max())
    lastbar=g.loc[:t.date-pd.Timedelta(minutes=15)].iloc[-1]
    # candidate levels on the correct side (support for buys, resistance for sells)
    cands={}
    cands["yesterday's "+("low" if d==1 else "high")]=p1.low if d==1 else p1.high
    cands["2-days-ago "+("low" if d==1 else "high")]=p2.low if d==1 else p2.high
    cands["last week's "+("low" if d==1 else "high")]=pw.low if d==1 else pw.high
    if len(today)>16:
        early=today.iloc[:-16]
        if len(early): cands["today's earlier "+("low" if d==1 else "high")]=early.low.min() if d==1 else early.high.max()
    sw=h4.loc[t.date-pd.Timedelta(days=10):t.date-pd.Timedelta(hours=12)]
    if len(sw): 
        v=(sw.low.values if d==1 else sw.high.values); k=np.abs(v-probe).argmin(); cands["4H swing "+("low" if d==1 else "high")]=v[k]
    cands["yesterday's "+("high" if d==1 else "low")+" (flipped: old "+("resistance→support" if d==1 else "support→resistance")+")"]=p1.high if d==1 else p1.low
    dist={k:abs(probe-v)/datr for k,v in cands.items()}
    ykey="yesterday's "+("low" if d==1 else "high")
    used=ykey if dist[ykey]<=0.25 else min(dist,key=dist.get); used_d=dist[used]
    lvl_y=cands["yesterday's "+("low" if d==1 else "high")]
    near_y=abs(probe-lvl_y)/datr<=0.25
    speed=-d*(last4.close.iloc[-1]-last4.close.iloc[0])/datr
    fast=speed>=0.14
    confirm=d*(lastbar.close-lastbar.open)>0
    broke=(today.close<lvl_y).any() if d==1 else (today.close>lvl_y).any()
    miss=[]
    if not near_y: miss.append(f"not at yesterday's {'low' if d==1 else 'high'} ({abs(probe-lvl_y)/datr:.2f} dATR away)")
    if not fast: miss.append(f"slow approach ({speed:+.2f})")
    if not confirm: miss.append("no confirmation candle")
    if near_y and broke: miss.append("yesterday's level already broken by a close today")
    rows.append(dict(n=t.n,date=t.date.strftime("%Y-%m-%d %H:%M"),dir=t.dir,result=t.out,R=round(t.R,2),
        at_yday_level=int(near_y),fast=int(fast),confirm=int(confirm),matches_all=int(near_y and fast and confirm and not broke),
        level_actually_used=used if used_d<=0.25 else "no clear level (price was mid-range)",dist_to_used=round(used_d,2),
        why_not_matching="; ".join(miss) if miss else "MATCHES YOUR RULES"))
X=pd.DataFrame(rows); X.to_csv("../DATA/my_trades_vs_rules.csv",index=False)
X["win"]=(X.result=="WIN").astype(int)
f=lambda z: f"{len(z):2d} trades, win {100*z.win.mean():3.0f}%, {z.R.sum():+5.1f}R" if len(z) else "0"
print("MATCHES ALL YOUR RULES     :",f(X[X.matches_all==1]))
print("breaks at least one rule   :",f(X[X.matches_all==0]))
print("\nrule by rule:")
print("  at yesterday's H/L       :",f(X[X.at_yday_level==1]),"| not:",f(X[X.at_yday_level==0]))
print("  fast approach            :",f(X[X.fast==1]),"| slow:",f(X[X.fast==0]))
print("  confirmation candle      :",f(X[X.confirm==1]),"| none:",f(X[X.confirm==0]))
print("\nWHICH LEVEL WAS REALLY USED:")
for k,z in X.groupby("level_actually_used"): print(f"  {k:<58} {f(z)}")
print("\nfirst 25 trades:"); print(X[["n","date","dir","result","level_actually_used","why_not_matching"]].head(25).to_string(index=False,max_colwidth=70))
