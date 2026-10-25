"""Event study and 2x2 regime table (issue #10), in-sample only.

Each shock gets a refill bucket (slow if below the refill cutoff) and a pressure bucket
(strong if signed OFI is above the pressure cutoff). Cutoffs come from the in-sample
shocks only ("median" in config.yaml, or a fixed number), so they can be frozen for #13.
    slow refill + strong pressure -> follow   (H1: the move continues)
    fast refill + weak pressure   -> fade     (H2: the move reverses)
    anything else, or a missing feature -> no trade
Optional neutral band: with pressure_low_cutoff set (e.g. -0.05 next to a pressure cutoff of
0.05), "weak" means reversing flow below the low cutoff, and shocks in between are no trade.

Usage (from the repo root, after `python src/events/build.py`):
    python src/events/study.py
Writes results/in_sample/{cutoffs.yaml, events.csv, regime_table.*, cells_2x2.*}
and figures/issue10/{shocks_per_day, average_path, refill_distributions, ofi_vs_return}.png
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analysis.stats import BP, clustered_mean, clustered_mean_se, to_markdown  # noqa: E402

TZ = "America/Chicago"
REGIMES = ["follow", "fade", "no trade"]
COLORS = {"follow": "#2a6fdb", "fade": "#d9480f", "no trade": "#6b7280"}


def read_events(path, tz=TZ):
    events = pd.read_csv(path)
    for col in ("t0", "entry_time"):
        if col in events:
            events[col] = pd.to_datetime(events[col], utc=True).dt.tz_convert(tz)
    events["date"] = events["date"].astype(str)
    return events


def in_period(events, period):
    start, end = (str(d) for d in period)
    return events[(events["date"] >= start) & (events["date"] <= end)].reset_index(drop=True)


def resolve_cutoff(values, rule):
    """'median' -> median of the given (in-sample) values; a number -> that number."""
    return float(np.nanmedian(values)) if rule == "median" else float(rule)


def fit_cutoffs(events, cfg):
    """Numeric cutoffs from in-sample events, in the form frozen_rules.yaml stores them."""
    return {
        "refill_column": cfg["refill_column"],
        "refill_rule": cfg["refill_cutoff"],
        "refill_cutoff": resolve_cutoff(events[cfg["refill_column"]], cfg["refill_cutoff"]),
        "pressure_column": cfg["pressure_column"],
        "pressure_rule": cfg["pressure_cutoff"],
        "pressure_cutoff": resolve_cutoff(events[cfg["pressure_column"]], cfg["pressure_cutoff"]),
        "pressure_low_cutoff": (None if cfg.get("pressure_low_cutoff") is None
                                else resolve_cutoff(events[cfg["pressure_column"]], cfg["pressure_low_cutoff"])),
    }


def assign_regimes(events, cutoffs):
    """Add slow_refill, strong_pressure and regime columns to a copy of events."""
    out = events.copy()
    refill, pressure = out[cutoffs["refill_column"]], out[cutoffs["pressure_column"]]
    known = refill.notna() & pressure.notna()
    slow = refill < cutoffs["refill_cutoff"]
    strong = pressure > cutoffs["pressure_cutoff"]
    low = cutoffs.get("pressure_low_cutoff")
    weak = ~strong if low is None else pressure < low
    sided = known & (strong | weak)  # shocks in a neutral band are in neither column
    out["slow_refill"] = np.where(known, slow, np.nan)
    out["strong_pressure"] = np.where(sided, strong, np.nan)
    out["regime"] = np.select([sided & slow & strong, sided & ~slow & weak],
                              ["follow", "fade"], default="no trade")
    return out


def _summary(group, horizons, main):
    row = {"n": len(group), "days": group["date"].nunique()}
    for h in horizons:
        stats = clustered_mean(group[f"y_{h}s"].to_numpy(float) * BP, group["date"].to_numpy())
        row[f"mean_bp_{h}s"], row[f"t_{h}s"] = stats["mean"], stats["t"]
    y = group[f"y_{main}s"].dropna()
    row[f"continued_pct_{main}s"] = 100 * (y > 0).mean() if len(y) else np.nan
    return row


def regime_table(events, horizons=(5, 30, 120), main=30):
    """Count, mean forward return (bp, + = continued) and day-clustered t per regime."""
    rows = {r: _summary(events[events["regime"] == r], horizons, main) for r in REGIMES}
    rows["all"] = _summary(events, horizons, main)
    table = pd.DataFrame(rows).T
    return table.astype({"n": int, "days": int})


def cell_table(events, horizon=30):
    """The 2x2 table: shocks, mean return (bp) and day-clustered t in each cell."""
    rows = []
    for slow, refill in ((1.0, "slow refill"), (0.0, "fast refill")):
        for strong, pressure in ((1.0, "strong pressure"), (0.0, "weak pressure")):
            cell = events[(events["slow_refill"] == slow) & (events["strong_pressure"] == strong)]
            stats = clustered_mean(cell[f"y_{horizon}s"].to_numpy(float) * BP, cell["date"].to_numpy())
            rows.append({"refill": refill, "pressure": pressure, "n": len(cell),
                         f"mean_bp_{horizon}s": stats["mean"], f"t_{horizon}s": stats["t"]})
    return pd.DataFrame(rows).set_index(["refill", "pressure"])


def path_matrix(grids, events, horizon_s=120):
    """Mid move in the shock direction (bp) from t0 to t0 + k seconds, one row per shock.

    grids: {date string: shocks.mid_grid(...)}; NaN after a contract change or a missing day.
    """
    offsets = pd.to_timedelta(np.arange(horizon_s + 1), unit="s")
    rows = np.full((len(events), horizon_s + 1), np.nan)
    for k, ev in enumerate(events.itertuples()):
        grid = grids.get(str(ev.date))
        if grid is None:
            continue
        window = grid.reindex(ev.t0 + offsets)
        mids = window["mid"].where(window["instrument_id"] == window["instrument_id"].iloc[0])
        rows[k] = ev.direction * (mids.to_numpy() / mids.iloc[0] - 1) * BP
    return rows


def average_paths(grids, events, horizon_s=120):
    """Mean path and 95% band (day-clustered) for each regime, indexed by seconds after t0."""
    paths = path_matrix(grids, events, horizon_s)
    out = {}
    for regime in REGIMES:
        mask = (events["regime"] == regime).to_numpy()
        if mask.sum() < 2:
            continue
        mean, se = clustered_mean_se(paths[mask], events.loc[mask, "date"].to_numpy())
        out[(regime, "mean")], out[(regime, "lo")], out[(regime, "hi")] = mean, mean - 1.96 * se, mean + 1.96 * se
    return pd.DataFrame(out, index=pd.RangeIndex(horizon_s + 1, name="seconds_after_shock"))


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _figure(title, xlabel, ylabel, size=(9, 4)):
    fig, ax = _plt().subplots(figsize=size)
    ax.set_title(title, loc="left", fontsize=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return fig, ax


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    _plt().close(fig)
    return path


def plot_shocks_per_day(events, path):
    counts = events.groupby("date").size()
    fomc = (events.groupby("date")["is_fomc_day"].any() if "is_fomc_day" in events
            else pd.Series(False, index=counts.index))
    fig, ax = _figure("Shocks per day", "trading day", "shocks", size=(11, 4))
    colors = ["#d9480f" if f else "#2a6fdb" for f in fomc.reindex(counts.index, fill_value=False)]
    ax.bar(range(len(counts)), counts.to_numpy(), color=colors)
    step = max(1, len(counts) // 12)
    ax.set_xticks(range(0, len(counts), step), counts.index[::step], rotation=45, ha="right")
    ax.text(0.99, 0.95, "orange = FOMC day", transform=ax.transAxes, ha="right", va="top", color="#d9480f")
    return _save(fig, path)


def plot_average_paths(paths, path):
    fig, ax = _figure("Average move after a shock, by regime", "seconds after the shock",
                      "move in the shock direction (bp)")
    for regime in REGIMES:
        if (regime, "mean") not in paths:
            continue
        x = paths.index.to_numpy()
        ax.plot(x, paths[(regime, "mean")], color=COLORS[regime], label=regime)
        ax.fill_between(x, paths[(regime, "lo")], paths[(regime, "hi")], color=COLORS[regime], alpha=0.15)
    ax.axhline(0.0, color="#6b7280", linewidth=1)
    ax.axvline(3.1, color="#6b7280", linewidth=1, linestyle=":")  # entry
    ax.legend(frameon=False)
    return _save(fig, path)


def plot_refill_distributions(events, cutoffs, path):
    fig, axes = _plt().subplots(1, 2, figsize=(10, 4))
    col = cutoffs["refill_column"]
    half = "half_life_best_s" if col == "refill_best" else "half_life_s"
    axes[0].hist(events[col].dropna(), bins=40, color="#2a6fdb")
    axes[0].axvline(cutoffs["refill_cutoff"], color="#d9480f", label="cutoff")
    axes[0].set_title(f"{col} (D at t0 + 3s / D_pre)", loc="left")
    axes[0].legend(frameon=False)
    axes[1].hist(events[half].dropna(), bins=30, color="#2a6fdb")
    never = events[half].isna().mean() * 100
    axes[1].set_title(f"{half} ({never:.0f}% never refilled within 3s)", loc="left")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path)


def plot_ofi_vs_return(events, cutoffs, path, horizon=30):
    col = cutoffs["pressure_column"]
    data = events.dropna(subset=[col, f"y_{horizon}s"])
    x, y = data[col].to_numpy(float), data[f"y_{horizon}s"].to_numpy(float) * BP
    fig, ax = _figure(f"Signed {col} vs {horizon}s forward return", f"{col} (+ = with the shock)",
                      f"{horizon}s return in the shock direction (bp)")
    ax.scatter(x, y, s=12, color="#2a6fdb", alpha=0.5)
    if len(data) > 2:
        slope, intercept = np.polyfit(x, y, 1)
        grid = np.linspace(x.min(), x.max(), 50)
        ax.plot(grid, intercept + slope * grid, color="#d9480f", label=f"slope {slope:.2f} bp per unit")
        ax.legend(frameon=False)
    ax.axhline(0.0, color="#6b7280", linewidth=1)
    return _save(fig, path)


def load_grids_for(cfg, dates):
    """1-second mid grids (bbo-1s files used by the detector) for the given dates."""
    from events.shocks import load_grids

    raw = Path(cfg["data"]["raw_dir"])
    paths = [p for p in sorted(raw.glob(f"ES_{cfg['shocks']['schema']}_*.dbn.zst"))
             if p.name.split("_")[-1].split(".")[0] in set(dates)]
    return {str(d): g for d, g in load_grids(paths, cfg["session"]["timezone"]).items()}


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="In-sample event study and 2x2 regime table.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/in_sample"))
    parser.add_argument("--fig-dir", type=Path, default=Path("figures/issue10"))
    parser.add_argument("--no-paths", action="store_true", help="skip the average-path figure")
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    study = cfg["study"]
    events = in_period(read_events(study["events"], cfg["session"]["timezone"]), study["in_sample"])
    if events.empty:
        parser.error("no in-sample events: run src/events/shocks.py and src/events/build.py first")
    cutoffs = fit_cutoffs(events, study)
    events = assign_regimes(events, cutoffs)
    main_h = study.get("main_horizon_s", 30)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "cutoffs.yaml").write_text(yaml.safe_dump(cutoffs, sort_keys=False))
    events.to_csv(args.out_dir / "events.csv", index=False)
    table, cells = regime_table(events, main=main_h), cell_table(events, main_h)
    for name, t in (("regime_table", table), ("cells_2x2", cells)):
        t.to_csv(args.out_dir / f"{name}.csv")
        (args.out_dir / f"{name}.md").write_text(to_markdown(t, 2))

    plot_shocks_per_day(events, args.fig_dir / "shocks_per_day.png")
    plot_refill_distributions(events, cutoffs, args.fig_dir / "refill_distributions.png")
    plot_ofi_vs_return(events, cutoffs, args.fig_dir / "ofi_vs_return.png", main_h)
    if not args.no_paths:
        grids = load_grids_for(cfg, events["date"].unique())
        paths = average_paths(grids, events)
        paths.to_csv(args.out_dir / "average_paths.csv")
        plot_average_paths(paths, args.fig_dir / "average_path.png")

    print(f"cutoffs: {cutoffs}")
    print(table.round(2).to_string())
    print(cells.round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
