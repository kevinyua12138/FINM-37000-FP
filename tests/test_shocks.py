import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from events.shocks import (  # noqa: E402
    EVENT_COLUMNS,
    daily_thresholds,
    detect_shocks,
    mid_grid,
    moves,
)

TZ = "America/Chicago"
FIRST_DAY = date(2025, 3, 3)
OPEN = "08:30"


def quotes(day, mids, instrument_id=42, offset=0.5):
    """One quote per second from 08:30 (plus `offset` seconds), one tick wide."""
    start = pd.Timestamp(f"{day} {OPEN}", tz=TZ) + pd.Timedelta(seconds=offset)
    index = start + pd.to_timedelta(np.arange(len(mids)), unit="s")
    mids = np.asarray(mids, dtype=float)
    return pd.DataFrame(
        {
            "bid_px_00": mids - 0.125,
            "ask_px_00": mids + 0.125,
            "instrument_id": np.full(len(mids), instrument_id),
        },
        index=index,
    )


def calm_mids(seed, n=1800):
    """Random walk in quarter-point steps: the 'normal' days that set the threshold."""
    steps = np.random.default_rng(seed).choice([-0.25, 0.0, 0.25], size=n, p=[0.2, 0.6, 0.2])
    return 5000 + np.cumsum(steps)


def flat_with_jumps(jumps, n=1800):
    """Flat price with level jumps: {second index: jump size}."""
    mids = np.full(n, 5000.0)
    for at, size in jumps.items():
        mids[at:] += size
    return mids


def history_grids(n_days):
    return {
        FIRST_DAY + timedelta(days=k): mid_grid(quotes(FIRST_DAY + timedelta(days=k), calm_mids(k)))
        for k in range(n_days)
    }


def second(day, k):
    """Grid label k seconds after the open."""
    return pd.Timestamp(f"{day} {OPEN}", tz=TZ) + pd.Timedelta(seconds=k)


class MidGridTests(unittest.TestCase):
    def test_value_at_each_second_is_last_quote_at_or_before_it(self):
        grid = mid_grid(quotes(FIRST_DAY, [100.0, 101.0, 102.0]))  # quotes at :00.5, :01.5, :02.5
        self.assertEqual(grid.at[second(FIRST_DAY, 1), "mid"], 100.0)  # :01.5 not known yet
        self.assertEqual(grid.at[second(FIRST_DAY, 2), "mid"], 101.0)

    def test_drops_empty_and_crossed_quotes(self):
        q = quotes(FIRST_DAY, [100.0, 101.0, 102.0])
        q.iloc[1, q.columns.get_loc("ask_px_00")] = 90.0  # crossed book
        q.iloc[2, q.columns.get_loc("bid_px_00")] = np.nan  # empty bid
        self.assertTrue((mid_grid(q)["mid"] == 100.0).all())


class MovesTests(unittest.TestCase):
    def test_ten_second_change(self):
        change = moves(mid_grid(quotes(FIRST_DAY, np.arange(30.0))))  # +1 per second
        self.assertTrue(change.iloc[:10].isna().all())  # nothing 10 s earlier
        self.assertTrue((change.iloc[10:] == 10.0).all())

    def test_ignores_moves_across_a_contract_roll(self):
        old = quotes(FIRST_DAY, [100.0] * 20, instrument_id=1)
        new = quotes(FIRST_DAY, [110.0] * 20, instrument_id=2, offset=20.5)
        change = moves(mid_grid(pd.concat([old, new])))
        roll = second(FIRST_DAY, 21)
        self.assertTrue(change[roll:roll + pd.Timedelta("9s")].isna().all())
        self.assertEqual(change[roll + pd.Timedelta("10s")], 0.0)


class ThresholdTests(unittest.TestCase):
    def test_uses_previous_five_days_only(self):
        grids = history_grids(7)
        days = sorted(grids)
        abs_moves = {d: moves(g).abs() for d, g in grids.items()}
        thresholds = daily_thresholds(abs_moves)

        self.assertTrue(thresholds[days[:5]].isna().all())  # no full history yet
        expected = pd.concat([abs_moves[d] for d in days[:5]]).dropna().quantile(0.995)
        self.assertAlmostEqual(thresholds[days[5]], expected)

        wild = dict(abs_moves)
        wild[days[6]] = abs_moves[days[6]] * 100  # change today's data
        self.assertEqual(daily_thresholds(wild)[days[6]], thresholds[days[6]])


class DetectTests(unittest.TestCase):
    def setUp(self):
        self.grids = history_grids(5)
        self.day = FIRST_DAY + timedelta(days=5)

    def detect(self, jumps):
        grids = dict(self.grids)
        grids[self.day] = mid_grid(quotes(self.day, flat_with_jumps(jumps)))
        return detect_shocks(grids)

    def test_one_event_per_jump_with_time_direction_size_and_contract(self):
        events = self.detect({600: 5.0})
        self.assertEqual(list(events.columns), EVENT_COLUMNS)
        self.assertEqual(len(events), 1)
        shock = events.iloc[0]
        self.assertEqual(shock["t0"], second(self.day, 601))  # jump quote arrives at 600.5 s
        self.assertEqual(shock["direction"], 1)
        self.assertEqual(shock["size"], 5.0)
        self.assertEqual(shock["instrument_id"], 42)
        self.assertGreater(shock["size"], shock["threshold"])

    def test_down_jump_has_negative_direction(self):
        self.assertEqual(self.detect({600: -5.0})["direction"].tolist(), [-1])

    def test_cooldown(self):
        self.assertEqual(len(self.detect({600: 5.0, 660: 5.0})), 1)  # 60 s apart
        self.assertEqual(len(self.detect({600: 5.0, 750: 5.0})), 2)  # 150 s apart

    def test_no_events_without_five_days_of_history(self):
        grids = history_grids(4)
        day = FIRST_DAY + timedelta(days=4)
        grids[day] = mid_grid(quotes(day, flat_with_jumps({600: 5.0})))
        events = detect_shocks(grids)
        self.assertTrue(events.empty)
        self.assertEqual(list(events.columns), EVENT_COLUMNS)


if __name__ == "__main__":
    unittest.main()
