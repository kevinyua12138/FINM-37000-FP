import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analysis.robustness import VARIATIONS, robustness_table  # noqa: E402
from backtest.oos import freeze  # noqa: E402
from events.study import read_events  # noqa: E402
from synthetic import CFG, write_cutoffs, write_events_csv  # noqa: E402


def test_one_row_per_variation_with_both_periods(tmp_path):
    events = read_events(write_events_csv(tmp_path / "events.csv"))
    rules = freeze(CFG, write_cutoffs(tmp_path / "cutoffs.yaml"), tmp_path / "frozen.yaml")
    rules = yaml.safe_load((tmp_path / "frozen.yaml").read_text())
    table = robustness_table(events, rules)
    assert list(table.index) == [label for label, _ in VARIATIONS]
    base = table.loc["baseline (frozen rules)"]
    assert base["in_sample: trades"] == 2 and base["out_of_sample: trades"] == 2
    doubled = table.loc["fees doubled"]
    assert doubled["in_sample: mean_pnl_usd"] == base["in_sample: mean_pnl_usd"] - 4.0


def test_extra_event_files_get_their_own_row(tmp_path):
    path = write_events_csv(tmp_path / "events.csv")
    freeze(CFG, write_cutoffs(tmp_path / "cutoffs.yaml"), tmp_path / "frozen.yaml")
    rules = yaml.safe_load((tmp_path / "frozen.yaml").read_text())
    table = robustness_table(read_events(path), rules, variations=[], extra={"quantile 0.99": path})
    assert list(table.index) == ["quantile 0.99"]
