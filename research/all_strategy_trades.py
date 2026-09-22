"""
Consolidated trade ledger across every strategy that can emit dated trades.

Purpose: see WHEN each strategy won and lost, on one timeline, so we can ask
the question that aggregate stats hide -- do different strategies win on the
SAME days? If they do, they are not independent edges; they are one market
move being counted several times.

Gold only (the trader's instrument). One row per trade, R computed from the
trade's own risk so strategies with different sizing are comparable.
"""
import _paths, numpy as np, pandas as pd, traceback

def norm(trades, name):
    out=[]
    for t in trades:
        if "time" not in t: continue
        risk = t.get("qty",0)*abs(t.get("entry",0)-t.get("stop",0))
        if risk<=0: continue
        R=t.get("pnl",0.0)/risk
        out.append(dict(strategy=name, time=pd.Timestamp(t["time"]),
                        dir=t.get("dir",""), entry=round(t.get("entry",0),2),
                        stop=round(t.get("stop",0),2),
                        target=round(t.get("target",0) or 0,2),
                        exit=t.get("exit_r",""), R=round(R,3),
                        outcome=("WIN" if R>0.05 else ("LOSS" if R<-0.05 else "BE"))))
    return out

JOBS=[]
def job(name, fn): JOBS.append((name,fn))

import liquidity_run, liquidity_sweep, structure_sweep, inducement_fvg
import volume_profile_rejection, mayne_playbook, prior_day_levels_backtest
import trident_killzone

job("LiquidityRun",      lambda: liquidity_run.run("XAUUSD_15m.csv"))
job("LiquiditySweep",    lambda: liquidity_sweep.run("XAUUSD_15m.csv"))
job("StructureSweep",    lambda: structure_sweep.run("XAUUSD_15m.csv"))
job("Inducement+FVG",    lambda: inducement_fvg.run("XAUUSD_15m.csv"))
job("VolProfileReject",  lambda: volume_profile_rejection.run("XAUUSD_15m.csv"))
job("MaynePlaybook",     lambda: mayne_playbook.run("XAUUSD_1h.csv"))
job("PriorDayLevels",    lambda: prior_day_levels_backtest.run("XAUUSD_1h.csv"))
job("TridentKillzone",   lambda: trident_killzone.run("XAUUSD_15m.csv"))

rows=[]
for name,fn in JOBS:
    try:
        r=fn()
        tr = r[0] if isinstance(r,tuple) else r
        n=norm(tr,name); rows+=n
        print(f"  {name:<20} {len(n):>5} trades")
    except Exception as e:
        print(f"  {name:<20} FAILED: {type(e).__name__}: {str(e)[:80]}")

d=pd.DataFrame(rows)
if len(d):
    d=d.sort_values("time").reset_index(drop=True)
    d["date"]=d.time.dt.date
    d.to_csv("/home/user/Binance-Trade-/DATA/all_strategy_trades.csv",index=False)
    print(f"\nTOTAL {len(d)} trades across {d.strategy.nunique()} strategies")
    print(f"span {d.time.min()} -> {d.time.max()}")
    print("\nPER STRATEGY")
    g=d.groupby("strategy").agg(n=("R","size"),wins=("outcome",lambda s:(s=="WIN").sum()),
        losses=("outcome",lambda s:(s=="LOSS").sum()),be=("outcome",lambda s:(s=="BE").sum()),
        expR=("R","mean"),totR=("R","sum"))
    g["win%"]=(100*g.wins/g.n).round(1)
    print(g.round(3).to_string())
