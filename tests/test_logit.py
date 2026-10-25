import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analysis.logit import auc, calibration_table, fit_logit, main, model_regimes, predict  # noqa: E402

X1 = np.array([0, 1, 0.5, 2, -1, 3, 1.5, 0.5, 2.5, -0.5])
Y = np.array([0, 1, 1, 1, 0, 1, 0, 0, 1, 1])


def test_matches_statsmodels_without_penalty():
    # reference values from statsmodels Logit(Y, [1, X1]).fit()
    beta = fit_logit(np.column_stack([np.ones(10), X1]), Y, l2=0.0)
    assert np.allclose(beta, [-0.34429053, 0.92700435])


def test_ridge_solution_satisfies_its_first_order_condition():
    X = np.column_stack([np.ones(10), X1, X1**2])
    beta = fit_logit(X, Y, l2=2.0)
    grad = X.T @ (Y - predict(X, beta))
    assert np.isclose(grad[0], 0.0, atol=1e-8)          # intercept is not penalized
    assert np.allclose(grad[1:], 2.0 * beta[1:], atol=1e-8)


def test_separable_data_does_not_crash():
    beta = fit_logit(np.column_stack([np.ones(4), [0.0, 1.0, 2.0, 3.0]]), np.array([0, 0, 1, 1]), l2=1.0)
    assert np.all(np.isfinite(beta)) and beta[1] > 0


def test_auc_known_values():
    assert auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]) == 0.75
    assert auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5
    assert auc([0, 0, 1], [0.1, 0.2, 0.9]) == 1.0 and np.isnan(auc([1, 1], [0.2, 0.3]))


def test_calibration_bins_have_equal_counts():
    p = np.linspace(0.05, 0.95, 20)
    table = calibration_table((p > 0.5).astype(int), p, bins=4)
    assert table["n"].tolist() == [5, 5, 5, 5] and table["mean_p"].is_monotonic_increasing
    assert table["observed"].tolist() == [0.0, 0.0, 1.0, 1.0]


def test_margin_maps_probabilities_to_regimes():
    regimes = model_regimes(np.array([0.7, 0.52, 0.5, 0.44, 0.3]), margin=0.05)
    assert regimes.tolist() == ["follow", "no trade", "no trade", "fade", "fade"]


def synthetic_events(n_days_in=10, n_days_out=5, per_day=4, seed=0):
    """Shocks whose 30 s outcome follows the sign of signed OFI, with some noise."""
    rng = np.random.default_rng(seed)
    days = list(pd.bdate_range("2025-02-03", periods=n_days_in).strftime("%Y-%m-%d")) + \
        list(pd.bdate_range("2025-05-05", periods=n_days_out).strftime("%Y-%m-%d"))
    rows = []
    for day in days:
        for k in range(per_day):
            ofi = rng.uniform(-1, 1)
            move = 0.5 if ofi + rng.normal(0, 0.3) > 0 else -0.5  # index points, in the shock direction
            rows.append({"t0": pd.Timestamp(f"{day} 10:{10 * k:02d}:00", tz="America/Chicago"), "date": day,
                         "direction": 1, "ofi": ofi, "refill_best": rng.uniform(0, 1),
                         "y_30s": move / 5000, "entry_bid": 5000.0, "entry_ask": 5000.25,
                         "exit_bid_30s": 5000.0 + move, "exit_ask_30s": 5000.25 + move})
    return pd.DataFrame(rows)


def test_fit_then_evaluate_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    synthetic_events().to_csv("events.csv", index=False)
    Path("config.yaml").write_text(
        "session: {timezone: America/Chicago}\n"
        "study: {events: events.csv, in_sample: ['2025-01-01', '2025-04-30'],"
        " out_of_sample: ['2025-05-01', '2025-06-30']}\n"
        "backtest: {horizon_s: 30, fee_per_side_usd: 2.0, point_value_usd: 50.0}\n"
        "logit: {features: [ofi, refill_best], l2: 1.0, margin: 0.05}\n")
    assert main(["fit"]) == 0 and Path("results/logit/model.yaml").exists()
    assert main(["evaluate"]) == 0
    metrics = pd.read_csv("results/logit/metrics.csv", index_col=0)
    assert metrics.loc["auc", "out_of_sample"] > 0.7  # OFI carries the signal by construction
    assert Path("figures/issue15/calibration.png").exists()
    with pytest.raises(SystemExit):
        main(["evaluate"])  # evaluated once only
