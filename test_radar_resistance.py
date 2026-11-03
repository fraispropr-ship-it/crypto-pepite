import unittest
from radar_resistance import candles, detect, flow, oi_change, BAR

class ResistanceTests(unittest.TestCase):
    def bars(self):
        bars=[]
        for i in range(100):
            # Separate visits to 100, with deep pullbacks.
            h=100 if i in (20,40,60,80) else 99.2
            bars.append(dict(t=i*BAR,o=98.7,h=h,l=98,c=98.8,v=100))
        for b in bars[-4:]:
            b.update(o=99.4,h=99.9,l=99.3,c=99.8)
        return bars
    def test_detects_repeated_level_before_break(self):
        z=detect(self.bars(),100*BAR)
        self.assertIsNotNone(z)
        self.assertGreaterEqual(z['tests'],3)
        self.assertAlmostEqual(z['level'],100)
    def test_no_prealert_after_break_or_stale_data(self):
        b=self.bars(); b[-1]['c']=102
        self.assertIsNone(detect(b,100*BAR))
        self.assertIsNone(detect(self.bars(),104*BAR))
    def test_no_level_from_single_touch(self):
        b=self.bars()
        for i in (20,40,60): b[i]['h']=99.2
        self.assertIsNone(detect(b,100*BAR))
    def test_does_not_count_adjacent_bars_as_independent_tests(self):
        b=self.bars()
        for x in b: x.update(h=100,l=99.8,c=99.9)
        self.assertIsNone(detect(b,100*BAR))
    def test_open_candle_excluded(self):
        self.assertEqual(len(candles([[0,1,2,0,1,5],[BAR,1,2,0,1,5]],BAR+1)),1)
    def test_flow_deduplicated_and_sample_labelled(self):
        rows=[dict(execId=str(i),time=100000+i*2000,side='Buy' if i<15 else 'Sell',size='1') for i in range(20)]
        f=flow(rows+rows,140000)
        self.assertEqual(f['count'],20)
        self.assertEqual(f['buy_pct'],75)
        self.assertEqual(f['delta_base'],10)
        self.assertTrue(f['sampled'])
        self.assertIsNone(flow(rows,300000))
    def test_oi_stale_and_initial_snapshots_unknown(self):
        self.assertIsNone(oi_change(None,100,1000000))
        self.assertIsNone(oi_change(dict(t=0,oi=100),110,3600000))
        self.assertAlmostEqual(oi_change(dict(t=0,oi=100),110,BAR)['pct'],10)

if __name__=='__main__': unittest.main()
