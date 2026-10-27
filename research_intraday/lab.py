"""Exploratory intraday lab. Public Zoomex data only; no account, orders or alerts.
Python >=3.10, pandas, numpy. Historical dates predate this experiment.
NOT a pristine final test: prior research covered part of 2025/2026.
"""
import concurrent.futures, datetime as dt, hashlib, json, os, time, urllib.parse, urllib.request
import numpy as np
import pandas as pd
from pathlib import Path
S='BTC ETH SOL XRP LINK ADA AVAX DOGE SUI AAVE NEAR APT BNB UNI ONDO HYPE INJ 1000PEPE WLD ZRO'.split()
BASE='https://openapi.zoomex.com/cloud/trade/v3/market/'
H=3600000
START=int(pd.Timestamp('2024-12-01',tz='UTC').timestamp()*1000)
END=int(pd.Timestamp('2026-01-01',tz='UTC').timestamp()*1000)
FEE=.0006; SLIP=.0002; CAPITAL=1000; RR=1.75
OUT=Path('research_intraday/data'); OUT.mkdir(parents=True,exist_ok=True)
def api(path,params):
 url=BASE+path+'?'+urllib.parse.urlencode(params)
 for n in range(4):
  try:
   with urllib.request.urlopen(url,timeout=30) as f: d=json.load(f)
   if d.get('retCode')!=0:raise ValueError(d.get('retMsg'))
   return d['result']['list']
  except Exception:
   if n==3: raise
   time.sleep(n+1)
def download(symbol):
 name=symbol+'USDT'; rows=[]; end=END-1
 while end>=START:
  a=api('kline',dict(category='linear',symbol=name,interval='60',end=end,limit=1000))
  if not a:break
  rows+=a; new=min(int(x[0]) for x in a)-1
  if new>=end:raise ValueError('kline pagination')
  end=new
 fr=[]; end=END-1
 while end>=START:
  a=api('funding/history',dict(category='linear',symbol=name,endTime=end,limit=200))
  if not a:break
  fr+=a; new=min(int(x['fundingRateTimestamp']) for x in a)-1
  if new>=end:raise ValueError('funding pagination')
  end=new
 data={'candles':rows,'funding':fr}; p=OUT/(name+'.json'); p.write_text(json.dumps(data)); return name,len(rows),len(fr)
def signals(df):
 c=df.c; h=df.h; l=df.l; o=df.o; v=df.v
 tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
 atr=tr.ewm(alpha=1/14,adjust=False).mean(); ema20=c.ewm(span=20,adjust=False).mean(); ema80=c.ewm(span=80,adjust=False).mean()
 ma=c.rolling(24).mean(); sd=c.rolling(24).std(); hi=h.shift().rolling(24).max(); lo=l.shift().rolling(24).min()
 # At close only. No fitted thresholds or optimisation.
 trend=np.where((c>ema80)&(ema20>ema80)&(c.shift()<=ema20.shift())&(c>ema20),1,np.where((c<ema80)&(ema20<ema80)&(c.shift()>=ema20.shift())&(c<ema20),-1,0))
 mean=np.where((c.shift()< (ma-2*sd).shift())&(c>ma-2*sd),1,np.where((c.shift()>(ma+2*sd).shift())&(c<ma+2*sd),-1,0))
 br=np.where((c>hi)&((h-l)>1.2*atr)&(v>v.shift().rolling(24).mean()),1,np.where((c<lo)&((h-l)>1.2*atr)&(v>v.shift().rolling(24).mean()),-1,0))
 exc=np.where(((h-l)>2*atr)&(c>o)&((o-l)>.55*(h-l)),1,np.where(((h-l)>2*atr)&(c<o)&((h-o)>.55*(h-l)),-1,0))
 return atr,{'tendance_reprise':trend,'retour_moyenne':mean,'cassure_volatilite':br,'rejet_exces':exc}
def load(sym):
 p=OUT/(sym+'USDT.json'); raw=json.loads(p.read_text()); rows=raw['candles']; d=pd.DataFrame([r[:6] for r in rows],columns=['t','o','h','l','c','v']).astype(float); d=d[(d.t>=START)&(d.t<END)].sort_values('t')
 dup=int(d.t.duplicated().sum()); d=d.drop_duplicates('t').reset_index(drop=True); expected=int((END-START)/H); missing=expected-len(d); invalid=int(((d.h<d[['o','c','l']].max(axis=1))|(d.l>d[['o','c','h']].min(axis=1))|(d[['o','h','l','c']]<=0).any(axis=1)|(d.v<0)).sum())
 complete=(missing==0 and invalid==0 and dup==0 and not (d.t.diff().iloc[1:]!=H).any());
 f={int(x['fundingRateTimestamp']):float(x['fundingRate']) for x in raw['funding'] if START<=int(x['fundingRateTimestamp'])<END}
 return d,f,{'candles':len(d),'missing':missing,'duplicates':dup,'invalid':invalid,'funding_count':len(f),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'complete_ohlc':bool(complete)}
