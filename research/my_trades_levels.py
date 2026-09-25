"""Were the trader's entries at support/resistance? Levels = confirmed swing highs/lows on 4H, 1H, 15m."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

L=pd.read_csv("../DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
A=pd.read_csv("../DATA/my_trades_anatomy.csv",parse_dates=["date"])
g=load_ohlcv("XAUUSD_15m.csv")
TF={"4H":("4h",2,pd.Timedelta(days=30)),"1H":("1h",3,pd.Timedelta(days=7)),"15m":("15min",3,pd.Timedelta(days=2))}

def pivots(rule,k):
    b=g.resample(rule).agg(dict(high="max",low="min")).dropna() if rule!="15min" else g[["high","low"]]
    step=pd.Timedelta(rule)
    H,Lw=b.high.values,b.low.values; out=[]
    for i in range(k,len(b)-k):
        conf=b.index[i+k]+step                      # known once the k-th bar after the pivot has closed
        if H[i]==H[i-k:i+k+1].max(): out.append((conf,b.index[i],H[i],-1))   # resistance
        if Lw[i]==Lw[i-k:i+k+1].min(): out.append((conf,b.index[i],Lw[i],1)) # support
    return pd.DataFrame(out,columns=["known","t","price","side"])
P={tf:pivots(r,k) for tf,(r,k,_) in TF.items()}

rows=[]
for (_,t),(_,a) in zip(L.iterrows(),A.iterrows()):
    d=1 if t.dir=="LONG" else -1; e=t.entry; risk=abs(e-t.sl)
    datr=risk/a.stop_in_datr; tol=0.1*datr
    recent=g.loc[t.date-pd.Timedelta(hours=4):t.date-pd.Timedelta(minutes=15)]
    probe=recent.high.max() if d==-1 else recent.low.min()     # how far price pushed into the level before entry
    best=None
    for tf in ("4H","1H","15m"):
        p=P[tf]; p=p[(p.known<=t.date)&(p.known>=t.date-TF[tf][2])&(p.side==-d if False else p.side==(1 if d==1 else -1))]
        # SELL wants resistance (side -1), BUY wants support (side +1)
        p=P[tf]; want=1 if d==1 else -1
        p=p[(p.known<=t.date)&(p.t>=t.date-TF[tf][2])&(p.side==want)]
        if not len(p): continue
        dist=np.abs(p.price.values-probe)
        j=dist.argmin()
        if dist[j]<=tol*1.5:
            lvl=p.price.values[j]
            touches=int(np.sum(np.abs(p.price.values-lvl)<=tol))
            best=dict(level_tf=tf,level=round(lvl,2),touches=touches,
                      entry_to_level_datr=round(d*(e-lvl)/datr,2),   # >0 = entry above support / below resistance
                      stop_beyond_level=int((t.sl<lvl) if d==1 else (t.sl>lvl)),
                      pierced=round(-d*(probe-lvl)/datr,2))          # >0 = price poked through the level before reversing
            break
    rows.append(dict(n=t.n,dir=t.dir,result=t.out,R=t.R,**(best or dict(level_tf="none"))))
Lv=pd.DataFrame(rows); Lv.to_csv("../DATA/my_trades_levels.csv",index=False)
Lv["win"]=(Lv.result=="WIN").astype(int); Lv["half"]=np.where(Lv.n<=41,1,2)
def row(lab,m):
    x=Lv[m]; f=lambda z: f"{len(z):2d} tr {100*z.win.mean():3.0f}% {z.R.sum():+5.1f}R" if len(z) else "  -"
    print(f"{lab:<46} {f(x)} | 1st {f(x[x.half==1])} | 2nd {f(x[x.half==2])}")
print("### Was the entry at a swing level (price tested it within the last 4h)?")
for tf in ("4H","1H","15m","none"): row(f"level from {tf}" if tf!="none" else "no level nearby",Lv.level_tf==tf)
row("any level (4H/1H/15m)",Lv.level_tf!="none")
at=Lv[Lv.level_tf!="none"]
print("\n### for trades AT a level")
row("level touched once (fresh)",(Lv.level_tf!="none")&(Lv.touches<=1))
row("level touched 2+ times (well-tested)",(Lv.level_tf!="none")&(Lv.touches>=2))
row("stop beyond the level",(Lv.level_tf!="none")&(Lv.stop_beyond_level==1))
row("stop NOT beyond the level",(Lv.level_tf!="none")&(Lv.stop_beyond_level==0))
row("price poked THROUGH the level first (sweep)",(Lv.level_tf!="none")&(Lv.pierced>0.02))
row("price stopped short / exactly at level",(Lv.level_tf!="none")&(Lv.pierced<=0.02))
print("\n### combine with the volatile-day finding")
vol=(A.vol_regime>1.2)|(A.news_spike_today==1)
row("at a level + volatile day",(Lv.level_tf!="none")&vol.values)
row("at a level + quiet day",(Lv.level_tf!="none")&~vol.values)
row("no level + volatile day",(Lv.level_tf=="none")&vol.values)
