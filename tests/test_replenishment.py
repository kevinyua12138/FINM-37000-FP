import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features.replenishment import replenishment_features  # noqa: E402

T0 = pd.Timestamp("2025-03-03 10:00:00", tz="America/Chicago")


def quotes(rows):
    """rows: (seconds after T0, bid_px, bid_sz, ask_px, ask_sz)"""
    index = pd.DatetimeIndex([T0 + pd.Timedelta(seconds=s) for s, *_ in rows])
    cols = ["bid_px_00", "bid_sz_00", "ask_px_00", "ask_sz_00"]
    return pd.DataFrame([r[1:] for r in rows], columns=cols, index=index)


def events(direction=1):
    return pd.DataFrame({"t0": [T0], "direction": [direction]})


def test_issue_9_example():
    # X = 5000.00 with 400 resting, eaten by a buyer, then refilled to 100 and 250 at X
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5000.75, 20, 5001.00, 30),
                (2, 4999.75, 20, 5000.00, 100), (3, 4999.75, 20, 5000.00, 250)])
    out = replenishment_features(q, events())
    assert out["refill_ratio"].iloc[0] == 250 / 400
    assert out["half_life_s"].iloc[0] == 3.0


def test_never_refilled_has_nan_half_life():
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5000.75, 20, 5001.00, 30), (2, 5000.75, 20, 5001.00, 500)])
    out = replenishment_features(q, events())
    assert out["refill_ratio"].iloc[0] == 0.0
    assert np.isnan(out["half_life_s"].iloc[0])


def test_down_shock_uses_bid_side():
    q = quotes([(-12, 5000.00, 200, 5000.25, 50), (0, 4999.00, 10, 4999.25, 30), (1, 5000.00, 150, 5000.25, 30)])
    out = replenishment_features(q, events(direction=-1))
    assert out["refill_ratio"].iloc[0] == 150 / 200
    assert out["half_life_s"].iloc[0] == 1.0


def test_price_back_through_x_counts_as_refilled():
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5000.75, 20, 5001.00, 30), (1, 4999.50, 20, 4999.75, 10)])
    out = replenishment_features(q, events())
    assert out["refill_ratio"].iloc[0] == 1.0
    assert out["half_life_s"].iloc[0] == 1.0


def test_only_the_3_second_window_counts():
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5000.75, 20, 5001.00, 30), (5, 4999.75, 20, 5000.00, 400)])
    out = replenishment_features(q, events())
    assert out["refill_ratio"].iloc[0] == 0.0
    assert np.isnan(out["half_life_s"].iloc[0])


def test_no_quote_before_the_window_gives_nan():
    q = quotes([(0, 5000.75, 20, 5001.00, 30), (1, 4999.75, 20, 5000.00, 300)])
    out = replenishment_features(q, events())
    assert np.isnan(out["refill_ratio"].iloc[0]) and np.isnan(out["half_life_s"].iloc[0])


def test_events_not_modified():
    q = quotes([(-12, 4999.75, 50, 5000.00, 400), (0, 5000.75, 20, 5001.00, 30)])
    ev = events()
    replenishment_features(q, ev)
    assert list(ev.columns) == ["t0", "direction"]
