"""Replicate the trader's engine EXACTLY, then re-run it causally.
Difference isolated: (a) H4 context applied from the H4 bar's OPEN (their
merge_asof backward) vs only after it CLOSES; (b) swings usable at their own
bar vs only after the 5 right-hand candles confirm them."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def swings(df, length=5, causal=False):
    h=df["high"].values; l=df["low"].values; n=len(df)
    sh=np.full(n,np.nan); sl=np.full(n,np.nan)
    for i in range(length, n-length):
        w=slice(i-length, i+length+1)
        if h[i]==h[w].max() and (h[i]>h[i-length:i]).all() and (h[i]>h[i+1:i+length+1]).all():
            sh[i+length if causal else i]=h[i]
        if l[i]==l[w].min() and (l[i]<l[i-length:i]).all() and (l[i]<l[i+1:i+length+1]).all():
            sl[i+length if causal else i]=l[i]
    # running "last established swing"
    return pd.Series(sh,index=df.index).ffill(), pd.Series(sl,index=df.index).ffill()

def process_htf(h4, length=5, causal=False):
    sh,sl = swings(h4,length,causal)
    o=h4["open"].values; c=h4["close"].values; hi=h4["high"].values; lo=h4["low"].values
    n=len(h4)
    ob_top=np.full(n,np.nan); ob_bot=np.full(n,np.nan); ob_type=np.zeros(n)
    cur_t=cur_b=np.nan; cur_ty=0
    shv=sh.values; slv=sl.values
    for i in range(n):
        bull = (not np.isnan(shv[i])) and c[i] > shv[i]
        bear = (not np.isnan(slv[i])) and c[i] < slv[i]
        if bull:
            for j in range(i-1, max(-1,i-20), -1):
                if c[j] < o[j]: cur_t,cur_b,cur_ty = hi[j],lo[j],1; break
        elif bear:
            for j in range(i-1, max(-1,i-20), -1):
                if c[j] > o[j]: cur_t,cur_b,cur_ty = hi[j],lo[j],-1; break
        ob_top[i],ob_bot[i],ob_type[i]=cur_t,cur_b,cur_ty
    return pd.DataFrame({"ob_top":ob_top,"ob_bottom":ob_bot,"ob_type":ob_type},index=h4.index)

def run(causal_htf, causal_swings, spread=0.0, rr=2.0):
    m15=load_ohlcv("XAUUSD_15m.csv","2022-06-24","2026-09-01")
    h4=m15.resample("4h").agg(open=("open","first"),high=("high","max"),
                              low=("low","min"),close=("close","last")).dropna()
    ctx=process_htf(h4,5,causal_swings)
    if causal_htf:
        ctx.index = ctx.index + pd.Timedelta(hours=4)   # only known once the H4 bar closes
    merged=pd.merge_asof(m15, ctx, left_index=True, right_index=True, direction="backward")
    msh,msl = swings(m15,5,causal_swings)
    merged["sh"]=msh; merged["sl"]=msl
    o=merged["open"].values;h=merged["high"].values;l=merged["low"].values;c=merged["close"].values
    obt=merged["ob_top"].values;obb=merged["ob_bottom"].values;oby=merged["ob_type"].values
    SH=merged["sh"].values; SL=merged["sl"].values; t=merged.index; n=len(c)
    trades=[]; busy=-1
    for i in range(1,n-1):
        if i<=busy: continue
        if np.isnan(obt[i]) or oby[i]==0: continue
        if oby[i]==-1:
            inob = (h[i]>=obb[i]) and (c[i]<=obt[i])
            msb  = (not np.isnan(SL[i])) and c[i]<SL[i] and c[i-1]>=SL[i-1]
            if inob and msb and not np.isnan(SH[i]) and SH[i]>c[i]:
                e=c[i]; s=SH[i]; d=-1
            else: continue
        else:
            inob = (l[i]<=obt[i]) and (c[i]>=obb[i])
            msb  = (not np.isnan(SH[i])) and c[i]>SH[i] and c[i-1]<=SH[i-1]
            if inob and msb and not np.isnan(SL[i]) and SL[i]<c[i]:
                e=c[i]; s=SL[i]; d=1
            else: continue
        risk=abs(e-s)
        if risk<=0: continue
        tgt = e+rr*risk if d>0 else e-rr*risk
        j=i+1; R=None
        while j<n:
            if d>0:
                if l[j]<=s: R=-1.0;break
                if h[j]>=tgt: R=rr;break
            else:
                if h[j]>=s: R=-1.0;break
                if l[j]<=tgt: R=rr;break
            j+=1
        if R is None: j=n-1; R=((c[j]-e) if d>0 else (e-c[j]))/risk
        trades.append(R - spread/risk); busy=j
    return np.array(trades)
