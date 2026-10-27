"""Predefined long-only regime ablation. No parameter search.
BTC filter: closed H4 close>SMA200, SMA200>previous SMA200.
Breadth: strictly >60% of eligible cohort above closed H4 SMA50.
Common eligibility: SMA200 and its preceding value must exist for all versions.
Exploratory: 2024/2025 have been inspected; not pristine final validation.
"""
import json,os,runpy
from pathlib import Path
import pandas as pd,numpy as np
import lab
original=lab.generate
report={'status':'exploratory_predefined_three_variants','results':{},'quality':{}}
for year in [2024,2025]:
 os.environ['LAB_YEAR']=str(year)
 lab.START=int(pd.Timestamp(f'{year-1}-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp(f'{year+1}-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data' if year==2025 else f'research_intraday/data_{year}')
 loaded={}
 for s in lab.S:
  d,f,q=lab.load(s);cut=int(pd.Timestamp(f'{year-1}-12-27',tz='UTC').timestamp()*1000);w=d[d.t>=cut]
  if len(w)==(lab.END-cut)//lab.H and not (w.t.diff().iloc[1:]!=lab.H).any() and q['invalid']==0 and len(f)>=1000:loaded[s]=d
 h4={}
 for s,d in loaded.items():
  g=d.assign(bucket=(d.t.astype('int64')//(4*lab.H))*(4*lab.H)).groupby('bucket')
  bars=g.agg(c=('c','last'),n=('c','size'));bars=bars[bars.n==4];bars.index=bars.index+4*lab.H;h4[s]=bars.c
 btc=h4['BTC'];sma=btc.rolling(200,min_periods=200).mean();eligible=sma.notna()&sma.shift().notna();trend=(btc>sma)&(sma>sma.shift())
 breadth=pd.concat({s:(c>c.rolling(50,min_periods=50).mean()).where(c.rolling(50).count()>=50) for s,c in h4.items()},axis=1).mean(axis=1)
 filt=pd.DataFrame({'eligible':eligible,'trend':trend,'breadth':breadth.reindex(btc.index)>0.6});times=filt.index.to_numpy();arr=filt.to_numpy();collected={1:[],2:[]}
 def capture(*args,**kw):
  mult=args[3] if len(args)>3 else kw.get('cost_mult',1)
  raw=original(*args,**kw)
  for t in raw:
   if t['strategy']!='force_relative' or t['side']!=1:continue
   idx=np.searchsorted(times,t['entry_t'],side='right')-1
   if idx<0 or not arr[idx,0]:continue
   for name,keep in [('reference',True),('btc_trend',arr[idx,1]),('btc_breadth',arr[idx,1] and arr[idx,2])]:
    if keep:collected[mult].append(dict(t,variant=name))
  return []
 lab.generate=capture
 path=Path(f'research_intraday/cross_report_{year}.json');before=path.read_bytes()
 try:runpy.run_path('research_intraday/cross_lab.py',run_name='__main__')
 finally:path.write_bytes(before);lab.generate=original
 report['quality'][str(year)]={'symbols':list(loaded),'common_h4_eligibility_starts':int(times[np.flatnonzero(eligible)[0]])}
 for mult,trades in collected.items():
  for variant in ['reference','btc_trend','btc_breadth']:
   p=lab.portfolio([x for x in trades if x['variant']==variant]);out={}
   for label,beg,end in [('first_half',f'{year}-01-01',f'{year}-07-01'),('third_quarter',f'{year}-07-01',f'{year}-10-01'),('fourth_quarter',f'{year}-10-01',f'{year+1}-01-01'),('year',f'{year}-01-01',f'{year+1}-01-01')]:
    a=int(pd.Timestamp(beg,tz='UTC').timestamp()*1000);b=int(pd.Timestamp(end,tz='UTC').timestamp()*1000);out[label]=lab.metrics([x for x in p if a<=x['entry_t'] and x['exit_t']<b])
   out['months']={str(m):lab.metrics([x for x in p if pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month==m]) for m in range(1,13)}
   worst=sorted(p,key=lambda x:x['net_r'],reverse=True)[5:];out['without_best_5']=lab.metrics(sorted(worst,key=lambda x:x['entry_t']))
   report['results'][f'{year}_{mult}x_{variant}']=out
Path('research_intraday/regime_long_report.json').write_text(json.dumps(report,indent=2))
