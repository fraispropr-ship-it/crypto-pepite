"""Re-evaluate historical V1 triggers with V2 H1/M15 gates using Zoomex candles.
Conditional retrospective test ONLY: tests filtering V1 signals, not fresh V2 setups.
Fails closed for missing market data; tracks coverage separately. No orders or Telegram.
"""
import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from radar_v2_filters import confirm_breakout

API = "https://openapi.zoomex.com/cloud/trade/v3/market/kline"
PARIS = ZoneInfo("Europe/Paris")
SESSION = requests.Session()


def candles(symbol, interval, end_ms, limit=100):
    args = dict(category="linear", symbol=symbol, interval=interval,
                end=int(end_ms), limit=limit)
    for attempt in range(3):
        try:
            r = SESSION.get(API, params=args, timeout=15)
            r.raise_for_status()
            j = r.json()
            if j.get("retCode") == 0 and isinstance(j.get("result", {}).get("list"), list):
                a = j["result"]["list"]
                if not a:
                    return None
                df = pd.DataFrame([x[:6] for x in a], columns=["t","o","h","l","c","v"]).astype(float)
                return df.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        except (requests.RequestException, ValueError, TypeError):
            pass
        time.sleep(0.3*(attempt+1))
    return None


def atr_at_signal(h1):
    pc = h1.c.shift()
    tr = pd.concat([h1.h-h1.l, (h1.h-pc).abs(), (h1.l-pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1])


def sample_stats(rows, fee_rate=0.0006):
    if not rows:
        return {"n": 0, "total_R_net_est": None, "mean_R_net_est": None}
    vals=[]
    for r in rows:
        e, sl, gross = float(r["entree"]), float(r["sl"]), float(r["resultat_R"])
        exit_px = e+gross*(e-sl)
        vals.append(gross-fee_rate*(e+max(exit_px,0))/(e-sl))
    return dict(n=len(vals), total_R_net_est=round(sum(vals),3),
                mean_R_net_est=round(sum(vals)/len(vals),4),
                winners=sum(x>0 for x in vals))


def replay(journal_path="radar_journal.csv"):
    with open(journal_path, newline="", encoding="utf-8") as f:
        rows=[r for r in csv.DictReader(f) if r["statut"] != "EXPIRE_SANS_DONNEES"]
    included, rejected, missing = [], [], []
    reasons = defaultdict(int)
    for idx, r in enumerate(rows, 1):
        try:
            moment = datetime.strptime(r["date_declenchement"], "%Y-%m-%d %H:%M").replace(tzinfo=PARIS)
            end_ms = int(moment.timestamp()*1000)
            level = float(r["id"].split("|")[-1])
            h1 = candles(r["symbole"], "60", end_ms-1, 100)
            m15 = candles(r["symbole"], "15", end_ms-1, 8)
            if h1 is None or m15 is None:
                missing.append((r,"API indisponible"))
                continue
            h1 = h1[h1.t+3_600_000 <= end_ms]
            m15 = m15[m15.t+900_000 <= end_ms]
            if len(h1)<20 or len(m15)<4 or int(h1.t.iloc[-1]+3_600_000)!=end_ms:
                missing.append((r,"historique incomplet ou désynchronisé"))
                continue
            ok, reason = confirm_breakout(h1,m15,level,atr_at_signal(h1),end_ms)
            (included if ok else rejected).append(r)
            reasons[reason]+=1
        except Exception as exc:
            missing.append((r, type(exc).__name__))
        if idx%20 == 0:
            print("PROGRESS",idx,"/",len(rows),flush=True)
    return {
        "scope":"Conditional V2 H1/M15 filters on historical V1 triggered trades only, not full V2 strategy",
        "total_v1":len(rows), "covered":len(included)+len(rejected), "missing":len(missing),
        "v1_all":sample_stats(rows),
        "v1_covered":sample_stats(included+rejected),
        "v2_passed":sample_stats(included),
        "v2_rejected":sample_stats(rejected),
        "rejection_reasons":dict(reasons),
        "missing_examples":[{"symbol":r["symbole"],"date":r["date_declenchement"],"reason":why} for r,why in missing[:15]],
        "limitations":["historical universe is V1 signals only","no V2-specific candidates",
                       "outcomes reused from V1, not simulated alternative entries/exits",
                       "taker fees estimated; slippage and funding excluded",
                       "BTC filter and sizing not included in this H1/M15 comparison"]
    }


if __name__ == "__main__":
    output = replay()
    with open("radar_v2_replay_report.json","w",encoding="utf-8") as f:
        json.dump(output,f,ensure_ascii=False,indent=2)
    print("REPORT_JSON_START")
    print(json.dumps(output, ensure_ascii=False,indent=2))
    print("REPORT_JSON_END")
