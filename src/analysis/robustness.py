"""Robustness table (issue #14): the frozen strategy with one thing changed at a time.

Every row reports in-sample and out-of-sample results side by side. When a row switches to
a different feature column, its cutoff is refit on the in-sample shocks with the frozen
rule (e.g. "median"), never on May-June. Exclusion rows keep the frozen cutoffs.

Usage (from the repo root, after `python src/backtest/oos.py run`):
    python src/analysis/robustness.py   # -> results/robustness.{csv,md}
Detector settings (threshold quantile, cooldown) need new shocks and events first, e.g.
    python src/events/shocks.py --config config_q099.yaml --output data/processed/shocks_q099.csv
    python src/events/build.py --shocks data/processed/shocks_q099.csv --output data/processed/events_q099.csv
    python src/analysis/robustness.py --extra "quantile 0.99=data/processed/events_q099.csv"
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analysis.stats import to_markdown  # noqa: E402
from backtest.engine import make_trades, summarize  # noqa: E402
from events.study import assign_regimes, in_period, read_events, resolve_cutoff  # noqa: E402

VARIATIONS = [
    ("baseline (frozen rules)", {}),
    ("horizon 5s", {"horizon_s": 5}),
    ("horizon 120s", {"horizon_s": 120}),
    ("pressure cutoff 0 (sign of OFI)", {"pressure_cutoff": 0.0}),
    ("refill at the old price X (prototype)", {"refill_column": "refill_ratio"}),
    ("trade imbalance instead of OFI", {"pressure_column": "ti"}),
    ("excluding FOMC afternoons", {"exclude": ["fomc_window"]}),
    ("excluding the first 5 minutes", {"exclude": ["open_window"]}),
    ("excluding the tariff week", {"exclude": ["stress_window"]}),
    ("fees doubled", {"fee_multiplier": 2.0}),
]
METRICS = ["trades", "mean_pnl_usd", "t_day_clustered", "hit_rate_pct", "break_even_cost_usd"]


def evaluate(events, rules, change):
    """One robustness row: METRICS for the in-sample and out-of-sample periods."""
    regimes, bt = dict(rules["regimes"]), rules["backtest"]
    for flag in change.get("exclude", []):
        events = events[~events[flag].astype(bool)]
    in_sample = in_period(events, rules["in_sample"])
    for kind in ("refill", "pressure"):
        if f"{kind}_column" in change:
            regimes[f"{kind}_column"] = change[f"{kind}_column"]
            regimes[f"{kind}_cutoff"] = resolve_cutoff(in_sample[change[f"{kind}_column"]],
                                                       regimes[f"{kind}_rule"])
        if f"{kind}_cutoff" in change:
            regimes[f"{kind}_cutoff"] = change[f"{kind}_cutoff"]
    horizon = change.get("horizon_s", bt["horizon_s"])
    fee = bt["fee_per_side_usd"] * change.get("fee_multiplier", 1.0)
    row = {}
    for name in ("in_sample", "out_of_sample"):
        period = assign_regimes(in_period(events, rules[name]), regimes)
        stats = summarize(make_trades(period, horizon, fee, bt["point_value_usd"]), period["date"].unique())
        for metric in METRICS:
            row[f"{name}: {metric}"] = stats.get(metric, float("nan"))
    return row


def robustness_table(events, rules, variations=VARIATIONS, extra=None):
    rows = {label: evaluate(events, rules, change) for label, change in variations}
    for label, path in (extra or {}).items():
        rows[label] = evaluate(read_events(path), rules, {})
    return pd.DataFrame(rows).T


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="Robustness table for the frozen strategy.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--frozen", type=Path, default=Path("config/frozen_rules.yaml"))
    parser.add_argument("--extra", action="append", default=[], help='"label=path/to/events.csv"')
    parser.add_argument("--out", type=Path, default=Path("results/robustness"))
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    if not args.frozen.exists():
        parser.error(f"{args.frozen} missing: run `python src/backtest/oos.py freeze` first")
    rules = yaml.safe_load(args.frozen.read_text())
    extra = dict(item.split("=", 1) for item in args.extra)
    table = robustness_table(read_events(cfg["study"]["events"]), rules, extra=extra)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out.with_suffix(".csv"))
    args.out.with_suffix(".md").write_text(to_markdown(table, 2))
    print(table.round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
