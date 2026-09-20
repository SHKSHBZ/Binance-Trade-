import sys; sys.path.insert(0,'/home/user/Binance-Trade-/research')
import _paths, numpy as np, pandas as pd
exec(open("/tmp/claude-0/-home-user-Binance-Trade-/6d7873e3-4b2e-5f76-ac13-9d1a92d87acb/scratchpad/trend_pos.py").read().split("G=daily(")[0])

def run2(d,N=40,trailA=3.0,allow=("L",),cost_frac=0.0001,risk=0.01,cap0=1000.0,rand=None):
    """As run(), but also returns the daily equity curve and the average
    NOTIONAL exposure, so the strategy can be compared against a passive
    allocation of the same size (the only fair benchmark in a bull market)."""
    o,h,l,c=d["open"].values,d["high"].values,d["low"].values,d["close"].values
    n=len(c);A=atr(h,l,c,20)
    hh=pd.Series(h).rolling(N).max().shift(1).values
    ll=pd.Series(l).rolling(N).min().shift(1).values
    rng=np.random.default_rng(rand) if rand is not None else None
    cap=cap0;pos=0;entry=stop=qty=0.0;best=0.0
    eq=[];notl=[];ntr=0
    for i in range(n):
        if pos!=0:
            if pos>0:
                best=max(best,h[i]); ts=best-trailA*A[i]
                if ts>stop: stop=ts
                if l[i]<=stop: cap+=qty*(stop*(1-cost_frac)-entry); pos=0;qty=0
            else:
                best=min(best,l[i]); ts=best+trailA*A[i]
                if ts<stop: stop=ts
                if h[i]>=stop: cap+=qty*(entry-stop*(1+cost_frac)); pos=0;qty=0
        if pos==0 and not np.isnan(hh[i]) and A[i]>0:
            sig=1 if c[i]>hh[i] else (-1 if c[i]<ll[i] else 0)
            if rng is not None and sig!=0: sig=1 if rng.random()<0.5 else -1
            if sig==1 and "L" in allow:
                entry=c[i]*(1+cost_frac);stop=entry-trailA*A[i]
                qty=(cap*risk)/(entry-stop);pos=1;best=entry;ntr+=1
            elif sig==-1 and "S" in allow:
                entry=c[i]*(1-cost_frac);stop=entry+trailA*A[i]
                qty=(cap*risk)/(stop-entry);pos=-1;best=entry;ntr+=1
        m=cap+(qty*(c[i]-entry) if pos>0 else (qty*(entry-c[i]) if pos<0 else 0))
        eq.append(m); notl.append(abs(qty)*c[i]/m if m>0 else 0)
    eq=np.array(eq);notl=np.array(notl)
    return eq,notl,ntr

def stats(eq,d,notl,label):
    c=d["close"].values
    r_s=np.diff(eq)/eq[:-1]; r_m=np.diff(c)/c[:-1]
    beta=np.cov(r_s,r_m)[0,1]/np.var(r_m)
    alpha_d=r_s.mean()-beta*r_m.mean()
    alpha_a=100*((1+alpha_d)**252-1)
    peak=np.maximum.accumulate(eq);dd=100*((peak-eq)/peak).max()
    yrs=(d.index[-1]-d.index[0]).days/365.25
    cagr=100*((eq[-1]/eq[0])**(1/yrs)-1)
    # exposure-matched passive benchmark
    ex=notl.mean()
    bench=100*(((c[-1]/c[0]-1)*ex+1)**(1/yrs)-1)
    print(f"  {label:<24} CAGR {cagr:+6.2f}%  maxDD {dd:5.2f}%  avgExposure {100*ex:5.1f}%"
          f"  | matched passive CAGR {bench:+6.2f}%  | beta {beta:5.2f}  ALPHA {alpha_a:+6.2f}%/yr")
    return cagr,dd,alpha_a

for name,f in [("GOLD","XAUUSD_4h.csv"),("BTC","BTCUSDT_4h_2023_to_2025.csv")]:
    d=daily(f)
    print(f"\n===== {name}  {d.index[0].date()} -> {d.index[-1].date()}  buy&hold {100*(d['close'].values[-1]/d['close'].values[0]-1):+.0f}% =====")
    for N,tA in [(40,3.0),(60,3.0),(40,5.0),(60,8.0)]:
        eq,notl,ntr=run2(d,N,tA,("L",))
        stats(eq,d,notl,f"N={N} trail={tA} LONG (n={ntr})")
    print("  -- NULL: random direction, same trail (N=40, trail=3) --")
    al=[]
    for sd in range(8):
        eq,notl,ntr=run2(d,40,3.0,("L","S"),rand=sd)
        r_s=np.diff(eq)/eq[:-1];c=d["close"].values;r_m=np.diff(c)/c[:-1]
        b=np.cov(r_s,r_m)[0,1]/np.var(r_m);a=100*((1+(r_s.mean()-b*r_m.mean()))**252-1)
        al.append(a)
    print(f"     null alpha: mean {np.mean(al):+.2f}%/yr  sd {np.std(al):.2f}  range [{min(al):+.2f},{max(al):+.2f}]")

# walk-forward on gold
print("\n===== GOLD WALK-FORWARD (long-only, N=40 trail=3) =====")
for lab,s,e in [("TRAIN 2020-2023","2020-01-01","2023-12-31"),("TEST  2024-2026","2024-01-01","2026-09-16")]:
    d=daily("XAUUSD_4h.csv",s,e)
    eq,notl,ntr=run2(d,40,3.0,("L",))
    stats(eq,d,notl,f"{lab} (n={ntr})")
