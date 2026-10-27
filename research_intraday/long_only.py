"""Long-only ablation. Parameters unchanged; filter before portfolio allocation."""
import json, os, runpy
from pathlib import Path
import lab
report={'method':'Long-only filter BEFORE portfolio allocation; unchanged rules and costs. Exploratory, fixed current universe. 19 symbols for four initial rules in 2025; cross-market 20 in 2025 and 17 in 2024.','results':{}}
for mult in [1,2]:
 trades=[]
 for sym in lab.S:
  d,f,q=lab.load(sym)
  if q['complete_ohlc'] and len(f)>=1000:trades.extend(lab.generate(sym,d,f,mult))
 for name in sorted({x['strategy'] for x in trades}):
  p=lab.portfolio([x for x in trades if x['strategy']==name and x['side']==1]);out={}
  for period,start,end in [('first_half','2025-01-01','2025-07-01'),('third_quarter','2025-07-01','2025-10-01'),('fourth_quarter','2025-10-01','2026-01-01'),('year','2025-01-01','2026-01-01')]:
   a=int(lab.pd.Timestamp(start,tz='UTC').timestamp()*1000);b=int(lab.pd.Timestamp(end,tz='UTC').timestamp()*1000)
   out[period]=lab.metrics([x for x in p if a<=x['entry_t'] and x['exit_t']<b])
  report['results'][f'2025_{mult}x_{name}']=out
original=lab.generate
lab.generate=lambda *a,**kw:[x for x in original(*a,**kw) if x['side']==1]
for year in [2024,2025]:
 os.environ['LAB_YEAR']=str(year);path=Path(f'research_intraday/cross_report_{year}.json');before=path.read_bytes()
 runpy.run_path('research_intraday/cross_lab.py',run_name='__main__')
 r=json.loads(path.read_text());path.write_bytes(before)
 for name,out in r['results'].items():report['results'][f'{year}_{name}']=out
Path('research_intraday/long_only_report.json').write_text(json.dumps(report,indent=2))
