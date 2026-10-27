"""V3.1 BTC regime experiment: frozen compression signals, fair baseline comparison.
No orders, alerts or changes to existing V1. No parameter fitting on holdout.
"""
import json
import pandas as pd
from radar_v3_benchmark import (SYMBOLS,START,END,SPLIT,H,MAX_HOLD,fetch,evaluate,summarize)
from radar_v3_strategies import compression,ema

def btc_regimes(btc):
    """BTC H4 regime known at each completed H1 bar, no partial H4 use."""
    # H1 't' is open timestamp. Group H4 by UTC starting at 00:00 UTC.
    x=btc.copy()
    x["bucket"]=(x.t.astype("int64")//(4*H))*(4*H)
    h4=x.groupby("bucket",sort=True).agg(c=("c","last"),n=("c","size")).reset_index()
    h4=h4[h4.n==4].copy()
    h4["e20"]=ema(h4.c,20)
    h4["e50"]=ema(h4.c,50)
    h4["e50_prev"]=h4.e50.shift(2)
    h4["known_at"]=h4.bucket+4*H
    def regime(z):
        if pd.isna(z.e50_prev):return 0
        if z.c>z.e50 and z.e20>z.e50 and z.e50>z.e50_prev:return 1
        if z.c<z.e50 and z.e20<z.e50 and z.e50<z.e50_prev:return -1
        return 0
    h4["regime"]=h4.apply(regime,axis=1)
    return h4[["known_at","regime"]].sort_values("known_at")

def make_trades():
    btc=fetch("BTCUSDT",start=START-350*H,end=END+MAX_HOLD*H)
    regimes=btc_regimes(btc)
    all_trades=[];errors={}
    for symbol in SYMBOLS:
        try:
            df=fetch(symbol)
            # align latest *fully closed* H4 BTC regime with signal bar close
            align=pd.merge_asof(pd.DataFrame({"known_at":(df.t+H).astype("int64")}),
                                regimes,on="known_at",direction="backward")
            labels=align.regime.fillna(0).astype(int).tolist()
            i=110
            while i<len(df)-MAX_HOLD:
                end=int(df.t.iloc[i]+H)
                if not START<=end<END:i+=1;continue
                signal=compression(df.iloc[max(0,i-115):i+1])
                if signal is None:i+=1;continue
                result=evaluate(df,i,signal)
                if result is None:i+=1;continue
                side=1 if signal["side"]=="LONG" else -1
                all_trades.append(dict(symbol=symbol,t=end,side=signal["side"],btc_regime=labels[i],**result))
                i=max(i+1,result["exit_index"]+1)
        except Exception as ex:
            errors[symbol]=f"{type(ex).__name__}: {ex}"
        print("DONE",symbol,"signals",len(all_trades),flush=True)
    return all_trades,errors

def partitions(trades):
    return {"train":summarize([x for x in trades if x["t"]<SPLIT]),
            "holdout":summarize([x for x in trades if x["t"]>=SPLIT]),
            "all":summarize(trades)}

def main():
    trades,errors=make_trades()
    aligned=[x for x in trades if (x["side"]=="LONG" and x["btc_regime"]==1) or
                                   (x["side"]=="SHORT" and x["btc_regime"]==-1)]
    nonneutral=[x for x in trades if x["btc_regime"]!=0]
    report={"scope":"Frozen V3 Compression vs BTC fully-closed H4 regime, matching underlying trades",
            "market_data_failures":errors,
            "baseline":partitions(trades),
            "btc_trend_aligned":partitions(aligned),
            "btc_nonneutral_any_direction":partitions(nonneutral),
            "counts":{"baseline":len(trades),"aligned":len(aligned),"nonneutral":len(nonneutral)},
            "assumptions":["No lookahead: only completed BTC H4 observations at H1 signal close",
                           "Same exact trades, costs, fills and outcome simulation as original V3 baseline",
                           "Training/holdout periods reused from previous research: not fresh external validation",
                           "No funding, no market spread calibration, fixed survivor crypto cohort",
                           "Filtering does not model portfolio-level overlapping exposures"],
            "trades":trades}
    with open("radar_v3_btc_regime_report.json","w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print("SUMMARY",json.dumps({k:v for k,v in report.items() if k!="trades"},ensure_ascii=False),flush=True)
    if errors:raise RuntimeError(f"Missing symbols: {sorted(errors)}")

if __name__=="__main__":main()
