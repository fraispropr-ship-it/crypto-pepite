"""Rebond Éclair: experimental long-only H1 rejection alerts, no trading orders.
Replaces Trend Retest. Fixed rules from research; live reference is indicative.
"""
import concurrent.futures,html,json,os,time,urllib.parse,urllib.request
from pathlib import Path
import pandas as pd
SYMBOLS=[s+'USDT' for s in 'BTC ETH SOL XRP LINK ADA AVAX DOGE SUI AAVE NEAR APT BNB UNI ONDO HYPE INJ 1000PEPE WLD ZRO'.split()]
H=3600000;FEE=.0006;SLIP=.0002;STATE=Path('rebond_eclair_state.json')
def call(url,payload=None):
 data=None if payload is None else json.dumps(payload).encode()
 req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def fetch(symbol,now):
 url='https://openapi.zoomex.com/cloud/trade/v3/market/kline?'+urllib.parse.urlencode(dict(category='linear',symbol=symbol,interval='60',limit=500))
 for n in range(3):
  try:
   obj=call(url)
   if obj.get('retCode')!=0:raise RuntimeError('Zoomex API error')
   d=pd.DataFrame([r[:6] for r in obj['result']['list']],columns=list('tohlcv')).astype(float).sort_values('t').reset_index(drop=True)
   ref=float(d.c.iloc[-1]);closed=d[d.t+H<=now].reset_index(drop=True)
   if len(closed)<250 or closed.t.duplicated().any() or (closed.t.diff().iloc[1:]!=H).any() or int(closed.t.iloc[-1])+H!=(now//H)*H:raise RuntimeError('Incomplete H1 coverage')
   if (closed[['o','h','l','c']]<=0).any().any() or (closed.h<closed[['o','c','l']].max(axis=1)).any() or (closed.l>closed[['o','c','h']].min(axis=1)).any():raise RuntimeError('Invalid OHLC')
   return detect(closed,symbol,now,ref)
  except Exception:
   if n==2:raise
   time.sleep(n+1)
def detect(d,symbol,now,ref):
 prev=d.c.shift();atr=pd.concat([d.h-d.l,(d.h-prev).abs(),(d.l-prev).abs()],axis=1).max(axis=1).ewm(alpha=1/14,adjust=False).mean();b=d.iloc[-1];a=float(atr.iloc[-1]);closed=int(b.t)+H
 if now-closed>15*60000:return None
 if not (b.h-b.l>2*a and b.c>b.o and b.o-b.l>.55*(b.h-b.l)):return None
 # Indicator uses closed bars only; reference may use forming bar price for timeliness.
 entry=ref*(1+SLIP);distance=1.5*a;stop=entry-distance;target=entry+1.75*distance
 if stop<=0:return None
 qty=1/(entry-stop*(1-SLIP)+FEE*(entry+stop*(1-SLIP)))
 if qty*entry>10000:return None
 return dict(id=f'{symbol}:{closed}',symbol=symbol,closed=closed,reference=ref,entry=entry,stop=stop,target=target,quantity=qty)
def send(token,chat,text,buttons=None):
 payload={'chat_id':chat,'text':text,'parse_mode':'HTML','disable_web_page_preview':True}
 if buttons:payload['reply_markup']={'inline_keyboard':buttons}
 try:r=call('https://api.telegram.org/bot'+token+'/sendMessage',payload)
 except Exception:raise RuntimeError('Telegram delivery failed (details redacted)') from None
 if not r.get('ok'):raise RuntimeError('Telegram rejected delivery')
def choose(found,state,now):
 day=str(now//(24*H));counts=state.get('counts',{});sent=state.get('sent',{})
 if now<state.get('busy_until',0) or counts.get(day,0)>=2:return None
 return next((s for s in sorted(found,key=lambda s:s['symbol']) if s['id'] not in sent),None)
def main():
 now=int(time.time()*1000);token=os.environ.get('TELEGRAM_TOKEN');chat=os.environ.get('TELEGRAM_CHAT_ID')
 if not token or not chat:raise RuntimeError('Missing Telegram secrets')
 state=json.loads(STATE.read_text()) if STATE.exists() else {'sent':{},'counts':{},'busy_until':0}
 found=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as e:
  futs={e.submit(fetch,s,now):s for s in SYMBOLS}
  for f in concurrent.futures.as_completed(futs):
   try:
    signal=f.result()
    if signal:found.append(signal)
   except Exception:errors.append(futs[f])
 if errors:raise RuntimeError('Incomplete scan, no alerts sent: '+','.join(sorted(errors)))
 signal=choose(found,state,now)
 gh='https://github.com/fraispropr-ship-it/crypto-pepite/actions/workflows/trend-retest.yml'
 if signal:
  s=signal;fmt=lambda x:format(x,'.8g')
  text=('<b>⚡ REBOND ÉCLAIR — LONG</b>\n<b>'+html.escape(s['symbol'])+'</b> · rejet après excès H1\n\nPrix de référence : <code>'+fmt(s['reference'])+'</code>\nSL indicatif : <code>'+fmt(s['stop'])+'</code>\nTP indicatif : <code>'+fmt(s['target'])+'</code>\nQuantité indicative : <code>'+fmt(s['quantity'])+'</code>\nRisque prévu : 1 USDT hors funding et gaps · levier ≤10×\nDurée maximale : 12h · cible brute 1,75× distance du stop\n\n⚠️ Expérimental, non validé. Vérifier prix, frais, taille minimale et quantité. Aucun ordre automatique.')
  send(token,chat,text,[[{'text':'📈 TradingView','url':'https://www.tradingview.com/chart/?symbol=ZOOMEX:'+s['symbol']+'.P&interval=60'}],[{'text':'▶️ Lancer dans GitHub','url':gh}]])
  state.setdefault('sent',{})[s['id']]=now;day=str(now//(24*H));state.setdefault('counts',{})[day]=state['counts'].get(day,0)+1;state['busy_until']=now+12*H
  STATE.write_text(json.dumps(state,indent=2))
 if os.environ.get('SEND_STATUS')=='true':
  send(token,chat,'<b>⚡ Rebond Éclair — scan terminé</b>\n20 cryptos contrôlées · longs uniquement.\n'+('Une alerte a été envoyée.' if signal else 'Aucune nouvelle alerte éligible.')+'\nMaximum 2 alertes/jour UTC ; blocage conservateur de 12h après une alerte.\nScanner expérimental : aucun ordre automatique.',[[{'text':'▶️ Lancer dans GitHub','url':gh}]])
 state['sent']={k:v for k,v in state.get('sent',{}).items() if now-v<45*24*H};state['counts']={k:v for k,v in state.get('counts',{}).items() if int(k)>=now//(24*H)-2};STATE.write_text(json.dumps(state,indent=2))
 print(json.dumps({'scanner':'Rebond Eclair','symbols':20,'candidates':len(found),'alerts_sent':int(signal is not None)}))
if __name__=='__main__':main()
