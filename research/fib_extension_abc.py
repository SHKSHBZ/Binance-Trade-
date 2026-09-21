"""
Fibonacci EXTENSION (trend-based A-B-C) — the PDF's strategy.

Different from the Fib work already in this repo: prior tests entered INSIDE a
retracement (0.5 / golden pocket). This one enters on the RESUMPTION (break of
the Point-C candle) and uses trend-based extension levels C + k*(B-A) as targets.

Structure (causal; a 3-candle pivot is confirmed at the 3rd candle's CLOSE):
  A = swing low, B = later swing high, C = later swing low with C > A  (bull)
  entry  = break of the high of C's candle
  stop   = below C's low
  target = C + k*(B-A)

THREE things are measured, in order of how much they matter:

 1) Do the levels get reached more often than their DISTANCE implies?
    (each level's hit rate vs its own geometric breakeven -- the test that
     produced a dead-flat null for the Kane midpoint)

 2) ARE FIB RATIOS SPECIAL? 1.000/1.618 are compared against deliberately
    NON-Fib controls (0.9, 1.1, 1.35, 1.5, 1.9, 2.2). If price reaches 1.618 no
    more reliably than 1.5, the ratio is decoration. This is the only test that
    can distinguish "Fibonacci" from "any target at that distance".

 3) The full strategy with the PDF's management, and with it switched off.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

FIB   = [0.618, 1.0, 1.272, 1.618, 2.618]
NONFIB= [0.9, 1.1, 1.35, 1.5, 1.9, 2.2]

def pivots(h, l, P=1):
    """P=1 reproduces the PDF's three-candle rule. Confirmed at bar i+P."""
    n=len(h); ph=[]; pl=[]
    for i in range(P, n-P):
        if h[i]==h[i-P:i+P+1].max(): ph.append((i, i+P, h[i]))   # (pivot bar, confirm bar, price)
        if l[i]==l[i-P:i+P+1].min(): pl.append((i, i+P, l[i]))
    return ph, pl

def structures(df, P=1, min_leg_atr=1.0):
    """Yield causal A-B-C setups. Everything known at C's confirmation bar."""
    h,l,c=df["high"].values,df["low"].values,df["close"].values
    n=len(c)
    pc=np.concatenate([[c[0]],c[:-1]])
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    A=pd.Series(tr).rolling(20).mean().bfill().values
    ph,pl=pivots(h,l,P)
    out=[]
    for direction in (1,-1):
        first = pl if direction==1 else ph      # A
        second= ph if direction==1 else pl      # B
        third = pl if direction==1 else ph      # C
        bi=0; ci=0
        for (ab,ac,av) in first:
            while bi<len(second) and second[bi][0]<=ab: bi+=1
            if bi>=len(second): break
            (bb,bc,bv)=second[bi]
            k=ci
            while k<len(third) and third[k][0]<=bb: k+=1
            if k>=len(third): continue
            (cb,cc,cv)=third[k]
            leg=abs(bv-av)
            if cc>=n-2 or A[cc]<=0 or leg<min_leg_atr*A[cc]: continue
            if direction==1 and not (cv>av and bv>av): continue   # higher low
            if direction==-1 and not (cv<av and bv<av): continue  # lower high
            out.append(dict(dir=direction,A=av,B=bv,C=cv,leg=leg,
                            cbar=cb,conf=cc,
                            trig=h[cb] if direction==1 else l[cb],
                            stop=l[cb] if direction==1 else h[cb]))
    return sorted(out,key=lambda x:x["conf"]), h,l,c,A,n

def race(df,P=1,levels=FIB,spread=0.0,minrisk_frac=0.0005,min_leg_atr=1.0):
    """For each structure: enter on the break of C's candle, then race EVERY
    level against the stop. Returns per-level hit rates + implied breakevens."""
    S,h,l,c,A,n=structures(df,P,min_leg_atr)
    res={k:[] for k in levels}; rrs={k:[] for k in levels}; used=0
    for s in S:
        d=s["dir"]; e=s["trig"]; st=s["stop"]
        # entry must trigger AFTER C is confirmed
        ei=None
        for j in range(s["conf"]+1, min(s["conf"]+1+200, n)):
            if (d>0 and l[j]<st) or (d<0 and h[j]>st): break          # invalidated first
            if (d>0 and h[j]>=e) or (d<0 and l[j]<=e): ei=j; break
        if ei is None: continue
        risk=abs(e-st)
        if risk<=0 or risk<minrisk_frac*e: continue
        used+=1
        for k in levels:
            tgt=s["C"]+d*k*s["leg"]
            if (d>0 and tgt<=e) or (d<0 and tgt>=e): continue
            rr=abs(tgt-e)/risk
            got=None
            for j in range(ei+1,n):
                if (d>0 and l[j]<=st) or (d<0 and h[j]>=st): got=0;break
                if (d>0 and h[j]>=tgt) or (d<0 and l[j]<=tgt): got=1;break
            if got is None: continue
            res[k].append(got); rrs[k].append(rr)
    return res,rrs,used

def report(name,df,P=1,cost=0.0):
    print(f"\n{'='*86}\n{name}   P={P} ({'PDF 3-candle rule' if P==1 else f'{2*P+1}-candle'})   bars={len(df)}\n{'='*86}")
    for tag,levels in (("FIB levels",FIB),("NON-FIB controls",NONFIB)):
        res,rrs,used=race(df,P,levels,spread=cost)
        print(f"--- {tag} --- (structures traded: {used})")
        print(f"{'level':>8}{'n':>7}{'hit%':>8}{'meanRR':>9}{'medRR':>8}{'expR':>9}{'totR':>10}")
        for k in levels:
            if not res[k]: continue
            hit=np.array(res[k]); rr=np.array(rrs[k])
            # TRUE per-trade expectancy: win pays that trade's own RR, loss pays -1
            R=np.where(hit==1, rr, -1.0)
            print(f"{k:>8.3f}{len(R):>7}{100*hit.mean():>8.1f}{rr.mean():>9.2f}{np.median(rr):>8.2f}"
                  f"{R.mean():>+9.3f}{R.sum():>+10.0f}")

if __name__=="__main__":
    G=load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16")
    B=pd.concat([load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"),
                 load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")])
    B=B[~B.index.duplicated()].sort_index()
    for P in (1,3):
        report("GOLD H1",G,P)
        report("BTC H1",B,P)
