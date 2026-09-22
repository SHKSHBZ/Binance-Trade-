"""
Line-by-line Python transliteration of tools/gold_merge.indie, run over the
same gold 1H data, compared trade-for-trade against the tested replica.
If the two lists differ, the chart is not showing the tested strategy.
"""
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
nan=float('nan')

def indie_run(df):
    H,L,C=df.high.values,df.low.values,df.close.values; n=len(C)
    def s(arr,i,k): return arr[i-k] if i-k>=0 else nan
    st=dict(big_hi=nan,big_lo=nan,trend=0.0,sm_hi=nan,sm_lo=nan,sand_lo=nan,sand_hi=nan,
            lo_b0=nan,lo_b1=nan,lo_b2=nan,lo_b3=nan,hi_b0=nan,hi_b1=nan,hi_b2=nan,hi_b3=nan,count=nan,
            t_dir=0.0,t_entry=nan,t_stop=nan,t_target=nan,t_age=0.0)
    trades=[]
    for i in range(n):
        hi=lambda k: s(H,i,k); lo=lambda k: s(L,i,k); cl=lambda k: s(C,i,k)
        bsh=all(hi(16)>=hi(k) for k in range(33) if k!=16)
        bsl=all(lo(16)<=lo(k) for k in range(33) if k!=16)
        if bsh: st['big_hi']=hi(16)
        if bsl: st['big_lo']=lo(16)
        if st['big_hi']==st['big_hi'] and cl(0)>st['big_hi']: st['trend']=1.0; st['big_hi']=nan
        if st['big_lo']==st['big_lo'] and cl(0)<st['big_lo']: st['trend']=-1.0; st['big_lo']=nan
        ssh=all(hi(3)>=hi(k) for k in range(7) if k!=3)
        ssl=all(lo(3)<=lo(k) for k in range(7) if k!=3)
        st['count']=1.0 if st['count']!=st['count'] else st['count']+1.0
        if st['count']>=500.0:
            st['count']=0.0
            for p in ('lo','hi'):
                st[p+'_b3']=st[p+'_b2']; st[p+'_b2']=st[p+'_b1']; st[p+'_b1']=st[p+'_b0']; st[p+'_b0']=nan
        if ssh:
            st['sand_lo']=st['sm_lo']; st['sm_hi']=hi(3)
            if st['hi_b0']!=st['hi_b0'] or hi(3)<st['hi_b0']: st['hi_b0']=hi(3)
        if ssl:
            st['sand_hi']=st['sm_hi']; st['sm_lo']=lo(3)
            if st['lo_b0']!=st['lo_b0'] or lo(3)>st['lo_b0']: st['lo_b0']=lo(3)
        mlo=st['lo_b0']
        for b in ('lo_b1','lo_b2','lo_b3'):
            if st[b]==st[b] and (mlo!=mlo or st[b]>mlo): mlo=st[b]
        mhi=st['hi_b0']
        for b in ('hi_b1','hi_b2','hi_b3'):
            if st[b]==st[b] and (mhi!=mhi or st[b]<mhi): mhi=st[b]
        wlo=mlo if (mlo==mlo and st['sand_lo']==st['sand_lo'] and mlo>st['sand_lo']) else nan
        whi=mhi if (mhi==mhi and st['sand_hi']==st['sand_hi'] and mhi<st['sand_hi']) else nan
        closed=False
        if st['t_dir']!=0.0:
            st['t_age']+=1.0; done=False
            if st['t_dir']>0 and (lo(0)<=st['t_stop'] or hi(0)>=st['t_target']): done=True
            if st['t_dir']<0 and (hi(0)>=st['t_stop'] or lo(0)<=st['t_target']): done=True
            if st['t_age']>=100.0: done=True
            if done:
                st['t_dir']=0.0; st['t_entry']=st['t_stop']=st['t_target']=nan; closed=True
        if st['t_dir']==0.0 and not closed:
            mr=0.0005*cl(0); mr=1.0 if mr<1.0 else mr
            gl=st['trend']>0.5 and wlo==wlo and lo(0)<wlo and cl(0)>wlo and lo(0)>st['sand_lo']
            gs=st['trend']<-0.5 and whi==whi and hi(0)>whi and cl(0)<whi and hi(0)<st['sand_hi']
            if gl:
                e=cl(0); sp=lo(0); sp=e-mr if sp>e-mr else sp
                st.update(t_dir=1.0,t_entry=e,t_stop=sp,t_target=e+3*(e-sp),t_age=0.0)
                trades.append((df.index[i],1,round(e,3),round(sp,3)))
            elif gs:
                e=cl(0); sp=hi(0); sp=e+mr if sp<e+mr else sp
                st.update(t_dir=-1.0,t_entry=e,t_stop=sp,t_target=e-3*(sp-e),t_age=0.0)
                trades.append((df.index[i],-1,round(e,3),round(sp,3)))
    return trades

if __name__=="__main__":
    g=load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16")
    ind=indie_run(g)
    ref=pd.read_csv("/home/user/Binance-Trade-/DATA/gold_merge_indicator_trades.csv",parse_dates=["time"])
    ref_set={(t,int(d),round(e,3),round(s_,3)) for t,d,e,s_ in zip(ref.time,ref["dir"],ref.entry,ref.stop)}
    ind_set=set(ind)
    both=ref_set&ind_set
    print(f"indicator transliteration: {len(ind)} trades | tested replica: {len(ref)} trades | identical: {len(both)}")
    print(f"only in indicator: {len(ind_set-ref_set)}   only in replica: {len(ref_set-ind_set)}")
    for x in sorted(ind_set^ref_set)[:6]: print("   diff:",x, "IND" if x in ind_set else "REF")

    print("\ndates of all differences:")
    diffs=sorted(ind_set^ref_set)
    print("   " + ", ".join(sorted({str(x[0].date()) for x in diffs})))
    # score the indicator's OWN trades with the same exit rules
    H,L,C=g.high.values,g.low.values,g.close.values; idx={t:i for i,t in enumerate(g.index)}
    R=[]; D=[]; T=[]
    for t,d,e,s_ in ind:
        i=idx[t]; risk=abs(e-s_); tg=e+d*3*risk; r=None
        for j in range(i+1,min(i+101,len(C))):
            if (d>0 and L[j]<=s_) or (d<0 and H[j]>=s_): r=-1.0;break
            if (d>0 and H[j]>=tg) or (d<0 and L[j]<=tg): r=3.0;break
        if r is None: j=min(i+100,len(C)-1); r=max(-1,min(3,((C[j]-e) if d>0 else (e-C[j]))/risk))
        R.append(r-0.25/risk); D.append(d); T.append(t)
    R=np.array(R); D=np.array(D)
    print(f"\nINDICATOR's own trades: n={len(R)} win={100*(R>0).mean():.1f}% expR={R.mean():+.3f}  LONG {R[D==1].mean():+.3f}  SHORT {R[D==-1].mean():+.3f}")
