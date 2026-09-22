import sys; sys.path.insert(0,'.')
import _paths, numpy as np, pandas as pd
from data_loader import load_ohlcv
import gold_merge as gm
nan=float('nan'); SPREAD=0.25; MAXHOLD=100; RR=3.0

def run(df, trend="h4", big=12, small=3, level="bucket", nb=4, bsize=500, h4=None, look=2000):
    """level='list'   : exact backtest semantics (list of lows in last `look` bars)
       level='bucket' : chart-friendly -- rolling max of swing lows kept in `nb` buckets of `bsize` bars"""
    h,l,c=df["high"].values,df["low"].values,df["close"].values; n=len(c)
    if trend=="h4": b4=gm.htf_bias(h4,3).shift(1).reindex(df.index,method="ffill").fillna(0).values
    big_hi=big_lo=nan; bias=0; sm_hi=sm_lo=nan; ext_lo=ext_hi=nan
    lows=[]; highs=[]
    bmx=[nan]*nb; bmn=[nan]*nb; cur=0; cnt=0      # bucket rolling max/min
    t_dir=0; out=[]
    for i in range(2*max(big,small)+2, n):
        if trend=="h4": bias=b4[i]
        else:
            p=i-big
            if all(h[p]>=h[p-k] and h[p]>=h[p+k] for k in range(1,big+1)): big_hi=h[p]
            if all(l[p]<=l[p-k] and l[p]<=l[p+k] for k in range(1,big+1)): big_lo=l[p]
            if big_hi==big_hi and c[i]>big_hi: bias=1; big_hi=nan
            if big_lo==big_lo and c[i]<big_lo: bias=-1; big_lo=nan
        cnt+=1
        if cnt>=bsize: cnt=0; cur=(cur+1)%nb; bmx[cur]=nan; bmn[cur]=nan
        q=i-small
        if all(h[q]>=h[q-k] and h[q]>=h[q+k] for k in range(1,small+1)):
            ext_lo=sm_lo; sm_hi=h[q]; highs.append((i,h[q]))
            bmn[cur]=h[q] if bmn[cur]!=bmn[cur] else min(bmn[cur],h[q])
        if all(l[q]<=l[q-k] and l[q]<=l[q+k] for k in range(1,small+1)):
            ext_hi=sm_hi; sm_lo=l[q]; lows.append((i,l[q]))
            bmx[cur]=l[q] if bmx[cur]!=bmx[cur] else max(bmx[cur],l[q])
        if level=="list":
            lows=[x for x in lows if i-x[0]<look]; highs=[x for x in highs if i-x[0]<look]
            cl=[v for _,v in lows if ext_lo==ext_lo and v>ext_lo]; trap_lo=max(cl) if cl else nan
            ch=[v for _,v in highs if ext_hi==ext_hi and v<ext_hi]; trap_hi=min(ch) if ch else nan
        else:
            mx=max([v for v in bmx if v==v], default=nan); mn=min([v for v in bmn if v==v], default=nan)
            trap_lo=mx if (mx==mx and ext_lo==ext_lo and mx>ext_lo) else nan
            trap_hi=mn if (mn==mn and ext_hi==ext_hi and mn<ext_hi) else nan
        closed_now=False
        if t_dir!=0:
            t_age+=1; R=None
            if t_dir>0:
                if l[i]<=t_s: R=-1.0
                elif h[i]>=t_t: R=RR
            else:
                if h[i]>=t_s: R=-1.0
                elif l[i]<=t_t: R=RR
            if R is None and t_age>=MAXHOLD:
                R=max(-1.0,min(RR,((c[i]-t_e) if t_dir>0 else (t_e-c[i]))/abs(t_e-t_s)))
            if R is not None:
                out.append(dict(time=df.index[t_i],dir=t_dir,entry=t_e,stop=t_s,target=t_t,
                                risk=abs(t_e-t_s),R=R-SPREAD/abs(t_e-t_s))); t_dir=0; closed_now=True
        if t_dir==0 and not closed_now:
            mr=max(0.0005*c[i],4*SPREAD)
            if bias==1 and trap_lo==trap_lo and l[i]<trap_lo and c[i]>trap_lo and l[i]>ext_lo:
                t_dir=1;t_e=c[i];t_s=min(l[i],c[i]-mr);t_t=t_e+RR*(t_e-t_s);t_age=0;t_i=i
            elif bias==-1 and trap_hi==trap_hi and h[i]>trap_hi and c[i]<trap_hi and h[i]<ext_hi:
                t_dir=-1;t_e=c[i];t_s=max(h[i],c[i]+mr);t_t=t_e-RR*(t_s-t_e);t_age=0;t_i=i
    return pd.DataFrame(out)

if __name__=="__main__":
    g=load_ohlcv("XAUUSD_1h.csv","2020-01-01","2026-09-16"); g4=load_ohlcv("XAUUSD_4h.csv","2020-01-01","2026-09-16")
    def show(tag,d):
        R=d.R.values; D=d["dir"].values; T=pd.DatetimeIndex(d.time); mid=T[len(T)//2]
        print(f"{tag:<46} n={len(R):<4} expR={R.mean():+.3f} P={100*gm.boot(R):4.1f}%  L {R[D==1].mean():+.3f} S {R[D==-1].mean():+.3f}"
              f"  tr {R[T<=mid].mean():+.3f} te {R[T>mid].mean():+.3f}")
    print("target: n=265 expR=+0.303\n")
    show("1 H4 trend, list look=2000 (sanity=backtest)", run(g,"h4",level="list",h4=g4))
    show("2 H4 trend, bucket 4x500",                     run(g,"h4",level="bucket",h4=g4))
    show("3 H4 trend, bucket 6x500",                     run(g,"h4",level="bucket",nb=6,h4=g4))
    for big in (12,16,24):
        show(f"4 H1 big={big} trend, bucket 4x500",      run(g,"h1big",big=big,level="bucket"))
