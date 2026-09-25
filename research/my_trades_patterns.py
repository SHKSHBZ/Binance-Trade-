import numpy as np, pandas as pd
A=pd.read_csv("../DATA/my_trades_anatomy.csv",parse_dates=["date"])
A["win"]=(A.result=="WIN").astype(int); A["half"]=np.where(A.index<41,"1st half","2nd half")
def row(lab,m):
    x=A[m]; o=A[~m]
    a=x[x.half=="1st half"]; b=x[x.half=="2nd half"]
    f=lambda z: f"{len(z):2d} tr {100*z.win.mean():3.0f}% {z.R.sum():+5.1f}R" if len(z) else "   -"
    print(f"{lab:<44} {f(x)} | 1st half {f(a)} | 2nd half {f(b)} || others {f(o)}")
print(f"ALL: {len(A)} trades, win {100*A.win.mean():.0f}%, {A.R.sum():+.1f}R\n")
print("### direction"); row("SELL",A.dir=="SHORT"); row("BUY",A.dir=="LONG")
print("### trend"); 
for k in ("with_15m_trend","with_1h_trend","with_4h_trend","with_daily_trend","price_side_4h_ema50"): row(f"{k}",A[k]==1)
row("with 1h AND 4h trend",(A.with_1h_trend==1)&(A.with_4h_trend==1))
print("### session (ET)")
for s_ in ["Asia","London","NY pre-open/news","NY open","NY lunch","NY afternoon"]: row(s_,A.session==s_)
print("### what price did BEFORE entry (in trade direction, daily ATRs)")
row("last 1h moved AGAINST trade (pullback)",A.move_before_1h<0); row("last 1h moved WITH trade (chasing)",A.move_before_1h>0)
row("last 4h moved AGAINST trade",A.move_before_4h<0); row("last 4h moved WITH trade",A.move_before_4h>0)
row("last 24h moved AGAINST trade",A.move_before_24h<0); row("last 24h moved WITH trade",A.move_before_24h>0)
print("### location")
row("entry outside yesterday's range",A.beyond_PDH_PDL!="inside"); row("entry inside yesterday's range",A.beyond_PDH_PDL=="inside")
row("with the day's direction (vs day open)",A.vs_day_open==1); row("against the day's direction",A.vs_day_open==0)
row("SELL in upper half of yesterday / BUY in lower half",((A.dir=="SHORT")&(A.loc_in_prev_day>0.5))|((A.dir=="LONG")&(A.loc_in_prev_day<0.5)))
print("### liquidity sweep just before entry"); row("sweep of PDH/PDL/Asia level in last 2h",A.swept_before.notna())
print("### volatility / news")
row("day already used > 1x daily ATR",A.day_range_used>1); row("day used < 0.6x ATR (quiet so far)",A.day_range_used<0.6)
row("news-like spike earlier today",A.news_spike_today==1)
row("volatile now (15m ATR > 1.2x 5-day)",A.vol_regime>1.2); row("quiet now (15m ATR < 0.8x)",A.vol_regime<0.8)
print("### stop")
row("stop behind last 3h swing",A.stop_behind_swing==1); row("stop inside the swing (exposed)",A.stop_behind_swing==0)
med=A.stop_in_datr.median(); row(f"tight stop (< {med:.2f} daily ATR)",A.stop_in_datr<med); row("wide stop",A.stop_in_datr>=med)
print("### RSI at entry (in trade direction: low=oversold for buys)")
A["rsi_dir"]=np.where(A.dir=="LONG",A.rsi,100-A.rsi)
row("RSI stretched AGAINST trade (<40)",A.rsi_dir<40); row("RSI 40-60",(A.rsi_dir>=40)&(A.rsi_dir<=60)); row("RSI already WITH trade (>60)",A.rsi_dir>60)
print("\n### LOSSES: how did they die?")
Ls=A[A.win==0]
print(f"  stopped within 1 hour: {(Ls.bars_to_result<=4).sum()} of {len(Ls)}")
print(f"  were in profit >= +1R first, then stopped: {(Ls.mfe_before_result>=1).sum()}")
print(f"  STOP HUNTS (hit stop, then went on to your 2R target within 24h): {Ls.stop_hunt.sum()} of {len(Ls)}")
W=A[A.win==1]
print(f"### WINS: went nearly straight (never worse than -0.3R): {(W.mae_before_result>-0.3).sum()} of {len(W)}; came within 0.2R of stop first: {(W.mae_before_result<-0.8).sum()}")
print(f"  winners that kept running to 4R+: {(W.ran_to_R>=4).sum()} of {len(W)}")
