"""40-crypto Trend Retest dry run: no Telegram messages, no orders."""
import json,time
from datetime import datetime,timezone
import requests
import trend_retest as tr

EXCLUDE={"XAU","XAUT","PAXG","XAG","GOLD","SILVER","SPX","SPY","QQQ","TSLA","AAPL","NVDA","MSFT","META","AMZN","COIN","MSTR","OIL","WTI","EUR","GBP"}
def main():
    started=time.monotonic()
    response=requests.get("https://openapi.zoomex.com/cloud/trade/v3/market/tickers",
                          params={"category":"linear"},timeout=30)
    response.raise_for_status()
    data=response.json()
    if data.get("retCode")!=0:raise RuntimeError("Zoomex tickers unavailable")
    candidates=[]
    for row in data["result"]["list"]:
        sym=row.get("symbol","")
        if not sym.endswith("USDT"):continue
        root=sym[:-4]
        if root in EXCLUDE or "STOCK" in root:continue
        try:
            turnover=float(row.get("turnover24h") or 0)
            if turnover>=10000000:candidates.append((turnover,sym))
        except (ValueError,TypeError):pass
    symbols=[s for _,s in sorted(candidates,reverse=True)[:40]]
    if len(symbols)<40:raise RuntimeError("Fewer than 40 eligible symbols")
    now=int(time.time()*1000)
    report={"run_at":datetime.now(timezone.utc).isoformat(),"symbols":symbols,"per_asset":{},"signals":[]}
    for n,sym in enumerate(symbols,1):
        t=time.monotonic()
        try:
            df=tr.fetch15(sym,now)
            signals=tr.detect(df,sym,now)
            report["per_asset"][sym]={"ok":True,"candles":len(df),"elapsed_s":round(time.monotonic()-t,2),"signals":len(signals)}
            report["signals"].extend(signals)
            print(f"CHECK {n}/40 {sym} OK candles={len(df)} signals={len(signals)}",flush=True)
        except Exception as e:
            report["per_asset"][sym]={"ok":False,"error":str(e),"elapsed_s":round(time.monotonic()-t,2)}
            print(f"CHECK {n}/40 {sym} FAIL {e}",flush=True)
    report["elapsed_s"]=round(time.monotonic()-started,2)
    report["ok"]=sum(x["ok"] for x in report["per_asset"].values())
    report["failed"]=40-report["ok"]
    with open("trend_retest_40_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps({"ok":report["ok"],"failed":report["failed"],"elapsed_s":report["elapsed_s"],"signal_count":len(report["signals"]),"failed_symbols":[s for s,v in report["per_asset"].items() if not v["ok"]]}),flush=True)
    if report["failed"]:raise RuntimeError("40-crypto scan not fully ready")
if __name__=="__main__":main()
