"""Deterministic checks for conservative fills and portfolio constraints."""
import numpy as np
import pandas as pd
import lab

def test_engine():
 t=int(pd.Timestamp('2025-02-01',tz='UTC').timestamp()*1000); n=25
 d=pd.DataFrame({'t':[t+i*lab.H for i in range(n)],'o':[100.]*n,'h':[100.5]*n,'l':[99.5]*n,'c':[100.]*n,'v':[100.]*n})
 d.loc[4,['h','l']]=[105.,95.]
 sig=np.zeros(n);sig[3]=1
 original=lab.signals
 try:
  lab.signals=lambda df:(pd.Series(np.ones(n)),{'test':sig})
  trade=lab.generate('BTC',d,{},1)[0]
  assert trade['reason']=='stop' and abs(trade['net_r']+1)<1e-9
  d.loc[4,['h','l']]=[100.5,99.5]
  without=lab.generate('BTC',d,{},1)[0]
  with_funding=lab.generate('BTC',d,{t+5*lab.H:.001},1)[0]
  assert with_funding['net_r']<without['net_r']
 finally:lab.signals=original

def test_portfolio():
 t=[dict(entry_t=0,exit_t=lab.H,symbol='A',net_r=-1),dict(entry_t=0,exit_t=lab.H,symbol='B',net_r=1),dict(entry_t=lab.H,exit_t=2*lab.H,symbol='C',net_r=2),dict(entry_t=2*lab.H,exit_t=3*lab.H,symbol='D',net_r=2)]
 p=lab.portfolio(t)
 assert [x['symbol'] for x in p]==['A','C'] and lab.metrics(p)['total_R']==1

if __name__=='__main__':
 test_engine();test_portfolio();print('tests passed')
