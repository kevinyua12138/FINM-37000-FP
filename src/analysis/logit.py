"""Logistic regression model (issue #15): the probability that a shock keeps going for 30 s.

Fit on Jan-Apr only, freeze, then evaluate once on May-June, the same discipline as #13:
    python src/analysis/logit.py fit        # -> results/logit/model.yaml + in-sample metrics
    git add results/logit && git commit -m "Freeze logistic model (#15)"
    python src/analysis/logit.py evaluate   # once -> out-of-sample AUC, calibration, backtest

Target: 1 if y_30s > 0 (continued), 0 if y_30s < 0 (reversed); flat shocks are left out of
the fit and the AUC. Features are standardized with in-sample means and standard deviations,
and a small ridge penalty (not on the intercept) keeps Newton's method stable.
Model backtest: follow if p > 0.5 + margin, fade if p < 0.5 - margin, otherwise no trade,
traded with the #12 engine (spread and fees included).
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analysis.stats import to_markdown  # noqa: E402
from backtest.engine import make_trades, plot_cumulative, summarize  # noqa: E402
from events.study import in_period, read_events  # noqa: E402

OUT = Path("results/logit")
FIGURES = Path("figures/issue15")


def fit_logit(X, y, l2=1.0, max_iter=100, tol=1e-10):
    """Ridge-penalized logistic regression by Newton's method. Column 0 must be the intercept."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    penalty = np.full(X.shape[1], float(l2))
    penalty[0] = 0.0
    beta = np.zeros(X.shape[1])
    for _ in range(max_iter):
        p = 1 / (1 + np.exp(-X @ beta))
        grad = X.T @ (y - p) - penalty * beta
        hess = (X * (p * (1 - p))[:, None]).T @ X + np.diag(penalty)
        step = np.linalg.lstsq(hess, grad, rcond=None)[0]  # stays defined if the data separate
        beta += step
        if np.max(np.abs(step)) < tol:
            break
    return beta


def predict(X, beta):
    return 1 / (1 + np.exp(-np.asarray(X, float) @ np.asarray(beta, float)))


def auc(y, p):
    """Area under the ROC curve (Mann-Whitney), with tied scores counted as one half."""
    y, ranks = np.asarray(y, int), pd.Series(np.asarray(p, float)).rank(method="average").to_numpy()
    pos, neg = y.sum(), len(y) - y.sum()
    if pos == 0 or neg == 0:
        return np.nan
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def log_loss(y, p, eps=1e-12):
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration_table(y, p, bins=10):
    """Mean predicted probability vs observed continuation rate in equal-count bins."""
    data = pd.DataFrame({"y": np.asarray(y, float), "p": np.asarray(p, float)})
    data["bin"] = pd.qcut(data["p"].rank(method="first"), min(bins, len(data)), labels=False)
    table = data.groupby("bin").agg(n=("y", "size"), mean_p=("p", "mean"), observed=("y", "mean"))
    return table.reset_index(drop=True)


def design(events, features, means, stds):
    z = (events[features].to_numpy(float) - np.asarray(means)) / np.asarray(stds)
    return np.column_stack([np.ones(len(events)), z])


def model_regimes(p, margin):
    return np.select([p > 0.5 + margin, p < 0.5 - margin], ["follow", "fade"], default="no trade")


def evaluate_period(events, model, horizon_s, bt):
    """Metrics, calibration table, trades and backtest summary for one period."""
    data = events.dropna(subset=model["features"]).reset_index(drop=True)
    p = predict(design(data, model["features"], model["means"], model["stds"]), model["coef"])
    y = data[f"y_{horizon_s}s"].to_numpy(float)
    moved = np.isfinite(y) & (y != 0)
    label = (y[moved] > 0).astype(int)
    metrics = {"shocks": len(data), "fit_rows": int(moved.sum()), "continued_rate": label.mean(),
               "auc": auc(label, p[moved]), "log_loss": log_loss(label, p[moved]),
               "brier": float(np.mean((p[moved] - label) ** 2))}
    trades = make_trades(data.assign(regime=model_regimes(p, model["margin"])), horizon_s,
                         bt["fee_per_side_usd"], bt["point_value_usd"])
    summary = summarize(trades, data["date"].unique())
    return metrics, calibration_table(label, p[moved]), trades, summary


