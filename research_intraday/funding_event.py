"""Long-only funding event hypothesis. Historical rate used only AFTER settlement.
Predict next funding timestamp from last observed interval; never next realized rate.
Signal: most recently settled rate <= -0.003; enter 1h before predicted settlement.
2h maximum, stop 2 ATR14 H1, target 2R, planned stop loss 1 USDT incl costs.
Exploratory fixed-universe H1 approximation, no orders.
"""
import json
from pathlib import Path
import pandas as pd,numpy as np
import lab
report={'status':'exploratory_not_final_validation','rules':__doc__,'results':{},'quality':{}}
for year in [2024,2025]:
 lab.START=int(pd.Timestamp(f'{year-1}-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp(f'{year+1}-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data' if year==2025 else f'research_intraday/data_{year}');start=int(pd.Timestamp(f'{year}-01-01',tz='UTC').timestamp()*1000)
 alltr={1:[],2:[]};used=[]
 for s in lab.S:
  d,f,q=lab.load(s);cut=start-5*24*lab.H;w=d[d.t>=cut]
  if len(w)!=(lab.END-cut)//lab.H or (w.t.diff().iloc[1:]!=lab.H).any() or q['invalid'] or len(f)<1000:continue
  used.append(s);prev=d.c.shift();atr=pd.concat([d.h-d.l,(d.h-prev).abs(),(d.l-prev).abs()],axis=1).max(axis=1).ewm(alpha=1/14,adjust=False).mean();idx={int(t):i for i,t in enumerate(d.t)};fundtimes=sorted(f)
  for n in range(1,len(fundtimes)):
   known=fundtimes[n];interval=known-fundtimes[n-1]
   if not lab.H<=interval<=8*lab.H or f[known]>-.003:continue
   entrytime=known+interval-lab.H
   if entrytime<=known or entrytime<start:continue
   j=idx.get(entrytime)
   if j is None or j<20 or j+2>=len(d):continue
   for m in alltr:
    fee=lab.FEE*m;slip=lab.SLIP*m;entry=float(d.o.iloc[j])*(1+slip);dist=2*float(atr.iloc[j-1]);stop=entry-dist;target=entry+2*dist;stopfill=stop*(1-slip);qty=1/(entry-stopfill+fee*(entry+stopfill))
    if qty*entry>10000 or stop<=0:continue
    ex=None;reason='time'
    for k in range(j,j+2):
     b=d.iloc[k]
     if b.o<=stop:ex=float(b.o)*(1-slip);reason='gap';break
     if b.l<=stop:ex=stop*(1-slip);reason='stop';break
     if b.h>=target:ex=target*(1-slip);reason='target';break
    if ex is None:ex=float(d.c.iloc[k])*(1-slip)
    funding=sum(qty*float(d.o.iloc[z])*f.get(int(d.t.iloc[z]),0) for z in range(j+1,k+1))
    net=qty*(ex-entry-fee*(entry+ex))-funding
    alltr[m].append(dict(symbol=s,entry_t=entrytime,exit_t=int(d.t.iloc[k])+lab.H,net_r=net,known_rate=f[known],funding_pnl=-funding,reason=reason))
 report['quality'][str(year)]={'symbols':used}
 for m,rows in alltr.items():
  # Most negative known rate first; no hindsight on funding actually paid.
  p=[];busy=0;counts={}
  for x in sorted(rows,key=lambda x:(x['entry_t'],x['known_rate'],x['symbol'])):
   day=x['entry_t']//(24*lab.H)
   if x['entry_t']<busy or counts.get(day,0)>=2:continue
   p.append(x);busy=x['exit_t'];counts[day]=counts.get(day,0)+1
  report['results'][f'{year}_{m}x']={'annual':lab.metrics(p),'funding_pnl_USDT':sum(x['funding_pnl'] for x in p),'halves':{str(h):lab.metrics([x for x in p if (pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month<=6)==(h==1)]) for h in [1,2]}}
  Path(f'research_intraday/funding_event_trades_{year}_{m}x.json').write_text(json.dumps(p))
Path('research_intraday/funding_event_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['results'],indent=2))
