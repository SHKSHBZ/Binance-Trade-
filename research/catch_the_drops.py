"""Were there drops? How big? Can they be caught in real time?"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

g1=load_ohlcv("XAUUSD_1h.csv")
cat=lambda a,b:(lambda x:x[~x.index.duplicated()].sort_index())(pd.concat([load_ohlcv(a),load_ohlcv(b)]))
b1=cat("BTCUSDT_1h_2023_to_2025.csv","BTCUSDT_1h_Jan_to_Jul2026.csv")

def zigzag(c, t):
    """swing legs on closes: a leg ends when price reverses by t from its extreme."""
    hi=lo=c[0]; hi_i=lo_i=0; i=0; n=len(c)
    while i<n:                                  # find the first confirmed swing
        p=c[i]
        if p>hi: hi,hi_i=p,i
        if p<lo: lo,lo_i=p,i
        if p<=hi*(1-t): d=-1; start,start_i=hi,hi_i; ext,ext_i=p,i; break
        if p>=lo*(1+t): d=1;  start,start_i=lo,lo_i; ext,ext_i=p,i; break
        i+=1
    legs=[]
    for j in range(i+1,n):
        p=c[j]
        if d==1:
            if p>ext: ext,ext_i=p,j
            elif p<=ext*(1-t):
                legs.append((1,start,ext,start_i,ext_i,p)); d=-1; start,start_i=ext,ext_i; ext,ext_i=p,j
        else:
            if p<ext: ext,ext_i=p,j
            elif p>=ext*(1+t):
                legs.append((-1,start,ext,start_i,ext_i,p)); d=1; start,start_i=ext,ext_i; ext,ext_i=p,j
    return legs

def part1(name,df,ths,cost_frac):
    c=df.close.values
    print(f"\n##### {name}: {c[0]:,.0f} -> {c[-1]:,.0f}")
    print(f"{'swing size':>10} {'# drops':>8} {'avg drop':>9} {'biggest':>8} {'avg hrs':>8} {'# rallies':>9} {'avg rally':>9} |"
          f" {'real sell caught/drop':>22} {'real buy caught/rally':>22}  (after costs, entry/exit at real closes)")
    for t in ths:
        L=zigzag(c,t)
        dn=[(s-e)/s for d,s,e,a,b,p in L if d==-1]; up=[(e-s)/s for d,s,e,a,b,p in L if d==1]
        hrs=[b-a for d,s,e,a,b,p in L if d==-1]
        # confirmation close of each reversal = where a swing-follower actually trades
        conf=[p for *_,p in L]
        cap_dn=[]; cap_up=[]
        for k in range(1,len(L)):
            entry=conf[k-1]; exit_=conf[k]
            if L[k][0]==-1: cap_dn.append((entry-exit_)/entry-2*cost_frac)
            else:           cap_up.append((exit_-entry)/entry-2*cost_frac)
        print(f"{100*t:>9.1f}% {len(dn):>8} {100*np.mean(dn):>8.1f}% {100*max(dn):>7.1f}% {np.mean(hrs):>8.0f} {len(up):>9} {100*np.mean(up):>8.1f}% |"
              f" {100*np.mean(cap_dn):>+21.2f}% {100*np.mean(cap_up):>+21.2f}%")

def part2(name,df,ds,cost_frac):
    """Real-time test: the moment price is d below its recent top (last 5 days), SELL.
    Stop = back at the top (risk d). Target = another d lower (1R) or 2d lower (2R).
    Does it keep falling or bounce back?  Mirror for rallies from the bottom."""
    h,l,c=df.high.values,df.low.values,df.close.values; n=len(c)
    hi=pd.Series(h).rolling(120,min_periods=1).max().values
    lo=pd.Series(l).rolling(120,min_periods=1).min().values
    print(f"\n{name}: the moment price is X% off its 5-day top -> SELL (stop at the top).  Mirror: X% off 5-day bottom -> BUY")
    print(f"{'X':>6} {'sells':>6} {'reach 1R first':>15} {'avg R @1R':>10} {'avg R @2R':>10} | {'buys':>5} {'reach 1R first':>15} {'avg R @1R':>10} {'avg R @2R':>10}")
    for dd in ds:
        res={}
        for side in (-1,1):
            out1=[];out2=[]; i=121; busy=0
            while i<n-1:
                ref=hi[i-1] if side==-1 else lo[i-1]
                trig=(c[i]<=ref*(1-dd) and c[i-1]>ref*(1-dd)) if side==-1 else (c[i]>=ref*(1+dd) and c[i-1]<ref*(1+dd))
                if not trig or i<busy: i+=1; continue
                e=c[i]; stop=ref; risk=abs(e-stop)
                if risk<=0: i+=1; continue
                for R_,out in ((1,out1),(2,out2)):
                    tgt=e+side*R_*risk; r=None
                    for j in range(i+1,min(i+24*10,n)):
                        if (side==-1 and h[j]>=stop) or (side==1 and l[j]<=stop): r=-1.0; break
                        if (side==-1 and l[j]<=tgt) or (side==1 and h[j]>=tgt): r=R_; break
                    if r is None: r=side*(c[j]-e)/risk
                    out.append(r-e*cost_frac/risk)
                busy=i+24; i+=1
            res[side]=(np.array(out1),np.array(out2))
        s1,s2=res[-1]; b1_,b2_=res[1]
        print(f"{100*dd:>5.1f}% {len(s1):>6} {100*(s1>0).mean():>14.0f}% {s1.mean():>+10.3f} {s2.mean():>+10.3f} | {len(b1_):>5} {100*(b1_>0).mean():>14.0f}% {b1_.mean():>+10.3f} {b2_.mean():>+10.3f}")

part1("GOLD (1h closes, 2020-2026)", g1, [0.005,0.01,0.02,0.03,0.05], 0.25/3000)
part1("BTC (1h closes, 2023-2026)",  b1, [0.02,0.03,0.05,0.08,0.10], 0.0006)
part2("GOLD", g1, [0.005,0.01,0.015,0.02,0.03], 0.25/3000)
part2("BTC",  b1, [0.02,0.03,0.05,0.08], 0.0006)
