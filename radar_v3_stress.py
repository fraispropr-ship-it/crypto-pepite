"""V3.5 frozen range-compression stress and portfolio risk test, no live actions.
Research cohort Jan-Oct 2026. No new out-of-sample data claimed.
"""
import json
from datetime import datetime,timezone
from radar_v3_benchmark import SYMBOLS,H,MAX_HOLD,fetch,evaluate,FEE,SLIPPAGE,summarize
from radar_v3_strategies import compression
from radar_v3_quality_exit import features
from radar_v3_regimes import regime,ms

START=ms("2026-01-15");END=ms("2026-10-20")
def candidates():
    out=[];missing={}
    for sym in SYMBOLS:
        try:
            df=fetch(sym,start=START-125*H,end=END+MAX_HOLD*H)
            i=110
            while i<len(df)-MAX_HOLD:
                t=int(df.t.iloc[i]+H)
                if not START<=t<END:i+=1;continue
                hist=df.iloc[max(0,i-115):i+1]
                sig=compression(hist)
                if sig is None:i+=1;continue
                result=evaluate(df,i,sig)
                if result is None:i+=1;continue
                f=features(df,i)
                if regime(hist)=="range" and .5<=f["bar_atr"]<=1.5:
                    # R-based cost uplift for round-trip additional slippage/fees;
                    # reconstruct price distance from next-open execution and original stop
                    side=1 if sig["side"]=="LONG" else -1
                    entry=float(df.o.iloc[i+1])*(1+side*SLIPPAGE)
                    risk=side*(entry-float(sig["stop"]))
                    cost_ratio=(2*entry)/risk
                    out.append(dict(symbol=sym,t=t,exit_time=int(df.t.iloc[result["exit_index"]]+H),
                                    net_r=result["net_r"],cost_ratio=cost_ratio))
                i=max(i+1,result["exit_index"]+1)
            print("DONE",sym,len(out),flush=True)
        except Exception as e:
            missing[sym]=str(e);print("MISSING",sym,str(e),flush=True)
    return sorted(out,key=lambda z:(z["t"],z["symbol"])),missing

def select(rows,max_concurrent=2,max_daily=2):
    retained=[];daily={}
    for x in rows:
        day=datetime.fromtimestamp(x["t"]/1000,tz=timezone.utc).strftime("%Y-%m-%d")
        if daily.get(day,0)>=max_daily:continue
        if sum(r["exit_time"]>x["t"] for r in retained)>=max_concurrent:continue
        retained.append(x);daily[day]=daily.get(day,0)+1
    return retained

def analyze(rows,extra_bps=0):
    adjusted=[dict(net_r=x["net_r"]-extra_bps/10000*x["cost_ratio"]) for x in rows]
    return summarize(adjusted)

def main():
    rows,missing=candidates()
    constrained=select(rows)
    costs=[0,5,10,20]  # additional per-side combined fee/slippage in basis points
    report=dict(scope="Retrospective stress-test of preselected range+0.5..1.5 ATR compression signals",
                n_raw=len(rows),n_constrained=len(constrained),
                cap="two new trades per UTC day; max two simultaneously open trades",
                market_data_errors=missing,
                scenario_bps="Extra fee+slippage basis points per side in addition to original assumptions",
                scenarios={str(b):{"raw":analyze(rows,b),"capped":analyze(constrained,b)} for b in costs},
                time_splits={label:{"raw":analyze([x for x in rows if lo<=x["t"]<hi]),
                                     "capped":analyze([x for x in constrained if lo<=x["t"]<hi])}
                             for label,lo,hi in [
                                ("jan_may",START,ms("2026-06-01")),
                                ("jun_aug",ms("2026-06-01"),ms("2026-09-01")),
                                ("sep_oct",ms("2026-09-01"),END)]},
                notes=["Not independent unseen data: regime and candle thresholds selected based on past history",
                       "Selection by ascending time and ticker is deterministic but not a portfolio ranking",
                       "Position risk assumed equal in R; drawdown/funding/orderbook not modeled",
                       "Conservative OHLC stop-first execution inherited from benchmark"])
    with open("radar_v3_stress_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report),flush=True)
    if missing:raise RuntimeError("Missing data")
if __name__=="__main__":main()
