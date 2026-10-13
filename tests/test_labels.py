import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from events.labels import entry_time, forward_return_labels  # noqa: E402

T0 = pd.Timestamp("2025-03-03 10:00:00", tz="America/Chicago")


def quotes(rows):
    """rows: (seconds after T0, mid, instrument_id)"""
    index = pd.DatetimeIndex([T0 + pd.Timedelta(seconds=s) for s, _, _ in rows])
    return pd.DataFrame({"mid": [m for _, m, _ in rows], "instrument_id": [i for _, _, i in rows]}, index=index)


def events(direction=1):
    return pd.DataFrame({"t0": [T0], "direction": [direction]})


def test_entry_is_observation_plus_latency():
    assert entry_time(T0) == T0 + pd.Timedelta("3.1s")


def test_entry_uses_first_quote_at_or_after_3_1s():
    q = quotes([(3.05, 90.0, 1), (3.1, 100.0, 1), (8.1, 101.0, 1), (33.1, 102.0, 1), (123.1, 103.0, 1)])
    out = forward_return_labels(q, events())
    assert out["y_5s"].iloc[0] == pytest.approx(0.01)  # 101 / 100 - 1, the 90.0 quote is ignored


def test_returns_for_all_horizons():
    q = quotes([(3.1, 100.0, 1), (8.1, 101.0, 1), (33.1, 102.0, 1), (123.1, 103.0, 1)])
    out = forward_return_labels(q, events())
    assert out[["y_5s", "y_30s", "y_120s"]].iloc[0].tolist() == pytest.approx([0.01, 0.02, 0.03])


def test_down_shock_return_is_signed_by_direction():
    q = quotes([(3.1, 100.0, 1), (8.1, 99.0, 1), (33.1, 98.0, 1), (123.1, 97.0, 1)])
    out = forward_return_labels(q, events(direction=-1))
    assert out["y_5s"].iloc[0] == pytest.approx(0.01)  # price fell after a down-shock, so the move continued


def test_label_missing_when_data_ends_before_horizon():
    q = quotes([(3.1, 100.0, 1), (8.1, 101.0, 1)])
    out = forward_return_labels(q, events())
    assert out["y_5s"].iloc[0] == pytest.approx(0.01)
    assert np.isnan(out["y_30s"].iloc[0]) and np.isnan(out["y_120s"].iloc[0])


def test_label_missing_when_quote_is_stale():
    q = quotes([(3.1, 100.0, 1), (9.5, 101.0, 1)])  # next quote is 1.4s after the 5s target
    assert np.isnan(forward_return_labels(q, events())["y_5s"].iloc[0])


def test_label_missing_across_contract_roll():
    q = quotes([(3.1, 100.0, 1), (8.1, 130.0, 2)])
    assert np.isnan(forward_return_labels(q, events())["y_5s"].iloc[0])


def test_label_missing_across_trading_day():
    q = quotes([(3.1, 100.0, 1), (15 * 3600 + 3.1, 101.0, 1)])  # exit quote is 01:00 the next day
    out = forward_return_labels(q, events(), horizons=(15 * 3600,))
    assert np.isnan(out["y_54000s"].iloc[0])


def test_issue6_figures_are_written(tmp_path):
    from events.figures import make_issue6_figures

    t0 = pd.date_range(T0, periods=4, freq="10min")
    ev = pd.DataFrame({
        "t0": t0, "direction": [1, -1, 1, -1], "half_life_s": [0.5, np.nan, 2.0, np.nan],
        "refill_ratio": [0.9, 0.0, 0.6, 0.1], "y_5s": [1e-4, -2e-4, 0.0, 3e-4],
        "y_30s": [2e-4, -1e-4, 1e-4, np.nan], "y_120s": [-1e-4, 2e-4, 0.0, 1e-4],
    })
    paths = make_issue6_figures(ev, tmp_path)
    assert len(paths) == 5 and all(p.exists() and p.stat().st_size > 0 for p in paths)
    assert (tmp_path / "events.csv").exists()