def generate(sym,d,f,cost_mult=1):
 atr,sigs=signals(d); data=d.to_numpy(); a=atr.to_numpy(); trades=[]
 for name,sides in sigs.items():
  for i in np.flatnonzero(sides):
   j=i+1
   if j+12>=len(data) or not np.isfinite(a[i]) or a[i]<=0:continue
   t,o,h,l,c,v=data[j]; t=int(t)
   if t<int(pd.Timestamp('2025-01-01',tz='UTC').timestamp()*1000):continue
   side=int(sides[i]); entry=o*(1+side*SLIP*cost_mult); distance=1.5*a[i]; stop=entry-side*distance; tp=entry+side*RR*distance
   # Net planned stop including assumed exit slippage and both fees: 1 USDT at stop (not guaranteed in gaps).
   stopfill=stop*(1-side*SLIP*cost_mult); lossunit=side*(entry-stopfill)+FEE*cost_mult*(entry+stopfill)
   if lossunit<=0:continue
   qty=1/lossunit
   if qty*entry>CAPITAL*10:continue
   reason='time'; ex=None
   for k in range(j,j+12):
    tk,op,hi,lo,cl,_=data[k]
    if (op<=stop if side==1 else op>=stop): ex=op*(1-side*SLIP*cost_mult);reason='gap';break
    if (lo<=stop if side==1 else hi>=stop):ex=stop*(1-side*SLIP*cost_mult);reason='stop';break
    if (hi>=tp if side==1 else lo<=tp):ex=tp*(1-side*SLIP*cost_mult);reason='target';break
   if ex is None:ex=data[k][4]*(1-side*SLIP*cost_mult)
   # If funding is timestamped at the candle open, use open as mark proxy; exclude at entry, include open at exit if held before open.
   funding=0
   for z in range(j+1,k+1):
    ts=int(data[z][0])
    if ts in f:funding+=side*qty*data[z][1]*f[ts]
   pnl=qty*(side*(ex-entry)-FEE*cost_mult*(entry+ex))-funding
   trades.append({'symbol':sym+'USDT','strategy':name,'entry_t':t,'exit_t':int(data[k][0])+H,'side':side,'entry':entry,'stop':stop,'tp':tp,'qty':qty,'net_r':pnl,'reason':reason})
 return trades
def portfolio(ts):
 # Two entries/day UTC, no overlapping position; simultaneous signals alphabetical. No hindsight sorting.
 ts=sorted(ts,key=lambda x:(x['entry_t'],x['symbol'])); out=[];busy=0; counts={}
 for x in ts:
  day=x['entry_t']//(24*H)
  if x['entry_t']<busy or counts.get(day,0)>=2:continue
  out.append(x);busy=x['exit_t'];counts[day]=counts.get(day,0)+1
 return out
def metrics(t):
 x=np.array([a['net_r'] for a in t]); gains=x[x>0].sum();loss=-x[x<0].sum(); eq=np.r_[0,x.cumsum()]; dd=np.max(np.maximum.accumulate(eq)-eq)
 return {'n':len(x),'total_R':round(float(x.sum()),3),'mean_R':round(float(x.mean()),4) if len(x) else None,'profit_factor':round(float(gains/loss),3) if loss else None,'max_drawdown_R':round(float(dd),3),'wins':int((x>0).sum())}
def main():
 errs={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
  fut={ex.submit(download,s):s for s in S}
  for f in concurrent.futures.as_completed(fut):
   try:print('download',f.result(),flush=True)
   except Exception as e:errs[fut[f]]=str(e);print('ERROR',fut[f],str(e),flush=True)
 quality={}; alltr={1:[],2:[]}
 for s in S:
  if s in errs:continue
  try:
   d,f,q=load(s);quality[s]=q
   if not q['complete_ohlc'] or len(f)<1000:errs[s]='Incomplete OHLC or insufficient funding';continue
   for m in alltr:alltr[m]+=generate(s,d,f,m)
  except Exception as e:errs[s]=str(e)
 if errs:
  print('INCOMPLETE',json.dumps(errs),flush=True)
 report={'status':'exploratory_not_pristine_test','data_errors':errs,'quality':quality,'assumptions':'H1 candles, next-open market entry, stop first within candle, 12h, 1 USDT planned net stop loss, 1000 USDT capital 10x max, one position, 2 entries/UTC day, cost 0.06% taker and 0.02% slippage each side, historical funding with open-price proxy, no min order size.','results':{}}
 for m,trades in alltr.items():
  for strategy in sorted({x['strategy'] for x in trades}):
   p=portfolio([x for x in trades if x['strategy']==strategy]); report['results'][str(m)+'x_'+strategy]={}
   for period,begin,end in [('development','2025-01-01','2025-07-01'),('validation','2025-07-01','2025-10-01'),('explored_later','2025-10-01','2026-01-01')]:
    a=int(pd.Timestamp(begin,tz='UTC').timestamp()*1000);b=int(pd.Timestamp(end,tz='UTC').timestamp()*1000)
    report['results'][str(m)+'x_'+strategy][period]=metrics([x for x in p if x['entry_t']>=a and x['exit_t']<b])
  with open('research_intraday/trades_'+str(m)+'x.json','w') as f:json.dump(trades,f)
 with open('research_intraday/lab_report.json','w') as f:json.dump(report,f,indent=2)
 print('REPORT',json.dumps(report['results']),flush=True)
if __name__=='__main__':main()
