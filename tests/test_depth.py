import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features.depth import depth_features  # noqa: E402

T0 = pd.Timestamp("2025-03-03 10:00:00", tz="America/Chicago")


def book_row(best_bid, bid_sizes, ask_sizes):
    """One 10-level snapshot: ticks 0.25 apart, best ask one tick above the best bid."""
    row = {}
    for i in range(10):
        row[f"bid_px_{i:02d}"], row[f"ask_px_{i:02d}"] = best_bid - 0.25 * i, best_bid + 0.25 * (i + 1)
        row[f"bid_sz_{i:02d}"], row[f"ask_sz_{i:02d}"] = bid_sizes[i], ask_sizes[i]
    return row


def quotes(rows):
    """rows: (seconds after T0, snapshot dict)"""
    return pd.DataFrame([r for _, r in rows], index=pd.DatetimeIndex([T0 + pd.Timedelta(seconds=s) for s, _ in rows]))


def events(direction=1):
    return pd.DataFrame({"t0": [T0], "direction": [direction]})


# Up-shock: 1000 contracts on the first 10 ask levels before, 200 right after, refilling.
UP = [(-12, book_row(5000.00, [50] * 10, [100] * 10)),
      (0, book_row(5003.00, [80] * 5 + [10] * 5, [20] * 10)),
      (2, book_row(5003.00, [80] * 5 + [10] * 5, [60] * 10)),
      (3, book_row(5003.00, [80] * 5 + [10] * 5, [90] * 5 + [50] * 5)),
      (5, book_row(5003.00, [80] * 5 + [10] * 5, [500] * 10))]  # after the window


def test_up_shock_imbalance_refill_and_half_life():
    out = depth_features(quotes(UP), events()).iloc[0]
    assert np.isclose(out["imb_5"], (400 - 100) / 500) and np.isclose(out["imb_10"], (450 - 200) / 650)
    assert out["refill_depth5"] == 450 / 500 and out["refill_depth10"] == 700 / 1000
    assert out["half_life_depth10_s"] == 2.0  # 600 >= 500 at t0 + 2s


def test_down_shock_uses_the_bid_side_and_flips_the_imbalance_sign():
    rows = [(-12, book_row(5000.00, [100] * 10, [50] * 10)),
            (0, book_row(4997.00, [20] * 10, [80] * 10)),
            (1, book_row(4997.00, [40] * 10, [80] * 10))]
    out = depth_features(quotes(rows), events(-1)).iloc[0]
    assert np.isclose(out["imb_10"], -(200 - 800) / 1000)  # more asks behind a down-move -> positive
    assert out["refill_depth10"] == 400 / 1000 and np.isnan(out["half_life_depth10_s"])


def test_missing_deep_levels_only_affect_the_10_level_features():
    q = quotes(UP).drop(columns=[f"{s}_{k}_09" for s in ("bid", "ask") for k in ("px", "sz")])
    out = depth_features(q, events()).iloc[0]
    assert np.isfinite(out["imb_5"]) and out["refill_depth5"] == 450 / 500
    assert np.isnan(out["imb_10"]) and np.isnan(out["refill_depth10"])


def test_no_quote_before_the_window_gives_nan():
    out = depth_features(quotes(UP[1:]), events()).iloc[0]
    assert np.isnan(out["refill_depth10"]) and np.isnan(out["half_life_depth10_s"])
    assert np.isfinite(out["imb_10"])  # the t0 snapshot still exists