def fit_model(events, features, horizon_s=30, l2=1.0, margin=0.05):
    data = events.dropna(subset=features + [f"y_{horizon_s}s"])
    data = data[data[f"y_{horizon_s}s"] != 0]
    means, stds = data[features].mean().to_numpy(), data[features].std().replace(0, 1).to_numpy()
    X = design(data, features, means, stds)
    coef = fit_logit(X, (data[f"y_{horizon_s}s"] > 0).astype(int).to_numpy(), l2)
    return {"features": list(features), "means": means.tolist(), "stds": stds.tolist(),
            "coef": coef.tolist(), "l2": float(l2), "margin": float(margin), "horizon_s": horizon_s,
            "fit_on": [str(events["date"].min()), str(events["date"].max())], "rows": len(data),
            "fit_at": datetime.now().isoformat(timespec="seconds")}


def plot_calibration(tables, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 1], [0, 1], color="#6b7280", linewidth=1, linestyle=":")
    for (label, table), color in zip(tables.items(), ["#2a6fdb", "#d9480f"]):
        ax.plot(table["mean_p"], table["observed"], marker="o", color=color, label=label)
    ax.set_xlabel("predicted P(continue)")
    ax.set_ylabel("observed continuation rate")
    ax.set_title("Calibration of the logistic model", loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _write(name, table, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / f"{name}.csv")
    (out / f"{name}.md").write_text(to_markdown(table, 3))


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="Fit the logistic model in-sample, or evaluate it once.")
    parser.add_argument("command", choices=["fit", "evaluate"])
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--force", action="store_true", help="re-evaluate even though results exist")
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    study, bt, lg = cfg["study"], cfg["backtest"], cfg["logit"]
    events = read_events(study["events"], cfg["session"]["timezone"])
    if args.command == "fit":
        in_sample = in_period(events, study["in_sample"])
        model = fit_model(in_sample, lg["features"], bt["horizon_s"], lg["l2"], lg["margin"])
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "model.yaml").write_text(yaml.safe_dump(model, sort_keys=False))
        metrics, calib, _, summary = evaluate_period(in_sample, model, bt["horizon_s"], bt)
        _write("metrics_in_sample", pd.Series(metrics).to_frame("in_sample"))
        _write("calibration_in_sample", calib)
        _write("backtest_in_sample", summary.to_frame("in_sample"))
        print(pd.Series(model["coef"], index=["const", *model["features"]]).round(3).to_string())
        print(pd.Series(metrics).round(3).to_string())
        print("commit results/logit/ before running `evaluate`")
        return 0

    if (OUT / "metrics.csv").exists() and not args.force:
        raise SystemExit("results/logit/metrics.csv exists: the model was already evaluated once")
    model = yaml.safe_load((OUT / "model.yaml").read_text())
    results = {name: evaluate_period(in_period(events, study[name]), model, bt["horizon_s"], bt)
               for name in ("in_sample", "out_of_sample")}
    _write("calibration_out_of_sample", results["out_of_sample"][1])
    _write("backtest", pd.DataFrame({n: r[3] for n, r in results.items()}))
    FIGURES.mkdir(parents=True, exist_ok=True)
    plot_calibration({n.replace("_", "-"): r[1] for n, r in results.items()}, FIGURES / "calibration.png")
    plot_cumulative({n.replace("_", "-"): r[2] for n, r in results.items()}, FIGURES / "cumulative_pnl.png")
    metrics = pd.DataFrame({n: r[0] for n, r in results.items()})
    _write("metrics", metrics)  # written last: its presence marks the evaluation as done
    print(metrics.round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
