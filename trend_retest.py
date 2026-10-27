"""Trend Retest: independent Telegram-only H4/H1/M15 signal scanner.
Research strategy not validated; alerts are informational and NEVER place orders.
"""
import os,json,time,html
from datetime import datetime,timezone
import requests,pandas as pd
BASE="https://openapi.zoomex.com/cloud/trade/v3/market/kline"
SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","LINKUSDT"]
STEP=900000
FEE=.0006
SLIPPAGE=.0002
STATE="trend_retest_state.json"

def fetch15(symbol,now):
    # 230 completed H4 candles of warmup + recent H1 and M15
    start=now-235*4*3600000
    end=(now//STEP)*STEP
    cursor=end
    session=requests.Session();chunks=[]
    while cursor>start:
        payload=None
        for attempt in range(4):
            try:
                rr=session.get(BASE,params={"category":"linear","symbol":symbol,"interval":"15","end":cursor-1,"limit":1000},timeout=25)
                rr.raise_for_status()
                payload=rr.json()
                if payload.get("retCode")==0 and payload.get("result",{}).get("list"):break
            except (requests.RequestException,ValueError):
                pass
            time.sleep(.5*(attempt+1))
        if not payload or payload.get("retCode")!=0 or not payload.get("result",{}).get("list"):
            raise RuntimeError("M15 historical candles unavailable")
        d=pd.DataFrame([row[:6] for row in payload["result"]["list"]],columns=list("tohlcv")).astype(float)
        chunks.append(d)
        earliest=int(d.t.min())
        if earliest>=cursor:raise RuntimeError("Pagination stalled")
        cursor=earliest
        if len(chunks)>15:raise RuntimeError("Pagination limit")
        time.sleep(.08)
    df=pd.concat(chunks).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    df=df[(df.t>=start)&(df.t+STEP<=now)].reset_index(drop=True)
    if df.empty or (df.t.astype("int64").diff().iloc[1:]!=STEP).any():
        raise RuntimeError("Incomplete M15 candles")
    return df

def aggregate(m15,interval):
    x=m15.copy()
    x["bucket"]=(x.t.astype("int64")//interval)*interval
    g=x.groupby("bucket",sort=True)
    d=g.agg(o=("o","first"),h=("h","max"),l=("l","min"),c=("c","last"),v=("v","sum"),n=("t","size")).reset_index().rename(columns={"bucket":"t"})
    return d[d.n==interval//STEP].reset_index(drop=True)

def atr(d,n=14):
    previous=d.c.shift(1)
    tr=pd.concat([(d.h-d.l),(d.h-previous).abs(),(d.l-previous).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def trend(h4,t):
    # Must be completely closed by time t
    sub=h4[h4.t+14400000<=t]
    if len(sub)<205:return 0
    e50=sub.c.ewm(span=50,adjust=False).mean()
    e200=sub.c.ewm(span=200,adjust=False).mean()
    if sub.c.iloc[-1]>e50.iloc[-1]>e200.iloc[-1] and e50.iloc[-1]>e50.iloc[-5]:return 1
    if sub.c.iloc[-1]<e50.iloc[-1]<e200.iloc[-1] and e50.iloc[-1]<e50.iloc[-5]:return -1
    return 0

def detect(df,symbol,now):
    h1=aggregate(df,3600000);h4=aggregate(df,14400000)
    a1=atr(h1);a15=atr(df)
    index={int(t):i for i,t in enumerate(df.t)}
    ideas=[]
    # Limit breakout candidates to last 2h, but require complete context.
    for i in range(max(205,len(h1)-4),len(h1)):
        bar=h1.iloc[i];closed=int(bar.t+3600000)
        if closed>now or closed<now-3*3600000:continue
        side=trend(h4,closed)
        if side==0:continue
        prev=h1.iloc[i-20:i]
        level=float(prev.h.max() if side==1 else prev.l.min())
        amp=float(a1.iloc[i])
        if amp<=0 or not .8<=(bar.h-bar.l)/amp<=1.8:continue
        if float(bar.v)<1.3*float(prev.v.mean()):continue
        if not ((bar.c>level and bar.c>bar.o) if side==1 else (bar.c<level and bar.c<bar.o)):continue
        k=index.get(closed)
        if k is None:continue
        found=None
        for r in range(k,min(k+4,len(df))):
            b=df.iloc[r];zone=.25*amp
            touched=b.l<=level+zone and b.h>=level-zone
            if not touched or (side==1 and b.c<level-zone) or (side==-1 and b.c>level+zone):continue
            for q in range(r+1,min(k+4,len(df))):
                x=df.iloc[q]
                confirmed=(side==1 and x.c>level and x.c>x.o and x.c>df.h.iloc[r]) or (side==-1 and x.c<level and x.c<x.o and x.c<df.l.iloc[r])
                if confirmed:
                    found=(r,q);break
            if found:break
        if not found:continue
        r,q=found
        confirmed_at=int(df.t.iloc[q]+STEP)
        if not now-40*60000<=confirmed_at<=now:continue
        # Current reference is last completed M15 close, not fictitious next-open fill.
        ref=float(df.c.iloc[-1])
        low=float(df.l.iloc[r:q+1].min());high=float(df.h.iloc[r:q+1].max())
        stop=low-.1*float(a15.iloc[q]) if side==1 else high+.1*float(a15.iloc[q])
        risk=side*(ref-stop)
        if risk<=0 or FEE*(ref+stop)/risk>.15:continue
        if abs(ref-level)>.9*amp:continue
        target=ref+side*2*risk
        signal_id=f"{symbol}:{int(bar.t)}:{confirmed_at}:{side}"
        ideas.append({"id":signal_id,"symbol":symbol,"side":"LONG" if side==1 else "SHORT",
                      "confirmed_at":confirmed_at,"reference":ref,"stop":stop,
                      "target":target,"level":level})
    return ideas

def send(token,chat,message):
    r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                    data={"chat_id":chat,"text":message,"parse_mode":"HTML","disable_web_page_preview":True},timeout=20)
    r.raise_for_status()
    if not r.json().get("ok"):raise RuntimeError("Telegram rejected message")

def main():
    token=os.environ.get("TELEGRAM_TOKEN");chat=os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:raise RuntimeError("Missing Telegram secrets")
    now=int(time.time()*1000)
    try:
        with open(STATE,encoding="utf8") as f:old=json.load(f)
    except FileNotFoundError:old={"sent":{}}
    sent=old.get("sent",{})
    errors={};found=[];new=[]
    for sym in SYMBOLS:
        try:
            signals=detect(fetch15(sym,now),sym,now)
            found+=signals
            for s in signals:
                if s["id"] not in sent:new.append(s)
        except Exception as ex:
            errors[sym]=str(ex);print("DATA_ERROR",sym,str(ex),flush=True)
    # Do not emit partial-market messages when data fails; a complete scan is required.
    if errors:raise RuntimeError("Incomplete scan: "+str(errors))
    for s in sorted(new,key=lambda x:x["confirmed_at"]):
        fmt=lambda v:format(v,".8g")
        txt=("<b>🎯 TREND RETEST — "+s["side"]+"</b>\n"
             +"<b>"+html.escape(s["symbol"])+"</b> · H4/H1/M15\n"
             +"Cassure H1 + retest M15 confirmé\n"
             +"Prix de référence (non garanti) : <code>"+fmt(s["reference"])+"</code>\n"
             +"SL indicatif : <code>"+fmt(s["stop"])+"</code>\n"
             +"TP 2R indicatif : <code>"+fmt(s["target"])+"</code>\n"
             +"Risque cible : 1 USDT (taille à vérifier)\n"
             +"<a href=\"https://www.tradingview.com/chart/?symbol=ZOOMEX:"+s["symbol"]+".P&interval=15\">TradingView M15</a>\n"
             +"⚠️ Stratégie expérimentale, vérifier prix et frais avant toute décision.")
        send(token,chat,txt)
        sent[s["id"]]=now
        # Immediately persist locally; workflow persists the file to GitHub.
        with open(STATE,"w") as f:json.dump({"sent":sent},f,indent=2)
        print("SENT",s["id"],flush=True)
    sent={k:v for k,v in sent.items() if now-v<45*86400000}
    with open(STATE,"w") as f:json.dump({"sent":sent},f,indent=2)
    print("SUMMARY",json.dumps({"new":len(new),"candidates":len(found),"symbols":len(SYMBOLS)}),flush=True)

if __name__=="__main__":main()
