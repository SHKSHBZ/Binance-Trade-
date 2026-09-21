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

def race(df,P=1,levels=FIB,spread=0.0,minrisk_frac=0.0005,min_leg_atr=1.0,
         maxhold=200,rand_entry=None):
    """Enter on the break of C's candle, race each level against the stop.

    maxhold  : HARD time limit. Without it a long sits open for years until a
               trending market drifts into any target, while the loss stays
               capped at -1R -- that is what faked the first two runs.
    rand_entry: seed for the NULL. Keeps the identical stop/target geometry but
               puts the entry on a random bar, so drift is priced in."""
    S,h,l,c,A,n=structures(df,P,min_leg_atr)
    o=df["open"].values
    res={k:[] for k in levels}; rrs={k:[] for k in levels}; sd={k:[] for k in levels}
    used=0
    rng=np.random.default_rng(rand_entry) if rand_entry is not None else None
    for s_ in S:
        d=s_["dir"]; e=s_["trig"]; st=s_["stop"]
        # --- HONEST FILL ---------------------------------------------------
        # C is a swing LOW confirmed P bars later, so by the first bar we are
        # allowed to act on (conf+1) price has usually ALREADY rallied past
        # h[C]. Filling at h[C] then buys at a stale price the market left
        # behind -- a guaranteed-favourable fill. A stop order fills at the
        # trigger only if the market is still on the right side of it;
        # otherwise it fills at the open.
        ei=None; fill=None
        for j in range(s_["conf"]+1, min(s_["conf"]+1+200, n)):
            if (d>0 and o[j]>=e) or (d<0 and o[j]<=e):
                ei=j; fill=o[j]; break            # gapped/already through
            if (d>0 and l[j]<st) or (d<0 and h[j]>st): break
            if (d>0 and h[j]>=e) or (d<0 and l[j]<=e):
                ei=j; fill=e; break
        if ei is None: continue
        e=fill
        if rng is not None:                      # NULL: same geometry, random bar
            ei=int(rng.integers(30,n-maxhold-2))
            e=c[ei]; st=e-d*abs(s_["trig"]-s_["stop"])
        risk=abs(e-st)
        if risk<=0 or risk<minrisk_frac*e: continue
        used+=1
        for k in levels:
            tgt=(s_["C"]+d*k*s_["leg"]) if rng is None else (e+d*k*s_["leg"])
            if (d>0 and tgt<=e) or (d<0 and tgt>=e): continue
            rr=abs(tgt-e)/risk
            end=min(ei+maxhold,n-1); got=None
            for j in range(ei+1,end+1):
                if (d>0 and l[j]<=st) or (d<0 and h[j]>=st): got=0;break
                if (d>0 and h[j]>=tgt) or (d<0 and l[j]<=tgt): got=1;break
            if got is None:                      # time-stopped: mark to market
                mtm=((c[end]-e) if d>0 else (e-c[end]))/risk
                res[k].append(np.clip(mtm,-1,rr)); rrs[k].append(rr); sd[k].append(d)
                continue
            res[k].append(float(rr) if got else -1.0); rrs[k].append(rr); sd[k].append(d)
    return res,rrs,sd,used

def report(name,df,P=1,cost=0.25,maxhold=200):
    print(f"\n{'='*92}\n{name}  P={P}  maxhold={maxhold} bars\n{'='*92}")
    for tag,levels in (("FIB",FIB),("NON-FIB control",NONFIB)):
        res,rrs,sd,used=race(df,P,levels,maxhold=maxhold)
        nres,_,_,_=race(df,P,levels,maxhold=maxhold,rand_entry=7)
        print(f"--- {tag} --- (structures: {used})")
        print(f"{'level':>7}{'n':>6}{'expR':>9}{'LONG':>9}{'SHORT':>9}{'NULL':>9}{'vs null':>9}")
        for k in levels:
            if not res[k]: continue
            R=np.array(res[k]); D=np.array(sd[k]); N=np.array(nres[k]) if nres[k] else np.array([0.])
            lo=R[D==1].mean() if (D==1).any() else float('nan')
            sh=R[D==-1].mean() if (D==-1).any() else float('nan')
            print(f"{k:>7.3f}{len(R):>6}{R.mean():>+9.3f}{lo:>+9.3f}{sh:>+9.3f}{N.mean():>+9.3f}{R.mean()-N.mean():>+9.3f}")

if __name__=="__main__":
    G=load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16")
    B=pd.concat([load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"),
                 load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")])
    B=B[~B.index.duplicated()].sort_index()
    for mh in (100,400):
        report("GOLD H1",G,3,maxhold=mh)
        report("BTC H1",B,3,maxhold=mh)
