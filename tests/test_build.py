import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from events.study import assign_regimes, fit_cutoffs, in_period, read_events  # noqa: E402
from synthetic import CFG, write_events_csv  # noqa: E402


def test_build_adds_every_feature_and_quote(tmp_path):
    ev = read_events(write_events_csv(tmp_path / "events.csv"))
    first = ev.iloc[0]
    assert first["refill_best"] == 60 / 400 and first["refill_ratio"] == 0.0
    assert first["ti"] == 1.0 and first["trade_volume"] > 0 and first["ofi"] > 0
    assert first["y_30s"] > 0 and ev.iloc[1]["y_30s"] < 0
    assert first["entry_ask"] - first["entry_bid"] == 0.25 and np.isfinite(first["exit_bid_30s"])
    assert not ev["stress_window"].any()
    assert ev["is_fomc_day"].tolist() == [False, False, False, True]  # May 7, 2025 was an FOMC day
    assert not ev["fomc_window"].any()  # 10:05 is before the 13:00 statement


def test_regimes_on_built_events(tmp_path):
    ev = in_period(read_events(write_events_csv(tmp_path / "events.csv")), CFG["study"]["in_sample"])
    cutoffs = fit_cutoffs(ev, CFG["study"])
    assert cutoffs["refill_cutoff"] == (60 / 400 + 390 / 400) / 2
    ev = assign_regimes(ev, {**cutoffs, "pressure_cutoff": -1.0})  # both shocks have buying pressure
    assert ev["regime"].tolist() == ["follow", "fade"]
