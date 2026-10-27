"""Expanded historical H4 setup replay, research only, no orders/Telegram.

Cohort: fixed documented liquid crypto symbols; retrospective selection caveat.
Scan H4 closes over a fixed date interval, generate original setup candidates
from CLOSED H4 and D candles, require closed H1 breakout and M15 confirmation,
then require subsequent retest. Uses original V2 indicators.
"""
import json,math
from datetime import datetime,timezone
import pandas as pd
from radar_alt import continuation,retournement,atr,H1,H4,JOUR
from radar_v2_replay import candles
from radar_v2_filters import confirm_breakout

SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","LINKUSDT","ADAUSDT","AVAXUSDT","DOGEUSDT","SUIUSDT","AAVEUSDT","NEARUSDT","APTUSDT"]
START=int(datetime(2026,9,10,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,10,22,tzinfo=timezone.utc).timestamp()*1000)
SLIPPAGE=.0002
FEE=.0006


def load(symbol,iv,start,end):
    dur={"15":900000,"60":H1,"240":H4,"D":JOUR}[iv]
    out=[]
    current=end
    while current>=start:
        segment=candles(symbol,iv,current-1,100)
        if segment is None:raise RuntimeError(f"market data missing {symbol} {iv} {current}")
        out.append(segment)
        earliest=int(segment.t.min())
        if earliest<=start:break
        if earliest>=current:raise RuntimeError("pagination stalled")
        current=earliest
    df=pd.concat(out).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return df[(df.t>=start)&(df.t+dur<=end)].reset_index(drop=True)


def simulate(m15,end,level,stop,maxbars=48):
    fut=m15[(m15.t>=end)&(m15.t<end+maxbars*900000)].reset_index(drop=True)
    if len(fut)!=maxbars or list(fut.t.astype(int))!=[end+i*900000 for i in range(maxbars)]:
        return None
    for i in range(8):
        x=fut.iloc[i]
        if x.l<=level*1.001 and x.c>level and x.c>x.o:
            entry=float(fut.iloc[i+1].o)*(1+SLIPPAGE)
            if entry<=stop:return None
            risk=entry-stop
            if FEE*(entry+stop)/risk>.15:return None
            tp=entry+2*risk
            for j in range(i+1,maxbars):
                bar=fut.iloc[j]
                if bar.l<=stop:exit_px=stop*(1-SLIPPAGE);why="SL";break
                if bar.h>=tp:exit_px=tp*(1-SLIPPAGE);why="TP";break
            else:exit_px=float(fut.iloc[-1].c)*(1-SLIPPAGE);why="EXP"
            r=(exit_px-entry-FEE*(entry+exit_px))/risk
            return dict(net_R=round(r,5),exit=why,entry=entry,stop=stop)
    return None


def run():
    trades=[]; counts=dict(setups=0,breakouts=0,confirmed=0,eligible=0,missing=0)
    for sym in SYMBOLS:
        if sym=="BTCUSDT":continue
        try:
            d=load(sym,"D",START-110*JOUR,END+JOUR)
            h4=load(sym,"240",START-240*H4,END+H4)
            h1=load(sym,"60",START-120*H1,END+H1)
            m15=load(sym,"15",START-H1,END+14*H1)
        except Exception as ex:
            print("MISSING",sym,str(ex),flush=True);counts["missing"]+=1;continue
        seen=set()
        for end in range(START,END,H4):
            past4=h4[h4.t+H4<=end]
            pastd=d[d.t+JOUR<=end]
            if len(past4)<80 or len(pastd)<60:continue
            for fn in (lambda:continuation(past4,pastd),lambda:retournement(past4)):
                candidate=fn()
                if not candidate:continue
                level=float(candidate["declenchement"]);stop=float(candidate["invalidation"])
                key=(sym,candidate["type"],round(level,8))
                if key in seen:continue
                seen.add(key);counts["setups"]+=1
                # Follow up to 24h for an H1 CLOSE beyond level. Evaluation causal.
                futures=h1[(h1.t+H1>end)&(h1.t+H1<=end+24*H1)]
                for _,bar in futures.iterrows():
                    at=int(bar.t+H1)
                    past1=h1[h1.t+H1<=at]
                    if bar.c<stop:break
                    if bar.c<=level:continue
                    counts["breakouts"]+=1
                    last15=m15[(m15.t+900000<=at)&(m15.t>=at-H1)]
                    h1atr=float(atr(past1).iloc[-1])
                    ok,why=confirm_breakout(past1,last15,level,h1atr,at)
                    if ok:
                        counts["confirmed"]+=1
                        result=simulate(m15,at,level,stop)
                        if result:
                            counts["eligible"]+=1
                            trades.append(dict(symbol=sym,type=candidate["type"],t=at,**result))
                    break
        print("DONE",sym,"trades",len(trades),flush=True)
    trades.sort(key=lambda x:x["t"])
    boundary=int(len(trades)*.65)
    def stat(arr):
        n=len(arr)
        return dict(n=n,mean_net_R=round(sum(x["net_R"] for x in arr)/n,4) if n else None,
                    total_net_R=round(sum(x["net_R"] for x in arr),3),
                    wins=sum(x["net_R"]>0 for x in arr))
    out=dict(symbols=SYMBOLS[1:],start="2026-09-10",end="2026-10-22",
             counts=counts,all=stat(trades),early=stat(trades[:boundary]),
             late=stat(trades[boundary:]),
             by_type={t:stat([x for x in trades if x["type"]==t]) for t in ("continuation","retournement")},
             trades=trades,
             caveats=["Fixed retrospective liquid-coin universe, not historical top100",
                      "No BTC gate, no funding, conservative same-bar SL first",
                      "No independent unseen future evaluation; parameter tuning performed previously",
                      "24-hour trigger search; 2-hour retest; 12-hour outcome"])
    with open("radar_v2_expanded_report.json","w",encoding="utf-8") as f:json.dump(out,f,indent=2)
    print("SUMMARY",json.dumps({k:v for k,v in out.items() if k!="trades"}),flush=True)

if __name__=="__main__":run()
