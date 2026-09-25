import numpy as np, pandas as pd
A=pd.read_csv("../DATA/my_trades_anatomy.csv",parse_dates=["date"])
def why(r):
    pb=r.move_before_4h<0; tr=r.with_15m_trend==1; vol=(r.vol_regime>1.2) or (r.news_spike_today==1); turn=r.move_before_1h>0
    good=[]; bad=[]
    good.append("pullback: last 4h moved against you, you entered on the swing back") if pb else bad.append(f"chased: price had already moved {abs(r.move_before_4h):.2f} daily ATR your way in the last 4h")
    good.append("with the 20h/200h trend") if tr else bad.append("against the 20h/200h trend (EMA80/800)")
    good.append("volatile/news day") if vol else bad.append("quiet day (no news spike, low volatility)")
    if turn: good.append("last hour already turning your way")
    if r.session=="London": bad.append("London session (your weakest)")
    if r.beyond_PDH_PDL!="inside": bad.append(f"entered {r.beyond_PDH_PDL} (outside yesterday's range)")
    score=int(pb)+int(tr)+int(vol)
    if r.result=="WIN":
        how=f"ran {r.ran_to_R:.0f}R before your original stop" if r.ran_to_R>=3 else "hit 2R"
        dip=f"; dipped to {r.mae_before_result:.1f}R first" if r.mae_before_result<-0.5 else ""
        text=f"WON — {'; '.join(good) if good else 'no clear support: lucky'}. {how}{dip}."
    else:
        if r.stop_hunt==1: death=f"STOP HUNT: stopped out, then went on to +{r.after_stop_went_R:.0f}R your way within 24h"
        elif r.mfe_before_result>=1: death=f"was +{r.mfe_before_result:.1f}R in profit, then reversed to the stop"
        elif r.mfe_before_result<0.3: death="never went your way (wrong from the start)"
        else: death=f"only reached +{r.mfe_before_result:.1f}R, then stopped"
        text=f"LOST — {death}. {'Warning signs: '+'; '.join(bad) if bad else 'Setup was good (all 3 conditions) — normal loss, part of the game'}."
    return score,text
out=[]
for _,r in A.iterrows():
    s,t=why(r)
    out.append(dict(n=r.n,date=r.date.strftime("%Y-%m-%d %H:%M"),dir=r.dir,result=r.result,R=round(r.R,2),score=f"{s}/3",session=r.session,why=t))
O=pd.DataFrame(out); O.to_csv("../DATA/my_trades_explained.csv",index=False)
sc=O.groupby("score").agg(trades=("R","size"),win=("result",lambda x:f"{100*(x=='WIN').mean():.0f}%"),totalR=("R","sum")).round(1)
lines=["# All 82 of your trades explained","",
"**Setup score (0–3)** counts how many of the three winning conditions a trade had:",
"1. **Pullback:** the last 4 hours moved *against* your trade, and you entered as it swung back.",
"2. **Trend:** the trade was with the 20h/200h trend (EMA80 vs EMA800 on the 15m chart).",
"3. **Volatile/news day:** a news-sized spike had already happened that day, or 15m volatility was above 1.2× its 5-day average.","",
"| score | trades | win % | total R |","|---|---|---|---|"]
for k,v in sc.iterrows(): lines.append(f"| {k} | {v.trades} | {v.win} | {v.totalR:+.1f} |")
lines+=["","| # | date (UTC) | dir | result | R | score | session | why |","|---|---|---|---|---|---|---|---|"]
for _,r in O.iterrows(): lines.append(f"| {r.n} | {r.date} | {r.dir} | {r.result} | {r.R:+.2f} | {r.score} | {r.session} | {r.why} |")
open("MY_82_TRADES_EXPLAINED.md","w").write("\n".join(lines))
print(sc); print(); print(O.head(12).to_string(max_colwidth=160))
