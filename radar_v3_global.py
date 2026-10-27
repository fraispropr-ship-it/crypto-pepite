"""V3.7 research: global pre-signal market context on fixed Range Compression trades.
BTC realized volatility; cross-sectional 24h dispersion; recent failed-breakout rate.
All features use only completed H1 bars, no live trading or alerts.
"""
import json
import numpy as np
import pandas as pd
from radar_v3_benchmark import SYMBOLS,H,MAX_HOLD,fetch,evaluate,summarize
from radar_v3_strategies import compression
from radar_v3_quality_exit import features
from radar_v3_regimes import regime,ms
START=ms("2026-01-15");END=ms("2026-10-20")
def summ(records):
    a=ms("2026-06-01");b=ms("2026-09-01")
    return {"all":summarize(records),"jan_may":summarize([r for r in records if r["t"]<a]),
            "jun_aug":summarize([r for r in records if a<=r["t"]<b]),
            "sep_oct":summarize([r for r in records if r["t"]>=b])}
def global_states(data):
    returns=[]
    for sym,df in data.items():
        d=df[["t","c"]].copy()
        d["r24"]=d.c/d.c.shift(24)-1
        returns.append(d.set_index("t")["r24"].rename(sym))
    matrix=pd.concat(returns,axis=1).sort_index()
    dispersion=matrix.std(axis=1)
    btc=data["BTCUSDT"].set_index("t").c
    vol=btc.pct_change().rolling(24).std()*(24**.5)
    # past H1 closed breakout failures; no future candles, trailing 72 h.
    high=btc.rolling(20).max().shift(1)
    low=btc.rolling(20).min().shift(1)
    breakout=((btc>high)|(btc<low)).astype(int)
    fail=(((btc.shift(1)>high.shift(1))&(btc<=high.shift(1)))|
          ((btc.shift(1)<low.shift(1))&(btc>=low.shift(1)))).astype(int)
    rate=fail.rolling(72).sum()/breakout.rolling(72).sum().clip(lower=1)
    state=pd.DataFrame({"dispersion":dispersion,"btc_vol":vol,"false_breakout":rate}).sort_index()
    # feature ranks anchored to trailing historical values, excluding current sample
    for name in ("dispersion","btc_vol","false_breakout"):
        s=state[name]
        state[name+"_rank"]=[float((s.iloc[max(0,i-240):i].dropna()<=s.iloc[i]).mean())
                             if i>=100 and len(s.iloc[max(0,i-240):i].dropna())>=60 and pd.notna(s.iloc[i])
                             else float("nan") for i in range(len(s))]
    return state
def main():
    data={};missing={}
    for sym in SYMBOLS:
        try:data[sym]=fetch(sym,start=START-400*H,end=END+MAX_HOLD*H).reset_index(drop=True)
        except Exception as e:missing[sym]=str(e)
    if missing:raise RuntimeError("Missing symbols: "+str(missing))
    state=global_states(data)
    rows=[]
    for sym,df in data.items():
        i=115
        while i<len(df)-MAX_HOLD:
            t=int(df.t.iloc[i]+H)
            if not START<=t<END:i+=1;continue
            hist=df.iloc[i-115:i+1]
            signal=compression(hist)
            if signal is None:i+=1;continue
            res=evaluate(df,i,signal)
            if res is None:i+=1;continue
            feat=features(df,i)
            if regime(hist)=="range" and .5<=feat["bar_atr"]<=1.5:
                # indexed at H1 open time, values reflect same just-closed signal candle
                st=state.loc[int(df.t.iloc[i])]
                rows.append(dict(symbol=sym,t=t,net_r=res["net_r"],
                                 btc_vol_rank=float(st.btc_vol_rank),
                                 dispersion_rank=float(st.dispersion_rank),
                                 false_breakout_rank=float(st.false_breakout_rank)))
            i=max(i+1,res["exit_index"]+1)
        print("DONE",sym,len(rows),flush=True)
    definitions={
        "btc_vol_low":lambda r:r["btc_vol_rank"]<.5,
        "btc_vol_high":lambda r:r["btc_vol_rank"]>=.75,
        "dispersion_low":lambda r:r["dispersion_rank"]<.5,
        "dispersion_high":lambda r:r["dispersion_rank"]>=.75,
        "breakout_failures_low":lambda r:r["false_breakout_rank"]<.5,
        "breakout_failures_high":lambda r:r["false_breakout_rank"]>=.75}
    report={"scope":"Exploratory global regime diagnostic on frozen V3 Range Compression trade cohort",
            "n":len(rows),"baseline":summ(rows),
            "groups":{name:summ([x for x in rows if f(x)]) for name,f in definitions.items()},
            "notes":["Same historical cohort, no unseen validation: post-hoc groups cannot prove edge",
                     "Global feature ranks computed using preceding <=240 H1 observations",
                     "No actual orderbook spreads or funding; historical survivor-coin sample",
                     "False breakout proxy uses BTC 20h boundary failure on previous hourly bars"]}
    with open("radar_v3_global_report.json","w") as f:json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report),flush=True)
if __name__=="__main__":main()
