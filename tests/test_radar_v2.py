import unittest
import pandas as pd
from radar_v2_filters import confirm_breakout, guarded_sizing


class RadarV2Tests(unittest.TestCase):
    def make_candles(self):
        start = 1_800_000_000_000
        h1 = pd.DataFrame([
            dict(t=start-3_600_000, o=99, h=100, l=98, c=99),
            dict(t=start, o=99.5, h=102, l=99, c=101.5),
        ])
        m15 = pd.DataFrame([
            dict(t=start+i*900_000, o=100+i*.2, h=101+i*.3,
                 l=99.5+i*.2, c=100.6+i*.25)
            for i in range(4)
        ])
        return h1, m15, start+3_600_000

    def test_valid_breakout(self):
        h1,m15,end=self.make_candles()
        ok,_=confirm_breakout(h1,m15,100,2,end)
        self.assertTrue(ok)

    def test_missing_m15_fails_closed(self):
        h1,m15,end=self.make_candles()
        self.assertFalse(confirm_breakout(h1,m15.iloc[:-1],100,2,end)[0])

    def test_late_breakout_rejected(self):
        h1,m15,end=self.make_candles()
        self.assertFalse(confirm_breakout(h1,m15,99,2,end)[0])

    def test_h1_sync_rejected(self):
        h1,m15,end=self.make_candles()
        self.assertFalse(confirm_breakout(h1,m15,100,2,end+900_000)[0])

    def test_h1_red_rejected(self):
        h1,m15,end=self.make_candles()
        h1.loc[1,'o']=102
        self.assertFalse(confirm_breakout(h1,m15,100,2,end)[0])

    def test_sizing_caps_risk_leverage_margin(self):
        result,_=guarded_sizing(100,95,.001,.001,.01,1,20)
        self.assertIsNotNone(result)
        self.assertLessEqual(result['risque_usdt'],1.0000001)
        self.assertLessEqual(result['lev'],10)
        self.assertLessEqual(result['marge'],20.0000001)

    def test_fee_too_large_rejected(self):
        result,_=guarded_sizing(100,99.95,.001,.001,.01)
        self.assertIsNone(result)

    def test_min_qty_rejected(self):
        result,_=guarded_sizing(100,95,1,10,.01)
        self.assertIsNone(result)

    def test_nonfinite_rejected(self):
        result,_=guarded_sizing(float('nan'),95,.01,.01,.01)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
