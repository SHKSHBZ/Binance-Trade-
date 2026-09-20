"""
SMT divergence — does a correlated pair's NON-CONFIRMATION predict reversal?

This is the one component of the Kane playbook with no prior in this project.
NQ/ES is unreachable here, so the test uses BTC/ETH (corr ~0.8, same band as
EURUSD/GBPUSD ~0.85; NQ/ES is ~0.95).

Setup, strictly causal:
  - confirmed pivots on the LEADER (strength P, stamped at the CONFIRMATION
    bar, never the pivot bar),
  - at the pivot bar, record the FOLLOWER's price at that same timestamp,
  - later, when the leader sweeps its swing high, ask whether the follower
    also exceeded its reference high.
      both exceed          -> CONFIRMATION
      leader only          -> SMT DIVERGENCE (the claimed reversal signal)
  - measure the next N bars: MFE/MAE in ATR units, in the REVERSAL direction.

Three controls, because co-moving pairs make near-ties look like signals:
  1. CONFIRMATION events (the signal's own opposite) — the key comparison,
  2. random bars/random side,
  3. leader and follower swapped.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def atr(h,l,c,n=20):
    pc=np.concatenate([[c[0]],c[:-1]])
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    return pd.Series(tr).rolling(n).mean().bfill().values

def load_pair():
    b=pd.concat([load_ohlcv("BTCUSDT_15m_2023_to_2025.csv"),
                 load_ohlcv("BTCUSDT_15m_Jan_to_Jul2026.csv")])
    b=b[~b.index.duplicated()].sort_index()
    e=load_ohlcv("ETHUSDT_15m.csv")
    ix=b.index.intersection(e.index)
    return b.loc[ix], e.loc[ix]

def events(L,F,P=5,tol=0.0,fwd=24):
    """L = leader, F = follower. Returns DataFrame of sweep events."""
    lh,ll,lc=L["high"].values,L["low"].values,L["close"].values
    fh,fl,fc=F["high"].values,F["low"].values,F["close"].values
    n=len(lc); AL=atr(lh,ll,lc); AF=atr(fh,fl,fc)
    # confirmed pivots on the leader, stamped at confirmation
    refh=np.full(n,np.nan); refh_bar=np.full(n,-1,int)
    refl=np.full(n,np.nan); refl_bar=np.full(n,-1,int)
    ch=cl=np.nan; chb=clb=-1
    for i in range(n):
        p=i-P
        if p>=P and p+P<n:
            if lh[p]==lh[p-P:p+P+1].max(): ch=lh[p]; chb=p
            if ll[p]==ll[p-P:p+P+1].min(): cl=ll[p]; clb=p
        refh[i]=ch; refh_bar[i]=chb; refl[i]=cl; refl_bar[i]=clb
    rows=[]
    for i in range(P*2+20, n-fwd-1):
        if AL[i]<=0 or AF[i]<=0: continue
        for side in (1,-1):                      # 1 = sweep a HIGH (short bias)
            ref = refh[i] if side==1 else refl[i]
            rb  = refh_bar[i] if side==1 else refl_bar[i]
            if np.isnan(ref) or rb<0 or rb>=i: continue
            swept = (lh[i]>ref) if side==1 else (ll[i]<ref)
            if not swept: continue
            # follower's reference at the SAME timestamp as the leader's pivot
            fref = fh[rb] if side==1 else fl[rb]
            thr  = tol*AF[i]
            if side==1:  f_confirmed = fh[i] > fref + thr
            else:        f_confirmed = fl[i] < fref - thr
            d=-side                               # reversal direction
            e=lc[i]; seg=slice(i+1,i+1+fwd)
            mfe=((e-ll[seg].min()) if d<0 else (lh[seg].max()-e))/AL[i]
            mae=((lh[seg].max()-e) if d<0 else (e-ll[seg].min()))/AL[i]
            rows.append(dict(i=i,side=side,divg=int(not f_confirmed),
                             mfe=mfe,mae=mae,held=int(mfe>mae),
                             fwd=((e-lc[i+fwd]) if d<0 else (lc[i+fwd]-e))/AL[i]))
    return pd.DataFrame(rows)

def control(L,n_draw,fwd=24,seed=0):
    h,l,c=L["high"].values,L["low"].values,L["close"].values
    n=len(c);A=atr(h,l,c);rng=np.random.default_rng(seed);rows=[]
    for k,i in enumerate(rng.integers(30,n-fwd-1,n_draw)):
        if A[i]<=0: continue
        d=-1 if k%2==0 else 1; e=c[i]; seg=slice(i+1,i+1+fwd)
        mfe=((e-l[seg].min()) if d<0 else (h[seg].max()-e))/A[i]
        mae=((h[seg].max()-e) if d<0 else (e-l[seg].min()))/A[i]
        rows.append(dict(mfe=mfe,mae=mae,held=int(mfe>mae)))
    return pd.DataFrame(rows)

def line(tag,d):
    if not len(d):
        print(f"  {tag:<34} n=0"); return
    r=d["mfe"].mean()/d["mae"].mean() if d["mae"].mean()>0 else float("nan")
    extra=f"  fwd={d['fwd'].mean():+.3f}" if "fwd" in d.columns else ""
    print(f"  {tag:<34} n={len(d):<6} held={100*d['held'].mean():5.1f}%  "
          f"MFE={d['mfe'].mean():.2f} MAE={d['mae'].mean():.2f} ratio={r:.3f}{extra}")

if __name__=="__main__":
    B,E=load_pair()
    print(f"BTC/ETH aligned: {len(B)} bars  {B.index[0]} -> {B.index[-1]}")
    r=np.corrcoef(np.diff(np.log(B.close.values)),np.diff(np.log(E.close.values)))[0,1]
    print(f"15m log-return correlation: {r:.3f}")
    for P in (5,10):
        for tol in (0.0,0.05,0.25):
            ev=events(B,E,P=P,tol=tol)
            if not len(ev): continue
            print(f"\n=== LEADER=BTC  pivots P={P}  tolerance={tol} ATR ===")
            line("SMT DIVERGENCE (signal)", ev[ev["divg"]==1])
            line("CONFIRMATION  (control 1)", ev[ev["divg"]==0])
            for s,nm in ((1,"sweep HIGH -> short"),(-1,"sweep LOW  -> long")):
                sub=ev[(ev["divg"]==1)&(ev.side==s)]
                if len(sub): line(f"   div, {nm}", sub)
    ev=events(B,E,P=5,tol=0.0)
    print("\n=== controls ===")
    c=control(B,len(ev)); print(f"  random levels (control 2)          n={len(c)}  held={100*c.held.mean():5.1f}%  ratio={c.mfe.mean()/c.mae.mean():.3f}")
    ev2=events(E,B,P=5,tol=0.0)
    print(f"  LEADER=ETH swapped (control 3):")
    line("   SMT DIVERGENCE", ev2[ev2["divg"]==1]); line("   CONFIRMATION", ev2[ev2["divg"]==0])
