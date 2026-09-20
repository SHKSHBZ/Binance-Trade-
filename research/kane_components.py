"""
KANE playbook — isolation test of the two NOVEL components on gold.

The sweep -> rejection -> reversal shape has already failed ~10x in this
project, so rebuilding the whole machine is not the cheap way to learn.
Two parts of this playbook have never been tested here:

  A) INVERSION ZONE  — an FVG that price closes fully through flips polarity
                       (bull FVG closed downward becomes resistance).
                       Claim: price rejects it on the retest.
  B) MIDPOINT TARGET — after a sweep of a dealing-range extreme, price is
                       drawn to the 50% of that range ("base hit").
                       Note the prior: gold does NOT mean-revert intraday
                       (measured earlier in this project), so this should fail.

Both are measured against controls, causally. Nothing here is a strategy yet.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def atr(h,l,c,n=20):
    pc=np.concatenate([[c[0]],c[:-1]])
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    return pd.Series(tr).rolling(n).mean().bfill().values

def pivots(h,l,P=3):
    n=len(h);ph=np.full(n,np.nan);pl=np.full(n,np.nan)
    for i in range(P,n-P):
        if h[i]==h[i-P:i+P+1].max(): ph[i+P]=h[i]   # stamped at CONFIRMATION bar
        if l[i]==l[i-P:i+P+1].min(): pl[i+P]=l[i]
    return ph,pl

# ---------------------------------------------------------------- A
def inversion_zones(df,fwd=24):
    """Every FVG; whether it later inverted; and what happened on the retest."""
    h,l,c=df["high"].values,df["low"].values,df["close"].values
    n=len(c);A=atr(h,l,c)
    rows=[]
    for i in range(2,n-1):
        for kind in ("bull","bear"):
            if kind=="bull" and not (l[i]>h[i-2]): continue
            if kind=="bear" and not (h[i]<l[i-2]): continue
            lo,hi=(h[i-2],l[i]) if kind=="bull" else (h[i],l[i-2])
            ce=0.5*(lo+hi)
            inv=None
            for j in range(i+1,min(i+400,n)):          # did it inverte?
                if kind=="bull" and c[j]<lo: inv=j;break
                if kind=="bear" and c[j]>hi: inv=j;break
            if inv is None: continue
            ret=None
            for j in range(inv+1,min(inv+200,n)):      # retest of the flipped zone
                if kind=="bull" and h[j]>=ce: ret=j;break   # now RESISTANCE
                if kind=="bear" and l[j]<=ce: ret=j;break   # now SUPPORT
            if ret is None or ret+fwd>=n or A[ret]<=0: continue
            d=-1 if kind=="bull" else 1                # expected reaction direction
            seg=slice(ret+1,ret+1+fwd)
            mfe=((ce-l[seg].min()) if d<0 else (h[seg].max()-ce))/A[ret]
            mae=((h[seg].max()-ce) if d<0 else (ce-l[seg].min()))/A[ret]
            fwdret=((ce-c[ret+fwd]) if d<0 else (c[ret+fwd]-ce))/A[ret]
            rows.append(dict(kind=kind,i=ret,mfe=mfe,mae=mae,fwd=fwdret,
                             held=int(mfe>mae)))
    return pd.DataFrame(rows)

def control_levels(df,n_draw,fwd=24,seed=0):
    """Control: random bars, random side, same forward window."""
    h,l,c=df["high"].values,df["low"].values,df["close"].values
    n=len(c);A=atr(h,l,c);rng=np.random.default_rng(seed);rows=[]
    idx=rng.integers(30,n-fwd-1,n_draw)
    for k,i in enumerate(idx):
        if A[i]<=0: continue
        d=-1 if k%2==0 else 1
        ce=c[i]; seg=slice(i+1,i+1+fwd)
        mfe=((ce-l[seg].min()) if d<0 else (h[seg].max()-ce))/A[i]
        mae=((h[seg].max()-ce) if d<0 else (ce-l[seg].min()))/A[i]
        rows.append(dict(mfe=mfe,mae=mae,fwd=((ce-c[i+fwd]) if d<0 else (c[i+fwd]-ce))/A[i],
                         held=int(mfe>mae)))
    return pd.DataFrame(rows)

# ---------------------------------------------------------------- B
def midpoint_test(df,P=3,minw=1.5,buf=0.0002,spread=0.25):
    """Dealing range from confirmed H1 swings. On a sweep of an extreme that
    closes back inside, does price reach the 50% midpoint before the sweep
    extreme? Reports the base rate AND the tradeable expectancy."""
    h,l,c=df["high"].values,df["low"].values,df["close"].values
    n=len(c);A=atr(h,l,c);ph,pl=pivots(h,l,P)
    last_h=last_l=np.nan; hits=[];trades=[]
    busy=-1
    for i in range(n):
        if not np.isnan(ph[i]): last_h=ph[i]
        if not np.isnan(pl[i]): last_l=pl[i]
        if np.isnan(last_h) or np.isnan(last_l) or last_h<=last_l: continue
        w=last_h-last_l
        if A[i]<=0 or w<minw*A[i]: continue
        mid=0.5*(last_h+last_l)
        for side in (1,-1):
            lvl = last_h if side==1 else last_l
            swept = (h[i]>lvl) if side==1 else (l[i]<lvl)
            closed_back = (c[i]<lvl) if side==1 else (c[i]>lvl)
            if not (swept and closed_back): continue
            e=c[i]
            if side==1 and not (e>mid): continue     # need room down to midpoint
            if side==-1 and not (e<mid): continue
            s = h[i]*(1+buf) if side==1 else l[i]*(1-buf)
            risk=abs(e-s)
            if risk<=0 or risk<max(0.0005*e,4*spread): continue
            rr=abs(mid-e)/risk
            got=None
            for j in range(i+1,n):
                if side==1:
                    if h[j]>=s: got=0;break
                    if l[j]<=mid: got=1;break
                else:
                    if l[j]<=s: got=0;break
                    if h[j]>=mid: got=1;break
            if got is None: continue
            hits.append(got)
            if i>busy:
                R=(rr if got else -1.0)-spread/risk
                trades.append(dict(R=R,rr=rr,risk=risk,side=side,got=got))
                busy=j
    return np.array(hits),pd.DataFrame(trades)

def boot(R,n=5000,seed=0):
    R=np.asarray(R,float)
    if len(R)==0: return 1.0
    rng=np.random.default_rng(seed);ix=rng.integers(0,len(R),(n,len(R)))
    return float((R[ix].mean(1)<=0).mean())

if __name__=="__main__":
    for tf,f in [("H1","XAUUSD_1h.csv"),("M15","XAUUSD_15m.csv")]:
        d=load_ohlcv(f,"2020-01-01","2026-09-16") if tf=="H1" else load_ohlcv(f,"2022-06-24","2026-09-16")
        print(f"\n{'='*74}\nGOLD {tf}   {d.index[0].date()} -> {d.index[-1].date()}   bars={len(d)}\n{'='*74}")
        print("--- A) INVERSION ZONES: does the flipped zone reject on retest? ---")
        z=inversion_zones(d); ctl=control_levels(d,len(z) if len(z) else 500)
        if len(z):
            print(f"  inverted-zone retests  n={len(z):<5} held={100*z.held.mean():5.1f}%  "
                  f"MFE={z.mfe.mean():.2f} MAE={z.mae.mean():.2f} ratio={z.mfe.mean()/z.mae.mean():.3f}  fwd24={z.fwd.mean():+.3f}")
            print(f"  CONTROL random levels  n={len(ctl):<5} held={100*ctl.held.mean():5.1f}%  "
                  f"MFE={ctl.mfe.mean():.2f} MAE={ctl.mae.mean():.2f} ratio={ctl.mfe.mean()/ctl.mae.mean():.3f}  fwd24={ctl.fwd.mean():+.3f}")
            for k in ("bull","bear"):
                s=z[z.kind==k]
                if len(s): print(f"    {k}-FVG inverted  n={len(s):<5} held={100*s.held.mean():5.1f}%  ratio={s.mfe.mean()/s.mae.mean():.3f}")
        print("--- B) MIDPOINT TARGET: reached before the sweep extreme? ---")
        hits,tr=midpoint_test(d)
        if len(hits):
            print(f"  base rate: midpoint reached first {100*hits.mean():.1f}%  (n={len(hits)})")
        if len(tr):
            R=tr.R.values
            print(f"  as a trade: n={len(tr)}  win={100*tr.got.mean():.1f}%  medianRR={tr.rr.median():.2f}  "
                  f"expR={R.mean():+.3f}  totR={R.sum():+.1f}  P(<=0)={100*boot(R):.1f}%")
            print(f"  breakeven win rate needed at that RR: {100/(1+tr.rr.median()):.1f}%")
