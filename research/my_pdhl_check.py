import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
L=pd.read_csv("../DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
A=pd.read_csv("../DATA/my_trades_anatomy.csv")
g=load_ohlcv("XAUUSD_15m.csv")
dd=g.resample("1D").agg(dict(high="max",low="min",close="last")).dropna()
dd=dd[dd.index.dayofweek<5]
tr=np.maximum(dd.high-dd.low,np.maximum((dd.high-dd.close.shift()).abs(),(dd.low-dd.close.shift()).abs())); dd["atr"]=tr.rolling(14).mean()
rows=[]
for (_,t),(_,a) in zip(L.iterrows(),A.iterrows()):
    day=t.date.normalize(); prev=dd[dd.index<day].iloc[-1]; datr=prev.atr
    d=1 if t.dir=="LONG" else -1; lvl=prev.low if d==1 else prev.high
    today=g.loc[day:t.date-pd.Timedelta(minutes=15)]
    probe=(today.low.min() if d==1 else today.high.max()) if len(today) else np.nan
    last4=g.loc[t.date-pd.Timedelta(hours=4):t.date-pd.Timedelta(minutes=15)]
    speed4=-d*(last4.close.iloc[-1]-last4.close.iloc[0])/datr if len(last4)>1 else np.nan   # >0 = came INTO the level
    last1=g.loc[t.date-pd.Timedelta(hours=1):t.date-pd.Timedelta(minutes=15)]
    speed1=-d*(last1.close.iloc[-1]-last1.close.iloc[0])/datr if len(last1)>1 else np.nan
    rows.append(dict(n=t.n,dir=t.dir,win=int(t.out=="WIN"),R=t.R,
        entry_to_level=round(d*(t.entry-lvl)/datr,2),     # 0 = right at yesterday's low (buy) / high (sell); >0 = inside the range
        today_reached=round(-d*(probe-lvl)/datr,2) if not np.isnan(probe) else np.nan,  # >=0 means today already touched/through the level
        speed_4h=round(speed4,2), speed_1h=round(speed1,2)))
X=pd.DataFrame(rows); X["half"]=np.where(X.n<=41,1,2)
print("distance of entry from yesterday's low (buys) / high (sells), in daily ATRs:")
print(X.entry_to_level.describe().round(2).to_string())
def row(lab,m):
    x=X[m]; f=lambda z: f"{len(z):2d} tr {100*z.win.mean():3.0f}% {z.R.sum():+5.1f}R" if len(z) else "  -"
    print(f"{lab:<52} {f(x)} | 1st {f(x[x.half==1])} | 2nd {f(x[x.half==2])}")
print()
row("entry within 0.25 dATR of yesterday's H/L",X.entry_to_level.abs()<=0.25)
row("entry 0.25-0.6 dATR inside the range",(X.entry_to_level>0.25)&(X.entry_to_level<=0.6))
row("entry deep inside range (>0.6)",X.entry_to_level>0.6)
row("entry beyond yesterday's H/L (outside range)",X.entry_to_level<-0.25)
print("\napproach SPEED into the level (last 4h move toward it, daily ATRs):")
q=X.speed_4h.quantile([1/3,2/3]).values
row(f"slow approach (< {q[0]:.2f})",X.speed_4h<q[0]); row("medium",(X.speed_4h>=q[0])&(X.speed_4h<q[1])); row(f"fast approach (> {q[1]:.2f})",X.speed_4h>=q[1])
print("last 1h:")
q=X.speed_1h.quantile([1/3,2/3]).values
row(f"last hour still pushing INTO level (> {q[1]:.2f})",X.speed_1h>=q[1]); row("middle",(X.speed_1h>=q[0])&(X.speed_1h<q[1])); row(f"last hour already turned AWAY (< {q[0]:.2f})",X.speed_1h<q[0])
X.to_csv("../DATA/my_trades_pdhl.csv",index=False)
