"""Offline V3.6 diagnostic: market-state features known at signal time.
Reports prespecified groups, not a production model or optimized classifier.
"""
import json
from datetime import datetime,timezone
from radar_v3_benchmark import SYMBOLS,H,MAX_HOLD,fetch,evaluate,summarize
from radar_v3_strategies import compression,atr
from radar_v3_quality_exit import features
from radar_v3_regimes import regime,ms

START=ms("2026-01-15");END=ms("2026-10-20")

def state(df,i):
    view=df.iloc[:i+1]
    prices=view.c
    a=atr(view).iloc[-1]
    last24=prices.iloc[-25:]
    move=float(last24.iloc[-1]/last24.iloc[0]-1)
    efficiency=abs(float(last24.iloc[-1]-last24.iloc[0]))/max(float(last24.diff().abs().sum()),1e-12)
    tr=(atr(view)/view.c).iloc[-101:]
    rank=float((tr.iloc[:-1]<=tr.iloc[-1]).mean())
    return {"abs_24h_move":abs(move),"efficiency":efficiency,"volatility_rank":rank}

def group(row):
    s=row["state"]
    return {"calm":s["volatility_rank"]<.5,
            "high_volatility":s["volatility_rank"]>=.75,
            "directional_24h":s["efficiency"]>=.35,
            "choppy_24h":s["efficiency"]<.2,
            "small_move_24h":s["abs_24h_move"]<.03,
            "large_move_24h":s["abs_24h_move"]>=.05}

def summary(rows):
    early=ms("2026-06-01");recent=ms("2026-09-01")
    return {"all":summarize(rows),
            "jan_may":summarize([r for r in rows if r["t"]<early]),
            "jun_aug":summarize([r for r in rows if early<=r["t"]<recent]),
            "sep_oct":summarize([r for r in rows if r["t"]>=recent])}

def main():
    trades=[];missing={}
    for sym in SYMBOLS:
        try:
            df=fetch(sym,start=START-125*H,end=END+MAX_HOLD*H)
            i=110
            while i<len(df)-MAX_HOLD:
                timestamp=int(df.t.iloc[i]+H)
                if not START<=timestamp<END:i+=1;continue
                hist=df.iloc[max(0,i-115):i+1]
                sig=compression(hist)
                if sig is None:i+=1;continue
                result=evaluate(df,i,sig)
                if result is None:i+=1;continue
                feat=features(df,i)
                if regime(hist)=="range" and .5<=feat["bar_atr"]<=1.5:
                    trades.append({"symbol":sym,"t":timestamp,"net_r":result["net_r"],"state":state(df,i)})
                i=max(i+1,result["exit_index"]+1)
            print("DONE",sym,flush=True)
        except Exception as ex:
            missing[sym]=str(ex)
            print("MISSING",sym,str(ex),flush=True)
    groups={"reference":summary(trades)}
    for name in ("calm","high_volatility","directional_24h","choppy_24h","small_move_24h","large_move_24h"):
        groups[name]=summary([r for r in trades if group(r)[name]])
    report={"scope":"Exploratory diagnostic on preselected Range Compression candidate",
            "counts":len(trades),"missing":missing,"groups":groups,
            "cautions":["Retrospective grouping; any apparent best filter is post-hoc",
                        "Historical 12 symbol survivorship and portfolio constraints not applied",
                        "Same baseline execution assumptions, funding and book depth excluded",
                        "No independent validation; don't deploy based on these groups"]}
    with open("radar_v3_market_state_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report),flush=True)
    if missing:raise RuntimeError("Incomplete market data")
if __name__=="__main__":main()
