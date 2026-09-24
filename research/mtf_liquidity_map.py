"""
Multi-timeframe S&R / liquidity-pool mapping strategy, per the trader's spec:

  Phase 1 (per HTF):  swing highs/lows = S&R levels.  Two swing highs (or lows)
                       within eps of each other = a liquidity pool (BSL/SSL).
  Phase 2 (pairing):  1W levels -> confirm/execute on 1D
                       1D levels -> confirm/execute on 4H
                       12H levels -> confirm/execute on 1H
                       4H levels  -> confirm/execute on 1H or 15M

Rule, made concrete and testable (SMC "liquidity sweep" reading of the spec,
same reading used for every SMC-style strategy in this repo):
  - HTF level is swept (LTF wick trades through it) -> watch window opens.
  - LTF "confirmation" = price breaks back through its own recent LTF swing
    in the fade direction (a mini structure shift) within W LTF bars.
  - Entry: LTF confirmation candle close.
  - Stop:  sweep extreme + small ATR(LTF) buffer.
  - Target: nearest opposing HTF level beyond entry; RMIN floor enforced.
  - Direction: fade the sweep (liquidity-grab-and-reverse, the SMC premise).

Causal: HTF pivot at bar i (window +-n) is only known n HTF bars later, and is
mapped to the LTF timeline by wall-clock timestamp, not by bar index, so a
level is never usable before the HTF candle that confirms it has actually
closed. 1M scalping execution (Phase 3) is NOT tested: no 1-minute gold/BTC
data exists in this repo, so it can't be tested honestly.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def atr(h,l,c,n=14):
    pc=np.concatenate([[c[0]],c[:-1]])
    return pd.Series(np.maximum(h-l,np.maximum(abs(h-pc),abs(l-pc)))).rolling(n).mean().bfill().values

def pivots(x,k,hi=True):
    n=len(x); out=[]
    for i in range(k,n-k):
        w=x[i-k:i+k+1]
        if (x[i]==w.max()) if hi else (x[i]==w.min()): out.append(i)
    return out

def htf_levels(df_htf, k, eps):
    """Return list of dicts: time_confirmed (wall clock), price, side(+1 low/-1 high), pool(bool)."""
    h,l = df_htf.high.values, df_htf.low.values
    idx = df_htf.index
    ph, pl = pivots(h,k,True), pivots(l,k,False)
    levels=[]
    for i in ph:
        if i+k>=len(idx): continue
        levels.append(dict(t=idx[i+k], price=h[i], side=-1, pool=False))
    for i in pl:
        if i+k>=len(idx): continue
        levels.append(dict(t=idx[i+k], price=l[i], side=1, pool=False))
    # flag pools: any two same-side levels within eps of each other
    for side in (-1,1):
        s=[x for x in levels if x["side"]==side]
        for a in range(len(s)):
            for b in range(a+1,len(s)):
                if abs(s[a]["price"]-s[b]["price"])/min(s[a]["price"],s[b]["price"])<=eps:
                    s[a]["pool"]=True; s[b]["pool"]=True
    levels.sort(key=lambda x:x["t"])
    return levels

def resample(df, rule):
    o = df.resample(rule).agg(dict(open="first",high="max",low="min",close="last",volume="sum")).dropna()
    return o

RULES = {"1W":"1W-MON","1D":"1D","12H":"12h","4H":"4h"}
KPIV  = {"1W":2,"1D":2,"12H":2,"4H":3}   # fractal half-width per HTF

def run(df_ltf, df_1h_base, htf, eps=0.0015, only_pools=False, W=20, k_ltf=3,
        atr_mult=0.25, rmin=1.5, maxhold=400, cost=0.25, cost_frac=None, rand=None):
    htf_df = resample(df_1h_base, RULES[htf])
    levels_all = htf_levels(htf_df, KPIV[htf], eps)
    if only_pools:
        levels_all = [x for x in levels_all if x["pool"]]
    if not levels_all: return pd.DataFrame()

    h,l,c = df_ltf.high.values, df_ltf.low.values, df_ltf.close.values
    idx = df_ltf.index; n=len(idx); A = atr(h,l,c)
    lvl_t = np.array([x["t"].value for x in levels_all])
    lvl_p = np.array([x["price"] for x in levels_all])
    lvl_s = np.array([x["side"] for x in levels_all])

    ph, pl = pivots(h,k_ltf,True), pivots(l,k_ltf,False)
    ltf_swing_hi = np.full(n, np.nan); ltf_swing_lo = np.full(n, np.nan)
    for i in ph:
        if i+k_ltf<n: ltf_swing_hi[i+k_ltf]=h[i]
    for i in pl:
        if i+k_ltf<n: ltf_swing_lo[i+k_ltf]=l[i]
    last_hi = pd.Series(ltf_swing_hi).ffill().values
    last_lo = pd.Series(ltf_swing_lo).ffill().values

    rng = np.random.default_rng(rand) if rand is not None else None
    swept = np.zeros(len(levels_all), bool)
    trades=[]; busy=-1
    for t in range(1, n):
        avail = lvl_t <= idx[t-1].value   # level must be confirmed strictly before this bar
        # find first available, unswept level crossed on this bar
        for j in np.where(avail & ~swept)[0]:
            side = lvl_s[j]; lv = lvl_p[j]
            if side==-1 and h[t]>lv:
                swept[j]=True
                if t<=busy: continue
                ext=h[t]
                for w in range(t, min(t+W,n)):
                    if h[w]>ext: ext=h[w]
                    if not np.isnan(last_lo[w]) and c[w]<last_lo[w]:
                        trig=w; break
                else: continue
                d=-1; e=c[trig]; stop=ext+atr_mult*A[trig]
                opp=lvl_p[(lvl_s==1)&(lvl_t<=idx[trig].value)&(lvl_p<e)]
                tgt = opp.max() if len(opp) else e-rmin*(stop-e)
                risk=stop-e
                if risk<=0 or tgt>=e: continue
                rr=(e-tgt)/risk
                if rr<rmin: continue
                trades.append(_close(d,trig,e,stop,tgt,rr,risk,idx,h,l,c,maxhold,cost,cost_frac,rng))
                busy=trades[-1].pop("_busy")
            elif side==1 and l[t]<lv:
                swept[j]=True
                if t<=busy: continue
                ext=l[t]
                for w in range(t, min(t+W,n)):
                    if l[w]<ext: ext=l[w]
                    if not np.isnan(last_hi[w]) and c[w]>last_hi[w]:
                        trig=w; break
                else: continue
                d=1; e=c[trig]; stop=ext-atr_mult*A[trig]
                opp=lvl_p[(lvl_s==-1)&(lvl_t<=idx[trig].value)&(lvl_p>e)]
                tgt = opp.min() if len(opp) else e+rmin*(e-stop)
                risk=e-stop
                if risk<=0 or tgt<=e: continue
                rr=(tgt-e)/risk
                if rr<rmin: continue
                trades.append(_close(d,trig,e,stop,tgt,rr,risk,idx,h,l,c,maxhold,cost,cost_frac,rng))
                busy=trades[-1].pop("_busy")
    return pd.DataFrame(trades)

def _close(d,fill,e,stop,tgt,rr,risk,idx,h,l,c,maxhold,cost,cost_frac,rng):
    if rng is not None:
        d = 1 if rng.random()<0.5 else -1
        stop=e-d*risk; tgt=e+d*rr*risk
    sp = cost if cost_frac is None else e*cost_frac
    n=len(c); R=None; j=fill
    for j in range(fill+1, min(fill+1+maxhold,n)):
        if (d<0 and h[j]>=stop) or (d>0 and l[j]<=stop): R=-1.0; break
        if (d<0 and l[j]<=tgt) or (d>0 and h[j]>=tgt): R=rr; break
    if R is None:
        j=min(fill+maxhold,n-1); R=max(-1.0,min(rr,((c[j]-e) if d>0 else (e-c[j]))/risk))
    return dict(time=idx[fill],dir=d,entry=e,stop=stop,target=tgt,rr=rr,R=R-sp/risk,_busy=j)

def boot(R,n=4000,seed=0):
    R=np.asarray(R,float)
    if not len(R): return 1.0
    ix=np.random.default_rng(seed).integers(0,len(R),(n,len(R))); return float((R[ix].mean(1)<=0).mean())

if __name__=="__main__":
    gold_1h = load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16")
    gold_15 = load_ohlcv("XAUUSD_15m.csv","2022-06-24","2026-09-16")
    gold_4h = load_ohlcv("XAUUSD_4h.csv","2020-01-01","2026-09-16")
    b1=pd.concat([load_ohlcv("BTCUSDT_1h_2023_to_2025.csv"),load_ohlcv("BTCUSDT_1h_Jan_to_Jul2026.csv")]); b1=b1[~b1.index.duplicated()].sort_index()
    b15=pd.concat([load_ohlcv("BTCUSDT_15m_2023_to_2025.csv"),load_ohlcv("BTCUSDT_15m_Jan_to_Jul2026.csv")]); b15=b15[~b15.index.duplicated()].sort_index()

    pairs = [
        ("GOLD","1W->1D", gold_1h.resample("1D").agg(dict(open="first",high="max",low="min",close="last",volume="sum")).dropna(), gold_1h, "1W", dict(cost=0.25)),
        ("GOLD","1D->4H", gold_4h, gold_1h, "1D", dict(cost=0.25)),
        ("GOLD","12H->1H", gold_1h, gold_1h, "12H", dict(cost=0.25)),
        ("GOLD","4H->1H",  gold_1h, gold_1h, "4H",  dict(cost=0.25)),
        ("GOLD","4H->15M", gold_15, gold_1h, "4H",  dict(cost=0.25)),
        ("BTC","1D->4H",  b1.resample("4h").agg(dict(open="first",high="max",low="min",close="last",volume="sum")).dropna(), b1, "1D", dict(cost_frac=0.0006)),
        ("BTC","4H->1H",  b1, b1, "4H", dict(cost_frac=0.0006)),
        ("BTC","4H->15M", b15, b1, "4H", dict(cost_frac=0.0006)),
    ]
    print(f"{'mkt':<5}{'pair':<10}{'pools':<7}{'n':>5}{'/yr':>5}{'win%':>7}{'medRR':>7}{'expR':>8}{'P':>7}{'LONG':>8}{'SHORT':>8}{'train':>8}{'test':>8}")
    for mkt,pair,df_ltf,df_1h,htf,kw in pairs:
        for pools in (False,True):
            d = run(df_ltf, df_1h, htf, only_pools=pools, **kw)
            yrs=(df_ltf.index[-1]-df_ltf.index[0]).days/365.25
            if not len(d):
                print(f"{mkt:<5}{pair:<10}{str(pools):<7}  n=0"); continue
            R=d.R.values; D=d["dir"].values; T=pd.DatetimeIndex(d.time); mid=T[len(T)//2]
            f=lambda x: f"{x.mean():+8.3f}" if len(x) else "     nan"
            print(f"{mkt:<5}{pair:<10}{str(pools):<7}{len(R):>5}{len(R)/yrs:>5.0f}{100*(R>0).mean():>7.1f}{d.rr.median():>7.1f}"
                  f"{R.mean():>+8.3f}{100*boot(R):>6.1f}%{f(R[D==1])}{f(R[D==-1])}{f(R[T<=mid])}{f(R[T>mid])}")
