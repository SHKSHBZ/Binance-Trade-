"""The trader's 82 real trades re-sized to a fixed $ risk per trade (Exness lots rounded down to 0.01, min 0.01)."""
import pandas as pd, numpy as np
L=pd.read_csv("DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
days=np.busday_count(L.date.min().date(),L.date.max().date())
def run(pnl,lots):
    eq=np.cumsum(pnl); dd=(eq-np.maximum.accumulate(np.concatenate([[0],eq]))[1:]).min()
    out=dict(total=pnl.sum(),per_day=pnl.sum()/days,dd=dd,worst_loss=pnl.min(),
             lots_med=np.median(lots),lots_min=lots.min(),lots_max=lots.max())
    for start in (2000,5000):
        bal=start+eq; out[f"low_{start}"]=bal.min(); out[f"end_{start}"]=bal[-1]
    m=pd.Series(pnl,index=L.date).resample("ME").sum(); out["months_up"]=f"{(m>0).sum()}/{len(m)}"
    out["best_m"]=m.max(); out["worst_m"]=m.min()
    return out
rows={}
lots=np.full(len(L),0.10); rows["YOUR WAY: fixed 0.10 lot"]=run(L.R.values*L.stop.values*10,lots)
for risk in (100,200,300):
    lots=np.maximum(np.floor(risk/(L.stop.values*100)*100)/100,0.01)
    rows[f"${risk} risk per trade"]=run(L.R.values*L.stop.values*100*lots,lots)
T=pd.DataFrame(rows).T
fmt=lambda v:f"{v:,.0f}" if isinstance(v,(float,np.floating)) and abs(v)>=10 else (f"{v:.2f}" if isinstance(v,(float,np.floating)) else v)
print(T.map(fmt).to_string())
print(f"\n{days} trading days. AED = USD x 3.6725")
for k,r in rows.items(): print(f"{k:<26} total ${r['total']:>7,.0f} = AED {r['total']*3.6725:>7,.0f}  | per day ${r['per_day']:.1f} = AED {r['per_day']*3.6725:.0f}")
