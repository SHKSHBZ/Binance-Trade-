"""Replay the trader's own 82 trades (same entry, same stop) with different exits on real gold 15m data."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

L=pd.read_csv("../DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
g=load_ohlcv("XAUUSD_15m.csv"); h,l,c=g.high.values,g.low.values,g.close.values; idx=g.index
et=idx.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None); ethr=et.hour+et.minute/60
COST=0.25; MAXB=500

def path(t0,d,e,risk):
    i=idx.searchsorted(t0.floor("15min")+pd.Timedelta(minutes=15))
    return i

def sim(i,d,e,risk,mode):
    stop=e-d*risk; best=e; half_done=False; banked=0.0
    for j in range(i,min(i+MAXB,len(c))):
        hi,lo=h[j],l[j]
        if mode.get("intraday") and 16.75<=ethr[j]<18:
            return banked+(1-0.5*half_done)*d*(c[j]-e)/risk
        # stop first (conservative)
        if (d==1 and lo<=stop) or (d==-1 and hi>=stop):
            return banked+(1-0.5*half_done)*d*(stop-e)/risk
        fav=hi if d==1 else lo
        best=max(best,fav) if d==1 else min(best,fav)
        gain=d*(best-e)/risk
        if mode.get("partial") and not half_done and gain>=mode["partial"]:
            banked+=0.5*mode["partial"]; half_done=True; stop=e
        tp=mode.get("tp")
        if tp and gain>=tp: return banked+(1-0.5*half_done)*tp
        if mode.get("be") and gain>=mode["be"]: stop=e if d==1 else e; stop=max(stop,e) if d==1 else min(stop,e)
        if mode.get("trail") and gain>=mode["trail"]:
            ts=best-d*mode["trail"]*risk
            stop=max(stop,ts) if d==1 else min(stop,ts)
    j=min(i+MAXB,len(c)-1); return banked+(1-0.5*half_done)*d*(c[j]-e)/risk

def run(mode,shift_h=0):
    out=[]
    for _,t in L.iterrows():
        d=1 if t.dir=="LONG" else -1; risk=abs(t.entry-t.sl)
        i=path(t.date-pd.Timedelta(hours=shift_h),d,t.entry,risk)
        if i>=len(c): out.append(np.nan); continue
        out.append(sim(i,d,t.entry,risk,mode)-COST/risk)
    return np.array(out)

# 1) which clock are the trade times in? pick the shift that reproduces the recorded WIN/LOSS best
rec=(L.out=="WIN").values
for s in (-3,-2,-1,0,1,2,3):
    r=run({"tp":2.0},s); ok=~np.isnan(r)
    print(f"time shift {s:+d}h: replay matches your recorded win/loss on {100*((r[ok]>0)==rec[ok]).mean():.0f}% of {ok.sum()} trades")

MODES={
 "YOUR ACTUAL: target 2R":{"tp":2.0},
 "target 1R":{"tp":1.0}, "target 1.5R":{"tp":1.5}, "target 2.5R":{"tp":2.5}, "target 3R":{"tp":3.0}, "target 4R":{"tp":4.0},
 "2R + stop to breakeven at +1R":{"tp":2.0,"be":1.0},
 "3R + stop to breakeven at +1R":{"tp":3.0,"be":1.0},
 "3R + breakeven at +1.5R":{"tp":3.0,"be":1.5},
 "half off at 1R, rest to 3R (BE)":{"partial":1.0,"tp":3.0},
 "half off at 1R, rest to 4R (BE)":{"partial":1.0,"tp":4.0},
 "no target, trail 1R after +1R":{"trail":1.0},
 "no target, trail 1.5R after +1.5R":{"trail":1.5},
 "2R but close by 16:45 NY (intraday)":{"tp":2.0,"intraday":True},
}
if __name__=="__main__":
    print()
    D=np.where(L.dir=="LONG",1,-1); first=L.date<"2026-01-01"
    base=None
    print(f"{'exit rule (same entries, same stops)':<40}{'total R':>9}{'avg R':>8}{'win%':>6}{'2025':>8}{'2026':>8}{'sells':>8}{'buys':>8}{'worst streak':>13}")
    for k,m in MODES.items():
        r=run(m); 
        streak=0; worst=0; cur=0
        for x in r:
            cur=cur+1 if x<0 else 0; worst=max(worst,cur)
        print(f"{k:<40}{r.sum():>+9.1f}{r.mean():>+8.3f}{100*(r>0).mean():>6.0f}{r[first].sum():>+8.1f}{r[~first].sum():>+8.1f}{r[D==-1].sum():>+8.1f}{r[D==1].sum():>+8.1f}{worst:>13}")
