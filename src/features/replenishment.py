"""Liquidity replenishment features (issue #9): refill ratio RR and refill half-life.

Definitions from the #9 discussion:
    The measured side is the side that was eaten: the ask after an up-shock, the bid after a down-shock.
    X is that side's best price at t0 - 10s (the start of the shock window) and D_pre its size.
    D(t) is the size resting at X during the observation window (t0, t0 + 3s]. On mbp-1 that is the
    best quote's size while the best price is X, 0 once the best price has moved past X (nothing is
    left at X), and D_pre if the price came back through X (refilled at a better price), as in the
    #6 prototype.
    RR = D(t0 + 3s) / D_pre. Half-life is the seconds from t0 until RR first reaches 0.5, NaN if never.
"""
import numpy as np
import pandas as pd

WINDOW = pd.Timedelta("10s")
OBSERVATION = pd.Timedelta("3s")


def _eaten(frame, direction):
    side = "ask" if direction > 0 else "bid"
    return frame[f"{side}_px_00"].to_numpy(float), frame[f"{side}_sz_00"].to_numpy(float)


def _last_at(quotes, ts):
    i = quotes.index.searchsorted(ts, side="right") - 1
    return None if i < 0 else quotes.iloc[[i]]


def depth_at_x(quotes, t0, direction, window=WINDOW, obs=OBSERVATION):
    """D(t) at X from t0 through t0 + obs, and D_pre. Returns (Series, d_pre)."""
    pre, start = _last_at(quotes, t0 - window), _last_at(quotes, t0)
    if pre is None:
        return pd.Series(dtype=float), np.nan
    x, d_pre = (v[0] for v in _eaten(pre, direction))
    after = quotes.iloc[quotes.index.searchsorted(t0, side="right"):
                        quotes.index.searchsorted(t0 + obs, side="right")]
    frame = pd.concat([start.set_axis(pd.DatetimeIndex([t0])), after])
    px, sz = _eaten(frame, direction)
    past = px > x if direction > 0 else px < x
    depth = np.where(px == x, sz, np.where(past, 0.0, d_pre))
    return pd.Series(depth, index=frame.index), d_pre


def replenishment_features(quotes, events, window=WINDOW, obs=OBSERVATION):
    """Add refill_ratio and half_life_s columns to a copy of events.

    quotes: sorted DatetimeIndex with bid_px_00, ask_px_00, bid_sz_00, ask_sz_00.
    events: columns t0 (timestamp) and direction (+1 up-shock, -1 down-shock).
    Both are NaN when there is no quote at or before t0 - window or D_pre is 0.
    """
    out = events.copy()
    ratio, half_life = np.full(len(out), np.nan), np.full(len(out), np.nan)
    for k, (t0, direction) in enumerate(zip(out["t0"], out["direction"])):
        depth, d_pre = depth_at_x(quotes, t0, direction, window, obs)
        if depth.empty or not d_pre > 0:
            continue
        ratio[k] = depth.iloc[-1] / d_pre
        back = depth[depth >= 0.5 * d_pre]
        if len(back):
            half_life[k] = (back.index[0] - t0).total_seconds()
    out["refill_ratio"], out["half_life_s"] = ratio, half_life
    return out
