"""Rebond Eclair, 40 current symbols, 2025-10-27 to 2026-10-27 UTC.
H1 next-open approximation to live H+03, no alert lock, no daily cap.
Current symbols induce survivorship bias. Costs/funding, no book/min-size data.
"""
import json,concurrent.futures,sys
from pathlib import Path
import numpy as np,pandas as pd
import lab
S=lab.S+'ZEC ENA XMR TAO ARB BCH TIA LTC TRX DOT ATOM FIL ETC OP XLM SEI WIF 1000BONK ALGO POL'.split()
START=int(pd.Timestamp('2025-10-27',tz='UTC').timestamp()*1000);END=int(pd.Timestamp('2026-10-27',tz='UTC').timestamp()*1000)
lab.START=int(pd.Timestamp('2025-10-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp('2025-12-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/one_year_early');lab.OUT.mkdir(exist_ok=True)
errors={}
if '--cached' not in sys.argv:
 with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
  fut={pool.submit(lab.download,s):s for s in S}
  for f in concurrent.futures.as_completed(fut):
   try:print('FETCH',f.result(),flush=True)
   except Exception as e:errors[fut[f]]=str(e);print('FAIL',fut[f],flush=True)
combined=Path('research_intraday/one_year_combined');combined.mkdir(exist_ok=True)
for s in S:
 try:
  a=json.loads((lab.OUT/(s+'USDT.json')).read_text());b=json.loads(Path('research_intraday/data_2026',s+'USDT.json').read_text());
  prior={int(r[0]):r for r in a['candles']}
  if any(int(r[0]) in prior and any(float(x)!=float(y) for x,y in zip(r[:6],prior[int(r[0])][:6])) for r in b['candles']):raise ValueError('conflicting candle overlap')
  prior_f={int(r['fundingRateTimestamp']):float(r['fundingRate']) for r in a['funding']}
  if any(int(r['fundingRateTimestamp']) in prior_f and float(r['fundingRate'])!=prior_f[int(r['fundingRateTimestamp'])] for r in b['funding']):raise ValueError('conflicting funding overlap')
  (combined/(s+'USDT.json')).write_text(json.dumps({'candles':a['candles']+b['candles'],'funding':a['funding']+b['funding']}))
 except Exception as e:errors[s]=str(e)
lab.END=END;lab.EVALUATION_START=START;lab.OUT=combined
quality={};rows={1:[],2:[]}
for s in S:
 if s in errors:continue
 try:
  d,f,q=lab.load(s);cut=START-200*lab.H;w=d[d.t>=cut];fund_ok=bool(f) and min(f)<=cut and max(f)>=END-8*lab.H and max(np.diff(sorted(f)),default=0)<=8*lab.H
  ok=len(w)==(END-cut)//lab.H and not (w.t.diff().iloc[1:]!=lab.H).any() and not q['invalid'] and fund_ok
  quality[s]={'eligible':bool(ok),'funding_contiguous':bool(fund_ok),'candles':q}
  if not ok:continue
  for m in rows:rows[m]+=[x for x in lab.generate(s,d,f,m) if x['side']==1 and x['strategy']=='rejet_exces']
 except Exception as e:errors[s]=str(e)
def portfolio(allrows):
 out=[];busy=0;counts={}
 for x in sorted(allrows,key=lambda a:(a['entry_t'],a['symbol'])):
  day=x['entry_t']//(24*lab.H)
  if False:continue
  out.append(x);busy=x['entry_t']+12*lab.H;counts[day]=counts.get(day,0)+1
 return out
report={'period':'2025-10-27 00:00 UTC to 2026-10-27 00:00 UTC exclusive','method':'H1 next-open not live H+03; all signals with no alert lock and no daily entry cap; simultaneous simulated positions; not a capital-constrained portfolio, symbol alphabetical priority; 1 USDT planned stop risk, 1000 USDT capital, leverage 10x max; fee 0.06% per side, slippage 0.02% per side, historic funding at H1 open proxy; stop-first OHLC ambiguity. Current universe survivorship bias, prior research explored period; no M15, book, instrument rounding, liquidation, actual dynamic entry, live scheduling, exchange fee-tier validation.','quality':quality,'errors':errors,'results':{}}
for m,allrows in rows.items():
 p=portfolio(allrows);r={'summary':lab.metrics(p),'monthly':{},'by_symbol':{},'without_best_5':lab.metrics(sorted(sorted(p,key=lambda x:x['net_r'],reverse=True)[5:],key=lambda x:x['entry_t'])),'trades':p}
 for x in p:
  key=pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').strftime('%Y-%m');r['monthly'].setdefault(key,[]).append(x);r['by_symbol'].setdefault(x['symbol'],[]).append(x)
 r['monthly']={k:lab.metrics(v) for k,v in r['monthly'].items()};r['by_symbol']={k:lab.metrics(v) for k,v in r['by_symbol'].items()};report['results'][str(m)+'x']=r
Path('research_intraday/rebond_all_signals_1y_report.json').write_text(json.dumps(report,indent=2));print('SUMMARY',json.dumps({'eligible':sum(x['eligible'] for x in quality.values()),'errors':errors,'results':{k:v['summary'] for k,v in report['results'].items()}}),flush=True)
