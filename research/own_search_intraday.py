import _paths, numpy as np, pandas as pd
from own_search import BUILD, CHECK, HOLD, COST
from own_search_nyet import d, run
from own_search_final import show
T=lambda hh,mm=0: hh*60+mm
V={}
for rr in (1.0,1.5,2.0):
    for fl in (T(16),T(16,45)):
        V[f"NY 9-10ET breakout trend rr{rr} flat {fl//60}:{fl%60:02d}ET"]=run(d,T(9),T(10),T(10),T(15),rr=rr,flat=fl)
V["NY breakout, half-range stop rr2 flat16:45"]=run(d,T(9),T(10),T(10),T(15),rr=2.0,flat=T(16,45),stop_frac=0.5)
for per,(a,b) in {"BUILD":BUILD,"CHECK":CHECK,"2026":HOLD}.items():
    print(f"=== {per} ===")
    for k,t in V.items(): show(k,t,a,b)
