"""EXACT replica of the trader's smc_utils.py + state_machine.py,
with a switch to make the two look-ahead sources causal."""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv

def find_swings(df, length=5, causal=False):
    df=df.copy(); window=length*2+1
    df['rolling_max']=df['high'].rolling(window=window,center=True).max()
    df['rolling_min']=df['low'].rolling(window=window,center=True).min()
    df['is_swing_high']=df['high']==df['rolling_max']
    df['is_swing_low']=df['low']==df['rolling_min']
    sh=np.where(df['is_swing_high'],df['high'],np.nan)
    sl=np.where(df['is_swing_low'],df['low'],np.nan)
    if causal:                      # swing only knowable `length` bars later
        sh=pd.Series(sh,index=df.index).shift(length).values
        sl=pd.Series(sl,index=df.index).shift(length).values
    df['swing_high_val']=sh; df['swing_low_val']=sl
    df['last_swing_high']=df['swing_high_val'].ffill()
    df['last_swing_low']=df['swing_low_val'].ffill()
    return df

def find_msb(df):
    df=df.copy()
    df['bullish_msb']=(df['close']>df['last_swing_high'].shift(1))&(df['close'].shift(1)<=df['last_swing_high'].shift(1))
    df['bearish_msb']=(df['close']<df['last_swing_low'].shift(1))&(df['close'].shift(1)>=df['last_swing_low'].shift(1))
    return df

def identify_order_blocks(df):
    df=df.copy()
    df['is_up_candle']=df['close']>df['open']; df['is_down_candle']=df['close']<df['open']
    tops=[];bots=[];tys=[];ct=cb=np.nan;cty=0
    bm=df['bullish_msb'].values; br=df['bearish_msb'].values
    up=df['is_up_candle'].values; dn=df['is_down_candle'].values
    hi=df['high'].values; lo=df['low'].values
    for i in range(len(df)):
        if bm[i]:
            for j in range(i-1,max(-1,i-20),-1):
                if dn[j]: ct,cb,cty=hi[j],lo[j],1; break
        elif br[i]:
            for j in range(i-1,max(-1,i-20),-1):
                if up[j]: ct,cb,cty=hi[j],lo[j],-1; break
        tops.append(ct);bots.append(cb);tys.append(cty)
    df['ob_top']=tops; df['ob_bottom']=bots; df['ob_type']=tys
    return df

def process_htf(df,swing_length=5,causal=False):
    df=find_swings(df,swing_length,causal); df=find_msb(df); df=identify_order_blocks(df)
    return df

def run(causal_htf=False, causal_swings=False, rr=2.0, spread=0.0):
    m15=load_ohlcv("XAUUSD_15m.csv","2022-06-24","2026-09-01")
    h4=m15.resample("4h").agg(open=("open","first"),high=("high","max"),
                              low=("low","min"),close=("close","last")).dropna()
    htf=process_htf(h4,5,causal_swings)
    cols=['ob_top','ob_bottom','ob_type','last_swing_high','last_swing_low']
    ctx=htf[cols].copy()
    if causal_htf: ctx.index=ctx.index+pd.Timedelta(hours=4)
    merged=pd.merge_asof(m15,ctx,left_index=True,right_index=True,direction='backward')
    merged=find_swings(merged,5,causal_swings)      # NOTE: overwrites HTF swing cols (their bug #3)
    merged=find_msb(merged)
    H=merged['high'].values;L=merged['low'].values;C=merged['close'].values
    OT=merged['ob_top'].values;OB=merged['ob_bottom'].values;OY=merged['ob_type'].values
    BM=merged['bullish_msb'].values;BR=merged['bearish_msb'].values
    SLv=merged['last_swing_low'].values;SHv=merged['last_swing_high'].values
    R=[]; in_tr=False; side=0; ep=sp=tp=0.0
    for i in range(1,len(merged)):
        if in_tr:
            if side==1:
                if L[i]<=sp: R.append(-1.0-spread/abs(ep-sp)); in_tr=False
                elif H[i]>=tp: R.append(rr-spread/abs(ep-sp)); in_tr=False
            else:
                if H[i]>=sp: R.append(-1.0-spread/abs(ep-sp)); in_tr=False
                elif L[i]<=tp: R.append(rr-spread/abs(ep-sp)); in_tr=False
            continue
        oy=OY[i]
        if np.isnan(oy) or oy==0: continue
        in_bull=(oy==1) and (L[i]<=OT[i]) and (C[i]>=OB[i])
        in_bear=(oy==-1) and (H[i]>=OB[i]) and (C[i]<=OT[i])
        if in_bull and BM[i]:
            ep=C[i]; sp=SLv[i]
            if np.isnan(sp) or sp>=ep: sp=OB[i]
            if ep-sp<=0: continue
            tp=ep+(ep-sp)*rr; in_tr=True; side=1
        elif in_bear and BR[i]:
            ep=C[i]; sp=SHv[i]
            if np.isnan(sp) or sp<=ep: sp=OT[i]
            if sp-ep<=0: continue
            tp=ep-(sp-ep)*rr; in_tr=True; side=-1
    return np.array(R)
