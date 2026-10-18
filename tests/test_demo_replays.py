import unittest

from scripts.export_demo_replays import DEMAND, export


class DemoReplayTests(unittest.TestCase):
    def test_normal_ride_completes_without_protection_trigger(self):
        data = export('normal_ride', DEMAND['normal_ride'])
        self.assertEqual(data['samples'][-1]['reopens'], 0)
        self.assertTrue(all(p['status'] == 'done' for p in data['passengers']))
        self.assertEqual(sum(e['type'] == 'leavers' for e in data['events']), 2)

    def test_safety_demo_uses_a_real_closing_reversal(self):
        data = export('anti_pinch', DEMAND['anti_pinch'])
        triggers = [e for e in data['events'] if e['type'] == 'anti_pinch_reopen']
        self.assertEqual([e['time'] for e in triggers], [8])
        before, reverse, after = data['samples'][7:10]
        self.assertEqual(before['state'], 'closing')
        self.assertEqual(reverse['state'], 'opening')
        self.assertAlmostEqual(reverse['door'], .5)
        self.assertEqual(after['state'], 'open')
        self.assertEqual(data['samples'][-1]['reopens'], 1)
        self.assertTrue(all(p['status'] == 'done' for p in data['passengers']))


if __name__ == '__main__':
    unittest.main()
