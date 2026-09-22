"""
GOLD-MERGE v1 — liquidity + SMC/ICT, built on the INTERNAL/EXTERNAL distinction.

Why this is not a repeat of structure_sweep.py (which scored -0.391):
that test swept the EXTERNAL low -- the swing low that DEFINES the uptrend.
Breaking it is a trend-break, so the old test was buying breakdowns and
calling them pullbacks. Its own findings doc admits this.

Here the trade is:
  H4 structure BULLISH  (BOS up, taken from the PREVIOUS CLOSED H4 bar)
  + price sweeps an INTERNAL low (inducement inside the leg)
  + closes back above it
  + the EXTERNAL low is still intact
  -> LONG   (mirror for shorts)

The control is the whole point: the SAME engine run on EXTERNAL sweeps.
If internal >> external, the SMC internal/external split carries information.
If internal ~= external, the distinction is decoration.

Causality: H4 context uses only closed H4 bars; M15 pivots are stamped at
their CONFIRMATION bar; entry at the reclaim close; stop floored at an
executable distance (the filter that caught the $0.10 Trident artifact).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

SPREAD = 0.25

def atr(h,l,c,n=20):
    pc=np.concatenate([[c[0]],c[:-1]])
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    return pd.Series(tr).rolling(n).mean().bfill().values

def confirmed_pivots(h,l,P):
    """Return arrays stamped at the CONFIRMATION bar (index i+P), never at i."""
    n=len(h); ph=np.full(n,np.nan); pl=np.full(n,np.nan)
    for i in range(P,n-P):
        if h[i]==h[i-P:i+P+1].max(): ph[i+P]=h[i]
        if l[i]==l[i-P:i+P+1].min(): pl[i+P]=l[i]
    return ph,pl

def htf_bias(h4, P=3):
    """+1 after a close breaks the last confirmed swing high, -1 after a low."""
    h,l,c=h4["high"].values,h4["low"].values,h4["close"].values
    n=len(c); ph,pl=confirmed_pivots(h,l,P)
    bias=np.zeros(n); sh=sl=np.nan; b=0
    for i in range(n):
        if not np.isnan(ph[i]): sh=ph[i]
        if not np.isnan(pl[i]): sl=pl[i]
        if not np.isnan(sh) and c[i]>sh: b=1; sh=np.nan
        if not np.isnan(sl) and c[i]<sl: b=-1; sl=np.nan
        bias[i]=b
    return pd.Series(bias,index=h4.index)

def run(mode="internal", P=3, sess=None, tgt="liq", rr=2.0,
        start="2020-01-01", end="2026-09-16", minfrac=0.0005, minspr=4.0,
        rand=None, maxhold=400):
    m15=load_ohlcv("XAUUSD_15m.csv",start,end)
    h4=load_ohlcv("XAUUSD_4h.csv",start,end)
    bias4=htf_bias(h4,P)
    # causal HTF map: an M15 bar sees only the PREVIOUS CLOSED H4 bar
    shifted=bias4.shift(1)
    bias=shifted.reindex(m15.index,method="ffill").values

    h,l,c=m15["high"].values,m15["low"].values,m15["close"].values
    t=m15.index; n=len(c); A=atr(h,l,c)
    ph,pl=confirmed_pivots(h,l,P)
    hh=t.hour.values
    inses=np.ones(n,bool) if sess is None else ((hh>=sess[0])&(hh<sess[1]))
    rng=np.random.default_rng(rand) if rand is not None else None

    lows=[]; highs=[]          # confirmed swing values, newest last
    ext_lo=ext_hi=np.nan
    trades=[]; busy=-1
    for i in range(n):
        if not np.isnan(pl[i]):
            lows.append((i,pl[i]))
            if np.isnan(ext_lo) or pl[i]<ext_lo: pass
        if not np.isnan(ph[i]): highs.append((i,ph[i]))
        b=bias[i]
        if np.isnan(b) or b==0 or A[i]<=0: continue
        lows=[(j,v) for j,v in lows if i-j<2000]
        highs=[(j,v) for j,v in highs if i-j<2000]
        if b>0 and len(lows)>=2:
            ext_lo=min(v for _,v in lows)                     # anchor of the leg
            internals=[v for _,v in lows if v>ext_lo]         # inducement levels
            lvls = internals if mode=="internal" else [ext_lo]
            if not lvls: continue
            lvl = max(lvls) if mode=="internal" else ext_lo   # nearest inducement
            if not (l[i] < lvl and c[i] > lvl): continue
            if mode=="internal" and l[i] <= ext_lo: continue  # external must hold
            d=1
        elif b<0 and len(highs)>=2:
            ext_hi=max(v for _,v in highs)
            internals=[v for _,v in highs if v<ext_hi]
            lvls = internals if mode=="internal" else [ext_hi]
            if not lvls: continue
            lvl = min(lvls) if mode=="internal" else ext_hi
            if not (h[i] > lvl and c[i] < lvl): continue
            if mode=="internal" and h[i] >= ext_hi: continue
            d=-1
        else: continue
        if not inses[i] or i<=busy: continue
        e=c[i]
        s = l[i] if d>0 else h[i]
        minrisk=max(minfrac*e, minspr*SPREAD)
        s = min(s, e-minrisk) if d>0 else max(s, e+minrisk)
        risk=abs(e-s)
        if risk<=0: continue
        if rng is not None: d = 1 if rng.random()<0.5 else -1; s = e-risk*d
        if tgt=="liq":
            pool=[v for _,v in (highs if d>0 else lows)]
            pool=[v for v in pool if (v>e if d>0 else v<e)]
            if not pool: continue
            g = min(pool) if d>0 else max(pool)
        else:
            g = e + d*rr*risk
        if abs(g-e)/risk < 1.0: continue
        R=None; end_i=min(i+maxhold,n-1)
        for j in range(i+1,end_i+1):
            if (d>0 and l[j]<=s) or (d<0 and h[j]>=s): R=-1.0; break
            if (d>0 and h[j]>=g) or (d<0 and l[j]<=g): R=abs(g-e)/risk; break
        if R is None: R=np.clip(((c[end_i]-e) if d>0 else (e-c[end_i]))/risk,-1,abs(g-e)/risk)
        trades.append(dict(time=t[i],dir=d,entry=e,stop=s,target=g,
                           R=R-SPREAD/risk,risk=risk))
        busy=j if R is not None else i+1
    return pd.DataFrame(trades)

def boot(R,n=4000,seed=0):
    R=np.asarray(R,float)
    if len(R)==0: return 1.0
    rng=np.random.default_rng(seed); ix=rng.integers(0,len(R),(n,len(R)))
    return float((R[ix].mean(1)<=0).mean())

def show(tag,d):
    if not len(d): print(f"  {tag:<34} n=0"); return None
    R=d.R.values
    print(f"  {tag:<34} n={len(R):<5} win={100*(R>0).mean():5.1f}%  expR={R.mean():+.3f}"
          f"  totR={R.sum():+7.1f}  P(<=0)={100*boot(R):5.1f}%")
    return R

if __name__=="__main__":
    print("="*86); print("GOLD-MERGE v1 — INTERNAL (signal) vs EXTERNAL (control), same engine")
    print("="*86)
    for tgt,rr in (("liq",0),("fixed",2.0),("fixed",3.0)):
        lab=f"target={'next liquidity' if tgt=='liq' else f'{rr:.0f}R'}"
        print(f"\n### {lab}")
        for sess,sl in ((None,"all hours"),((12,16),"12-16 UTC")):
            di=run("internal",sess=sess,tgt=tgt,rr=rr)
            de=run("external",sess=sess,tgt=tgt,rr=rr)
            print(f"  -- {sl} --")
            show("INTERNAL sweep (signal)",di)
            show("EXTERNAL sweep (control)",de)
