"""One-contract market orders, one open position, observed bid/ask plus explicit fees."""
import numpy as np
import pandas as pd


def assign_regimes(events, refill_cutoff=0.5, ofi_cutoff=0.0):
    out = events.copy()
    valid = np.isfinite(out.refill_ratio) & np.isfinite(out.ofi)
    fast = out.refill_ratio >= refill_cutoff
    out['regime'] = np.select(
        [valid & ~fast & (out.ofi > ofi_cutoff), valid & fast & (out.ofi < -ofi_cutoff),
         valid & fast & (out.ofi > ofi_cutoff), valid & ~fast & (out.ofi < -ofi_cutoff)],
        ['slow / same', 'fast / reversing', 'fast / same', 'slow / reversing'], default='neutral / missing')
    out['signal'] = np.select([out.regime.eq('slow / same'), out.regime.eq('fast / reversing')], [1, -1], default=0)
    return out


def simulate(events, cfg, *, horizon=30, fee=None, slip_ticks=0, latency_suffix='', signal=None):
    """signal +1 follows the shock, -1 fades it; slippage is per side."""
    r = cfg['research']
    fee = r['fee_per_side_usd'] if fee is None else fee
    ev = events.copy()
    if signal is not None:
        ev['signal'] = signal
    suffix = latency_suffix
    cols = [f'entry_time{suffix}', f'entry_bid{suffix}', f'entry_ask{suffix}',
            f'exit_time_{horizon}{suffix}', f'exit_bid_{horizon}{suffix}', f'exit_ask_{horizon}{suffix}']
    ev = ev.reindex(columns=list(dict.fromkeys([*ev.columns, *cols])))
    ev = ev[ev.signal.ne(0)].dropna(subset=cols).sort_values(cols[0])
    trades, available = [], None
    for x in ev.to_dict('records'):
        entry_ts, exit_ts = x[cols[0]], x[cols[3]]
        if available is not None and entry_ts <= available:
            continue
        side = int(x['signal'] * x['direction'])
        # Check displayed size when available; the simulation is for one contract.
        entry_size = x.get(('entry_ask_size' if side == 1 else 'entry_bid_size') + suffix, np.inf)
        exit_size = x.get((f'exit_bid_size_{horizon}' if side == 1 else f'exit_ask_size_{horizon}') + suffix, np.inf)
        if min(entry_size, exit_size) < r['contracts']:
            continue
        entry = x[cols[2]] if side == 1 else x[cols[1]]
        exit_price = x[cols[4]] if side == 1 else x[cols[5]]
        mid_change = side * ((x[cols[4]] + x[cols[5]]) - (x[cols[1]] + x[cols[2]])) / 2
        gross = side * (exit_price - entry) * r['dollars_per_point'] * r['contracts']
        slippage = 2 * slip_ticks * r['tick_size'] * r['dollars_per_point'] * r['contracts']
        fees = 2 * fee * r['contracts']
        trades.append(dict(t0=x['t0'], date=x['date'], regime=x.get('regime', 'model'),
                           side=side, entry_time=entry_ts, exit_time=exit_ts, entry_price=entry,
                           exit_price=exit_price, mid_pnl=mid_change * r['dollars_per_point'] * r['contracts'],
                           gross_pnl=gross, fees=fees, slippage=slippage, net_pnl=gross-fees-slippage))
        available = exit_ts
    return pd.DataFrame(trades, columns=['t0','date','regime','side','entry_time','exit_time','entry_price',
                                        'exit_price','mid_pnl','gross_pnl','fees','slippage','net_pnl'])


def metrics(trades, days):
    daily = trades.groupby('date').net_pnl.sum().reindex(days, fill_value=0)
    n = len(trades)
    pnl = trades.net_pnl.to_numpy(float)
    equity = np.r_[0., pnl.cumsum()]
    sd = daily.std(ddof=1)
    return dict(trades=n, days=len(days), gross_pnl_usd=trades.gross_pnl.sum(),
                net_pnl_usd=pnl.sum(), mean_net_usd=pnl.mean() if n else np.nan,
                win_rate=float((pnl > 0).mean()) if n else np.nan,
                max_drawdown_usd=float((np.maximum.accumulate(equity)-equity).max()),
                daily_pnl_sharpe=float(daily.mean()/sd*np.sqrt(252)) if sd > 0 else np.nan,
                breakeven_roundtrip_fee_usd=float(trades.gross_pnl.mean()) if n else np.nan)
