"""Regression tests for audited V3 historical execution."""
import unittest
import pandas as pd
from radar_v3_benchmark import evaluate, FEE, SLIPPAGE

def bars(points):
    return pd.DataFrame([dict(t=i*3600000,o=o,h=h,l=l,c=c,v=1000)
                         for i,(o,h,l,c) in enumerate(points)])

class ExecutionAudit(unittest.TestCase):
    def test_long_gap_through_stop_fills_at_open(self):
        d=bars([(100,102,99,101),(100,102,99,101),(90,92,88,89)])
        r=evaluate(d,0,dict(side="LONG",stop=95))
        # gap only after entry. The first post-entry candle is ordinary.
        self.assertEqual(r["exit"],"GAP_SL")
        entry=100*(1+SLIPPAGE)
        exit_px=90*(1-SLIPPAGE)
        expected=(exit_px-entry-FEE*(entry+exit_px))/(entry-95)
        self.assertAlmostEqual(r["net_r"],expected,places=5)

    def test_short_gap_through_stop_fills_at_open(self):
        d=bars([(100,101,99,100),(100,101,98,99),(111,114,110,113)])
        r=evaluate(d,0,dict(side="SHORT",stop=105))
        self.assertEqual(r["exit"],"GAP_SL")
        self.assertLess(r["net_r"],-1)

    def test_same_bar_sl_wins(self):
        d=bars([(100,101,99,100),(100,112,93,100)])
        r=evaluate(d,0,dict(side="LONG",stop=95))
        self.assertEqual(r["exit"],"SL")

    def test_no_future_entry(self):
        d=bars([(100,101,99,100)])
        self.assertIsNone(evaluate(d,0,dict(side="LONG",stop=95)))

if __name__=="__main__":unittest.main()
