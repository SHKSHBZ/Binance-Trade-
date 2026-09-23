"""Change ONE of the assumed choices at a time (gold 15m) to see if any of them
is why the equal-highs/lows strategy loses."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
import eqh_sweep_fvg as m
g=load_ohlcv("XAUUSD_15m.csv","2022-06-24","2026-09-16"); yrs=(g.index[-1]-g.index[0]).days/365.25
BASE=dict(K=5,TMIN=5,TMAX=100,DELTA=0.001,RMIN=2.0)
def go(tag,entry,eps=0.001,glob=None,**kw):
    for k,v in BASE.items(): setattr(m,k,v)
    for k,v in (glob or {}).items(): setattr(m,k,v)
    d=m.run(g,eps=eps,entry=entry,cost=0.25,**kw)
    if not len(d): print(f"  {tag:<34} n=0"); return
    R=d.R.values; T=pd.DatetimeIndex(d.time); mid=T[len(T)//2]
    print(f"  {tag:<34} n={len(R):<4} win={100*(R>0).mean():4.1f}%  expR={R.mean():+.3f}  P={100*m.boot(R):5.1f}%"
          f"  train {R[T<=mid].mean():+.3f} test {R[T>mid].mean():+.3f}")
for entry,lab in (("A","ENTRY A (trigger close)"),("B","ENTRY B (FVG)")):
    print(f"\n### {lab}")
    go("baseline (my choices)",entry)
    for k in (3,8):             go(f"swing points {k} candles each side",entry,glob=dict(K=k))
    for t in (50,200):          go(f"equal highs up to {t} candles apart",entry,glob=dict(TMAX=t))
    for dl in (0.0005,0.002):   go(f"cancel if close >{100*dl:.2f}% beyond",entry,glob=dict(DELTA=dl))
    for a in (0.0,0.5,2.0):     go(f"stop = sweep extreme + {a} ATR",entry,atr_mult=a)
    for r in (1.5,3.0):         go(f"minimum R = {r}",entry,glob=dict(RMIN=r))
    if entry=="B":              go("FVG entry at gap edge, not middle",entry,fvg_at="edge")
