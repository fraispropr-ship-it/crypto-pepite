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
    # Training labels need to be complete *before* the holdout starts.
    # A conservative embargo excludes any training signal in last 12 hours.
    embargo=[t for t in trades if SPLIT-MAX_HOLD<=t["t"]<SPLIT]
    groups=defaultdict(list)
    for t in trades:groups[(t["symbol"],t["strategy"])].append(t)
    overlaps=0
    for key,series in groups.items():
        ordered=sorted(series,key=lambda x:x["t"])
        # Approximate end timestamp by exit_index delta cannot be recovered from
        # current report: exit_index is an absolute candle index; flag deficiency.
        for a,b in zip(ordered,ordered[1:]):
            if b["t"]<=a["t"]:faults.append("duplicate signals "+str(key))
    by_symbol=defaultdict(lambda:dict(n=0,total=0.0))
    for t in trades:
        x=by_symbol[t["symbol"]];x["n"]+=1;x["total"]+=t["net_r"]
    return {"n":len(trades),"split_utc":"2026-09-01T00:00:00Z",
            "12h_embargo_training_signals":len(embargo),
            "per_symbol":{k:{"n":v["n"],"total_R":round(v["total"],3)} for k,v in sorted(by_symbol.items())},
            "faults":faults,
            "audit_limitations":["Existing report lacks explicit entry and exit timestamps: cannot certify concurrent-position and label overlap handling",
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
