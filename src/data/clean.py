"""Clean one full quote session and build an as-of (never forward-looking) grid."""
import numpy as np
import pandas as pd
from features.imbalance import book_features

TZ = 'America/Chicago'


def clean_quotes(raw):
    if not isinstance(raw.index, pd.DatetimeIndex) or raw.index.tz is None:
        raise ValueError('Quotes require a timezone-aware DatetimeIndex.')
    q = raw.copy()
    q.index = q.index.tz_convert(TZ)
    q = q.sort_index(kind='stable').between_time('08:30', '15:00', inclusive='left')
    # Keep invalid rows as barriers: stale pre-gap quotes must not bridge a bad book.
    q['valid'] = book_features(q, levels=1)['I_1'].notna().to_numpy()
    q['mid'] = ((q.bid_px_00 + q.ask_px_00) / 2).where(q.valid)
    return q


def second_grid(q, max_stale_s=1):
    """One session, with last quote AT or BEFORE each exact second."""
    if q.empty:
        return pd.DataFrame(columns=['mid', 'instrument_id'])
    last = q.loc[~q.index.duplicated(keep='last')]
    times = pd.date_range(q.index[0].ceil('s'), q.index[-1].floor('s'), freq='1s')
    positions = last.index.get_indexer(times, method='ffill')
    grid = last.iloc[positions][['mid', 'instrument_id']].copy()
    age = (times - last.index[positions]).total_seconds()
    grid.index = times
    grid.loc[age > max_stale_s, 'mid'] = np.nan
    # Never compute ten-second returns across invalid/stale seconds or contract switches.
    grid['segment'] = (grid.mid.isna() | grid.instrument_id.ne(grid.instrument_id.shift())).cumsum()
    return grid


def load_day(path):
    import databento as db
    raw = db.DBNStore.from_file(path).to_df(tz=TZ)
    columns = [c for c in raw if c.startswith(('bid_px_', 'ask_px_', 'bid_sz_', 'ask_sz_'))]
    columns += [c for c in ['instrument_id', 'action', 'side', 'size'] if c in raw]
    return clean_quotes(raw[columns])
