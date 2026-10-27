import unittest
import pandas as pd
from radar_v3_btc_regime import btc_regimes

class RegimeTests(unittest.TestCase):
    def test_partial_h4_not_visible(self):
        H=3600000
        rows=[dict(t=i*H,c=100+i*.1) for i in range(350)]
        z=btc_regimes(pd.DataFrame(rows))
        self.assertTrue(all(int(t)%(4*H)==0 for t in z.known_at))
        self.assertEqual(int(z.known_at.iloc[0]),4*H)

    def test_not_future_data(self):
        H=3600000
        d=pd.DataFrame([dict(t=i*H,c=100+i*.1) for i in range(350)])
        a=btc_regimes(d)
        d.loc[d.index[-1],"c"]=999999
        b=btc_regimes(d)
        self.assertEqual(a.iloc[:-1].regime.tolist(),b.iloc[:-1].regime.tolist())

if __name__=="__main__":unittest.main()
