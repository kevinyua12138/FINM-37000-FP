"""Event table: shocks (#5) + forward-return labels (#6) + book, replenishment and order-flow
features (#7, #9, #8) + entry/exit quotes for the backtest (#12) + calendar flags (#4).

Reads the shock list, then one mbp-1 day at a time (only one day of quotes is ever in
memory), and writes one row per shock. Only days that have shocks need mbp-1 files.

Usage (from the repo root, after `python src/events/shocks.py`):
    python src/events/build.py --list-missing > get_mbp1.sh   # download commands for missing days
    python src/events/build.py                  # -> data/processed/events.csv

Columns added to each shock, all signed by the shock direction where it matters:
    entry_time, y_5s, y_30s, y_120s            labels (#6), positive = the move continued
    refill_ratio, half_life_s                  depth left at the old price X (#9, prototype)
    refill_best, half_life_best_s              depth at the current best price (#9, Meeting 1)
    ofi_contracts, ofi, ti, trade_volume       order flow over (t0, t0 + 3s] (#8)
    imb_1, micro_gap_ticks                     top-of-book imbalance and microprice gap at t0 (#7)
    entry_bid, entry_ask, exit_bid_{h}s, ...   quotes the backtest trades at (#12)
    is_fomc_day, ..., fomc_window, open_window, stress_window   flags for robustness (#14)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from events.labels import HORIZONS, MAX_STALE, entry_time, forward_return_labels  # noqa: E402
from features.imbalance import book_features  # noqa: E402
from features.orderflow import orderflow_features  # noqa: E402
from features.replenishment import best_quote_refill, replenishment_features  # noqa: E402

TZ = "America/Chicago"
TICK = 0.25
QUOTE_COLUMNS = ["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "instrument_id"]
TRADE_COLUMNS = ["action", "side", "size"]
FLAG_COLUMNS = ["is_fomc_day", "is_cpi_day", "is_nfp_day", "is_macro_day", "is_roll_day", "is_half_day"]


def valid_quotes(quotes):
    """Rows with a positive bid and an ask above it, plus a mid column."""
    bid, ask = quotes["bid_px_00"], quotes["ask_px_00"]
    q = quotes[(bid > 0) & (ask > bid)]
    return q.assign(mid=(q["bid_px_00"] + q["ask_px_00"]) / 2)


def _first_at_or_after(quotes, ts, max_stale=MAX_STALE):
    i = quotes.index.searchsorted(ts)
    if i >= len(quotes) or quotes.index[i] - ts > max_stale:
        return None
    return quotes.iloc[i]


def add_trade_quotes(quotes, events, horizons=HORIZONS):
    """Bid and ask at entry (first quote at or after t0 + 3.1s) and at each exit.

    Same conventions as the labels: an exit is NaN if its quote is stale, on another
    contract or on another day.
    """
    out = events.copy()
    cols = {"entry_bid": [], "entry_ask": []}
    for h in horizons:
        cols[f"exit_bid_{h}s"], cols[f"exit_ask_{h}s"] = [], []
    for t0 in out["t0"]:
        start = entry_time(t0)
        entry = _first_at_or_after(quotes, start)
        cols["entry_bid"].append(np.nan if entry is None else entry["bid_px_00"])
        cols["entry_ask"].append(np.nan if entry is None else entry["ask_px_00"])
        for h in horizons:
            exit_ = None if entry is None else _first_at_or_after(quotes, start + pd.Timedelta(seconds=h))
            same = (exit_ is not None and exit_["instrument_id"] == entry["instrument_id"]
                    and exit_.name.date() == entry.name.date())
            cols[f"exit_bid_{h}s"].append(exit_["bid_px_00"] if same else np.nan)
            cols[f"exit_ask_{h}s"].append(exit_["ask_px_00"] if same else np.nan)
    for name, values in cols.items():
        out[name] = values
    return out


def book_snapshot(quotes, events):
    """Top-of-book imbalance I_1 and microprice gap G at t0 (#7), signed by direction."""
    out = events.copy()
    pos = quotes.index.searchsorted(pd.DatetimeIndex(out["t0"]), side="right") - 1
    known = pos >= 0
    imb, gap = np.full(len(out), np.nan), np.full(len(out), np.nan)
    if known.any():
        rows = quotes.iloc[pos[known]].reset_index(drop=True)
        feats = book_features(rows, levels=1, tick_size=TICK)
        direction = out.loc[known, "direction"].to_numpy(float)
        imb[known] = direction * feats["I_1"].to_numpy()
        gap[known] = direction * feats["G"].to_numpy() / TICK
    out["imb_1"], out["micro_gap_ticks"] = imb, gap
    return out


def add_flags(events, stress_window=None):
    """Calendar flags (#4) plus intraday windows used by the robustness table (#14)."""
    from data.calendar import flags_for_day

    out = events.copy()
    flags = []
    for day in out["date"]:
        try:
            flags.append(flags_for_day(str(day)))
        except ValueError:  # the calendar only covers 2025
            flags.append({c: False for c in FLAG_COLUMNS})
    for c in FLAG_COLUMNS:
        out[c] = [bool(f[c]) for f in flags]
    local = pd.DatetimeIndex(out["t0"]).tz_convert(TZ)
    minutes = (local.hour * 60 + local.minute + local.second / 60).to_numpy()
    out["minutes_from_open"] = minutes - (8 * 60 + 30)
    out["open_window"] = out["minutes_from_open"] < 5
    out["fomc_window"] = out["is_fomc_day"] & (minutes >= 13 * 60) & (minutes < 15 * 60)
    if stress_window:
        start, end = (str(d) for d in stress_window)
        out["stress_window"] = (out["date"].astype(str) >= start) & (out["date"].astype(str) <= end)
    else:
        out["stress_window"] = False
    return out


def build_day(raw_quotes, day_events, horizons=HORIZONS):
    """All per-shock columns for one day of mbp-1 quotes."""
    quotes = valid_quotes(raw_quotes)
    out = forward_return_labels(quotes, day_events, horizons)
    out = replenishment_features(quotes, out)
    out = best_quote_refill(quotes, out)
    out = orderflow_features(raw_quotes, out)  # keeps trade rows the book filter would drop
    out = add_trade_quotes(quotes, out, horizons)
    return book_snapshot(quotes, out)


def build_events(shocks, load_day, stress_window=None, horizons=HORIZONS):
    """Event table for every shock whose day of quotes `load_day(date)` can provide."""
    parts, missing = [], []
    for day, day_events in shocks.groupby("date", sort=True):
        raw = load_day(day)
        if raw is None or raw.empty:
            missing.append(day)
            continue
        parts.append(build_day(raw.sort_index(), day_events.reset_index(drop=True), horizons))
    if missing:
        print(f"skipped {len(missing)} shock days without mbp-1 quotes: {', '.join(map(str, missing))}")
    if not parts:
        return pd.DataFrame()
    events = pd.concat(parts, ignore_index=True)
    events["size_ticks"] = events["size"] / TICK
    return add_flags(events, stress_window)


def read_shocks(path, tz=TZ):
    shocks = pd.read_csv(path)
    shocks["t0"] = pd.to_datetime(shocks["t0"], utc=True).dt.tz_convert(tz)
    shocks["date"] = shocks["date"].astype(str)
    return shocks


def mbp1_path(raw_dir, day):
    return Path(raw_dir) / f"ES_mbp-1_{day}.dbn.zst"


def load_mbp1(raw_dir, day, tz=TZ):
    """One day of mbp-1 quotes and trades, or None if the file is not downloaded."""
    path = mbp1_path(raw_dir, day)
    if not path.exists():
        return None
    import databento as db  # only needed for real files; tests use synthetic quotes

    df = db.DBNStore.from_file(path).to_df(tz=tz)
    return df[[c for c in QUOTE_COLUMNS + TRADE_COLUMNS if c in df.columns]]


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="Build the per-shock event table.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--shocks", type=Path, help="default: shocks.output in config.yaml")
    parser.add_argument("--output", type=Path, help="default: study.events in config.yaml")
    parser.add_argument("--list-missing", action="store_true", help="print download commands and stop")
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    tz, raw_dir = cfg["session"]["timezone"], cfg["data"]["raw_dir"]
    shocks = read_shocks(args.shocks or Path(cfg["shocks"]["output"]), tz)
    days = sorted(shocks["date"].unique())
    if args.list_missing:
        missing = [d for d in days if not mbp1_path(raw_dir, d).exists()]
        print(f"{len(missing)} of {len(days)} shock days need mbp-1", file=sys.stderr)
        for d in missing:
            print(f"python src/data/download.py {d} --schema mbp-1")
        return 0

    events = build_events(shocks, lambda d: load_mbp1(raw_dir, d, tz),
                          cfg.get("study", {}).get("stress_window"))
    output = args.output or Path(cfg["study"]["events"])
    output.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(output, index=False)
    print(f"{len(events)} events from {len(days)} shock days -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
