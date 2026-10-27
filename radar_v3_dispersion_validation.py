"""V3.8 historical robustness of predeclared high-dispersion rule.
Earlier data; 2 new trades/day, max 2 simultaneous, stress extra 5/10 bps per side.
Not a clean unseen holdout: historical universe and hypothesis were selected retrospectively.
"""
import json
from datetime import datetime,timezone
import pandas as pd
from radar_v3_benchmark import SYMBOLS,H,MAX_HOLD,fetch,evaluate,summarize
from radar_v3_strategies import compression
from radar_v3_quality_exit import features
from radar_v3_regimes import regime,ms

START=ms("2025-09-01");END=ms("2026-01-15")
def states(data):
    cols=[]
    for sym,df in data.items():
        d=df[["t","c"]].copy();d["r24"]=d.c/d.c.shift(24)-1
        cols.append(d.set_index("t").r24.rename(sym))
    disp=pd.concat(cols,axis=1).sort_index().std(axis=1)
    rank=pd.Series(index=disp.index,dtype=float)
    for i in range(100,len(disp)):
        prev=disp.iloc[max(0,i-240):i].dropna()
        if len(prev)>=60 and pd.notna(disp.iloc[i]):
            rank.iloc[i]=float((prev<=disp.iloc[i]).mean())
    return rank

def capped(rows):
    kept=[];daily={}
    for x in sorted(rows,key=lambda r:(r["t"],r["symbol"])):
        day=datetime.fromtimestamp(x["t"]/1000,tz=timezone.utc).strftime("%Y-%m-%d")
        if daily.get(day,0)>=2:continue
        if sum(q["exit_time"]>x["t"] for q in kept)>=2:continue
        kept.append(x);daily[day]=daily.get(day,0)+1
    return kept
def summary(rows,stress_bps=0):
    return summarize([{"net_r":x["net_r"]-(stress_bps/10000)*x["cost_ratio"]} for x in rows])
def main():
    data={};failures={}
    for sym in SYMBOLS:
        try:data[sym]=fetch(sym,start=START-400*H,end=END+MAX_HOLD*H)
        except Exception as exc:failures[sym]=str(exc)
    if failures:raise RuntimeError(str(failures))
    ranks=states(data);rows=[]
    for sym,df in data.items():
        i=115
        while i<len(df)-MAX_HOLD:
            t=int(df.t.iloc[i]+H)
            if not START<=t<END:i+=1;continue
            window=df.iloc[i-115:i+1]
            sig=compression(window)
            if sig is None:i+=1;continue
            trade=evaluate(df,i,sig)
            if trade is None:i+=1;continue
            f=features(df,i)
            if regime(window)=="range" and .5<=f["bar_atr"]<=1.5:
                val=ranks.get(int(df.t.iloc[i]),float("nan"))
                if pd.notna(val) and val>=.75:
                    direction=1 if sig["side"]=="LONG" else -1
                    entry=float(df.o.iloc[i+1])*(1+direction*.0002)
                    risk=direction*(entry-float(sig["stop"]))
                    rows.append({"symbol":sym,"t":t,"exit_time":int(df.t.iloc[trade["exit_index"]]+H),
                                 "net_r":trade["net_r"],"cost_ratio":2*entry/risk})
            i=max(i+1,trade["exit_index"]+1)
        print("DONE",sym,len(rows),flush=True)
    limited=capped(rows)
    bysymbol={sym:summary([r for r in limited if r["symbol"]==sym]) for sym in SYMBOLS}
    bymonth={}
    for r in limited:
        key=datetime.fromtimestamp(r["t"]/1000,tz=timezone.utc).strftime("%Y-%m")
        bymonth.setdefault(key,[]).append(r)
    report={"scope":"Prior-period fixed threshold high-dispersion Range Compression research",
            "dates":["2025-09-01","2026-01-15"],"n":len(rows),"capped_n":len(limited),
            "costs":{"additional_0bps":summary(limited),
                     "additional_5bps_per_side":summary(limited,5),
                     "additional_10bps_per_side":summary(limited,10)},
            "per_symbol":bysymbol,"per_month":{k:summary(v) for k,v in sorted(bymonth.items())},
            "notes":["Previously optimized on 2026 dataset: this is a retrospective earlier-period challenge, not live-forward validation",
                     "Fixed modern crypto selection is survivorship biased",
                     "2 max trades per UTC day, 2 simultaneous by H1 candle close approximation",
                     "Portfolio correlation, funding and orderbook execution omitted"]}
    with open("radar_v3_dispersion_validation.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report),flush=True)
if __name__=="__main__":main()
