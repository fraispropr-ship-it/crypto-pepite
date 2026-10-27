"""Per-asset regime diagnostic for frozen V3 compression trades. Offline research."""
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from radar_v3_benchmark import SYMBOLS,H,MAX_HOLD,fetch,evaluate,summarize
from radar_v3_strategies import compression,atr,ema
from radar_v3_quality_exit import features

def ms(s):return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)
START=ms("2026-01-15");END=ms("2026-10-20")
SPLIT=ms("2026-06-01")
def regime(df):
    """Only historical closed bars available at current signal close."""
    if len(df)<110:return "unknown"
    close=df.c
    a=atr(df)
    v=float(a.iloc[-1]/close.iloc[-1])
    historical=(a/close).iloc[-101:-1].dropna()
    if len(historical)<80:return "unknown"
    volatility_rank=float((historical<=v).mean())
    e20=ema(close,20);e50=ema(close,50)
    slope=abs(float(e50.iloc[-1]-e50.iloc[-6]))/float(a.iloc[-1])
    directional=abs(float(close.iloc[-1]-close.iloc[-25]))/max(1e-12,float((close.diff().abs()).iloc[-24:].sum()))
    if volatility_rank>=.8 and directional<.3:return "chaotic"
    if slope>=.25 and directional>=.3:return "trending"
    return "range"

def stats(items):
    return dict(all=summarize(items),
                early=summarize([x for x in items if x["t"]<SPLIT]),
                later=summarize([x for x in items if x["t"]>=SPLIT]))
def main():
    rows=[];missing={}
    for sym in SYMBOLS:
        try:
            df=fetch(sym,start=START-125*H,end=END+MAX_HOLD*H)
            i=110
            while i<len(df)-MAX_HOLD:
                t=int(df.t.iloc[i]+H)
                if not START<=t<END:i+=1;continue
                view=df.iloc[max(0,i-115):i+1]
                sig=compression(view)
                if sig is None:i+=1;continue
                result=evaluate(df,i,sig)
                if result is None:i+=1;continue
                rows.append(dict(symbol=sym,t=t,net_r=result["net_r"],regime=regime(view),
                                 bar_atr=features(df,i)["bar_atr"]))
                i=max(i+1,result["exit_index"]+1)
            print("DONE",sym,len(rows),flush=True)
        except Exception as exc:
            missing[sym]=str(exc)
            print("MISSING",sym,str(exc),flush=True)
    results={"baseline":stats(rows)}
    for name in ("trending","range","chaotic","unknown"):
        results[name]=stats([x for x in rows if x["regime"]==name])
        results[name+"_amplitude"]=stats([x for x in rows if x["regime"]==name and .5<=x["bar_atr"]<=1.5])
    report=dict(scope="Exploratory, per-symbol H1 regime labels on fixed historical V3 compression cohort",
                periods=["2026-01-15 to 2026-05-31","2026-06-01 to 2026-10-19"],
                thresholds={"chaotic":"volatility rank >=80pct and efficiency <0.3",
                            "trending":"EMA50 5h absolute slope >=0.25 ATR and path efficiency >=0.3"},
                signal_count=len(rows),missing=missing,results=results,
                warnings=["Exploratory regime thresholds are not validated on independent future data",
                          "No lookahead: indicators use only signal-time closed H1 candles",
                          "Fixed current symbols; no funding, concurrency or live execution modeled"])
    with open("radar_v3_regimes_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report),flush=True)
    if missing:raise RuntimeError("Missing data for some symbols")
if __name__=="__main__":main()
