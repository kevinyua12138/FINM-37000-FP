"""Final README results section (issue #17), generated from results/ and figures/.

    python src/report/readme_results.py   # rewrites the block between the markers in README.md

Everything between the two markers below is regenerated on each run, so rerun it after any
change instead of editing that block by hand. The prose lives in two files you write:
docs/findings.md (your interpretation) and docs/limitations.md. The first run creates
starter versions of both; later runs include them as they are and never overwrite them.
"""
import argparse
from pathlib import Path

import pandas as pd

START, END = "<!-- results:start -->", "<!-- results:end -->"

TABLES = [  # (heading, markdown file written by an earlier step)
    ("2x2 regime table, in-sample (#10, #11)", "results/in_sample/cells_2x2.md"),
    ("Forward returns by regime, in-sample (#10)", "results/in_sample/regime_table.md"),
    ("Day-clustered regressions, in-sample (#11)", "results/in_sample/regression.md"),
    ("Backtest with frozen rules: in-sample vs out-of-sample (#12, #13)", "results/oos/summary.md"),
    ("Forward returns by regime, out-of-sample (#13)", "results/oos/regime_table.md"),
    ("Robustness (#14)", "results/robustness.md"),
    ("Logistic model (#15)", "results/logit/metrics.md"),
    ("Depth sample, mbp-10 (#16)", "results/depth/summary.md"),
]
FIGURES = [
    ("Shocks per day", "figures/issue10/shocks_per_day.png"),
    ("Average move after a shock, by regime", "figures/issue10/average_path.png"),
    ("Refill ratio and half-life", "figures/issue10/refill_distributions.png"),
    ("Signed OFI vs 30 s return", "figures/issue10/ofi_vs_return.png"),
    ("Cumulative P&L, in-sample and out-of-sample", "figures/issue13/cumulative_pnl.png"),
    ("Logistic model calibration", "figures/issue15/calibration.png"),
    ("Best-quote vs 10-level refill", "figures/issue16/refill_best_vs_depth10.png"),
]
FINDINGS_STARTER = """<!-- Write your interpretation here. Suggested order: did H1 and H2 hold in-sample
(the follow and fade rows of the regime table), did the frozen rule survive May-June after
costs (H3), and which robustness rows change the answer. -->
- H1 (slow refill + strong pressure -> continuation):
- H2 (fast refill + weak pressure -> reversal):
- H3 (profitable out-of-sample after spread and fees):
"""
LIMITATIONS_STARTER = """- One half-year of ES (January-June 2025), regular hours only, so few FOMC days and one tariff episode.
- mbp-1 shows only the best level; the 10-level check (#16) covers a small depth sample.
- One contract per trade, filled at the touch with 100 ms latency; no queue position or market impact.
- Fees are an assumption (config.yaml `backtest.fee_per_side_usd`), not a broker quote.
- The regime cutoffs are in-sample medians; other splits are only explored in the robustness table.
- The prototype (#6) ran on September 2026 data; all reported results use 2025.
"""


def _csv(root, path):
    p = root / path
    return pd.read_csv(p, index_col=0) if p.exists() else None


def _get(table, row, col):
    try:
        value = table.loc[row, col]
        return float(value) if pd.notna(value) else None
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _fmt(value, digits=2, prefix=""):
    return "n/a" if value is None else f"{prefix}{value:,.{digits}f}"


def headline(root):
    """Auto-written sentences from the results files; skips whatever has not been run yet."""
    lines = []
    events_in, events_out = _csv(root, "results/in_sample/events.csv"), _csv(root, "results/oos/events.csv")
    if events_in is not None:
        lines.append(f"- In-sample: {len(events_in)} shocks on {events_in['date'].nunique()} trading days.")
    if events_out is not None:
        lines.append(f"- Out-of-sample: {len(events_out)} shocks on {events_out['date'].nunique()} trading days.")
    regimes = _csv(root, "results/in_sample/regime_table.csv")
    if regimes is not None:
        for name in ("follow", "fade"):
            n, mean, t = (_get(regimes, name, c) for c in ("n", "mean_bp_30s", "t_30s"))
            lines.append(f"- In-sample {name} shocks ({_fmt(n, 0)}) moved {_fmt(mean)} bp in the shock "
                         f"direction over 30 s (day-clustered t = {_fmt(t)}).")
    summary = _csv(root, "results/oos/summary.csv")
    if summary is not None:
        col = "out_of_sample"
        cost = (_get(summary, "mean_spread_cost_usd", col) or 0) + (_get(summary, "fees_per_trade_usd", col) or 0)
        lines.append(
            f"- Out-of-sample, the frozen rules made {_fmt(_get(summary, 'mean_pnl_usd', col), prefix='$')} per "
            f"contract per trade after spread and fees (t = {_fmt(_get(summary, 't_day_clustered', col))}, "
            f"{_fmt(_get(summary, 'trades', col), 0)} trades, hit rate {_fmt(_get(summary, 'hit_rate_pct', col), 1)}%). "
            f"Break-even round-trip cost {_fmt(_get(summary, 'break_even_cost_usd', col), prefix='$')} "
            f"vs {_fmt(cost, prefix='$')} paid.")
    logit = _csv(root, "results/logit/metrics.csv")
    if logit is not None:
        lines.append(f"- Logistic model AUC: {_fmt(_get(logit, 'auc', 'in_sample'), 3)} in-sample, "
                     f"{_fmt(_get(logit, 'auc', 'out_of_sample'), 3)} out-of-sample.")
    return "\n".join(lines) if lines else "- No results yet: run the pipeline in the README first."


def _prose(root, name, starter):
    path = root / "docs" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(starter)
    return path.read_text().strip()


def results_block(root):
    root = Path(root)
    parts = [START, "## Results", "", "### Headline numbers", "", headline(root), "",
             "### Findings", "", _prose(root, "findings.md", FINDINGS_STARTER), ""]
    figures = [(title, path) for title, path in FIGURES if (root / path).exists()]
    if figures:
        parts += ["### Figures", ""] + [f"**{title}**\n\n![{title}]({path})\n" for title, path in figures]
    for heading, path in TABLES:
        if (root / path).exists():
            parts += [f"### {heading}", "", (root / path).read_text().strip(), ""]
    parts += ["### Limitations", "", _prose(root, "limitations.md", LIMITATIONS_STARTER), "", END]
    return "\n".join(parts) + "\n"


def update_readme(root="."):
    """Replace (or append) the results block in README.md. Returns the new README text."""
    readme = Path(root) / "README.md"
    text = readme.read_text() if readme.exists() else ""
    block = results_block(root)
    if START in text and END in text:
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1].lstrip("\n")
        text = before + block + after
    else:
        text = text.rstrip("\n") + "\n\n" + block
    readme.write_text(text)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Regenerate the README results section.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    update_readme(args.root)
    print(f"updated {args.root / 'README.md'} (edit docs/findings.md and docs/limitations.md for the prose)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
