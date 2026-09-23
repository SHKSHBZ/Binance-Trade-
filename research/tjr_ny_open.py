"""
TJR-style NY-open liquidity sweep + MSS (SMC), as close as the data allows.

Rules encoded:
  levels   : Asia H/L (19:00-02:00 ET), London H/L (02:00-08:00 ET), PDH/PDL
  window   : sweep must happen 09:30-11:30 ET (New York time, DST-aware)
  sweep    : a bar trades beyond a level and a close is back inside within 3 bars
  MSS      : a later bar (by 12:00 ET) closes beyond the most recent confirmed
             swing point that preceded the sweep (the higher low for a short)
  entry    : close of the MSS bar   [APPROXIMATION: no 1m data for BOS/IFVG]
  stop     : beyond the sweep wick  (the rules' conservative stop), floored
  target   : nearest opposing session level (DOL), or fixed 2R / 2.5R
  exit     : stop, target, or 16:00 ET close. One trade per day.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def run(df, P=2, tgt="dol", rr=2.0, spread=0.25, spread_frac=None, minrr=1.0,
        rand=None, fail_bars=3):
    et = df.index.tz_localize("UTC").tz_convert("America/New_York")
    d = df.copy(); d["et"] = et; d["day"] = et.date; d["hm"] = et.hour*60+et.minute
    H,L,C = d.high.values, d.low.values, d.close.values
    n=len(C)
    # confirmed swings (stamped at confirmation bar)
    sh=np.full(n,np.nan); sl=np.full(n,np.nan)
    for i in range(P,n-P):
        if H[i]==H[i-P:i+P+1].max(): sh[i+P]=H[i]
        if L[i]==L[i-P:i+P+1].min(): sl[i+P]=L[i]
    last_sh=pd.Series(sh).ffill().values; last_sl=pd.Series(sl).ffill().values
    rng=np.random.default_rng(rand) if rand is not None else None
    days=sorted(d.day.unique()); pos={dy:np.where(d.day.values==dy)[0] for dy in days}
    trades=[]
    for k in range(1,len(days)):
        dy=days[k]; prev=days[k-1]; ix=pos[dy]; px=pos[prev]
        if len(ix)<10 or len(px)<10: continue
        hm=d.hm.values
        asia=np.concatenate([px[hm[px]>=19*60], ix[hm[ix]<2*60]])
        lon=ix[(hm[ix]>=2*60)&(hm[ix]<8*60)]
        if len(asia)<3 or len(lon)<3: continue
        lv_hi=[H[asia].max(), H[lon].max(), H[px].max()]
        lv_lo=[L[asia].min(), L[lon].min(), L[px].min()]
        win=ix[(hm[ix]>=9*60+30)&(hm[ix]<11*60+30)]
        done=False
        for i in win:
            if done: break
            for side in (-1,1):             # -1: swept a HIGH -> short ; +1: swept a LOW -> long
                if done: break
                lvls = lv_hi if side==-1 else lv_lo
                hit=[v for v in lvls if (H[i]>v if side==-1 else L[i]<v)]
                if not hit: continue
                lvl = max(hit) if side==-1 else min(hit)
                # fail back inside within fail_bars
                j_fail=None; ext=H[i] if side==-1 else L[i]
                for j in range(i, min(i+fail_bars, n)):
                    ext = max(ext,H[j]) if side==-1 else min(ext,L[j])
                    if (side==-1 and C[j]<lvl) or (side==1 and C[j]>lvl): j_fail=j; break
                if j_fail is None: continue
                ref = last_sl[i-1] if side==-1 else last_sh[i-1]   # swing that led into the sweep
                if ref!=ref: continue
                # MSS: close beyond ref, by 12:00 ET
                j_mss=None
                for j in range(j_fail, n):
                    if d.day.values[j]!=dy or hm[j]>=12*60: break
                    ext = max(ext,H[j]) if side==-1 else min(ext,L[j])
                    if (side==-1 and C[j]<ref) or (side==1 and C[j]>ref): j_mss=j; break
                if j_mss is None: continue
                e=C[j_mss]; dirn = -side if False else (1 if side==1 else -1)   # long after low sweep
                sp = spread if spread_frac is None else e*spread_frac
                stop = ext + (sp if dirn<0 else -sp)
                minrisk=max(0.0005*e, 4*sp)
                if abs(e-stop)<minrisk: stop = e+minrisk if dirn<0 else e-minrisk
                if rng is not None:
                    dirn = 1 if rng.random()<0.5 else -1
                    stop = e - dirn*abs(e-stop)
                risk=abs(e-stop)
                if tgt=="dol":
                    opp=[v for v in (lv_lo if dirn<0 else lv_hi) if (v<e if dirn<0 else v>e)]
                    if not opp: continue
                    tp = max(opp) if dirn<0 else min(opp)
                    if abs(tp-e)/risk < minrr: continue
                else:
                    tp = e + dirn*rr*risk
                # manage until 16:00 ET same day
                R=None
                for j in range(j_mss+1, n):
                    if d.day.values[j]!=dy or hm[j]>=16*60:
                        R=((C[j-1]-e) if dirn>0 else (e-C[j-1]))/risk; break
                    if (dirn>0 and L[j]<=stop) or (dirn<0 and H[j]>=stop): R=-1.0; break
                    if (dirn>0 and H[j]>=tp) or (dirn<0 and L[j]<=tp): R=abs(tp-e)/risk; break
                if R is None: continue
                trades.append(dict(time=d.index[j_mss],dir=dirn,entry=e,stop=stop,target=tp,
                                   risk=risk,rr=abs(tp-e)/risk,R=R-sp/risk))
                done=True
    return pd.DataFrame(trades)

def boot(R,n=4000,seed=0):
    R=np.asarray(R,float)
    if not len(R): return 1.0
    ix=np.random.default_rng(seed).integers(0,len(R),(n,len(R)))
    return float((R[ix].mean(1)<=0).mean())

def report(tag,d,years):
    if not len(d): print(f"  {tag:<34} n=0"); return
    R=d.R.values; D=d["dir"].values; T=pd.DatetimeIndex(d.time); mid=T[len(T)//2]
    eq=1.0
    for r in R: eq*=1+0.01*r
    print(f"  {tag:<34} n={len(R):<4}({len(R)/years:>3.0f}/yr) win={100*(R>0).mean():4.1f}% "
          f"avgRR={d.rr.median():.1f} expR={R.mean():+.3f} P={100*boot(R):4.1f}%  "
          f"L {R[D==1].mean() if (D==1).any() else float('nan'):+.2f} S {R[D==-1].mean() if (D==-1).any() else float('nan'):+.2f}  "
          f"tr {R[T<=mid].mean():+.3f} te {R[T>mid].mean():+.3f}  1%risk/yr {100*(eq**(1/years)-1):+.1f}%")

if __name__=="__main__":
    b=pd.concat([load_ohlcv("BTCUSDT_5m_2023_to_2025.csv"),load_ohlcv("BTCUSDT_5m_Jan_to_Jul2026.csv")])
    b=b[~b.index.duplicated()].sort_index(); yb=(b.index[-1]-b.index[0]).days/365.25
    g=load_ohlcv("XAUUSD_15m.csv","2022-06-24","2026-09-16"); yg=(g.index[-1]-g.index[0]).days/365.25
    print(f"BTC 5m {b.index[0].date()}..{b.index[-1].date()}   |   GOLD 15m {g.index[0].date()}..{g.index[-1].date()}\n")
    for name,df,yrs,kw in (("BTC 5m",b,yb,dict(spread_frac=0.0001)),("GOLD 15m (coarse)",g,yg,dict(spread=0.25))):
        print(f"### {name}")
        for tag,tk in (("target = opposing session level",dict(tgt="dol")),
                       ("target = fixed 2R",dict(tgt="fixed",rr=2.0)),
                       ("target = fixed 2.5R",dict(tgt="fixed",rr=2.5))):
            report(tag, run(df,**kw,**tk), yrs)
        nul=[run(df,**kw,tgt="dol",rand=s).R.mean() for s in range(5)]
        print(f"  NULL (same trades, random side, DOL target): {np.mean(nul):+.3f} +/- {np.std(nul):.3f}\n")
