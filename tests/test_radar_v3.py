import unittest
import pandas as pd
from radar_v3_strategies import STRATEGIES,context,candidate
from radar_v3_benchmark import evaluate,summarize

class V3Tests(unittest.TestCase):
    def test_three_independent_strategies(self):
        self.assertEqual(len(STRATEGIES),3)

    def test_no_setup_on_insufficient_history(self):
        df=pd.DataFrame([dict(t=0,o=1,h=2,l=.5,c=1.2,v=100)])
        for f in STRATEGIES.values():self.assertIsNone(f(df))

    def test_directional_stop_validation(self):
        self.assertIsNone(candidate("x",1,100,101,0))
        self.assertIsNone(candidate("x",-1,100,99,0))

    def test_stop_first_conservative(self):
        candles=pd.DataFrame([
            dict(t=0,o=100,h=102,l=99,c=101,v=100),
            dict(t=3600000,o=100,h=120,l=90,c=105,v=100)])
        r=evaluate(candles,0,dict(side="LONG",stop=95))
        self.assertEqual(r["exit"],"SL")
        self.assertLess(r["net_r"],-1)

    def test_summary_empty(self):
        self.assertIsNone(summarize([])["mean_r"])

if __name__=="__main__":unittest.main()
