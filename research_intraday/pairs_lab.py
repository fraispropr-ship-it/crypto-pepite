"""Fixed dollar-neutral pairs hypotheses; exploratory H1 screening only.
Two legs = one operation, planned net stop risk 1 USDT; not two independent trades.
H1 joint extremes are conservative bounds, not synchronized executable quotes.
Current fixed cohort has survivorship bias. Funding uses candle-open price proxy.
"""
import json
from pathlib import Path
import pandas as pd,numpy as np
import lab
report={'status':'exploratory_not_execution_validated','rules':'Every 4h rank past 24h returns. Momentum: long strongest short weakest; reversal: inverse. Equal initial USDT notional. Spread stop=1.5*48h realized hourly spread vol*sqrt(12), floor 0.5%. TP=1.75*stop; max12h; max2 pair operations per UTC day; no overlap. All four fees and leg slippage included. Conservative unsynchronized hourly joint-extreme bounds; needs finer execution validation if promising.','results':{},'quality':{}}
for year in [2024,2025]:
 lab.START=int(pd.Timestamp(f'{year-1}-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp(f'{year+1}-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data' if year==2025 else f'research_intraday/data_{year}')
 start=int(pd.Timestamp(f'{year}-01-01',tz='UTC').timestamp()*1000);loaded={};fund={}
 for s in lab.S:
  d,f,q=lab.load(s);cut=start-5*24*lab.H;w=d[d.t>=cut]
  if len(w)!=(lab.END-cut)//lab.H or (w.t.diff().iloc[1:]!=lab.H).any() or q['invalid'] or len(f)<1000:continue
  loaded[s]=w.set_index('t');fund[s]=f
 symbols=sorted(loaded);times=loaded[symbols[0]].index.to_numpy();arrays={s:loaded[s][['o','h','l','c']].to_numpy() for s in symbols};close=pd.DataFrame({s:loaded[s].c for s in symbols});ret24=close.pct_change(24).to_numpy();hourret=close.pct_change().to_numpy();report['quality'][str(year)]={'symbols':symbols}
 for mode in ['momentum','reversal']:
  for mult in [1,2]:
   slip=lab.SLIP*mult;fee=lab.FEE*mult;trades=[];busy=0;counts={}
   for j in range(50,len(times)-12):
    t=int(times[j]);day=t//(24*lab.H)
    if t<start or (t//lab.H)%4 or t<busy or counts.get(day,0)>=2:continue
    ranking=ret24[j-1];lo=int(np.argmin(ranking));hi=int(np.argmax(ranking))
    if lo==hi:continue
    li,si=(hi,lo) if mode=='momentum' else (lo,hi);ls,ss=symbols[li],symbols[si];L,S=arrays[ls],arrays[ss]
    diff=hourret[j-48:j,li]-hourret[j-48:j,si];dist=max(.005,1.5*float(np.std(diff,ddof=1))*np.sqrt(12))
    if not np.isfinite(dist) or dist>.08:continue
    el=L[j,0]*(1+slip);es=S[j,0]*(1-slip);notional=1/(dist+4*fee+2*slip)
    if 2*notional>10000:continue
    reason='time';gross=None;ambiguous=False
    for k in range(j,j+12):
     op=L[k,0]/el-S[k,0]/es;worst=L[k,2]/el-S[k,1]/es;best=L[k,1]/el-S[k,2]/es
     if op<=-dist:gross=op;reason='gap';break
     if worst<=-dist:gross=-dist;reason='stop';ambiguous=bool(best>=1.75*dist);break
     if best>=1.75*dist:gross=1.75*dist;reason='target';break
    if gross is None:gross=L[k,3]/el-S[k,3]/es
    exit_scale=L[k,3]/el+S[k,3]/es
    cost=fee*(2+exit_scale)+slip*exit_scale
    funding=sum(L[z,0]/el*fund[ls].get(int(times[z]),0)-S[z,0]/es*fund[ss].get(int(times[z]),0) for z in range(j+1,k+1))
    net=notional*(gross-cost-funding)
    trades.append(dict(entry_t=t,exit_t=int(times[k])+lab.H,long=ls,short=ss,net_r=net,reason=reason,ambiguous=ambiguous,notional_per_leg=notional,stop_spread=dist))
    busy=int(times[k])+lab.H;counts[day]=counts.get(day,0)+1
   result={'annual':lab.metrics(trades),'ambiguous':sum(x['ambiguous'] for x in trades)}
   result['halves']={str(h):lab.metrics([x for x in trades if (pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month<=6)==(h==1)]) for h in [1,2]}
   result['months']={str(m):lab.metrics([x for x in trades if pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month==m]) for m in range(1,13)}
   report['results'][f'{year}_{mult}x_{mode}']=result
   Path(f'research_intraday/pairs_trades_{year}_{mult}x_{mode}.json').write_text(json.dumps(trades))
Path('research_intraday/pairs_report.json').write_text(json.dumps(report,indent=2))
