"""Post-screen uncertainty audit, not an independent validation."""
import json
from pathlib import Path
import pandas as pd,numpy as np
import lab
lab.START=int(pd.Timestamp('2025-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp('2026-10-27',tz='UTC').timestamp()*1000);lab.EVALUATION_START=int(pd.Timestamp('2026-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data_2026')
r={};rng=np.random.default_rng(20261027)
for m in [1,2]:
 rows=[]
 for s in lab.S:
  d,f,q=lab.load(s)
  if q['complete_ohlc']:rows += [x for x in lab.generate(s,d,f,m) if x['side']==1 and x['strategy']=='rejet_exces']
 p=lab.portfolio(rows);groups={}
 for x in p:groups.setdefault(x['entry_t']//(24*lab.H),[]).append(x['net_r'])
 g=list(groups.values());means=[]
 for _ in range(5000):
  values=[v for i in rng.integers(0,len(g),len(g)) for v in g[i]];means.append(np.mean(values))
 trimmed=sorted(p,key=lambda x:x['net_r'],reverse=True)[5:]
 r[str(m)]={'all':lab.metrics(p),'day_cluster_bootstrap_mean_95pct':np.quantile(means,[.025,.975]).tolist(),'without_best_5':lab.metrics(sorted(trimmed,key=lambda x:x['entry_t'])),'by_symbol':{s:lab.metrics([x for x in p if x['symbol']==s]) for s in sorted({x['symbol'] for x in p})},'trades':p}
Path('research_intraday/rejection_audit_2026.json').write_text(json.dumps(r,indent=2))
for k,v in r.items():print(k,v['day_cluster_bootstrap_mean_95pct'],v['without_best_5'])
