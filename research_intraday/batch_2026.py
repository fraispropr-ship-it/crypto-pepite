"""2026 replication batch; unchanged pre-existing rules, no search on 2026."""
import json
from pathlib import Path
import pandas as pd
import lab
lab.START=int(pd.Timestamp('2025-12-01',tz='UTC').timestamp()*1000);lab.END=int(pd.Timestamp('2026-10-27',tz='UTC').timestamp()*1000);lab.EVALUATION_START=int(pd.Timestamp('2026-01-01',tz='UTC').timestamp()*1000);lab.OUT=Path('research_intraday/data_2026')
report={'status':'exploratory_2026_replication_not_pristine','window':'2026-01-01 to 2026-10-27 exclusive UTC','results':{},'quality':{}}
raw={1:[],2:[]}
for s in lab.S:
 d,f,q=lab.load(s);report['quality'][s]=q
 if not q['complete_ohlc']:continue
 for m in raw:raw[m]+=lab.generate(s,d,f,m)
for m,rows in raw.items():
 for name in sorted({x['strategy'] for x in rows}):
  p=lab.portfolio([x for x in rows if x['strategy']==name and x['side']==1]);r={'all':lab.metrics(p)}
  r['months']={str(month):lab.metrics([x for x in p if pd.Timestamp(x['entry_t'],unit='ms',tz='UTC').month==month]) for month in range(1,11)}
  report['results'][f'{m}x_{name}']=r
# Run cross-market unchanged signal code with only dates and data eligibility adapted to partial year.
src=Path('research_intraday/cross_lab.py').read_text();src=src.replace('YEAR=int(os.environ.get("LAB_YEAR","2025"))','YEAR=2026');src=src.replace('pd.Timestamp(f"{YEAR+1}-01-01",tz="UTC")','pd.Timestamp("2026-10-27",tz="UTC")');src=src.replace("len(f)>=1000","(f and min(f)<=window_start and max(f)>=lab.END-8*lab.H and max(np.diff(sorted(f)),default=0)<=8*lab.H)")
original=lab.generate
lab.generate=lambda *a,**kw:[x for x in original(*a,**kw) if x['side']==1]
exec(compile(src,'cross_2026','exec'),{'__name__':'__research__'})
lab.generate=original
report['cross']=json.loads(Path('research_intraday/cross_report_2026.json').read_text())
Path('research_intraday/batch_2026_report.json').write_text(json.dumps(report,indent=2))
# Structural setup screen, exact rules unchanged.
src=Path('research_intraday/structural_long.py').read_text().replace('for year in [2024,2025]:','for year in [2026]:').replace("pd.Timestamp(f'{year+1}-01-01',tz='UTC')","pd.Timestamp('2026-10-27',tz='UTC')").replace('len(f)<1000',"(not f or min(f)>cut or max(f)<lab.END-8*lab.H or max(np.diff(sorted(f)),default=0)>8*lab.H)").replace("Path('research_intraday/structural_long_report.json')","Path('research_intraday/structural_long_report_2026.json')")
exec(compile(src,'structural_2026','exec'),{'__name__':'__research__'})
