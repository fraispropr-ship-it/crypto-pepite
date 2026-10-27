"""Fetch a second non-overlapping year; no private API or trading."""
import concurrent.futures
import pandas as pd
from pathlib import Path
import lab
lab.START=int(pd.Timestamp('2023-12-01',tz='UTC').timestamp()*1000)
lab.END=int(pd.Timestamp('2025-01-01',tz='UTC').timestamp()*1000)
lab.OUT=Path('research_intraday/data_2024');lab.OUT.mkdir(exist_ok=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as e:
 fs={e.submit(lab.download,s):s for s in lab.S}
 for f in concurrent.futures.as_completed(fs):
  try:print(f.result(),flush=True)
  except Exception as ex:print('ERROR',fs[f],str(ex),flush=True)
