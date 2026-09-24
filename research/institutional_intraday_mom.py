"""
Institutional / academic strategy #2: Intraday momentum (Gao, Han, Li & Zhou 2018, JFE).
Paper: return from the previous close to 10:00 ET (overnight + first half hour) predicts the
return of the LAST half hour. Trade: at the start of the last window, go long if the morning
return was positive, short if negative; flat at window end. One trade per day.
Gold's daily close is 17:00 ET; US-session close used for the 'day' = 16:00/17:00 ET variants.
BUILD <= 2024, TEST 2025-2026 (not used to pick anything).
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def prep(df):
    et=df.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    s=pd.Series(df.close.values,index=et); s=s[~s.index.duplicated()]
    return s

def px_at(s, day, hh, mm, prev=False):
    t=day+pd.Timedelta(hours=hh,minutes=mm)-(pd.Timedelta(days=1) if prev else pd.Timedelta(0))
    # price = close of the last 15m bar ENDING at t  (bar opening at t-15m)
    return s.get(t-pd.Timedelta(minutes=15),np.nan)

def run(s, pred, trade, cost_frac):
    days=pd.DatetimeIndex(s.index.normalize().unique())
    days=days[days.dayofweek<5]
    out=[]
    for d in days:
        (a_prev,a_h,a_m),(b_h,b_m)=pred
        p0=px_at(s,d,a_h,a_m,prev=a_prev) if a_prev is not None else np.nan
        p1=px_at(s,d,b_h,b_m)
        (c_h,c_m),(e_h,e_m)=trade
        q0=px_at(s,d,c_h,c_m); q1=px_at(s,d,e_h,e_m)
        if np.isnan([p0,p1,q0,q1]).any() or p0==p1: continue
        sig=np.sign(p1/p0-1); r=sig*(q1/q0-1)-cost_frac
        out.append((d,sig,r))
    return pd.DataFrame(out,columns=["day","sig","r"]).set_index("day")

def show(lab,t):
    def seg(x):
        if len(x)<10: return "   n/a"
        tstat=x.r.mean()/x.r.std()*np.sqrt(len(x))
        return f"n={len(x):4d} avg {1e4*x.r.mean():+5.1f}bp hit {100*(x.r>0).mean():3.0f}% t={tstat:+4.1f}"
    b=t[:"2024-12-31"]; o=t["2025-01-01":]
    yr=" ".join(f"{y}:{1e4*v:+.1f}" for y,v in t.r.groupby(t.index.year).mean().items())
    print(f"{lab:<46} BUILD {seg(b)} | TEST {seg(o)} | bp/yr {yr}")

if __name__=="__main__":
    g=prep(load_ohlcv("XAUUSD_15m.csv"))
    cat=lambda a,b:(lambda x:x[~x.index.duplicated()].sort_index())(pd.concat([load_ohlcv(a),load_ohlcv(b)]))
    bt=prep(cat("BTCUSDT_15m_2023_to_2025.csv","BTCUSDT_15m_Jan_to_Jul2026.csv"))
    P={"prev 17:00 -> 10:00 (paper's first half hr)":((True,17,0),(10,0)),
       "09:30 -> 10:00 only":((False,9,30),(10,0)),
       "prev 17:00 -> 15:30 (paper's 2nd predictor)":((True,17,0),(15,30))}
    T={"trade 15:30-16:00 (paper)":((15,30),(16,0)),
       "trade 15:00-16:00":((15,0),(16,0)),
       "trade 10:00-16:00 (hold the day)":((10,0),(16,0))}
    for name,s,cf in (("GOLD",g,0.25/2500),("BTC",bt,0.0006)):
        print(f"\n===== {name} =====")
        for pn,pv in P.items():
            for tn,tv in T.items():
                if pn.startswith("prev 17:00 -> 15:30") and not tn.startswith("trade 15:30"): continue
                show(f"{pn[:22]} | {tn[:22]}",run(s,pv,tv,cf))
