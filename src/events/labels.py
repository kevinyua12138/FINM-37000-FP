"""Event timeline and forward-return labels (issue #6).

Timeline for a shock detected at t0:
    features are observed in (t0, t0 + OBSERVATION]
    entry is the first quote at or after t0 + OBSERVATION + LATENCY
    y_h is the return from the entry quote to the first quote at or after entry + h
"""
import numpy as np
import pandas as pd

OBSERVATION = pd.Timedelta("3s")
LATENCY = pd.Timedelta("100ms")
HORIZONS = (5, 30, 120)
MAX_STALE = pd.Timedelta("1s")


def entry_time(t0):
    return t0 + OBSERVATION + LATENCY


def forward_return_labels(quotes, events, horizons=HORIZONS, max_stale=MAX_STALE):
    """Add entry_time and y_{h}s columns to a copy of events.

    quotes: sorted DatetimeIndex with columns mid and instrument_id.
    events: columns t0 (timestamp) and direction (+1 up-shock, -1 down-shock).
    y_{h}s = direction * (mid_exit / mid_entry - 1), so positive means the move continued.
    A label is NaN when a required quote is missing or stale (more than max_stale after
    its target time), or the exit quote is on a different instrument or trading day.
    """
    index, mid, inst = quotes.index, quotes["mid"].to_numpy(), quotes["instrument_id"].to_numpy()
    out = events.copy()
    out["entry_time"] = out["t0"].map(entry_time)
    labels = {h: np.full(len(out), np.nan) for h in horizons}

    for k, (entry_ts, direction) in enumerate(zip(out["entry_time"], out["direction"])):
        i = index.searchsorted(entry_ts)
        if i >= len(index) or index[i] - entry_ts > max_stale:
            continue
        for h in horizons:
            target = entry_ts + pd.Timedelta(seconds=h)
            j = index.searchsorted(target)
            if j >= len(index) or index[j] - target > max_stale:
                continue
            if inst[j] != inst[i] or index[j].date() != index[i].date():
                continue
            labels[h][k] = direction * (mid[j] / mid[i] - 1)

    for h in horizons:
        out[f"y_{h}s"] = labels[h]
    return out
