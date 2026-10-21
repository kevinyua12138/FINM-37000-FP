"""Optional issue #16: I_5/I_10 and refill across the ten PRE-SHOCK price levels.

Levels beyond the visible ladder are unknown, not zero. Prices better than the
current best on that side are empty. This function requires real mbp-10 inputs.
"""
import numpy as np
import pandas as pd
from features.imbalance import book_features


def depth_features(quotes, events):
    rows=[]
    for ev in events.itertuples():
        pre=quotes.index.searchsorted(ev.t0-pd.Timedelta('10s'),side='right')-1
        end=quotes.index.searchsorted(ev.t0+pd.Timedelta('3s'),side='right')-1
        row=dict(t0=ev.t0,I_5=np.nan,I_10=np.nan,RR_10=np.nan)
        if pre<0 or end<0:
            rows.append(row); continue
        a,b=quotes.iloc[pre],quotes.iloc[end]
        if (ev.t0-pd.Timedelta('10s')-quotes.index[pre]>pd.Timedelta('1s')
                or ev.t0+pd.Timedelta('3s')-quotes.index[end]>pd.Timedelta('1s')
                or a.instrument_id!=b.instrument_id or quotes.index[pre].date()!=quotes.index[end].date()):
            rows.append(row); continue
        f5=book_features(quotes.iloc[[end]],levels=5).iloc[0]
        f10=book_features(quotes.iloc[[end]],levels=10).iloc[0]
        row.update(I_5=ev.direction*f5.I_N,I_10=ev.direction*f10.I_N)
        if np.isnan(f10.I_N) or np.isnan(book_features(quotes.iloc[[pre]],levels=10).I_N.iloc[0]):
            rows.append(row);continue
        side='ask' if ev.direction>0 else 'bid'
        px=[f'{side}_px_{i:02d}' for i in range(10)]
        sz=[f'{side}_sz_{i:02d}' for i in range(10)]
        old_prices,new_prices=a[px].to_numpy(float),b[px].to_numpy(float)
        quantities=b[sz].to_numpy(float); recovered=[]
        for price in old_prices:
            match=np.flatnonzero(new_prices==price)
            worse=price>new_prices[-1] if side=='ask' else price<new_prices[-1]
            recovered.append(quantities[match[0]] if len(match) else (np.nan if worse else 0.))
        denominator=a[sz].sum()
        row['RR_10']=np.sum(recovered)/denominator if denominator>0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
