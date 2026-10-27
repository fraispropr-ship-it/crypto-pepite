"""Historical robustness check of fixed V3 compression filters, offline only."""
import json
from datetime import datetime,timezone
from radar_v3_benchmark import SYMBOLS,H,MAX_HOLD,fetch,evaluate,summarize
from radar_v3_strategies import compression
from radar_v3_quality_exit import features

def ms(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)
START=ms("2026-01-15")
END=ms("2026-06-01")
FILTERS={
 "reference":lambda x:True,
 "bar_0_5_to_1_5_atr":lambda x:0.5<=x["bar_atr"]<=1.5,
 "volume_2":lambda x:x["vol"]>=2,
 "extension_0_4":lambda x:x["extension"]<=0.4,
 "volume_1_5_extension_0_4":lambda x:x["vol"]>=1.5 and x["extension"]<=0.4,
}
def main():
    records=[];missing={}
    for symbol in SYMBOLS:
        try:
            df=fetch(symbol,start=START-125*H,end=END+MAX_HOLD*H)
            i=110
            while i<len(df)-MAX_HOLD:
                t=int(df.t.iloc[i]+H)
                if not START<=t<END:i+=1;continue
                signal=compression(df.iloc[max(0,i-115):i+1])
                if signal is None:i+=1;continue
                result=evaluate(df,i,signal)
                if result is None:i+=1;continue
                records.append(dict(symbol=symbol,t=t,net_r=result["net_r"],features=features(df,i)))
                i=max(i+1,result["exit_index"]+1)
            print("DONE",symbol,len(records),flush=True)
        except Exception as exc:
            missing[symbol]=str(exc);print("MISSING",symbol,str(exc),flush=True)
    months=[ms(x) for x in ("2026-02-01","2026-03-01","2026-04-01","2026-05-01","2026-06-01")]
    stats={}
    for name,condition in FILTERS.items():
        selected=[r for r in records if condition(r["features"])]
        stats[name]={"all":summarize(selected),"by_period":{
            str(a):summarize([r for r in selected if a<=r["t"]<b])
            for a,b in zip([START]+months[:-1],months)}}
    report={"scope":"Earlier-period robustness, parameters fixed before this evaluation",
            "period":"2026-01-15 through 2026-05-31",
            "symbols":SYMBOLS,"total_signals":len(records),"missing":missing,
            "results":stats,"limitations":["Earlier history is retrospective, not forward test",
              "Fixed current crypto universe may cause survivorship bias",
              "No funding or realized orderbook execution modeled",
              "No re-optimization using this period"]}
    with open("radar_v3_robustness_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report),flush=True)
    if missing:raise RuntimeError("Market data missing for some symbols")
if __name__=="__main__":main()
