"""mbp-10 depth features (issue #16): I_5, I_10 and the 10-level refill ratio.

Run on a small depth sample (config.yaml `depth:`), because mbp-10 files are much larger
than mbp-1. For each shock, signed by the shock direction where it matters:
    imb_5, imb_10         I_N from #7 over the first 5 / 10 levels at t0, times direction
                          (+ = more resting size behind the move, e.g. bid depth after an up-shock)
    refill_depth5/10      size summed over the first 5 / 10 levels of the eaten side at
                          t0 + 3s, divided by the same sum at t0 - 10s
    half_life_depth10_s   seconds from t0 until the 10-level sum is back to half its
                          pre-shock size, NaN if not within 3s
This sees liquidity that refills just behind the new best price, which mbp-1 cannot. The old
price X itself has left the eaten side after a 9+ tick shock (an up-shock puts the old ask
below the new bid), so a same-price refill measure is not recoverable even with depth data.

Usage (from the repo root, after build.py and the mbp-10 downloads):
    python src/features/depth.py   # -> data/processed/events_depth.csv, results/depth/, figures/issue16/
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from features.imbalance import book_features  # noqa: E402

WINDOW = pd.Timedelta("10s")
OBSERVATION = pd.Timedelta("3s")
TICK = 0.25


def _valid(quotes):
    bid, ask = quotes["bid_px_00"], quotes["ask_px_00"]
    return quotes[(bid > 0) & (ask > bid)]


def side_depth(book, side, levels):
    """Size summed over the first `levels` levels of one side; NaN if a level's size is missing."""
    cols = [f"{side}_sz_{i:02d}" for i in range(levels)]
    if not set(cols) <= set(book.columns):
        return pd.Series(np.nan, index=book.index)
    return book[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=levels)


def depth_features(quotes, events, window=WINDOW, obs=OBSERVATION, levels=(5, 10)):
    """Add imb_N, refill_depthN (for each N in levels) and half_life_depth{max}_s to events."""
    out = events.copy()
    book = _valid(quotes)
    idx, n = book.index, len(out)
    at_t0 = idx.searchsorted(pd.DatetimeIndex(out["t0"]), side="right") - 1
    direction = out["direction"].to_numpy(float)
    known = at_t0 >= 0
    deepest = max(levels)
    for lv in levels:
        imb = np.full(n, np.nan)
        if known.any():
            feats = book_features(book.iloc[at_t0[known]].reset_index(drop=True), levels=lv, tick_size=TICK)
            imb[known] = direction[known] * feats["I_N"].to_numpy()
        out[f"imb_{lv}"] = imb
    sums = {(side, lv): side_depth(book, side, lv).to_numpy(float) for side in ("bid", "ask") for lv in levels}
    ratios = {lv: np.full(n, np.nan) for lv in levels}
    half_life = np.full(n, np.nan)
    for k, (t0, d) in enumerate(zip(out["t0"], direction)):
        pre = idx.searchsorted(t0 - window, side="right") - 1
        if pre < 0 or at_t0[k] < 0:
            continue
        end = idx.searchsorted(t0 + obs, side="right")
        rows = np.r_[at_t0[k], np.arange(at_t0[k] + 1, end)]  # state at t0, then updates in (t0, t0 + obs]
        side = "ask" if d > 0 else "bid"
        for lv in levels:
            before = sums[(side, lv)][pre]
            if before > 0:
                path = sums[(side, lv)][rows]
                ratios[lv][k] = path[-1] / before
                if lv == deepest:
                    hit = np.flatnonzero(path >= 0.5 * before)
                    if len(hit):
                        half_life[k] = (idx[rows[hit[0]]] - t0).total_seconds()
    for lv in levels:
        out[f"refill_depth{lv}"] = ratios[lv]
    out[f"half_life_depth{deepest}_s"] = half_life
    return out


def load_mbp10(raw_dir, day, tz="America/Chicago"):
    path = Path(raw_dir) / f"ES_mbp-10_{day}.dbn.zst"
    if not path.exists():
        return None
    import databento as db  # only needed for real files; tests use synthetic books

    df = db.DBNStore.from_file(path).to_df(tz=tz)
    keep = [c for c in df.columns if c[:7] in ("bid_px_", "ask_px_", "bid_sz_", "ask_sz_")]
    return df[keep]


def depth_summary(events, horizon=30):
    """How the 10-level refill compares with refill_best on the same shocks."""
    from analysis.stats import BP, clustered_mean

    rows = {}
    for col in ("refill_best", "refill_depth5", "refill_depth10"):
        data = events.dropna(subset=[col, f"y_{horizon}s"])
        if data.empty:
            continue
        slow = data[col] < data[col].median()
        y = data[f"y_{horizon}s"].to_numpy(float) * BP
        lo = clustered_mean(y[slow.to_numpy()], data.loc[slow, "date"].to_numpy())
        hi = clustered_mean(y[~slow.to_numpy()], data.loc[~slow, "date"].to_numpy())
        rows[col] = {"shocks": len(data), f"mean_bp_{horizon}s_below_median": lo["mean"],
                     "t_below": lo["t"], f"mean_bp_{horizon}s_above_median": hi["mean"], "t_above": hi["t"],
                     "spearman_with_refill_best": data[col].corr(data["refill_best"], method="spearman")}
    return pd.DataFrame(rows).T


def plot_refill_comparison(events, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = events.dropna(subset=["refill_best", "refill_depth10"])
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.scatter(data["refill_best"], data["refill_depth10"], s=14, color="#2a6fdb", alpha=0.6)
    ax.set_xlabel("refill_best (best quote, mbp-1)")
    ax.set_ylabel("refill_depth10 (10 levels, mbp-10)")
    ax.set_title("Refill measured at the best quote vs 10 levels deep", loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main(argv=None):
    import yaml

    from analysis.stats import to_markdown
    from events.study import read_events

    parser = argparse.ArgumentParser(description="mbp-10 depth features on the depth sample.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    days = [str(d) for d in cfg["depth"]["days"]]
    events = read_events(cfg["study"]["events"], cfg["session"]["timezone"])
    parts, missing = [], []
    for day in days:
        day_events = events[events["date"] == day]
        if day_events.empty:
            continue
        quotes = load_mbp10(cfg["data"]["raw_dir"], day, cfg["session"]["timezone"])
        if quotes is None:
            missing.append(day)
            continue
        parts.append(depth_features(quotes.sort_index(), day_events.reset_index(drop=True)))
    if missing:
        print("download first:\n" + "\n".join(f"python src/data/download.py {d} --schema mbp-10" for d in missing))
    if not parts:
        parser.error("no depth-sample shocks with mbp-10 files")
    depth = pd.concat(parts, ignore_index=True)
    output = Path(cfg["depth"]["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    depth.to_csv(output, index=False)
    summary = depth_summary(depth)
    Path("results/depth").mkdir(parents=True, exist_ok=True)
    summary.to_csv("results/depth/summary.csv")
    Path("results/depth/summary.md").write_text(to_markdown(summary, 2))
    Path("figures/issue16").mkdir(parents=True, exist_ok=True)
    plot_refill_comparison(depth, "figures/issue16/refill_best_vs_depth10.png")
    print(f"{len(depth)} depth-sample shocks on {depth['date'].nunique()} days -> {output}")
    print(summary.round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
