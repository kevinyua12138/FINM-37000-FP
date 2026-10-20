import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from features import book_features


def snapshot():
    return pd.DataFrame({
        'bid_px_00': [100.0], 'ask_px_00': [100.5],
        'bid_sz_00': [30], 'ask_sz_00': [10],
        'bid_px_01': [99.75], 'ask_px_01': [100.75],
        'bid_sz_01': [20], 'ask_sz_01': [5],
        'bid_px_02': [99.25], 'ask_px_02': [101.25],
        'bid_sz_02': [40], 'ask_sz_02': [10],
    }, index=pd.Index(['event'], name='event_id'))


class BookFeaturesTests(unittest.TestCase):
    def test_known_top_values(self):
        row = book_features(snapshot(), levels=1).iloc[0]
        self.assertAlmostEqual(row.I_1, 0.5)
        self.assertAlmostEqual(row.I_N, 0.5)
        self.assertAlmostEqual(row.microprice, 100.375)
        self.assertAlmostEqual(row.G, 0.125)
        self.assertTrue(np.isnan(row.DS))

    def test_depth_and_uneven_spacing(self):
        row = book_features(snapshot(), levels=3).iloc[0]
        self.assertAlmostEqual(row.I_N, 65 / 115)
        self.assertAlmostEqual(row.DS, 15.0)  # bid slope 20 minus ask slope 5

    def test_symmetric_book(self):
        frame = snapshot()
        for i in range(3):
            frame[f'ask_sz_{i:02d}'] = frame[f'bid_sz_{i:02d}']
        row = book_features(frame, levels=3).iloc[0]
        self.assertEqual(row.I_1, 0)
        self.assertEqual(row.I_N, 0)
        self.assertEqual(row.G, 0)
        self.assertEqual(row.DS, 0)

    def test_missing_depth_preserves_top(self):
        row = book_features(snapshot()).iloc[0]
        self.assertEqual(row.I_1, 0.5)
        self.assertTrue(np.isnan(row.I_N))
        self.assertTrue(np.isnan(row.DS))

    def test_invalid_top(self):
        for col, val in [('bid_px_00', 101), ('ask_px_00', 100),
                         ('bid_sz_00', -1), ('ask_sz_00', np.inf),
                         ('bid_px_00', 100.01), ('bid_px_00', np.nan),
                         ('bid_px_00', 0), ('ask_px_00', (2**63 - 1) / 1e9)]:
            with self.subTest(col=col, val=val):
                frame = snapshot().astype(float)
                frame.loc['event', col] = val
                self.assertTrue(book_features(frame, levels=3).isna().all().all())

    def test_zero_sizes(self):
        frame = snapshot()
        frame['bid_sz_00'] = 0
        self.assertEqual(book_features(frame, levels=1).iloc[0].I_1, -1)
        frame['ask_sz_00'] = 0
        self.assertTrue(book_features(frame, levels=1).isna().all().all())

    def test_bad_depth_only_masks_depth(self):
        for col, val in [('bid_px_01', 100), ('ask_px_01', 100.25),
                         ('ask_sz_02', -1), ('bid_sz_02', np.nan)]:
            with self.subTest(col=col):
                frame = snapshot().astype(float)
                frame.loc['event', col] = val
                row = book_features(frame, levels=3).iloc[0]
                self.assertEqual(row.I_1, 0.5)
                self.assertTrue(np.isnan(row.I_N))
                self.assertTrue(np.isnan(row.DS))

    def test_alignment_and_no_mutation(self):
        frame = pd.concat([snapshot(), snapshot()])
        original = frame.copy(deep=True)
        out = book_features(frame, levels=3)
        pd.testing.assert_index_equal(frame.index, out.index)
        pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(len(out), 2)

    def test_empty(self):
        self.assertEqual(book_features(snapshot().iloc[:0], levels=3).shape, (0, 5))

    def test_invalid_parameters_and_schema(self):
        for levels in [0, 11, True, 1.5]:
            with self.assertRaises(ValueError):
                book_features(snapshot(), levels=levels)
        for tick in [0, -1, np.nan, np.inf]:
            with self.assertRaises(ValueError):
                book_features(snapshot(), tick_size=tick)
        with self.assertRaises(ValueError):
            book_features(snapshot().drop(columns='bid_px_00'))

    def test_ten_level_book(self):
        frame = pd.DataFrame({f'{side}_{kind}_{i:02d}': [value]
                              for i in range(10)
                              for side, kind, value in [
                                  ('bid', 'px', 100-i*.25), ('ask', 'px', 100.5+i*.25),
                                  ('bid', 'sz', 20), ('ask', 'sz', 10)]})
        row = book_features(frame).iloc[0]
        self.assertAlmostEqual(row.I_N, 1/3)
        self.assertAlmostEqual(row.DS, 10)


if __name__ == '__main__':
    unittest.main()
