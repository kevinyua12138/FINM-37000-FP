"""Shock detector (issue #5).

A shock is a 10-second move in the ES mid price that is larger than the 99.5th
percentile of 10-second moves over the previous 5 trading days. After a shock,
detection pauses for a 120-second cooldown. Settings live under `shocks:` in
config.yaml.

Timing: the 1-second grid holds the last valid quote at or before each second, so a
shock stamped t0 only uses information available at t0. The first 5 days are used
only as threshold history. Moves that span a contract roll are ignored.

Input is Databento bbo-1s (one quote per second, enough to find shocks) or mbp-1.

Usage (from the repo root):
    python src/events/shocks.py                  # reads data/raw/ES_bbo-1s_*.dbn.zst
    python src/events/shocks.py --schema mbp-1   # same detector on mbp-1 files
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "America/Chicago"
WINDOW = pd.Timedelta("10s")
QUANTILE = 0.995
HISTORY_DAYS = 5
COOLDOWN = pd.Timedelta("120s")
EVENT_COLUMNS = ["t0", "date", "direction", "size", "threshold", "instrument_id"]


def mid_grid(quotes, freq="1s"):
    """Mid price and instrument_id on a regular grid for one trading day.

    quotes: DatetimeIndex with columns bid_px_00, ask_px_00, instrument_id.
    The value at second t is the last valid quote at or before t. Empty, locked
    and crossed quotes are dropped.
    """
    bid, ask = quotes["bid_px_00"], quotes["ask_px_00"]
    valid = quotes[(bid > 0) & (ask > bid)]
    grid = pd.DataFrame(
        {
            "mid": (valid["bid_px_00"] + valid["ask_px_00"]) / 2,
            "instrument_id": valid["instrument_id"],
        }
    )
    return grid.resample(freq, closed="right", label="right").last().ffill()


def moves(grid, window=WINDOW):
    """Signed mid change over `window`: mid(t) - mid(t - window).

    NaN when t - window is not on the grid or is on a different contract.
    """
    prev = grid.shift(freq=window).reindex(grid.index)
    change = grid["mid"] - prev["mid"]
    return change.where(grid["instrument_id"] == prev["instrument_id"])


def daily_thresholds(abs_moves_by_day, quantile=QUANTILE, history_days=HISTORY_DAYS):
    """Threshold for each day from the previous `history_days` days only.

    abs_moves_by_day: {date: Series of absolute moves}. A day without a full
    history gets NaN, so no shocks are detected on it.
    """
    days = sorted(abs_moves_by_day)
    out = {}
    for i, day in enumerate(days):
        past_days = days[max(0, i - history_days):i]
        past = [abs_moves_by_day[d].dropna() for d in past_days]
        past = [p for p in past if len(p)]
        if len(past_days) < history_days or not past:
            out[day] = np.nan
        else:
            out[day] = pd.concat(past).quantile(quantile)
    return pd.Series(out, name="threshold", dtype=float)


def detect_day(grid, threshold, window=WINDOW, cooldown=COOLDOWN):
    """Shocks in one day: seconds where |move| > threshold, at most one per cooldown."""
    if not np.isfinite(threshold):
        return pd.DataFrame(columns=EVENT_COLUMNS)
    change = moves(grid, window)
    rows, last = [], None
    for t in change.index[change.abs() > threshold]:
        if last is not None and t - last < cooldown:
            continue
        rows.append(
            {
                "t0": t,
                "date": t.date(),
                "direction": int(np.sign(change[t])),
                "size": abs(change[t]),
                "threshold": threshold,
                "instrument_id": int(grid.at[t, "instrument_id"]),
            }
        )
        last = t
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def detect_shocks(
    grids,
    window=WINDOW,
    quantile=QUANTILE,
    history_days=HISTORY_DAYS,
    cooldown=COOLDOWN,
):
    """Event table across days. grids: {date: mid_grid(...)} for each trading day."""
    abs_moves = {day: moves(grid, window).abs() for day, grid in grids.items()}
    thresholds = daily_thresholds(abs_moves, quantile, history_days)
    found = [detect_day(grids[d], thresholds[d], window, cooldown) for d in sorted(grids)]
    found = [f for f in found if len(f)]
    if not found:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return pd.concat(found, ignore_index=True)


def load_quotes(path, tz=TZ):
    """bid_px_00, ask_px_00 and instrument_id from a Databento DBN file."""
    import databento as db  # only needed for real files; the tests use synthetic quotes

    df = db.DBNStore.from_file(path).to_df(tz=tz)
    columns = ["bid_px_00", "ask_px_00", "instrument_id"]
    return df[columns] if len(df) else pd.DataFrame(columns=columns)


def load_grids(paths, tz=TZ):
    """{date: 1-second grid} from DBN files. Files with no quotes (holidays) are skipped."""
    grids = {}
    for path in paths:
        quotes = load_quotes(path, tz)
        if quotes.empty:
            continue
        for day, day_quotes in quotes.groupby(quotes.index.date):
            grids[day] = mid_grid(day_quotes)
    return grids


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="Detect ES shocks from downloaded quotes.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--schema", help="raw files to read, e.g. bbo-1s or mbp-1")
    parser.add_argument("--output", type=Path, help="CSV path (default: shocks.output)")
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    s = cfg["shocks"]
    schema = args.schema or s["schema"]
    raw_dir = Path(cfg["data"]["raw_dir"])
    paths = sorted(raw_dir.glob(f"ES_{schema}_*.dbn.zst"))
    if not paths:
        parser.error(f"no ES_{schema}_*.dbn.zst files in {raw_dir}")

    grids = load_grids(paths, cfg["session"]["timezone"])
    events = detect_shocks(
        grids,
        window=pd.Timedelta(seconds=s["window_s"]),
        quantile=s["quantile"],
        history_days=s["history_days"],
        cooldown=pd.Timedelta(seconds=s["cooldown_s"]),
    )
    output = args.output or Path(s["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(output, index=False)
    tested = max(len(grids) - s["history_days"], 0)
    print(
        f"{len(events)} shocks on {tested} days "
        f"({len(grids)} days loaded, the first {s['history_days']} are history only) -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
