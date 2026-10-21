"""Attach three-second features and executable quotes to each detected shock."""
import numpy as np
import pandas as pd
from features.imbalance import book_features
from features.orderflow import orderflow_updates, window_flow
from features.replenishment import replenishment_features


def quote_at(q, target, instrument, *, after, stale):
    pos = q.index.searchsorted(target, side='left' if after else 'right')
    if not after:
        pos -= 1
    if pos < 0 or pos >= len(q):
        return None
    row, ts = q.iloc[pos], q.index[pos]
    if (not row.valid or row.instrument_id != instrument or ts.date() != target.date()
            or abs(ts - target).total_seconds() > stale):
        return None
    return pos


def enrich_events(q, events, cfg):
    """Raw receive timestamps preserve the 100ms latency; process one day at a time."""
    r = cfg['research']
    stale, obs = r['max_stale_s'], pd.Timedelta(seconds=r['observation_s'])
    updates = orderflow_updates(q)
    rows = []
    for event in events.to_dict('records'):
        t0, inst, direction = event['t0'], event['instrument_id'], event['direction']
        pre = quote_at(q, t0 - pd.Timedelta(seconds=cfg['shocks']['window_s']), inst, after=False, stale=stale)
        end = quote_at(q, t0 + obs, inst, after=False, stale=stale)
        start = quote_at(q, t0, inst, after=False, stale=stale)
        if pre is None or end is None or start is None:
            continue
        window = q.iloc[pre:end + 1]
        if (not window.valid.all() or window.instrument_id.nunique() != 1
                or window.index.to_series().diff().max() > pd.Timedelta(seconds=stale)):
            continue
        features = replenishment_features(window, pd.DataFrame([event]),
                      window=pd.Timedelta(seconds=cfg['shocks']['window_s']), obs=obs).iloc[0]
        event.update(refill_ratio=features.refill_ratio, half_life_s=features.half_life_s)
        lo, hi = q.index.searchsorted(t0, side='right'), q.index.searchsorted(t0 + obs, side='right')
        event.update(window_flow(updates.iloc[lo:hi], direction))
        snapshot = book_features(q.iloc[[end]], levels=1).iloc[0]
        event.update(I_1=direction * snapshot.I_1, G=direction * snapshot.G)
        event['size_ticks'] = event['size'] / r['tick_size']
        event['threshold_ticks'] = event['threshold'] / r['tick_size']
        for latency in [r['latency_ms'], 500]:
            suffix = '' if latency == r['latency_ms'] else '_lag500'
            target = t0 + obs + pd.Timedelta(milliseconds=latency)
            i = quote_at(q, target, inst, after=True, stale=stale)
            if i is None:
                continue
            event['entry_time' + suffix] = q.index[i]
            event['entry_bid_size' + suffix], event['entry_ask_size' + suffix] = q.iloc[i][['bid_sz_00', 'ask_sz_00']]
            event['entry_bid' + suffix], event['entry_ask' + suffix] = q.iloc[i][['bid_px_00', 'ask_px_00']]
            # Horizons start at the ACTUAL executable entry quote.
            for h in [5, 30, 120]:
                j = quote_at(q, q.index[i] + pd.Timedelta(seconds=h), inst, after=True, stale=stale)
                if j is None:
                    continue
                path = q.iloc[i:j + 1]
                if (not path.valid.all() or path.instrument_id.nunique() != 1
                        or path.index.to_series().diff().max() > pd.Timedelta(seconds=stale)):
                    continue
                event[f'exit_time_{h}' + suffix] = q.index[j]
                event[f'exit_bid_size_{h}' + suffix], event[f'exit_ask_size_{h}' + suffix] = q.iloc[j][['bid_sz_00', 'ask_sz_00']]
                event[f'exit_bid_{h}' + suffix], event[f'exit_ask_{h}' + suffix] = q.iloc[j][['bid_px_00', 'ask_px_00']]
                event[f'y_{h}s' + suffix] = direction * (q.iloc[j]['mid'] / q.iloc[i]['mid'] - 1)
        # A compact path for the in-sample event-study figure (from actual entry).
        if 'entry_time' in event and 'y_120s' in event:
            for h in range(0, 121, 5):
                j = quote_at(q, event['entry_time'] + pd.Timedelta(seconds=h), inst, after=True, stale=stale)
                if j is not None:
                    i = quote_at(q, event['entry_time'], inst, after=True, stale=stale)
                    event[f'path_{h}'] = direction * (q.iloc[j]['mid'] - q.iloc[i]['mid']) / r['tick_size']
        rows.append(event)
    return pd.DataFrame(rows)
