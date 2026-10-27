"""Radar Alt V4: isolated offline H4 trend / H1 breakout / M15 retest benchmark.
Rules fixed before inspection. No orders, Telegram sends, or main changes.
All timestamps UTC. Signal at H1 candle close; H4 only fully closed bars.
"""
import json,time
from datetime import datetime,timezone
import requests,pandas as pd
BASE="https://openapi.zoomex.com/cloud/trade/v3/market/kline"
FEE=.0006
SLIPPAGE=.0002

SYMBOLS=[]
STEP=900000
START=int(datetime(2026,6,1,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,10,20,tzinfo=timezone.utc).timestamp()*1000)
SPLIT=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp()*1000)

def fetch15(symbol):
    cursor=END+13*3600000
    start=START-220*4*3600000
    chunks=[]
    session=requests.Session()
    while cursor>start:
        j=None
        for attempt in range(4):
            try:
                r=session.get(BASE,params=dict(category="linear",symbol=symbol,interval="15",end=cursor-1,limit=1000),timeout=25)
                r.raise_for_status()
                j=r.json()
                if j.get("retCode")==0 and j.get("result",{}).get("list"):break
            except (requests.RequestException,ValueError):pass
            time.sleep(0.5*(attempt+1))
        if j is None or j.get("retCode")!=0 or not j.get("result",{}).get("list"):
            raise RuntimeError("Unable to fetch M15 history")
        d=pd.DataFrame([x[:6] for x in j["result"]["list"]],columns=list("tohlcv")).astype(float)
        chunks.append(d)
        last=int(d.t.min())
        if last>=cursor:raise RuntimeError("Pagination stalled")
        cursor=last
        if len(chunks)>110:raise RuntimeError("Pagination cap reached")
        time.sleep(.07)
    df=pd.concat(chunks).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    df=df[(df.t>=start)&(df.t+STEP<=END+13*3600000)].reset_index(drop=True)
    if df.empty or (df.t.astype("int64").diff().iloc[1:]!=STEP).any():
        raise RuntimeError("Missing M15 historical candles")
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

def evaluate(m15,start_i,side,stop,risk,entry):
    tp=entry+side*2*risk
    last=min(start_i+47,len(m15)-1)
    for j in range(start_i,last+1):
        b=m15.iloc[j]
        opened=float(b.o)
        if (side==1 and opened<=stop) or (side==-1 and opened>=stop):
            px=opened*(1-side*SLIPPAGE);reason="GAP_SL";break
        if (side==1 and b.l<=stop) or (side==-1 and b.h>=stop):
            px=stop*(1-side*SLIPPAGE);reason="SL";break
        if (side==1 and b.h>=tp) or (side==-1 and b.l<=tp):
            px=tp*(1-side*SLIPPAGE);reason="TP";break
    else:
        j=last;px=float(m15.c.iloc[j])*(1-side*SLIPPAGE);reason="TIME"
    result=(side*(px-entry)-FEE*(entry+px))/risk
    return dict(net_r=round(result,6),reason=reason,exit_time=int(m15.t.iloc[j]+STEP))

