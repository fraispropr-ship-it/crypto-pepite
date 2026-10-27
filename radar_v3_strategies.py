"""Radar Alt V3 research strategies. Pure offline signals, no exchange orders.

Three independent candidates evaluated at the CLOSE of the latest candle.
DataFrame columns: t,o,h,l,c,v. Decisions use closed candles only.
"""
import math
import pandas as pd

def atr(df,n=14):
    c=df.c.shift(1)
    tr=pd.concat([(df.h-df.l),(df.h-c).abs(),(df.l-c).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def ema(s,n):
    return s.ewm(span=n,adjust=False).mean()

def context(df):
    if len(df)<100:return 0
    e20,e50=ema(df.c,20),ema(df.c,50)
    return 1 if df.c.iloc[-1]>e50.iloc[-1] and e20.iloc[-1]>e50.iloc[-1] and e50.iloc[-1]>e50.iloc[-5] else -1 if df.c.iloc[-1]<e50.iloc[-1] and e20.iloc[-1]<e50.iloc[-1] and e50.iloc[-1]<e50.iloc[-5] else 0

def candidate(name, side, price, stop, timestamp):
    if not math.isfinite(price) or not math.isfinite(stop):return None
    if (side==1 and stop>=price) or (side==-1 and stop<=price):return None
    risk=abs(price-stop)
    if risk<=0:return None
    return dict(strategy=name, side="LONG" if side==1 else "SHORT",
                signal_time=int(timestamp),trigger=float(price),stop=float(stop),
                target=float(price+side*2*risk))

def compression(df):
    if len(df)<110:return None
    side=context(df)
    if not side:return None
    x=df.iloc[-1];prev=df.iloc[-21:-1]
    widths=(df.c.rolling(20).std()/df.c.rolling(20).mean()).iloc[-101:-1].dropna()
    if len(widths)<80:return None
    # Require previous contraction vs own history; no current candle leakage.
    recent_width=float(widths.iloc[-1])
    if recent_width>float(widths.quantile(.25)):return None
    high,low=float(prev.h.max()),float(prev.l.min())
    a=float(atr(df).iloc[-1])
    if side==1 and not (x.c>high and x.c>x.o):return None
    if side==-1 and not (x.c<low and x.c<x.o):return None
    if abs(float(x.c)-(high if side==1 else low))>0.7*a:return None
    if x.v<1.3*float(df.v.iloc[-21:-1].mean()):return None
    return candidate("compression_expansion",side,float(x.c),low-0.2*a if side==1 else high+0.2*a,x.t)

def pullback(df):
    if len(df)<105:return None
    side=context(df)
    if not side:return None
    x=df.iloc[-1];p=df.iloc[-2]
    e20=ema(df.c,20)
    a=float(atr(df).iloc[-1])
    if side==1 and not (p.l<=e20.iloc[-2] and x.c>e20.iloc[-1] and x.c>p.h and x.c>x.o):return None
    if side==-1 and not (p.h>=e20.iloc[-2] and x.c<e20.iloc[-1] and x.c<p.l and x.c<x.o):return None
    if abs(float(x.c-e20.iloc[-1]))>1.2*a:return None
    return candidate("trend_pullback",side,float(x.c),min(float(p.l),float(x.l))-0.2*a if side==1 else max(float(p.h),float(x.h))+0.2*a,x.t)

def momentum(df):
    if len(df)<105:return None
    side=context(df)
    if not side:return None
    x=df.iloc[-1];a=float(atr(df).iloc[-1])
    high=float(df.h.iloc[-11:-1].max());low=float(df.l.iloc[-11:-1].min())
    if not (0.7*a<=x.h-x.l<=1.7*a):return None
    if x.v<1.5*float(df.v.iloc[-21:-1].mean()):return None
    if side==1 and not (x.c>high and x.c>x.o and (x.c-x.l)/(x.h-x.l)>.75):return None
    if side==-1 and not (x.c<low and x.c<x.o and (x.h-x.c)/(x.h-x.l)>.75):return None
    stop=float(x.l)-0.2*a if side==1 else float(x.h)+0.2*a
    return candidate("momentum_continuation",side,float(x.c),stop,x.t)

STRATEGIES={"compression_expansion":compression,"trend_pullback":pullback,"momentum_continuation":momentum}
