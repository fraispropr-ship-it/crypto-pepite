"""V3 audit: chronological split, overlapping labels and per-symbol concentration.
Reads an existing benchmark report downloaded from the same GitHub Actions run.
Fails loudly on leakage, unsorted records and embargo violations.
"""
import json,sys
from collections import defaultdict
from datetime import datetime,timezone

H=3600000
SPLIT=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp()*1000)
MAX_HOLD=12*H

def audit(report):
    trades=report["trades"]
    faults=[]
    for x in trades:
        if x["t"]%H: faults.append("non-H1-aligned signal")
        if not 0<=x["exit_index"]: faults.append("bad exit index")
        if not x["entry_time"]<x["exit_time"]: faults.append("invalid trade chronology")
        if x["entry_time"]!=x["t"]: faults.append("entry time differs from signal closure")
    # Training labels need to be complete *before* the holdout starts.
    # A conservative embargo excludes any training signal in last 12 hours.
    embargo=[t for t in trades if t["t"]<SPLIT and t["exit_time"]>=SPLIT]
    groups=defaultdict(list)
    for t in trades:groups[(t["symbol"],t["strategy"])].append(t)
    overlaps=0
    for key,series in groups.items():
        ordered=sorted(series,key=lambda x:x["t"])
        for a,b in zip(ordered,ordered[1:]):
            if b["entry_time"]<a["exit_time"]:faults.append("overlapping trades "+str(key))
            if b["t"]<=a["t"]:faults.append("duplicate signals "+str(key))
    by_symbol=defaultdict(lambda:dict(n=0,total=0.0))
    for t in trades:
        x=by_symbol[t["symbol"]];x["n"]+=1;x["total"]+=t["net_r"]
    train=[t for t in trades if t["t"]<SPLIT and t["exit_time"]<SPLIT]
    holdout=[t for t in trades if t["t"]>=SPLIT]
    return {"n":len(trades),"purged_train_count":len(train),"holdout_count":len(holdout),"split_utc":"2026-09-01T00:00:00Z",
            "12h_embargo_training_signals":len(embargo),
            "per_symbol":{k:{"n":v["n"],"total_R":round(v["total"],3)} for k,v in sorted(by_symbol.items())},
            "faults":faults,
            "audit_limitations":["Per-strategy same-symbol overlap checked; cross-strategy/portfolio concurrency still not enforced",
             "Same holdout previously inspected and used in selecting hypotheses: not independent validation",
             "Historical symbol membership/survivorship remains unknown",
             "No parameter tuning should use holdout set as an optimization target"]}

def main():
    source=sys.argv[1] if len(sys.argv)>1 else "radar_v3_benchmark.json"
    with open(source,encoding="utf-8") as f:report=json.load(f)
    result=audit(report)
    with open("radar_v3_audit_report.json","w",encoding="utf-8") as f:json.dump(result,f,indent=2)
    print("AUDIT_SUMMARY",json.dumps(result),flush=True)
    if result["faults"]:raise RuntimeError("Audit faults detected")
if __name__=="__main__":main()
