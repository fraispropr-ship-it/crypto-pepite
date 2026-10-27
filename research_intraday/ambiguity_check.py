"""Optimistic same-hour fill bound on already selected portfolios; not a backtest result."""
import json
from pathlib import Path
import pandas as pd
import lab
out={}
for year in [2024,2025]:
 lab.START=int(pd.Timestamp(f'{year-1}-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp(f'{year+1}-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data' if year==2025 else f'research_intraday/data_{year}')
 data={s:lab.load(s)[0].set_index('t') for s in lab.S}
 for name in ['compression_retest','false_break_reentry']:
  rows=json.loads(Path(f'research_intraday/structural_trades_{year}_1x_{name}.json').read_text());changed=[];n=0
  for x in rows:
   y=dict(x);bar=data[x['symbol']].loc[x['exit_t']-lab.H]
   if x['reason']=='stop' and bar.h>=x['target']:
    n+=1;stopfill=x['stop']*(1-lab.SLIP);qty=1/(x['entry']-stopfill+lab.FEE*(x['entry']+stopfill));y['net_r']+=qty*(x['target']-x['stop'])*(1-lab.SLIP)*(1-lab.FEE)
   changed.append(y)
  out[f'{year}_{name}']={'ambiguous_trades':n,'optimistic_fixed_portfolio':lab.metrics(changed)}
Path('research_intraday/ambiguity_report.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
