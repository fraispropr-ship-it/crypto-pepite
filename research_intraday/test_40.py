"""Exploratory 40 current contracts, fixed setup and portfolio, 2026 only.
Current-constituent survivorship and 24h liquidity selection bias; not pristine.
"""
import concurrent.futures,json
from pathlib import Path
import pandas as pd
import lab
EXTRA='ZEC ENA XMR TAO ARB BCH TIA LTC TRX DOT ATOM FIL ETC OP XLM SEI WIF 1000BONK ALGO POL'.split()
lab.START=int(pd.Timestamp('2025-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp('2026-10-27',tz='UTC').timestamp()*1000);lab.EVALUATION_START=int(pd.Timestamp('2026-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data_2026')
errors={}
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as e:
 fut={e.submit(lab.download,s):s for s in EXTRA}
 for f in concurrent.futures.as_completed(fut):
  try:print('FETCH',f.result(),flush=True)
  except Exception as ex:errors[fut[f]]=str(ex);print('ERROR',fut[f],str(ex),flush=True)
report={'period':'2026-01-01 to 2026-10-27 UTC exclusive','errors':errors,'quality':{},'extra':EXTRA,'results':{}}
raw={1:[],2:[]}
for s in lab.S+EXTRA:
 try:
  d,f,q=lab.load(s);cut=lab.EVALUATION_START-5*24*lab.H;w=d[d.t>=cut];fundok=bool(f) and min(f)<=cut and max(f)>=lab.END-8*lab.H and max(pd.Series(sorted(f)).diff().fillna(0))<=8*lab.H
  ok=len(w)==(lab.END-cut)//lab.H and not (w.t.diff().iloc[1:]!=lab.H).any() and q['invalid']==0 and fundok
  report['quality'][s]={'eligible':bool(ok),'candles':q,'funding_contiguous':bool(fundok)}
  if not ok:continue
  for m in raw:raw[m]+=[x for x in lab.generate(s,d,f,m) if x['side']==1 and x['strategy']=='rejet_exces']
 except Exception as ex:errors[s]=str(ex)
for m,rows in raw.items():
 for cohort,syms in [('20',lab.S),('40',lab.S+EXTRA)]:
  p=lab.portfolio([x for x in rows if x['symbol'].removesuffix('USDT') in syms]);v={'annual':lab.metrics(p),'by_month':{str(n):lab.metrics([x for x in p if pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month==n]) for n in range(1,11)}}
  v['without_best_5']=lab.metrics(sorted(sorted(p,key=lambda x:x['net_r'],reverse=True)[5:],key=lambda x:x['entry_t']))
  report['results'][f'{cohort}_{m}x']=v
Path('research_intraday/test_40_report.json').write_text(json.dumps(report,indent=2));print('RESULT',json.dumps(report['results']),flush=True)
