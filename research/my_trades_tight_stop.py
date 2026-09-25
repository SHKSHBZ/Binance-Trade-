"""Trader's 82 real entries replayed with a hard $5 stop. Bracketed: worst case (stop first on ambiguous
candles, entry candle counted) vs best case (target first, entry candle skipped)."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
L=pd.read_csv("../DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
g=load_ohlcv("XAUUSD_15m.csv"); h,l,c=g.high.values,g.low.values,g.close.values; idx=g.index
COST=0.25
def replay(stop_usd, tgt_usd, worst):
    out=[]
    for _,t in L.iterrows():
        d=1 if t.dir=="LONG" else -1; e=t.entry
        tgt=abs(t.tp-e) if tgt_usd=="orig" else tgt_usd
        i0=idx.searchsorted(t.date.floor("15min"))          # candle containing the entry
        start=i0 if worst else i0+1
        R=None
        for j in range(start,min(start+500,len(c))):
            hit_s=(l[j]<=e-stop_usd) if d==1 else (h[j]>=e+stop_usd)
            hit_t=(h[j]>=e+tgt) if d==1 else (l[j]<=e-tgt)
            if j==i0 and worst: hit_t=False                   # can't credit the target inside the entry candle
            if hit_s and hit_t: R=-1.0 if worst else tgt/stop_usd; break
            if hit_s: R=-1.0; break
            if hit_t: R=tgt/stop_usd; break
        if R is None: j=min(start+499,len(c)-1); R=d*(c[j]-e)/stop_usd
        out.append(R-COST/stop_usd)
    return np.array(out)
days=np.busday_count(L.date.min().date(),L.date.max().date())
print(f"your real result (your own stops, 2R): win {100*(L.R>0).mean():.0f}%, total {L.R.sum():+.1f}R\n")
print(f"{'$5 stop, target':<22}{'case':<7}{'win %':>7}{'total R':>9}{'avg R':>8} | $300 risk (0.60 lot): total $ ; per day AED | start $2,000 lowest")
for tgt in (5,10,15,25,"orig"):
    for worst in (True,False):
        R=replay(5.0,tgt,worst); pnl=R*300; eq=2000+np.cumsum(pnl)
        lab=f"${tgt}" if tgt!="orig" else "your original TP"
        print(f"{lab:<22}{'worst' if worst else 'best':<7}{100*(R>0).mean():>6.0f}%{R.sum():>+9.1f}{R.mean():>+8.2f} | ${pnl.sum():>8,.0f} ; AED {pnl.sum()/days*3.6725:>5.0f}/day | ${eq.min():>8,.0f}")
