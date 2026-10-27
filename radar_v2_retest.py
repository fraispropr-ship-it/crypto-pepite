"""Research: H1 breakout then M15 retest (no live orders).

Conditional cohort of original V1 triggered levels. Enter only after a later
M15 candle touches breakout level and closes back above it; execution at NEXT
M15 open. Use pre-existing structural V1 invalidation as stop; fixed 2R TP;
conservative SL-first within M15; 12h horizon; costs included.
"""
import csv,json,math,time
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import pandas as pd
from radar_v2_replay import candles,atr_at_signal
from radar_v2_filters import confirm_breakout

PARIS=ZoneInfo("Europe/Paris")
HOUR=3600000
M15=900000
FEE=.0006
SLIPPAGE=.0002
HORIZON=12
RETEST_WINDOW=8  # 8 M15 bars = 2h after breakout
TOLERANCE=.001   # 0.1% overshoot below breakout permitted


def evaluate(row):
    end=int(datetime.strptime(row["date_declenchement"],"%Y-%m-%d %H:%M").replace(tzinfo=PARIS).timestamp()*1000)
    symbol=row["symbole"]
    level=float(row["id"].split("|")[-1])
    sl=float(row["sl"])
    # Fetch historical candles ending after outcome window: includes H1 breakout + 12h follow-up
    h1=candles(symbol,"60",end-1,100)
    m15=candles(symbol,"15",end+(HORIZON+3)*HOUR,100)
    if h1 is None or m15 is None:return dict(status="missing",reason="API")
    h1=h1[h1.t+HOUR<=end]
    historical=m15[(m15.t+M15<=end)&(m15.t>=end-HOUR)]
    after=m15[(m15.t>=end)&(m15.t<end+(HORIZON+1)*HOUR)].sort_values("t").reset_index(drop=True)
    if len(h1)<20 or int(h1.t.iloc[-1]+HOUR)!=end or len(historical)!=4:
        return dict(status="missing",reason="history")
    atr=atr_at_signal(h1)
    signal_ok,why=confirm_breakout(h1,historical,level,atr,end)
    if not signal_ok:return dict(status="filtered",reason=why)
    if len(after)<HORIZON*4 or list(after.t.astype(int))[:HORIZON*4]!=[end+i*M15 for i in range(HORIZON*4)]:
        return dict(status="missing",reason="future candles incomplete")
    for i in range(RETEST_WINDOW):
        x=after.iloc[i]
        if x.l<=level*(1+TOLERANCE) and x.c>level and x.c>x.o:
            # cannot buy at close of the confirmation bar; use next bar open
            entry=float(after.iloc[i+1].o)*(1+SLIPPAGE)
            if not entry>sl>0:return dict(status="filtered",reason="invalidated stop")
            risk=entry-sl
            if FEE*(entry+sl)/risk>.15:return dict(status="filtered",reason="fees excessive")
            tp=entry+2*risk
            # evaluate from the NEXT candle (whose open is execution)
            for j in range(i+1,HORIZON*4):
                bar=after.iloc[j]
                if bar.l<=sl:exit_price=sl*(1-SLIPPAGE);reason="SL";break
                if bar.h>=tp:exit_price=tp*(1-SLIPPAGE);reason="TP";break
            else:
                exit_price=float(after.iloc[HORIZON*4-1].c)*(1-SLIPPAGE)
                reason="EXPIRE"
            gross=(exit_price-entry)/risk
            net=gross-FEE*(entry+exit_price)/risk
            return dict(status="trade",net_R=round(net,5),gross_R=round(gross,5),
                        exit=reason,delay_M15=i+1)
    return dict(status="no_retest",reason="no confirmed retest")


def metrics(rows):
    if not rows:return dict(n=0,net_total_R=0,net_mean_R=None,win_rate=None)
    v=[x["net_R"] for x in rows]
    return dict(n=len(v),net_total_R=round(sum(v),3),net_mean_R=round(sum(v)/len(v),4),
                win_rate=round(sum(x>0 for x in v)/len(v),4),
                tp=sum(x["exit"]=="TP" for x in rows),
                sl=sum(x["exit"]=="SL" for x in rows),
                expire=sum(x["exit"]=="EXPIRE" for x in rows))


def main():
    with open("radar_journal.csv",newline="",encoding="utf-8") as f:
        rows=[r for r in csv.DictReader(f) if r["statut"]!="EXPIRE_SANS_DONNEES"]
    results=[]; counts=defaultdict(int); reasons=defaultdict(int)
    for i,r in enumerate(rows,1):
        try:z=evaluate(r)
        except Exception as ex:z=dict(status="missing",reason=type(ex).__name__)
        z.update(symbol=r["symbole"],date=r["date_declenchement"],setup=r["type"])
        results.append(z);counts[z["status"]]+=1
        if z.get("reason"):reasons[z["reason"]]+=1
        if i%20==0:print("PROGRESS",i,len(rows),flush=True)
    trades=[x for x in results if x["status"]=="trade"]
    out=dict(method="Conditional V1 trigger cohort; V2 H1/M15 confirmation plus later retest entry",
             rows=len(rows),counts=dict(counts),reasons=dict(reasons),metrics=metrics(trades),
             by_type={typ:metrics([x for x in trades if x["setup"]==typ]) for typ in ("continuation","retournement")},
             trades=trades,
             notes=["12h max after breakout, retest within 2h, next M15 open fill",
                    "0.06% taker each side and 0.02% adverse slippage each side",
                    "V1 structural stop and fixed 2R, same-bar stop before target",
                    "No intrabar execution ordering, exchange funding, or liquidity modeling",
                    "Not a full independent V2 setup universe; selection bias possible"])
    with open("radar_v2_retest_report.json","w",encoding="utf-8") as f:json.dump(out,f,ensure_ascii=False,indent=2)
    print("RESULT_SUMMARY",json.dumps({k:v for k,v in out.items() if k!="trades"},ensure_ascii=False),flush=True)


if __name__=="__main__":main()
