"""
STRUCTURED S/R STRATEGY built from the trader's own rules + trade log findings.
  LEVELS : yesterday's high/low (UTC day, wicks) + 4H swing highs/lows (2 bars each side, last 10 days, unbroken)
  TOUCH  : 15m candle reaches the level (within 0.1 dATR) and does NOT close through it
  SPEED  : fast approach: last 4h moved >= 0.14 dATR toward the level
  CONFIRM: that candle closes back away from the level
  STOP   : beyond level/candle extreme + 0.05 dATR (0.1..0.6 dATR) ; TARGET 2R ; one trade at a time
Each trade is tagged with level type and session (London time) so the structure can be chosen on
BUILD data (2022-06..2024-06), then checked on CHECK (2024-07..2025-05) and the trader's period (2025-05..2026-09).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
from my_pdhl_strategy import prep

def sess_of(lh):
    return np.select([lh<7,lh<12,lh<16.5,lh<21],["Asia","London","Overlap","NY pm"],"Late")

def levels_4h(g):
    b=g.resample("4h").agg(dict(high="max",low="min")).dropna(); H,Lw=b.high.values,b.low.values; out=[]
    for i in range(2,len(b)-2):
        kn=b.index[i+2]+pd.Timedelta(hours=4)
        if H[i]==H[i-2:i+3].max(): out.append((kn,b.index[i],H[i],-1))
        if Lw[i]==Lw[i-2:i+3].min(): out.append((kn,b.index[i],Lw[i],1))
    return pd.DataFrame(out,columns=["known","t","price","side"]).sort_values("known").reset_index(drop=True)

def run(g, cost=0.25, speed=0.14, allowed=None, exitm="2R"):
    h,l,c,o=g.high.values,g.low.values,g.close.values,g.open.values; n=len(c); idx=g.index
    datr=g.datr.values; PDH=g.PDH.values; PDL=g.PDL.values; day=g.uday.values
    lon=idx.tz_localize("UTC").tz_convert("Europe/London").tz_localize(None); S=sess_of(lon.hour+lon.minute/60)
    lv=levels_4h(g); kn=lv.known.values; lt=lv.t.values; lp=lv.price.values; ls=lv.side.values
    nxt=0; active=[]; out=[]; busy=-1; used=set()
    for i in range(17,n-1):
        while nxt<len(lv) and kn[nxt]<=idx[i]: active.append(nxt); nxt+=1
        if i%16==0:
            cut=idx[i]-pd.Timedelta(days=10); active=[k for k in active if lt[k]>=cut]
        # drop broken 4H levels (a close beyond)
        active=[k for k in active if not ((ls[k]==-1 and c[i-1]>lp[k]) or (ls[k]==1 and c[i-1]<lp[k]))]
        if i<=busy: continue
        cands=[("Y-high",PDH[i],-1),("Y-low",PDL[i],1)]+[("4H-high" if ls[k]==-1 else "4H-low",lp[k],-ls[k]*-1 if False else (-1 if ls[k]==-1 else 1)) for k in active]
        tol=0.1*datr[i]
        for typ,lvl,d in cands:
            if np.isnan(lvl): continue
            if allowed and (typ,S[i]) not in allowed and (typ,"*") not in allowed: continue
            ext=l[i] if d==1 else h[i]
            if not (-d*(ext-lvl) >= -tol): continue            # reached the level
            if d*(c[i]-lvl)<=0: continue                        # closed through it -> not holding
            if d*(c[i]-o[i])<=0: continue                       # confirmation candle
            if -d*(c[i-1]-c[i-17]) < speed*datr[i] and -d*(ext-c[i-16]) < speed*datr[i]: continue   # fast approach
            key=(day[i],typ,round(lvl,1))
            if key in used: continue
            used.add(key)
            recent=l[i-3:i+1].min() if d==1 else h[i-3:i+1].max()
            stop=(min(recent,lvl) if d==1 else max(recent,lvl))-d*0.05*datr[i]
            e=c[i]; risk=d*(e-stop)
            if not (0.1*datr[i]<=risk<=0.6*datr[i]): continue
            best=e; st=stop; R=None
            for j in range(i+1,min(i+501,n)):
                if (d==1 and l[j]<=st) or (d==-1 and h[j]>=st): R=d*(st-e)/risk; break
                best=max(best,h[j]) if d==1 else min(best,l[j]); gain=d*(best-e)/risk
                if exitm=="2R" and gain>=2: R=2.0; break
                if exitm=="trail" and gain>=1.5:
                    ts=best-d*1.5*risk; st=max(st,ts) if d==1 else min(st,ts)
            if R is None: j=min(i+500,n-1); R=d*(c[j]-e)/risk
            out.append(dict(time=idx[i],dir=d,typ=typ,sess=S[i],R=R-cost/risk,risk=risk)); busy=j; break
    return pd.DataFrame(out)

if __name__=="__main__":
    g=prep(load_ohlcv("XAUUSD_15m.csv")); t=run(g)
    t.to_pickle("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/structured_all.pkl")
    P={"BUILD 22-06..24-06":("2022-06-24","2024-06-30"),"CHECK 24-07..25-05":("2024-07-01","2025-05-07"),"YOURS 25-05..26-09":("2025-05-08","2026-09-16")}
    def cell(x): return f"{len(x):3d} {x.R.mean():+.2f}" if len(x) else "  0   -  "
    print(f"{'level / session':<22}"+"".join(f"{k:>22}" for k in P))
    for typ in ["Y-high","Y-low","4H-high","4H-low"]:
        for s in ["Asia","London","Overlap","NY pm","Late","ALL"]:
            m=(t.typ==typ)&((t.sess==s) if s!="ALL" else True)
            print(f"{typ+' '+s:<22}"+"".join(f"{cell(t[m&(t.time>=a)&(t.time<=b+' 23:59')]):>22}" for a,b in P.values()))
        print()
    for s in ["Asia","London","Overlap","NY pm"]:
        m=t.sess==s; print(f"{'ALL levels '+s:<22}"+"".join(f"{cell(t[m&(t.time>=a)&(t.time<=b+' 23:59')]):>22}" for a,b in P.values()))
    print(f"{'EVERYTHING':<22}"+"".join(f"{cell(t[(t.time>=a)&(t.time<=b+' 23:59')]):>22}" for a,b in P.values()))
