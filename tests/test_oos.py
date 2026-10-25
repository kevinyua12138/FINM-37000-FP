import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backtest.oos import freeze, run  # noqa: E402
from synthetic import CFG, write_cutoffs, write_events_csv  # noqa: E402


def test_freeze_records_every_choice(tmp_path):
    rules = freeze(CFG, write_cutoffs(tmp_path / "cutoffs.yaml"), tmp_path / "frozen_rules.yaml")
    assert rules["regimes"]["refill_cutoff"] == 0.5 and rules["backtest"]["horizon_s"] == 30
    assert rules["out_of_sample"] == ["2025-05-01", "2025-06-30"] and (tmp_path / "frozen_rules.yaml").exists()


def test_out_of_sample_runs_once(tmp_path):
    events = write_events_csv(tmp_path / "events.csv")
    frozen = tmp_path / "frozen_rules.yaml"
    freeze(CFG, write_cutoffs(tmp_path / "cutoffs.yaml"), frozen)
    kwargs = dict(out_dir=tmp_path / "oos", fig_dir=tmp_path / "fig")
    summary = run(events, frozen, **kwargs)
    assert summary.loc["trades", "out_of_sample"] == 2 and summary.loc["trades", "in_sample"] == 2
    assert (tmp_path / "fig" / "cumulative_pnl.png").exists()
    with pytest.raises(SystemExit):
        run(events, frozen, **kwargs)  # a second run is refused
    assert run(events, frozen, force=True, **kwargs).loc["trades", "out_of_sample"] == 2


def test_no_out_of_sample_events_is_an_error(tmp_path):
    import pandas as pd

    events = tmp_path / "events.csv"
    full = pd.read_csv(write_events_csv(events))
    full[full["date"] < "2025-05-01"].to_csv(events, index=False)
    frozen = tmp_path / "frozen_rules.yaml"
    freeze(CFG, write_cutoffs(tmp_path / "cutoffs.yaml"), frozen)
    with pytest.raises(SystemExit):
        run(events, frozen, out_dir=tmp_path / "oos", fig_dir=tmp_path / "fig")
