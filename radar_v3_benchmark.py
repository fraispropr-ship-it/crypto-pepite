"""Offline V3 walk-forward benchmark, not trading automation.

Fixed symbol cohort introduces survivorship bias. Uses H1 closed bars, fills next H1
open with adverse slippage, SL-before-TP conservative OHLC, 12h max, fees both sides.
Signals cannot overlap on the same symbol. One held-out chronological split per symbol.
"""
import json,os,time
from datetime import datetime,timezone
import requests,pandas as pd
from radar_v3_strategies import STRATEGIES

BASE="https://openapi.zoomex.com/cloud/trade/v3/market/kline"
SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","LINKUSDT","ADAUSDT","AVAXUSDT","DOGEUSDT","SUIUSDT","AAVEUSDT","NEARUSDT","APTUSDT"]
H=3600000
START=int(datetime(2026,6,1,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,10,20,tzinfo=timezone.utc).timestamp()*1000)
SPLIT=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp()*1000)
FEE=.0006;SLIPPAGE=.0002;MAX_HOLD=12
SESSION=requests.Session()

def fetch(symbol,start=START-130*H,end=END+MAX_HOLD*H):
    frames=[];cursor=end
    while cursor>start:
        j=None
        for attempt in range(3):
            try:
                response=SESSION.get(BASE,params=dict(category="linear",symbol=symbol,interval="60",end=cursor-1,limit=1000),timeout=20)
                response.raise_for_status()
                j=response.json()
                if j.get("retCode")==0 and j.get("result",{}).get("list"):break
            except (requests.RequestException,ValueError):pass
            time.sleep(.5*(attempt+1))
        if not j or j.get("retCode")!=0 or not j.get("result",{}).get("list"):
            raise RuntimeError("historical candles unavailable")
        block=pd.DataFrame([x[:6] for x in j["result"]["list"]],columns=list("tohlcv")).astype(float)
        frames.append(block)
        earliest=int(block.t.min())
        if earliest>=cursor:raise RuntimeError("pagination stalled")
        cursor=earliest
        if len(frames)>50:raise RuntimeError("pagination safety limit")
        time.sleep(.08)
    df=pd.concat(frames).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    df=df[(df.t>=start)&(df.t+H<=end)].reset_index(drop=True)
    if df.empty:
        raise RuntimeError(f"No candles for {symbol}")
    times=df.t.astype("int64")
    if (times.diff().iloc[1:]!=H).any():
        raise RuntimeError(f"Non-contiguous H1 candles for {symbol}")
    if int(times.iloc[0])>start+H or int(times.iloc[-1])+H<end-H:
        raise RuntimeError(f"Truncated H1 history for {symbol}")
    if (df.h < df.l).any() or (df.o <= 0).any() or (df.c <= 0).any():
        raise RuntimeError(f"Invalid OHLC candles for {symbol}")
    return df

def evaluate(df,i,sig):
    if i+1>=len(df):return None
    side=1 if sig["side"]=="LONG" else -1
    stop=sig["stop"]
    entry=float(df.o.iloc[i+1])*(1+side*SLIPPAGE)
    risk=side*(entry-stop)
    if risk<=0:return None
    if FEE*(entry+stop)/risk>.15:return None
    target=entry+side*2*risk
    last=min(i+MAX_HOLD,len(df)-1)
    for j in range(i+1,last+1):
        bar=df.iloc[j]
        open_px=float(bar.o)
        if (open_px<=stop if side==1 else open_px>=stop):
            exit_price=open_px*(1-side*SLIPPAGE);reason="GAP_SL";break
        hit_sl=bar.l<=stop if side==1 else bar.h>=stop
        hit_tp=bar.h>=target if side==1 else bar.l<=target
        if hit_sl:exit_price=stop*(1-side*SLIPPAGE);reason="SL";break
        if hit_tp:exit_price=target*(1-side*SLIPPAGE);reason="TP";break
    else:
        exit_price=float(df.c.iloc[last])*(1-side*SLIPPAGE);reason="TIME"
    r=(side*(exit_price-entry)-FEE*(entry+exit_price))/risk
    return dict(net_r=round(r,6),exit=reason,exit_index=last if reason=="TIME" else j)

def summarize(items):
    vals=[x["net_r"] for x in items];n=len(vals)
    return dict(n=n,total_r=round(sum(vals),3),mean_r=round(sum(vals)/n,4) if n else None,
                winners=sum(v>0 for v in vals),win_rate=round(sum(v>0 for v in vals)/n,3) if n else None,
                profit_factor=round(sum(v for v in vals if v>0)/abs(sum(v for v in vals if v<0)),3) if any(v<0 for v in vals) else None)

def main():
    trades=[];missing={}
    for sym in SYMBOLS:
        try:df=fetch(sym)
        except Exception as e:
            missing[sym]=str(e);print("MISSING",sym,str(e),flush=True);continue
        for name,fn in STRATEGIES.items():
            i=110
            while i<len(df)-MAX_HOLD:
                if not START<=int(df.t.iloc[i]+H)<END:
                    i+=1;continue
                # Strictly closed current and preceding bars.
                sig=fn(df.iloc[max(0,i-115):i+1])
                if sig is None:i+=1;continue
                result=evaluate(df,i,sig)
                if result is None:i+=1;continue
                trades.append(dict(symbol=sym,strategy=name,side=sig["side"],t=int(df.t.iloc[i]+H),**result))
                i=max(i+1,result["exit_index"]+1)
        print("DONE",sym,flush=True)
    overview={}
    for name in STRATEGIES:
        v=[t for t in trades if t["strategy"]==name]
        overview[name]=dict(train=summarize([t for t in v if t["t"]<SPLIT]),
                            holdout=summarize([t for t in v if t["t"]>=SPLIT]),
                            all=summarize(v))
    report=dict(method="Fixed-symbol H1 V3 research; closed candles, next-open fills; gap stop handling",
                window=["2026-06-01","2026-10-20"],holdout_starts="2026-09-01",
                market_data_failures=missing,strategies=overview,total=summarize(trades),
                assumptions=["FEE 0.06% each side; SLIPPAGE 0.02% each side",
                             "SL prioritized if stop and target occur in one OHLC bar",
                             "12h maximum holding; same-symbol overlap suppressed within each strategy",
                             "Fixed current-symbol universe: survivorship and selection bias",
                             "No funding, no orderbook fills, no BTC regime gate; not live validation"],
                trades=trades)
    with open("radar_v3_benchmark.json","w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print("SUMMARY",json.dumps({k:v for k,v in report.items() if k!="trades"},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
