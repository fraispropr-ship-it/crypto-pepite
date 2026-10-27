"""Fetch and test unchanged funding-event rules through 2026-10-26 UTC."""
import concurrent.futures,json,sys
from pathlib import Path
import pandas as pd
import lab
lab.START=int(pd.Timestamp('2025-12-01',tz='UTC').timestamp()*1000)
lab.END=int(pd.Timestamp('2026-10-27',tz='UTC').timestamp()*1000)
lab.OUT=Path('research_intraday/data_2026');lab.OUT.mkdir(exist_ok=True)
errors={}
if '--cached' not in sys.argv:
 with concurrent.futures.ThreadPoolExecutor(max_workers=20) as e:
  futures={e.submit(lab.download,s):s for s in lab.S}
  for f in concurrent.futures.as_completed(futures):
   try:print('FETCH',f.result(),flush=True)
   except Exception as ex:errors[futures[f]]=str(ex);print('ERROR',futures[f],str(ex),flush=True)
if errors:raise RuntimeError(json.dumps(errors))
# Reuse identical strategy source, changing only year and historical window.
src=Path('research_intraday/funding_event.py').read_text()
src=src.replace('for year in [2024,2025]:','for year in [2026]:')
src=src.replace("pd.Timestamp(f'{year+1}-01-01',tz='UTC')","pd.Timestamp('2026-10-27',tz='UTC')")
src=src.replace("Path('research_intraday/funding_event_report.json')","Path('research_intraday/funding_event_report_2026.json')")
src=src.replace('len(f)<1000', '(not f or min(f)>cut or max(f)<lab.END-8*lab.H or max(np.diff(sorted(f)),default=0)>8*lab.H)')
exec(compile(src,'funding_event_2026','exec'))
