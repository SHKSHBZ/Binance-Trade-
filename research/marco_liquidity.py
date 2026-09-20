"""
Marco Trade's Liquidity Playbook — causal backtest.

PDF rules:
  HTF (M30): mark a high/low that was RESPECTED and caused price to move away
             -> resting liquidity. Level stays valid while UNSWEPT.
  LTF (M5/M15): inside a session window, price returns and trades BEYOND the
             level (runs stops), fails to continue, and CLOSES back across it
             -> the trap.  swept HIGH -> SHORT.  swept LOW -> LONG.
  Stop:    beyond the sweep wick ("always cover the last high/low").
  Target:  the opposing respected liquidity pool (NOT a fixed R).
  One trade per level; level is consumed once swept.

Causality enforced:
  - an M30 swing is only CONFIRMED pivot+P bars later,
  - and only usable by the LTF after that M30 bar has CLOSED,
  - "respected" displacement measured only with bars up to confirmation.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def atr(h,l,c,n=14):
    pc=np.concatenate([[c[0]],c[:-1]])
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    return pd.Series(tr).rolling(n).mean().bfill().values

def build_levels(m30, P=3, K=2.0, eq_only=False, eq_tol=0.0008):
    """Return list of dicts: {price, side, avail_time} ; side +1 = high (sell-side
    liquidity above), -1 = low. Only 'respected' (displaced >= K*ATR) levels."""
    h=m30["high"].values; l=m30["low"].values; c=m30["close"].values
    t=m30.index; n=len(c); A=atr(h,l,c)
    lv=[]
    for p in range(P, n-P):
        conf = p+P                      # confirmation bar
        if conf>=n: break
        # pivot high?
        if h[p]==h[p-P:p+P+1].max():
            disp = h[p]-l[p:conf+1].min()          # how far price moved away, causal
            if A[conf]>0 and disp >= K*A[conf]:
                lv.append({"price":h[p],"side":1,"avail":t[conf]+pd.Timedelta(minutes=30)})
        if l[p]==l[p-P:p+P+1].min():
            disp = h[p:conf+1].max()-l[p]
            if A[conf]>0 and disp >= K*A[conf]:
                lv.append({"price":l[p],"side":-1,"avail":t[conf]+pd.Timedelta(minutes=30)})
    if eq_only:   # keep only levels that pair with another within tolerance (equal H/L)
        keep=[]
        for i,a in enumerate(lv):
            for j,b in enumerate(lv):
                if i!=j and a["side"]==b["side"] and abs(a["price"]-b["price"])/a["price"]<eq_tol:
                    keep.append(a); break
        lv=keep
    return lv

def run(ltf_file="XAUUSD_15m.csv", start="2022-06-24", end="2026-09-01",
        P=3, K=2.0, WAIT=12, sess=(13,16), eq_only=False, spread=0.25, buf=0.0002,
        tgt_mode="near", fixed_rr=2.0):
    ltf=load_ohlcv(ltf_file,start,end)
    m30=ltf.resample("30min").agg(open=("open","first"),high=("high","max"),
                                  low=("low","min"),close=("close","last")).dropna()
    levels=build_levels(m30,P,K,eq_only)
    if not levels: return np.array([]),0
    lv=sorted(levels,key=lambda x:x["avail"])
    H=ltf["high"].values;L=ltf["low"].values;C=ltf["close"].values;T=ltf.index
    n=len(C); hh=T.hour
    inses = np.ones(n,bool) if sess is None else ((hh>=sess[0])&(hh<sess[1]))
    avail=np.array([x["avail"] for x in lv]); price=np.array([x["price"] for x in lv])
    side=np.array([x["side"] for x in lv])
    swept=np.zeros(len(lv),bool)          # consumed the moment price trades beyond it
    ptr=0; active=[]
    trades=[]; busy=-1; armed=None; nsweeps=0
    for i in range(n):
        while ptr<len(lv) and avail[ptr]<=T[i]:
            active.append(ptr); ptr+=1
        # ---- progress an armed trap ----
        if armed is not None:
            li,ext,dl = armed
            Lp=price[li]
            if i>dl: armed=None
            elif side[li]==1:
                ext=max(ext,H[i])
                if C[i]<Lp:
                    if i>busy:
                        e=C[i]; s=ext*(1+buf)
                        opp=[price[k] for k in active if (not swept[k]) and side[k]==-1 and price[k]<e]
                        if s>e:
                            if tgt_mode=="fixed": tg=e-fixed_rr*(s-e)
                            elif opp: tg=max(opp) if tgt_mode=="near" else min(opp)
                            else: tg=None
                        else: tg=None
                        if tg is not None:
                            r=_sim(-1,e,s,tg,H,L,C,i,n,spread)
                            trades.append(r); busy=r[1]
                    armed=None
                else: armed=(li,ext,dl)
            else:
                ext=min(ext,L[i])
                if C[i]>Lp:
                    if i>busy:
                        e=C[i]; s=ext*(1-buf)
                        opp=[price[k] for k in active if (not swept[k]) and side[k]==1 and price[k]>e]
                        if s<e:
                            if tgt_mode=="fixed": tg=e+fixed_rr*(e-s)
                            elif opp: tg=min(opp) if tgt_mode=="near" else max(opp)
                            else: tg=None
                        else: tg=None
                        if tg is not None:
                            r=_sim(1,e,s,tg,H,L,C,i,n,spread)
                            trades.append(r); busy=r[1]
                    armed=None
                else: armed=(li,ext,dl)
        # ---- sweeps consume levels ALWAYS (market reality), arm only in-session ----
        still=[]
        for k in active:
            if swept[k]: continue
            hit = (side[k]==1 and H[i]>price[k]) or (side[k]==-1 and L[i]<price[k])
            if hit:
                swept[k]=True; nsweeps+=1
                if armed is None and inses[i]:
                    armed=(k, H[i] if side[k]==1 else L[i], i+WAIT)
            else:
                still.append(k)
        active=still
    R=np.array([x[0] for x in trades])
    return R, nsweeps

def _sim(d,e,s,tgt,H,L,C,i,n,spread):
    risk=abs(e-s); j=i+1; R=None
    while j<n:
        if d>0:
            if L[j]<=s: R=-1.0;break
            if H[j]>=tgt: R=(tgt-e)/risk;break
        else:
            if H[j]>=s: R=-1.0;break
            if L[j]<=tgt: R=(e-tgt)/risk;break
        j+=1
    if R is None: j=n-1; R=((C[j]-e) if d>0 else (e-C[j]))/risk
    return (R-spread/risk, j, abs(tgt-e)/risk)