def scan(df,symbol):
    h1=aggregate(df,3600000);h4=aggregate(df,14400000)
    a1=atr(h1)
    at15=atr(df)
    index={int(t):i for i,t in enumerate(df.t)}
    trades=[];busy_until=0
    for i in range(205,len(h1)-2):
        bar=h1.iloc[i];closed=int(bar.t+3600000)
        if not START<=closed<END or closed<busy_until:continue
        side=trend(h4,closed)
        if not side:continue
        prev=h1.iloc[i-20:i]
        level=float(prev.h.max() if side==1 else prev.l.min())
        amp=float(a1.iloc[i])
        if not amp>0 or not .8<=(bar.h-bar.l)/amp<=1.8:continue
        if float(bar.v)<1.3*float(prev.v.mean()):continue
        if not ((bar.c>level and bar.c>bar.o) if side==1 else (bar.c<level and bar.c<bar.o)):continue
        k=index.get(closed)
        if k is None:continue
        # Up to 4 M15 candles to retest, then require a confirming M15
        # candle within that same 4-candle window. No forward peeking at entry.
        test=None
        for r in range(k,min(k+4,len(df)-2)):
            b=df.iloc[r]
            zone=.25*amp
            touched=(b.l<=level+zone and b.h>=level-zone)
            if not touched:continue
            if side==1 and b.c<level-zone:continue
            if side==-1 and b.c>level+zone:continue
            test=r
            break
        if test is None:continue
        confirm=None
        for q in range(test+1,min(k+4,len(df)-1)):
            b=df.iloc[q]
            if (side==1 and b.c>level and b.c>b.o and b.c>df.h.iloc[test]) or (side==-1 and b.c<level and b.c<b.o and b.c<df.l.iloc[test]):
                confirm=q
                break
        if confirm is None:continue
        entry_i=confirm+1
        if entry_i>=len(df):continue
        entry=float(df.o.iloc[entry_i])*(1+side*SLIPPAGE)
        # Stop beyond retest extremes, plus 0.1 M15 ATR
        low=float(df.l.iloc[test:confirm+1].min())
        high=float(df.h.iloc[test:confirm+1].max())
        stop=(low-.1*float(at15.iloc[confirm])) if side==1 else (high+.1*float(at15.iloc[confirm]))
        risk=side*(entry-stop)
        if risk<=0 or FEE*(entry+stop)/risk>.15:continue
        if abs(entry-level)>.9*amp:continue
        result=evaluate(df,entry_i,side,stop,risk,entry)
        trades.append(dict(symbol=symbol,t=closed,entry_time=int(df.t.iloc[entry_i]),side=side,stop=stop,entry=entry,**result))
        busy_until=result["exit_time"]
    return trades

def stats(rows):
    vals=[r["net_r"] for r in rows]
    gains=sum(max(v,0) for v in vals);loss=sum(-min(v,0) for v in vals)
    return {"n":len(vals),"total_R":round(sum(vals),3),"mean_R":round(sum(vals)/len(vals),4) if vals else None,"pf":round(gains/loss,3) if loss else None}

def main():
    from radar_alt import HORS_CRYPTO, MOTS_HORS_CRYPTO, base_de
    tick=requests.get("https://openapi.zoomex.com/cloud/trade/v3/market/tickers",params={"category":"linear"},timeout=30).json()
    if tick.get("retCode")!=0:raise RuntimeError("Zoomex tickers unavailable")
    elig=[]
    for row in tick["result"]["list"]:
        sym=row.get("symbol","")
        if not sym.endswith("USDT") or base_de(sym) in HORS_CRYPTO or any(m in sym for m in MOTS_HORS_CRYPTO):continue
        try:
            v=float(row.get("turnover24h") or 0)
            if v>=10000000:elig.append((v,sym))
        except (ValueError,TypeError):pass
    symbols=[v for _,v in sorted(elig,reverse=True)[:40]]
    if len(symbols)!=40:raise RuntimeError("Fewer than 40 markets")
    alltrades=[];errors={}
    for sym in symbols:
        try:
            rows=scan(fetch15(sym),sym)
            alltrades+=rows
            print("DONE",sym,len(rows),flush=True)
        except Exception as exc:
            errors[sym]=str(exc);print("MISSING",sym,str(exc),flush=True)
    report={"method":"Fixed V4 H4/H1/M15 retest offline research, no live integration",
            "rules":"H4 EMA50/200; H1 20-bar break, 0.8-1.8 ATR, 1.3x volume; 4 M15 retest/confirm; 2R; max12h",
            "assumptions":"0.06% taker fee each side; 0.02% adverse slippage each side; stop first on same M15 bar",
            "symbols":symbols,"errors":errors,"overall":stats(alltrades),
            "train":stats([x for x in alltrades if x["t"]<SPLIT and x["exit_time"]<SPLIT]),
            "holdout":stats([x for x in alltrades if x["t"]>=SPLIT]),
            "by_symbol":{s:stats([x for x in alltrades if x["symbol"]==s]) for s in symbols},
            "limitations":["Historical sample and candidate were selected after V1-V3 research; September holdout not pristine",
                           "No concurrent cross-asset portfolio allocation, funding, orderbook spread or real execution",
                           "40 present-day high-volume symbols; survivorship bias"],"trades":alltrades}
    with open("trend_retest_40_backtest_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps({k:v for k,v in report.items() if k!="trades"}),flush=True)
    if errors:raise RuntimeError("Market data missing for one or more symbols")
if __name__=="__main__":main()
