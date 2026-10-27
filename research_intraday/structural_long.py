"""Two fixed structural long hypotheses; no parameter optimisation.
H1 screen only, conservative same-bar stop-first; not final validation.
Selection: largest past 24h turnover proxy, not alphabetical.
"""
import json
from pathlib import Path
import numpy as np,pandas as pd
import lab

def candidates(d,f,symbol,m):
 c=d.c;prev=c.shift();atr=pd.concat([d.h-d.l,(d.h-prev).abs(),(d.l-prev).abs()],axis=1).max(axis=1).ewm(alpha=1/14,adjust=False).mean()
 turnover=(d.v*d.c).rolling(24).sum(); out=[]
 high12=d.h.shift(2).rolling(12).max();low12=d.l.shift(2).rolling(12).min();low24=d.l.shift().rolling(24).min()
 compression=((high12-low12)<=2*atr.shift(2))&(c.shift()>high12)&(d.l<=high12+.15*atr)&(c>high12)&(c>d.o)
 reversal=(d.l<low24)&(c>low24)&(c>d.o)
 for i in np.flatnonzero((compression|reversal).to_numpy()):
  if i<120 or i>=len(d)-13:continue
  b=d.iloc[i];old=d.iloc[i-24:i]; prior=d.iloc[i-13:i-1];breakbar=d.iloc[i-1];a=float(atr.iloc[i]);entry=float(d.o.iloc[i+1])*(1+lab.SLIP*m)
  if not a>0:continue
  proposals=[]
  # A compact preceding 12h range, breakout, then retest on the following hour.
  high=float(prior.h.max());low=float(prior.l.min());width=high-low
  if width<=2*float(atr.iloc[i-2]) and breakbar.c>high and b.l<=high+.15*a and b.c>high and b.c>b.o:
   target=float(d.h.iloc[i-120:i-13].max());proposals.append(('compression_retest',low-.1*a,target))
  # Sweep of the preceding 24h low, followed by a bullish close back inside the range.
  level=float(old.l.min())
  if b.l<level and b.c>level and b.c>b.o:
   proposals.append(('false_break_reentry',float(b.l)-.1*a,float(old.h.max())))
  for name,stop,structural_target in proposals:
   distance=entry-stop
   if distance<.5*a:continue
   if structural_target<=entry or (structural_target-entry)/distance<1.5:continue
   target=min(structural_target,entry+2*distance)
   stopfill=stop*(1-lab.SLIP*m);loss=entry-stopfill+lab.FEE*m*(entry+stopfill)
   if lab.FEE*m*(entry+stopfill)/distance>.15:continue
   qty=1/loss
   if qty*entry>10000:continue
   j=i+1;ex=None;reason='time'
   for k in range(j,j+12):
    bar=d.iloc[k]
    if bar.o<=stop:ex=float(bar.o)*(1-lab.SLIP*m);reason='gap';break
    if bar.l<=stop:ex=stop*(1-lab.SLIP*m);reason='stop';break
    if bar.h>=target:ex=target*(1-lab.SLIP*m);reason='target';break
   if ex is None:ex=float(d.c.iloc[k])*(1-lab.SLIP*m)
   funding=sum(qty*float(d.o.iloc[z])*f.get(int(d.t.iloc[z]),0) for z in range(j+1,k+1))
   out.append(dict(symbol=symbol,strategy=name,entry_t=int(d.t.iloc[j]),exit_t=int(d.t.iloc[k])+lab.H,side=1,entry=entry,stop=stop,target=target,net_r=qty*(ex-entry-lab.FEE*m*(entry+ex))-funding,reason=reason,priority=float(turnover.iloc[i])))
 return out

def allocate(rows):
 # Prioritise liquidity observed at signal close. One position, max two entries per UTC day.
 busy=0;counts={};out=[]
 for x in sorted(rows,key=lambda x:(x['entry_t'],-x['priority'],x['symbol'])):
  day=x['entry_t']//(24*lab.H)
  if x['entry_t']<busy or counts.get(day,0)>=2:continue
  out.append(x);busy=x['exit_t'];counts[day]=counts.get(day,0)+1
 return out

report={'status':'exploratory_screen_H1_no_pristine_final_test','rules':'See structural_long.py. Fixed rules; structural stop/target, RR 1.5 to 2 gross; 1 USDT planned stop incl costs, 12h, 2/day UTC, 1 position; historical funding at open-price proxy. Current universe survivorship bias; minimum order sizes not checked.','results':{},'quality':{}}
for year in [2024,2025]:
 lab.START=int(pd.Timestamp(f'{year-1}-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp(f'{year+1}-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data' if year==2025 else f'research_intraday/data_{year}')
 raw={1:[],2:[]};used=[]
 for s in lab.S:
  d,f,q=lab.load(s);cut=int(pd.Timestamp(f'{year-1}-12-27',tz='UTC').timestamp()*1000);w=d[d.t>=cut]
  if len(w)!=(lab.END-cut)//lab.H or (w.t.diff().iloc[1:]!=lab.H).any() or q['invalid'] or len(f)<1000:continue
  used.append(s)
  for m in raw:raw[m]+=candidates(d,f,s,m)
 report['quality'][str(year)]={'symbols':used}
 for m,rows in raw.items():
  for name in ['compression_retest','false_break_reentry']:
   start=int(pd.Timestamp(f'{year}-01-01',tz='UTC').timestamp()*1000)
   p=allocate([x for x in rows if x['strategy']==name and x['entry_t']>=start]);r={'annual':lab.metrics(p)}
   r['halves']={str(h):lab.metrics([x for x in p if (pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month<=6)==(h==1)]) for h in [1,2]}
   r['months']={str(month):lab.metrics([x for x in p if pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month==month]) for month in range(1,13)}
   top=sorted(p,key=lambda x:x['net_r'],reverse=True)[5:];r['without_best_5']=lab.metrics(sorted(top,key=lambda x:x['entry_t']))
   report['results'][f'{year}_{m}x_{name}']=r
   Path(f'research_intraday/structural_trades_{year}_{m}x_{name}.json').write_text(json.dumps(p))
Path('research_intraday/structural_long_report.json').write_text(json.dumps(report,indent=2))
