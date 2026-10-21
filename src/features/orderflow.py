"""Issue #8: Cont-style quote OFI and aggressor-signed trade imbalance."""
import numpy as np
import pandas as pd


def orderflow_updates(q):
    bp, ap, bs, a_s = q.bid_px_00, q.ask_px_00, q.bid_sz_00, q.ask_sz_00
    bp0, ap0, bs0, as0 = bp.shift(), ap.shift(), bs.shift(), a_s.shift()
    e = (np.where(bp >= bp0, bs, 0) - np.where(bp <= bp0, bs0, 0)
         - np.where(ap <= ap0, a_s, 0) + np.where(ap >= ap0, as0, 0))
    same = q.instrument_id.eq(q.instrument_id.shift())
    if 'valid' in q:
        same &= q.valid & q.valid.shift(fill_value=False)
    out = pd.DataFrame({'ofi_update': np.where(same, e, 0.0)}, index=q.index)
    if {'action', 'side', 'size'}.issubset(q.columns):
        trade = q.action.eq('T') & q.side.isin(['A', 'B'])
        size = q['size'].where(trade, 0).astype(float)
        out['signed_volume'] = np.where(q.side.eq('B'), size, -size)
        out['volume'] = size
    else:
        out['signed_volume'] = np.nan
        out['volume'] = np.nan
    return out


def window_flow(updates, direction):
    total = updates.ofi_update.abs().sum()
    ofi = direction * updates.ofi_update.sum() / total if total else 0.0
    volume = updates.volume.sum(min_count=1)
    # No trades is neutral; absent trade fields is missing, not invented volume.
    ti = direction * updates.signed_volume.sum() / volume if volume > 0 else (0.0 if volume == 0 else np.nan)
    return dict(ofi=ofi, ti=ti, trade_volume=volume)
