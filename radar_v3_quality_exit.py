"""V3.2 research: entry-quality filters and alternative exit policies.
Uses *identical* compression signal occurrences for all experiments.
Training is before Sep 1; Sep-Oct holdout is reported, not optimized.
Research only; never places orders or sends alerts.
"""
import json
import pandas as pd
from radar_v3_benchmark import SYMBOLS,START,END,SPLIT,H,MAX_HOLD,FEE,SLIPPAGE,fetch,summarize,evaluate
from radar_v3_strategies import compression,atr

def features(df,i):
    bar=df.iloc[i]
    hist=df.iloc[i-20:i]
    vol=float(bar.v)/float(hist.v.mean())
    a=float(atr(df.iloc[max(0,i-100):i+1]).iloc[-1])
    spread=float(bar.h-bar.l)/a if a>0 else 999
    side=1 if bar.c>bar.o else -1
    breakout=float(hist.h.max()) if side==1 else float(hist.l.min())
    extension=side*(float(bar.c)-breakout)/a if a>0 else 999
    return dict(vol=round(vol,4),bar_atr=round(spread,4),extension=round(extension,4))

def alternative(df,i,signal,policy):
    if i+1>=len(df):return None
    side=1 if signal["side"]=="LONG" else -1
    stop=float(signal["stop"])
    entry=float(df.o.iloc[i+1])*(1+side*SLIPPAGE)
    risk=side*(entry-stop)
    if risk<=0 or FEE*(entry+stop)/risk>.15:return None
    tp_mult={"reference":2.0,"tp_1_5":1.5,"tp_2_5":2.5,"atr_trail":None}[policy]
    hard_stop=stop; peak=entry
    last=min(i+MAX_HOLD,len(df)-1)
    for j in range(i+1,last+1):
        x=df.iloc[j]
        # Previous complete bar's trail state only; never tighten using current-bar extrema
        current_stop=hard_stop
        target=entry+side*tp_mult*risk if tp_mult else None
        if (x.l<=current_stop if side==1 else x.h>=current_stop):
            exit_price=current_stop*(1-side*SLIPPAGE);why="SL";break
        if target is not None and (x.h>=target if side==1 else x.l<=target):
            exit_price=target*(1-side*SLIPPAGE);why="TP";break
        if policy=="atr_trail":
            # fixed 1.5 initial R trail behind max favorable excursion, no intrabar lookahead
            peak=max(peak,float(x.h)) if side==1 else min(peak,float(x.l))
            hard_stop=max(hard_stop,peak-side*1.5*risk) if side==1 else min(hard_stop,peak-side*1.5*risk)
    else:
        exit_price=float(df.c.iloc[last])*(1-side*SLIPPAGE);why="TIME"
    value=(side*(exit_price-entry)-FEE*(entry+exit_price))/risk
    return dict(net_r=round(value,6),exit=why)

QUALITY={
    "reference":lambda x:True,
    "volume_1_5":lambda x:x["vol"]>=1.5,
    "volume_2_0":lambda x:x["vol"]>=2.0,
    "body_atr_0_5_1_5":lambda x:0.5<=x["bar_atr"]<=1.5,
    "extension_below_0_4":lambda x:x["extension"]<=0.4,
    "volume_1_5_and_extension_0_4":lambda x:x["vol"]>=1.5 and x["extension"]<=0.4,
}
POLICIES=["reference","tp_1_5","tp_2_5","atr_trail"]

def split_stats(items):
    return {key:summarize([t for t in items if (t["t"]<SPLIT)==(key=="train")])
            for key in ("train","holdout")}

def main():
    records=[];missing={}
    for sym in SYMBOLS:
        try:
            df=fetch(sym)
            i=110
            while i<len(df)-MAX_HOLD:
                t=int(df.t.iloc[i]+H)
                if not START<=t<END:i+=1;continue
                signal=compression(df.iloc[max(0,i-115):i+1])
                if signal is None:i+=1;continue
                reference=evaluate(df,i,signal)
                if reference is None:i+=1;continue
                feats=features(df,i)
                r=dict(symbol=sym,t=t,features=feats,reference=reference["net_r"],
                       policies={})
                for policy in POLICIES:
                    alt=alternative(df,i,signal,policy)
                    if alt is not None:r["policies"][policy]=alt["net_r"]
                records.append(r)
                # Keep exact same baseline entry cohort as original benchmark
                i=max(i+1,reference["exit_index"]+1)
            print("DONE",sym,len(records),flush=True)
        except Exception as ex:
            missing[sym]=f"{type(ex).__name__}: {ex}"
    baseline=[dict(t=x["t"],net_r=x["reference"]) for x in records]
    q={name:split_stats([dict(t=x["t"],net_r=x["reference"]) for x in records if f(x["features"])])
       for name,f in QUALITY.items()}
    p={name:split_stats([dict(t=x["t"],net_r=x["policies"][name]) for x in records if name in x["policies"]])
       for name in POLICIES}
    output=dict(scope="Fixed-cohort sensitivity analysis, not forward validation",
                symbols=SYMBOLS,market_data_failures=missing,total_cohort=len(records),
                baseline=split_stats(baseline),quality=q,exit_policies=p,
                assumptions=["All variants use same frozen entry timestamps; no selection on holdout",
                             "Quality thresholds predeclared as research candidates, not tuned live",
                             "ATR trail adjusted for subsequent bars only; 12h expiration",
                             "Portfolio concurrency, funding and real spreads not modeled",
                             "Do not infer profitable deployable strategy from in-sample performance"],
                records=records)
    with open("radar_v3_quality_exit_report.json","w",encoding="utf-8") as f:
        json.dump(output,f,ensure_ascii=False,indent=2)
    print("SUMMARY",json.dumps({k:v for k,v in output.items() if k!="records"},ensure_ascii=False),flush=True)
    if missing:raise RuntimeError("Incomplete universe")

if __name__=="__main__":main()
