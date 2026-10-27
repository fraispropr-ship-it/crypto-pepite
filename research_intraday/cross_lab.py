"""Three fixed cross-market hypotheses on cached Zoomex H1 data.
Research only; no orders or messaging. Run lab.py first to fetch data.
Same cost/portfolio model as lab.py, validation is exploratory, not pristine.
"""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
import lab

YEAR=int(os.environ.get("LAB_YEAR","2025"))
lab.START=int(pd.Timestamp(f"{YEAR-1}-12-01",tz="UTC").timestamp()*1000)
lab.END=int(pd.Timestamp(f"{YEAR+1}-01-01",tz="UTC").timestamp()*1000)
lab.EVALUATION_START=int(pd.Timestamp(f"{YEAR}-01-01",tz="UTC").timestamp()*1000)
lab.OUT=Path("research_intraday/data" if YEAR==2025 else f"research_intraday/data_{YEAR}")

loaded={}
quality={}
for sym in lab.S:
 try:
  d,f,q=lab.load(sym); quality[sym]=q
  window_start=int(pd.Timestamp(f'{YEAR-1}-12-27',tz='UTC').timestamp()*1000)
  window=d[d.t>=window_start]
  full=(len(window)==(lab.END-window_start)//lab.H and not (window.t.diff().iloc[1:]!=lab.H).any())
  if full and q['invalid']==0 and len(f)>=1000:loaded[sym]=(d,f)
 except (FileNotFoundError,ValueError):pass
if 'BTC' not in loaded:raise RuntimeError('BTC data missing')
btc=loaded['BTC'][0].set_index('t'); market=btc.c.pct_change(24); shock=btc.c.pct_change()
# Ranks use data available at each close, never future candles; all eligible symbols have complete coverage.
returns=pd.concat({s:d.set_index('t').c.pct_change(24) for s,(d,f) in loaded.items()},axis=1)
ranks=returns.rank(axis=1,method='average',pct=True)
alltr={1:[],2:[]}
for sym,(d,f) in loaded.items():
 ts=d.t.to_numpy(); b=market.reindex(ts).to_numpy(); sh=shock.reindex(ts).to_numpy(); rank=ranks[sym].reindex(ts).to_numpy()
 c=d.c; o=d.o; prev=c.shift(1); tr=pd.concat([d.h-d.l,(d.h-prev).abs(),(d.l-prev).abs()],axis=1).max(axis=1); atr=tr.ewm(alpha=1/14,adjust=False).mean(); ema=c.ewm(span=20,adjust=False).mean()
 # Trading every four hours on top/bottom quintile in direction of BTC's 24h return.
 every=((d.t.astype('int64')//lab.H)%4==3).to_numpy()
 relative=np.where(every&(rank>=.8)&(b>.01)&(c.to_numpy()>ema.to_numpy()),1,np.where(every&(rank<=.2)&(b<-.01)&(c.to_numpy()<ema.to_numpy()),-1,0))
 # Shock reversal: the preceding hour BTC moved at least 2%; current alt candle must reverse.
 prior_sh=np.r_[np.nan,sh[:-1]]
 shock_reversal=np.where((prior_sh<-.02)&(c.to_numpy()>o.to_numpy()),1,np.where((prior_sh>.02)&(c.to_numpy()<o.to_numpy()),-1,0))
 # The funding rate is known only after settlement; join backward strictly as of candle close.
 ff=pd.DataFrame({'fund_t':list(f.keys()),'rate':list(f.values())}).sort_values('fund_t')
 hh=pd.DataFrame({'close_t':d.t.astype('int64')+lab.H}).sort_values('close_t')
 joined=pd.merge_asof(hh,ff,left_on='close_t',right_on='fund_t',direction='backward'); rate=joined.rate.to_numpy(); age=(joined.close_t-joined.fund_t).to_numpy()
 cr=c.to_numpy(); em=ema.to_numpy(); prevc=np.r_[np.nan,cr[:-1]]; preve=np.r_[np.nan,em[:-1]]
 funding=np.where((age<=8*lab.H)&(rate<-.0003)&(prevc<=preve)&(cr>em),1,np.where((age<=8*lab.H)&(rate>.0003)&(prevc>=preve)&(cr<em),-1,0))
 rules={'force_relative':relative,'choc_btc_retour':shock_reversal,'funding_extreme_retournement':funding}
 lab.signals=lambda df,a=atr,r=rules:(a,r)
 for m in alltr:alltr[m].extend(lab.generate(sym,d,f,m))
report={'status':'exploratory_no_pristine_final_test','symbols':list(loaded),'excluded':sorted(set(lab.S)-set(loaded)),'assumptions':'See lab.py; H1 fills, conservative same-bar stop first, 1 position, 2 entries per UTC day, funding open proxy. 2x means doubled fee and slippage.','results':{}}
for m,trades in alltr.items():
 for strategy in sorted({x['strategy'] for x in trades}):
  p=lab.portfolio([x for x in trades if x['strategy']==strategy]); out={}
  for name,beg,end in [('first_half',f'{YEAR}-01-01',f'{YEAR}-07-01'),('third_quarter',f'{YEAR}-07-01',f'{YEAR}-10-01'),('fourth_quarter',f'{YEAR}-10-01',f'{YEAR+1}-01-01')]:
   a=int(pd.Timestamp(beg,tz='UTC').timestamp()*1000); b=int(pd.Timestamp(end,tz='UTC').timestamp()*1000)
   out[name]=lab.metrics([x for x in p if a<=x['entry_t'] and x['exit_t']<b])
  report['results'][str(m)+'x_'+strategy]=out
open(f'research_intraday/cross_report_{YEAR}.json','w').write(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
