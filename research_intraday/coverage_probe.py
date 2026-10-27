"""Read-only Zoomex historical endpoint probe; no orders or account access."""
import concurrent.futures, datetime as dt, json, urllib.parse, urllib.request, time
SYMBOLS='BTC ETH SOL XRP LINK ADA AVAX DOGE SUI AAVE NEAR APT BNB UNI ONDO HYPE INJ 1000PEPE WLD ZRO'.split()
DATES=['2023-01-01','2024-01-01','2025-01-01']
BASE='https://openapi.zoomex.com/cloud/trade/v3/market/'
def probe(task):
 sym,date=task; stamp=int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.timezone.utc).timestamp()*1000)
 q=urllib.parse.urlencode(dict(category='linear',symbol=sym+'USDT',interval='60',end=stamp,limit=3))
 for i in range(3):
  try:
   with urllib.request.urlopen(BASE+'kline?'+q,timeout=30) as r: obj=json.load(r)
   rows=obj.get('result',{}).get('list',[])
   return {'symbol':sym+'USDT','date':date,'returned':len(rows),'latest_utc':dt.datetime.fromtimestamp(int(rows[0][0])/1000,dt.timezone.utc).isoformat() if rows else None,'error':obj.get('retMsg') if obj.get('retCode') else None}
  except Exception as exc:
   if i==2:return {'symbol':sym+'USDT','date':date,'error':str(exc)}
   time.sleep(2+i)
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
  rows=list(ex.map(probe,[(s,d) for s in SYMBOLS for d in DATES]))
 print(json.dumps(rows,indent=2));
 with open('research_intraday/coverage_probe.json','w') as f:json.dump(rows,f,indent=2)
