import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analysis.stats import cluster_ols, clustered_mean, clustered_mean_se  # noqa: E402

Y = np.array([1.0, 2.0, 0.5, 3.0, -1.0, 4.0, 2.5, 0.0])
X1 = np.array([0.0, 1.0, 0.5, 2.0, -1.0, 3.0, 1.5, 0.5])
DAYS = np.array(["d1", "d1", "d2", "d2", "d3", "d3", "d4", "d4"])


def test_matches_statsmodels_cluster_robust_ols():
    # reference values from statsmodels OLS(Y, X).fit(cov_type="cluster", groups=DAYS)
    table = cluster_ols(Y, np.column_stack([np.ones(8), X1]), DAYS, ["const", "x"])
    assert np.allclose(table["coef"], [0.29737609, 1.28279883])
    assert np.allclose(table["se"], [0.30619702, 0.11100108])
    assert table.attrs == {"n": 8, "clusters": 4}


def test_clustered_mean_matches_statsmodels():
    stats = clustered_mean(Y, DAYS)
    assert stats["mean"] == 1.5 and np.isclose(stats["se"], 0.10206207) and stats["clusters"] == 4


def test_one_row_per_cluster_is_white_hc1():
    X = np.column_stack([np.ones(8), X1])
    table = cluster_ols(Y, X, np.arange(8), ["const", "x"])
    bread = np.linalg.inv(X.T @ X)
    u = Y - X @ table["coef"].to_numpy()
    hc1 = 8 / (8 - 2) * bread @ (X.T * u**2) @ X @ bread
    assert np.allclose(table["se"], np.sqrt(np.diag(hc1)))


def test_same_day_shocks_do_not_count_as_independent():
    # copying every shock 10 times shrinks an iid standard error, but not a day-clustered one
    once = clustered_mean(Y, DAYS)["se"]
    tenfold = clustered_mean(np.repeat(Y, 10), np.repeat(DAYS, 10))["se"]
    assert np.isclose(once, tenfold, rtol=0.05)


def test_empty_and_nan_inputs():
    assert np.isnan(clustered_mean(np.array([np.nan, np.nan]), np.array(["d1", "d2"]))["mean"])
    assert clustered_mean(np.array([1.0, np.nan, 3.0, 5.0]), np.array(["a", "a", "b", "c"]))["n"] == 3


def test_column_wise_mean_and_se():
    values = np.column_stack([Y, 2 * Y, np.full(8, np.nan)])
    mean, se = clustered_mean_se(values, DAYS)
    assert np.allclose(mean[:2], [1.5, 3.0]) and np.allclose(se[:2], [0.10206207, 0.20412415])
    assert np.isnan(mean[2]) and np.isnan(se[2])
