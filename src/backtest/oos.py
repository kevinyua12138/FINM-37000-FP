"""Out-of-sample evaluation (issue #13): freeze the rules, then apply them once.

    python src/backtest/oos.py freeze   # config/frozen_rules.yaml from the in-sample run
    git add config/frozen_rules.yaml && git commit -m "Freeze trading rules (#13)"
    git tag rules-frozen && git push origin rules-frozen
    # only now: download May-June, rerun src/events/shocks.py and src/events/build.py
    python src/backtest/oos.py run      # once -> results/oos/ and figures/issue13/

`run` refuses to overwrite an existing results/oos/summary.csv, so the test really runs
once. --force exists for genuine bugs; say so in the write-up if you use it.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analysis.stats import to_markdown  # noqa: E402
from backtest.engine import make_trades, plot_cumulative, summarize  # noqa: E402
from events.study import assign_regimes, in_period, read_events, regime_table  # noqa: E402

FROZEN = Path("config/frozen_rules.yaml")


def _git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def freeze(cfg, cutoffs_path, frozen_path=FROZEN):
    """Write every choice the out-of-sample run needs into one file."""
    import yaml

    cutoffs = yaml.safe_load(Path(cutoffs_path).read_text())
    study, bt, shocks = cfg["study"], cfg["backtest"], cfg["shocks"]
    rules = {
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "in_sample": [str(d) for d in study["in_sample"]],
        "out_of_sample": [str(d) for d in study["out_of_sample"]],
        "shocks": {k: shocks[k] for k in ("window_s", "quantile", "history_days", "cooldown_s")},
        "regimes": cutoffs,
        "backtest": {k: bt[k] for k in ("horizon_s", "fee_per_side_usd", "point_value_usd")},
    }
    frozen_path = Path(frozen_path)
    frozen_path.parent.mkdir(parents=True, exist_ok=True)
    frozen_path.write_text(yaml.safe_dump(rules, sort_keys=False))
    return rules


def run(events_path, frozen_path=FROZEN, out_dir=Path("results/oos"), fig_dir=Path("figures/issue13"),
        force=False):
    """Apply the frozen rules to both periods; only the out-of-sample one is new."""
    import yaml

    out_dir, fig_dir = Path(out_dir), Path(fig_dir)
    if (out_dir / "summary.csv").exists() and not force:
        raise SystemExit(f"{out_dir}/summary.csv exists: the out-of-sample test already ran once")
    rules = yaml.safe_load(Path(frozen_path).read_text())
    events = read_events(events_path)
    periods = {"in_sample": rules["in_sample"], "out_of_sample": rules["out_of_sample"]}
    by_period = {name: assign_regimes(in_period(events, p), rules["regimes"]) for name, p in periods.items()}
    if by_period["out_of_sample"].empty:
        raise SystemExit("no out-of-sample events: download May-June, rerun shocks.py and build.py")

    bt = rules["backtest"]
    trades = {name: make_trades(ev, bt["horizon_s"], bt["fee_per_side_usd"], bt["point_value_usd"])
              for name, ev in by_period.items()}
    summary = pd.DataFrame({name: summarize(trades[name], ev["date"].unique())
                            for name, ev in by_period.items()})
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    oos = by_period["out_of_sample"]
    oos.to_csv(out_dir / "events.csv", index=False)
    trades["out_of_sample"].to_csv(out_dir / "trades.csv", index=False)
    table = regime_table(oos, main=bt["horizon_s"])
    table.to_csv(out_dir / "regime_table.csv")
    (out_dir / "regime_table.md").write_text(to_markdown(table, 2))
    (out_dir / "summary.md").write_text(to_markdown(summary, 2))
    summary.to_csv(out_dir / "summary.csv")  # written last: its presence marks the run as done
    plot_cumulative({"in-sample": trades["in_sample"], "out-of-sample": trades["out_of_sample"]},
                    fig_dir / "cumulative_pnl.png")
    return summary


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="Freeze the rules, or run the out-of-sample test once.")
    parser.add_argument("command", choices=["freeze", "run"])
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--cutoffs", type=Path, default=Path("results/in_sample/cutoffs.yaml"))
    parser.add_argument("--frozen", type=Path, default=FROZEN)
    parser.add_argument("--force", action="store_true", help="rerun even though results/oos exists")
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    if args.command == "freeze":
        rules = freeze(cfg, args.cutoffs, args.frozen)
        print(yaml.safe_dump(rules, sort_keys=False))
        print(f"wrote {args.frozen}; commit it and tag the commit before downloading May-June")
    else:
        print(run(cfg["study"]["events"], args.frozen, force=args.force).round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
