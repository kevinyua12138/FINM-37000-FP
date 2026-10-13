import csv
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.calendar import build_calendar, flags_for_day


class CalendarTests(unittest.TestCase):
    def test_full_year_and_range(self):
        rows = build_calendar()
        self.assertEqual(len(rows), 365)
        self.assertEqual(len({r['date'] for r in rows}), 365)
        self.assertEqual(rows[0]['date'], '2025-01-01')
        self.assertEqual(rows[-1]['date'], '2025-12-31')
        self.assertEqual(sum(r['is_roll_day'] for r in rows), 4)
        self.assertEqual(sum(r['is_cpi_day'] for r in rows), 11)
        self.assertEqual(sum(r['is_nfp_day'] for r in rows), 11)
        self.assertEqual(sum(r['is_fomc_day'] for r in rows), 8)
        self.assertEqual(len(build_calendar('2025-06-18', '2025-06-18')), 1)

    def test_roll_conventions(self):
        self.assertTrue(flags_for_day('2025-03-17')['is_roll_day'])
        self.assertFalse(flags_for_day('2025-03-13')['is_roll_day'])
        observed = flags_for_day('2025-03-13', actual_roll_dates=['2025-03-13'])
        self.assertTrue(observed['is_actual_roll_day'])
        self.assertFalse(observed['is_roll_day'])

    def test_holidays_and_overlap(self):
        self.assertTrue(flags_for_day('2025-01-01')['is_holiday'])
        mourning = flags_for_day('2025-01-09')
        self.assertTrue(mourning['is_holiday'])
        self.assertTrue(mourning['is_half_day'])
        self.assertFalse(flags_for_day('2025-10-13')['is_holiday'])
        self.assertFalse(flags_for_day('2025-11-11')['is_holiday'])
        self.assertTrue(flags_for_day('2025-11-28')['is_half_day'])
        july3 = flags_for_day('2025-07-03')
        self.assertTrue(july3['is_half_day'])
        self.assertTrue(july3['is_nfp_day'])
        self.assertTrue(july3['is_macro_day'])
        self.assertTrue(flags_for_day('2025-03-08')['is_weekend'])
        normal = flags_for_day('2025-03-03')
        self.assertFalse(normal['is_macro_day'])
        self.assertEqual(normal['holiday_name'], '')

    def test_actual_release_dates_after_shutdown(self):
        for day, flag in [('2025-10-24', 'is_cpi_day'),
                          ('2025-11-20', 'is_nfp_day'),
                          ('2025-12-16', 'is_nfp_day'),
                          ('2025-12-18', 'is_cpi_day')]:
            self.assertTrue(flags_for_day(day)[flag])
        for day in ['2025-10-03', '2025-10-15', '2025-11-07', '2025-11-13']:
            self.assertFalse(flags_for_day(day)['is_macro_day'])
        self.assertFalse(flags_for_day('2025-06-17')['is_fomc_day'])
        self.assertTrue(flags_for_day('2025-06-18')['is_fomc_day'])

    def test_chicago_conversion_and_dst(self):
        self.assertTrue(flags_for_day('2025-01-16T01:00:00Z')['is_cpi_day'])
        self.assertTrue(flags_for_day('2025-06-12T00:30:00Z')['is_cpi_day'])
        self.assertEqual(flags_for_day(datetime(2025, 6, 12, 0, 30, tzinfo=timezone.utc))['date'],
                         '2025-06-11')
        self.assertEqual(flags_for_day(date(2025, 6, 12))['date'], '2025-06-12')

    def test_invalid_inputs(self):
        for value in ['2024-12-31', '2026-01-01', 'bad', '2025-02-30',
                      '2025-01-15T08:30:00']:
            with self.assertRaises(ValueError):
                flags_for_day(value)
        with self.assertRaises(ValueError):
            build_calendar('2025-02-01', '2025-01-01')
        with self.assertRaises(ValueError):
            build_calendar(actual_roll_dates=['2026-03-16'])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'nested' / 'calendar.csv'
            result = subprocess.run([sys.executable, str(ROOT / 'main.py'),
                                     '--start', '2025-07-03', '--end', '2025-07-04',
                                     '--output', str(output), '--actual-roll-date', '2025-07-03'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['is_nfp_day'], 'True')
            self.assertEqual(rows[0]['is_actual_roll_day'], 'True')
            self.assertEqual(rows[1]['is_holiday'], 'True')
            invalid = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--start', '2026-01-01',
                                      '--output', str(Path(tmp) / 'invalid.csv')], capture_output=True)
            self.assertEqual(invalid.returncode, 2)
            self.assertFalse((Path(tmp) / 'invalid.csv').exists())


if __name__ == '__main__':
    unittest.main()
