"""H1 ATR threshold sweep on historical V1 signals, conditional V2 replay.
A selection exercise, NOT a full strategy backtest. No trading/Telegram.
"""
import csv,json
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from radar_v2_replay import candles, atr_at_signal
from radar_v2_filters import confirm_breakout
import radar_v2_filters as filters

PARIS=ZoneInfo("Europe/Paris")
THRESHOLDS=[1.0,1.2,1.4,1.6,1.8,2.0,2.25,2.5,3.0,3.5,4.0,5.0,10.0]
def net_r(r):
    e,sl,g=float(r["entree"]),float(r["sl"]),float(r["resultat_R"])
    return g-0.0006*(e+max(0,e+g*(e-sl)))/(e-sl)

def main():
    with open("radar_journal.csv",newline="",encoding="utf-8") as f:
        rows=[r for r in csv.DictReader(f) if r["statut"]!="EXPIRE_SANS_DONNEES"]
    samples=[]; missing=[]
    for i,r in enumerate(rows,1):
        try:
            end=int(datetime.strptime(r["date_declenchement"],"%Y-%m-%d %H:%M").replace(tzinfo=PARIS).timestamp()*1000)
            h1=candles(r["symbole"],"60",end-1,100)
            m15=candles(r["symbole"],"15",end-1,8)
            if h1 is None or m15 is None: raise ValueError("missing API")
            h1=h1[h1.t+3600000<=end]
            m15=m15[m15.t+900000<=end]
            if len(h1)<20 or int(h1.t.iloc[-1]+3600000)!=end: raise ValueError("unsynced H1")
            level=float(r["id"].split("|")[-1])
            a=atr_at_signal(h1)
            amplitude=float(h1.iloc[-1].h-h1.iloc[-1].l)/a
            old=filters.MAX_H1_ATR
            try:
                filters.MAX_H1_ATR=100000
                accepted,_=confirm_breakout(h1,m15,level,a,end)
            finally: filters.MAX_H1_ATR=old
            samples.append(dict(date=end,ratio=amplitude,passes_other=accepted,r=net_r(r),type=r["type"]))
        except Exception as exc:
            missing.append(dict(symbol=r["symbole"],reason=str(exc)))
        if i%25==0:print("PROGRESS",i,len(rows),flush=True)
    samples.sort(key=lambda x:x["date"])
    cutoff=int(len(samples)*.65)
    train,test=samples[:cutoff],samples[cutoff:]
    def aggregate(sub, threshold):
        keep=[x for x in sub if x["passes_other"] and x["ratio"]<=threshold]
        if not keep:return dict(n=0,mean_net_R=None,total_net_R=0)
        total=sum(x["r"] for x in keep)
        return dict(n=len(keep),mean_net_R=round(total/len(keep),4),total_net_R=round(total,3))
    table=[dict(threshold=t,train=aggregate(train,t),test=aggregate(test,t),all=aggregate(samples,t)) for t in THRESHOLDS]
    eligible=[x for x in table if x["train"]["n"]>=8]
    best=max(eligible,key=lambda x:x["train"]["mean_net_R"]) if eligible else None
    out=dict(scope="Conditional H1 gate on previously triggered V1 trades; NOT independent V2 outcomes",
             total=len(rows),covered=len(samples),missing=missing[:10],
             chronological_split=dict(train=len(train),test=len(test)),
             thresholds=table,
             selected_train_threshold=best["threshold"] if best else None,
             holdout_result=best["test"] if best else None,
             warnings=["H1 threshold tuned on same historical universe; train/test split only one holdout",
                       "Filters besides H1 amplitude unchanged; BTC and position sizing excluded",
                       "V1 entry/exit and approximate fee-based outcomes reused, no slippage or funding",
                       "Do not infer forward profitability or launch live trading from this"])
    with open("radar_v2_h1_sweep_report.json","w",encoding="utf-8") as f:json.dump(out,f,ensure_ascii=False,indent=2)
    print("REPORT_START");print(json.dumps(out,ensure_ascii=False,indent=2));print("REPORT_END")

if __name__=="__main__":main()
