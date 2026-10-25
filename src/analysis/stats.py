"""Day-clustered statistics and regression table (issue #11).

Shocks on the same day are not independent (49 of the 78 prototype shocks came from one
FOMC afternoon), so every t-stat here clusters by trading day. CR1 cluster-robust variance:
    V = c (X'X)^-1 [sum_g X_g' u_g u_g' X_g] (X'X)^-1,   c = G/(G-1) * (N-1)/(N-K)
This matches statsmodels OLS(...).fit(cov_type="cluster"). p-values use the normal
approximation, which is fine with ~80 trading days and needs no scipy.

Usage (from the repo root, after `python src/events/study.py`):
    python src/analysis/stats.py   # -> results/in_sample/regression.{csv,md}
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

BP = 1e4


def _p_value(t):
    return math.erfc(abs(t) / math.sqrt(2)) if np.isfinite(t) else np.nan


def cluster_ols(y, X, clusters, names=None):
    """OLS coefficients with CR1 day-clustered standard errors.

    y: (N,), X: (N, K) including any constant, clusters: (N,) labels such as dates.
    Returns a DataFrame indexed by `names` with coef, se, t, p; attrs hold n and clusters.
    """
    y, X = np.asarray(y, float), np.asarray(X, float)
    if X.ndim == 1:
        X = X[:, None]
    groups, _ = pd.factorize(np.asarray(clusters))
    n, k = X.shape
    n_clusters = groups.max() + 1 if n else 0
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    scores = np.zeros((max(n_clusters, 1), k))
    np.add.at(scores, groups, X * resid[:, None])
    if n_clusters > 1 and n > k:
        c = n_clusters / (n_clusters - 1) * (n - 1) / (n - k)
        se = np.sqrt(np.diag(c * xtx_inv @ (scores.T @ scores) @ xtx_inv))
    else:
        se = np.full(k, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = beta / se
    table = pd.DataFrame({"coef": beta, "se": se, "t": t, "p": [_p_value(v) for v in t]},
                         index=names or [f"x{i}" for i in range(k)])
    table.attrs.update(n=n, clusters=n_clusters)
    return table


def clustered_mean(y, clusters):
    """Mean of y with a day-clustered standard error, t-stat and p-value."""
    y, clusters = np.asarray(y, float), np.asarray(clusters)
    keep = np.isfinite(y)
    if not keep.any():
        return {"mean": np.nan, "se": np.nan, "t": np.nan, "p": np.nan, "n": 0, "clusters": 0}
    row = cluster_ols(y[keep], np.ones(keep.sum()), clusters[keep], ["mean"]).iloc[0]
    return {"mean": row["coef"], "se": row["se"], "t": row["t"], "p": row["p"],
            "n": int(keep.sum()), "clusters": int(pd.unique(clusters[keep]).size)}


def clustered_mean_se(values, clusters):
    """Column-wise mean and CR1 day-clustered standard error of a 2-D array with NaNs.

    Used for the confidence band of the average price path (one column per second).
    """
    values, clusters = np.asarray(values, float), np.asarray(clusters)
    means, ses = np.full(values.shape[1], np.nan), np.full(values.shape[1], np.nan)
    for j in range(values.shape[1]):
        col = values[:, j]
        keep = np.isfinite(col)
        if keep.sum() < 2:
            continue
        stats = clustered_mean(col[keep], clusters[keep])
        means[j], ses[j] = stats["mean"], stats["se"]
    return means, ses


def regression_table(events, y_col="y_30s", features=("refill_best", "ofi", "ti"), cluster_col="date"):
    """Regress the forward return (bp, signed by shock direction) on shock features."""
    cols = [y_col, *features]
    data = events.dropna(subset=cols)
    X = np.column_stack([np.ones(len(data)), *(data[f].to_numpy(float) for f in features)])
    return cluster_ols(data[y_col].to_numpy(float) * BP, X, data[cluster_col], ["const", *features])


def regime_regression(events, y_col="y_30s", cluster_col="date"):
    """Forward return (bp) on follow and fade dummies; the constant is the no-trade mean."""
    data = events.dropna(subset=[y_col])
    X = np.column_stack([np.ones(len(data)), data["regime"].eq("follow"), data["regime"].eq("fade")])
    return cluster_ols(data[y_col].to_numpy(float) * BP, X, data[cluster_col], ["const", "follow", "fade"])


def to_markdown(table, digits=3):
    """Small markdown table without the optional tabulate dependency."""
    def cell(value):
        if isinstance(value, (float, np.floating)):
            return "n/a" if np.isnan(value) else str(round(float(value), digits))
        return str(value)

    head = "| | " + " | ".join(map(str, table.columns)) + " |"
    rule = "|---" * (len(table.columns) + 1) + "|"
    labels = [" / ".join(map(str, i)) if isinstance(i, tuple) else str(i) for i in table.index]
    rows = ["| " + " | ".join([label, *map(cell, values)]) + " |"
            for label, values in zip(labels, table.astype(object).to_numpy())]
    return "\n".join([head, rule, *rows]) + "\n"


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="Day-clustered regression table (in-sample).")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--events", type=Path, default=Path("results/in_sample/events.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/in_sample"))
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())["study"]
    events = pd.read_csv(args.events)
    y_col = f"y_{cfg.get('main_horizon_s', 30)}s"
    features = cfg.get("regression_features", ["refill_best", "ofi", "ti"])
    tables = {
        "features": regression_table(events, y_col, features),
        "regimes": regime_regression(events, y_col),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(tables, names=["model", "term"])
    combined.to_csv(args.out_dir / "regression.csv")
    with open(args.out_dir / "regression.md", "w") as f:
        for name, table in tables.items():
            f.write(f"### {name}: {y_col} in bp, N={table.attrs['n']}, days={table.attrs['clusters']}\n\n")
            f.write(to_markdown(table) + "\n")
    print(combined.round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
