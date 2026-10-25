import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from events.shocks import mid_grid  # noqa: E402
from events.study import (  # noqa: E402
    assign_regimes, average_paths, cell_table, fit_cutoffs, path_matrix, regime_table,
)

TZ = "America/Chicago"
CUTOFFS = {"refill_column": "refill_best", "refill_cutoff": 0.5,
           "pressure_column": "ofi", "pressure_cutoff": 0.0}


def events():
    """One shock per 2x2 cell, plus one with a missing feature."""
    return pd.DataFrame({
        "date": ["2025-03-03", "2025-03-03", "2025-03-04", "2025-03-04", "2025-03-05"],
        "refill_best": [0.2, 0.9, 0.2, 0.9, np.nan],
        "ofi": [0.4, -0.3, -0.1, 0.6, 0.5],
        "y_5s": [1e-4, -1e-4, 0.0, 2e-4, 0.0],
        "y_30s": [2e-4, -3e-4, 1e-4, 0.0, 5e-4],
        "y_120s": [3e-4, -2e-4, 0.0, 1e-4, 0.0],
    })


def test_regimes_follow_the_2x2_rules():
    out = assign_regimes(events(), CUTOFFS)
    # slow+strong, fast+weak, slow+weak, fast+strong, missing refill
    assert out["regime"].tolist() == ["follow", "fade", "no trade", "no trade", "no trade"]
    assert out["slow_refill"].tolist()[:4] == [1.0, 0.0, 1.0, 0.0] and np.isnan(out["slow_refill"].iloc[4])


def test_neutral_band_keeps_weak_but_not_reversing_flow_out_of_fade():
    ev = pd.DataFrame({"date": ["2025-03-03"] * 4, "refill_best": [0.2, 0.9, 0.9, 0.9],
                       "ofi": [0.4, -0.3, 0.02, -0.02]})
    band = {**CUTOFFS, "pressure_cutoff": 0.05, "pressure_low_cutoff": -0.05}
    out = assign_regimes(ev, band)
    assert out["regime"].tolist() == ["follow", "fade", "no trade", "no trade"]
    assert out["strong_pressure"].tolist()[:2] == [1.0, 0.0] and out["strong_pressure"].iloc[2:].isna().all()
    no_band = assign_regimes(ev, {**CUTOFFS, "pressure_cutoff": 0.05})
    assert no_band["regime"].tolist() == ["follow", "fade", "fade", "fade"]


def test_median_cutoffs_come_from_the_given_events():
    cfg = {"refill_column": "refill_best", "refill_cutoff": "median",
           "pressure_column": "ofi", "pressure_cutoff": 0.25}
    cutoffs = fit_cutoffs(events(), cfg)
    assert cutoffs["refill_cutoff"] == 0.55 and cutoffs["pressure_cutoff"] == 0.25
    assert cutoffs["refill_rule"] == "median"


def test_regime_and_cell_tables():
    out = assign_regimes(events(), CUTOFFS)
    table = regime_table(out)
    assert table.loc["follow", "n"] == 1 and table.loc["no trade", "n"] == 3 and table.loc["all", "n"] == 5
    assert np.isclose(table.loc["fade", "mean_bp_30s"], -3.0)
    cells = cell_table(out)
    assert cells["n"].tolist() == [1, 1, 1, 1]  # the missing-feature shock is in no cell
    assert np.isclose(cells.loc[("slow refill", "strong pressure"), "mean_bp_30s"], 2.0)


def quotes(day, mids):
    start = pd.Timestamp(f"{day} 10:00:00", tz=TZ)
    index = start + pd.to_timedelta(np.arange(len(mids)), unit="s")
    mids = np.asarray(mids, float)
    return pd.DataFrame({"bid_px_00": mids - 0.125, "ask_px_00": mids + 0.125,
                         "instrument_id": np.full(len(mids), 7)}, index=index)


def test_paths_are_signed_by_direction_and_relative_to_t0():
    mids = 5000 + 0.25 * np.arange(200)  # +1 tick per second
    grid = mid_grid(quotes("2025-03-03", mids))
    t0 = pd.Timestamp("2025-03-03 10:00:10", tz=TZ)
    ev = pd.DataFrame({"t0": [t0, t0], "date": ["2025-03-03"] * 2, "direction": [1, -1],
                       "regime": ["follow", "follow"]})
    paths = path_matrix({"2025-03-03": grid}, ev, horizon_s=5)
    start = grid.at[t0, "mid"]
    assert paths[0, 0] == 0.0 and np.isclose(paths[0, 5], (start + 1.25) / start * 1e4 - 1e4)
    assert np.allclose(paths[1], -paths[0])
    avg = average_paths({"2025-03-03": grid}, ev, horizon_s=5)
    assert np.allclose(avg[("follow", "mean")], 0.0)  # the two paths cancel
