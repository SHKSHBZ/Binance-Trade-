"""Why does UT Bot + MA Sabres lose? Uses the trader's own run() unchanged,
only varying the cost setting, timeframe and instrument."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
import ut_sabres_backtest as ut
from data_loader import load_ohlcv

def stats(tr, label):
    if not tr: print(f"  {label:<40} no trades"); return
    R=np.array([t["R"] for t in tr]); D=np.array([t["dir"] for t in tr])
    stopd=np.array([abs(t["entry"]-t["stop"])/t["entry"] for t in tr])
    t0,t1=tr[0]["time"],tr[-1]["time"]; yrs=max((t1-t0).days/365.25,0.1)
    print(f"  {label:<40} n={len(R):<5}({len(R)/yrs:>4.0f}/yr) win={100*(R>0).mean():4.1f}%  "
          f"avgR={R.mean():+.3f}  LONG {R[D=='LONG'].mean():+.3f}  SHORT {R[D=='SHORT'].mean():+.3f}  "
          f"median stop {100*np.median(stopd):.2f}% of price")

print("UT Bot (key 2, ATR 1) + TEMA-50 baseline — trader's own run(), costs varied\n")
cases=[("BTC 15m 2023-25","BTCUSDT_15m_2023_to_2025.csv",0.0004),
       ("BTC 1h  2023-25","BTCUSDT_1h_2023_to_2025.csv",0.0004),
       ("BTC 1h  2026",   "BTCUSDT_1h_Jan_to_Jul2026.csv",0.0004),
       ("GOLD 15m",       "XAUUSD_15m.csv",0.00003),
       ("GOLD 1h",        "XAUUSD_1h.csv",0.00003)]
for lab,f,comm in cases:
    for c_,tag in ((comm,"with costs"),(0.0,"ZERO costs")):
        ut.COMMISSION_PCT=c_
        tr,_,_=ut.run(f)
        stats(tr,f"{lab} {tag}")
    # how much of 1R the round-trip cost eats, at the median stop
    ut.COMMISSION_PCT=comm; tr,_,_=ut.run(f)
    sd=np.median([abs(t["entry"]-t["stop"])/t["entry"] for t in tr])
    print(f"    -> round-trip cost = {2*comm/sd:.2f}R per trade at the median stop\n")
