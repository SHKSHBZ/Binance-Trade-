"""Per-trade anatomy of the trader's 82 trades: context at entry (closed candles only) + what happened after."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

L=pd.read_csv("../DATA/ledger_82_trades.csv"); L["date"]=pd.to_datetime(L.date)
g=load_ohlcv("XAUUSD_15m.csv")
et=g.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
g["et"]=et; g["hr"]=et.hour+et.minute/60; g["sday"]=(et+pd.Timedelta(hours=6)).normalize()
sd=g.groupby("sday").agg(O=("open","first"),H=("high","max"),L=("low","min"),C=("close","last"))
tr=np.maximum(sd.H-sd.L,np.maximum((sd.H-sd.C.shift()).abs(),(sd.L-sd.C.shift()).abs()))
sd["datr"]=tr.rolling(14).mean().shift(1); sd["PDH"]=sd.H.shift(1); sd["PDL"]=sd.L.shift(1); sd["PDC"]=sd.C.shift(1)
sd["d_sma20"]=sd.C.rolling(20).mean().shift(1); sd["d_prevC"]=sd.C.shift(1)
g=g.join(sd[["O","datr","PDH","PDL","PDC","d_sma20","d_prevC"]],on="sday")
asia=g[(g.hr>=18)|(g.hr<2)].groupby("sday").agg(AH=("high","max"),AL=("low","min"))
g=g.join(asia,on="sday")
c=g.close
g["ema80"]=c.ewm(span=80,adjust=False).mean(); g["ema800"]=c.ewm(span=800,adjust=False).mean()
dl=c.diff(); up=dl.clip(lower=0).ewm(alpha=1/14).mean(); dn=(-dl.clip(upper=0)).ewm(alpha=1/14).mean(); g["rsi"]=100-100/(1+up/dn)
tr15=np.maximum(g.high-g.low,np.maximum((g.high-c.shift()).abs(),(g.low-c.shift()).abs()))
g["atr15"]=tr15.rolling(14).mean(); g["atr15_5d"]=tr15.rolling(480).mean()
g["dayH"]=g.groupby("sday").high.cummax(); g["dayL"]=g.groupby("sday").low.cummin()
# 1H and 4H trend from closed higher-timeframe candles
h1=g.close.resample("1h").last().dropna(); h4=g.close.resample("4h").last().dropna()
t1=pd.Series(np.sign(h1.ewm(span=50,adjust=False).mean()-h1.ewm(span=200,adjust=False).mean()).values,index=h1.index+pd.Timedelta(hours=1))
t4=pd.Series(np.sign(h4.ewm(span=50,adjust=False).mean()-h4.ewm(span=200,adjust=False).mean()).values,index=h4.index+pd.Timedelta(hours=4))
t4b=pd.Series(np.sign(h4-h4.ewm(span=50,adjust=False).mean()).values,index=h4.index+pd.Timedelta(hours=4))
g["t1h"]=t1.reindex(g.index,method="ffill"); g["t4h"]=t4.reindex(g.index,method="ffill"); g["px_vs_4hema50"]=t4b.reindex(g.index,method="ffill")
# news-like spike: a 15m bar with range > 3x its 5-day average
g["spike"]=(tr15>3*g.atr15_5d).astype(int); g["spike_today"]=g.groupby("sday").spike.cummax()
H,Lo,C=g.high.values,g.low.values,g.close.values

def sess(hr):
    if 18<=hr or hr<2: return "Asia"
    if hr<8: return "London"
    if hr<9.5: return "NY pre-open/news"
    if hr<11: return "NY open"
    if hr<13: return "NY lunch"
    return "NY afternoon"

rows=[]
for _,t in L.iterrows():
    d=1 if t.dir=="LONG" else -1; e=t.entry; risk=abs(e-t.sl)
    k=g.index.searchsorted(t.date.floor("15min"))-1        # last fully closed bar before entry
    s=g.iloc[k]; datr=s.datr
    look=lambda n: slice(max(0,k-n+1),k+1)
    mv=lambda n: d*(C[k]-C[max(0,k-n)])/datr                 # move in trade direction, in daily ATRs
    # liquidity sweep in the last 2h: price traded beyond a level AGAINST the trade and closed back
    sw=[]
    for name,lvl,side in (("PDH",s.PDH,1),("PDL",s.PDL,-1),("AsiaH",s.AH if s.hr>=2 and s.hr<17 else np.nan,1),("AsiaL",s.AL if s.hr>=2 and s.hr<17 else np.nan,-1)):
        if np.isnan(lvl) or side!=-d: continue
        hh=H[look(8)].max(); ll=Lo[look(8)].min()
        if side==1 and hh>lvl and C[k]<lvl: sw.append(name)
        if side==-1 and ll<lvl and C[k]>lvl: sw.append(name)
    rng=s.PDH-s.PDL
    # stop placement vs recent swing (last 3h)
    swing=H[look(12)].max() if d==-1 else Lo[look(12)].min()
    stop_beyond_swing=(t.sl>=swing) if d==-1 else (t.sl<=swing)
    # AFTER entry
    i=k+1; stop=e-d*risk; tp=e+d*2*risk; mfe=0; mae=0; res_bar=None
    for j in range(i,min(i+500,len(C))):
        fav=d*((H[j] if d==1 else Lo[j])-e)/risk; adv=d*((Lo[j] if d==1 else H[j])-e)/risk
        if (d==1 and Lo[j]<=stop) or (d==-1 and H[j]>=stop):
            mae=-1; res_bar=j; break
        mae=min(mae,adv); mfe=max(mfe,fav)
        if fav>=2 and res_bar is None: res_bar=j; break
    # for losses: did price later reach the 2R target anyway (within 24h after stop)?  -> stop hunt
    hunted=False; went_on=np.nan
    if t.out=="LOSS" and res_bar is not None:
        seg=slice(res_bar+1,min(res_bar+97,len(C)))
        went_on=d*((H[seg].max() if d==1 else Lo[seg].min())-e)/risk
        hunted=went_on>=2
    # MFE for wins beyond 2R (how far the winner ran before hitting the original stop, 5 days)
    run_max=0
    for j in range(i,min(i+500,len(C))):
        if (d==1 and Lo[j]<=stop) or (d==-1 and H[j]>=stop): break
        run_max=max(run_max,d*((H[j] if d==1 else Lo[j])-e)/risk)
    rows.append(dict(
        n=t.n, date=t.date, dir=t.dir, result=t.out, R=t.R, hours_held=t.hrs,
        entry=e, stop_usd=round(risk,2), stop_in_datr=round(risk/datr,2),
        et_time=g.et.iat[k+1].strftime("%H:%M") if k+1<len(g) else "", session=sess(g.hr.iat[min(k+1,len(g)-1)]), weekday=t.date.day_name()[:3],
        with_15m_trend=int(np.sign(s.ema80-s.ema800)==d), with_1h_trend=int(s.t1h==d), with_4h_trend=int(s.t4h==d),
        with_daily_trend=int(np.sign(s.d_prevC-s.d_sma20)==d), price_side_4h_ema50=int(s.px_vs_4hema50==d),
        move_before_1h=round(mv(4),2), move_before_4h=round(mv(16),2), move_before_24h=round(mv(96),2),
        loc_in_prev_day=round((e-s.PDL)/rng,2) if rng>0 else np.nan,
        vs_day_open=int(np.sign(e-s.O)==d), beyond_PDH_PDL=("above PDH" if e>s.PDH else "below PDL" if e<s.PDL else "inside"),
        day_range_used=round((max(s.dayH,H[k])-min(s.dayL,Lo[k]))/datr,2),
        swept_before=",".join(sw) if sw else "", rsi=round(s.rsi,1),
        vol_regime=round(s.atr15/s.atr15_5d,2), news_spike_today=int(s.spike_today),
        stop_behind_swing=int(stop_beyond_swing),
        mae_before_result=round(mae,2), mfe_before_result=round(mfe,2), bars_to_result=(res_bar-i+1) if res_bar is not None else np.nan,
        ran_to_R=round(run_max,1), stop_hunt=int(hunted), after_stop_went_R=round(went_on,1) if not np.isnan(went_on) else np.nan))
A=pd.DataFrame(rows)
A.to_csv("../DATA/my_trades_anatomy.csv",index=False)
print(len(A),"trades analysed; saved DATA/my_trades_anatomy.csv")
