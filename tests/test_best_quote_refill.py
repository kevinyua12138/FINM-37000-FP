import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features.replenishment import best_quote_refill, replenishment_features  # noqa: E402

T0 = pd.Timestamp("2025-03-03 10:00:00", tz="America/Chicago")


def quotes(rows):
    """rows: (seconds after T0, bid_px, bid_sz, ask_px, ask_sz)"""
    index = pd.DatetimeIndex([T0 + pd.Timedelta(seconds=s) for s, *_ in rows])
    cols = ["bid_px_00", "bid_sz_00", "ask_px_00", "ask_sz_00"]
    return pd.DataFrame([r[1:] for r in rows], columns=cols, index=index)


def events(direction=1):
    return pd.DataFrame({"t0": [T0], "direction": [direction]})


# Meeting 1 example: 400 on the best ask before, a buyer sweeps 12 ticks, 124 rest on the
# new best ask three seconds later.
MEETING_1 = [(-12, 4999.75, 50, 5000.00, 400), (0, 5002.75, 20, 5003.00, 30),
             (2, 5002.75, 20, 5003.00, 90), (3, 5003.00, 20, 5003.25, 124)]


def test_meeting_1_example():
    out = best_quote_refill(quotes(MEETING_1), events()).iloc[0]
    assert out["refill_best"] == 124 / 400
    assert np.isnan(out["half_life_best_s"])  # never back to 200


def test_x_based_ratio_is_zero_on_the_same_quotes():
    out = replenishment_features(quotes(MEETING_1), events()).iloc[0]
    assert out["refill_ratio"] == 0.0  # the ask never came back to 5000.00


def test_fast_refill_half_life():
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5002.75, 20, 5003.00, 30),
                (1, 5002.75, 20, 5003.00, 250), (3, 5002.75, 20, 5003.00, 300)])
    out = best_quote_refill(q, events()).iloc[0]
    assert out["refill_best"] == 0.75 and out["half_life_best_s"] == 1.0


def test_down_shock_uses_bid_side():
    q = quotes([(-12, 5000.00, 200, 5000.25, 50), (0, 4997.00, 10, 4997.25, 30),
                (2, 4997.00, 150, 4997.25, 30)])
    out = best_quote_refill(q, events(-1)).iloc[0]
    assert out["refill_best"] == 0.75 and out["half_life_best_s"] == 2.0


def test_only_the_3_second_window_counts():
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5002.75, 20, 5003.00, 30),
                (5, 5002.75, 20, 5003.00, 400)])
    out = best_quote_refill(q, events()).iloc[0]
    assert out["refill_best"] == 30 / 400 and np.isnan(out["half_life_best_s"])


def test_missing_history_or_empty_pre_quote_gives_nan():
    no_pre = quotes([(0, 5002.75, 20, 5003.00, 30)])
    empty_pre = quotes([(-12, 4999.75, 50, 5000.00, 0), (0, 5002.75, 20, 5003.00, 30)])
    for q in (no_pre, empty_pre):
        out = best_quote_refill(q, events()).iloc[0]
        assert np.isnan(out["refill_best"]) and np.isnan(out["half_life_best_s"])
