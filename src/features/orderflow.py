"""Order-flow features (issue #8): order-flow imbalance (OFI) and trade imbalance (TI).

Both are measured over the observation window (t0, t0 + 3s] and signed by the shock
direction, so a positive value means pressure in the same direction as the shock.

OFI follows Cont, Kukanov and Stoikov (2014). Between consecutive top-of-book states,
    e = 1{b >= b_prev} B - 1{b <= b_prev} B_prev - 1{a <= a_prev} A + 1{a >= a_prev} A_prev
where b, a are the best bid and ask prices and B, A their sizes. The window starts from the
last valid quote at or before t0, so the first increment is that state -> the first update
after t0.
    ofi_contracts = direction * sum(e)              contracts
    ofi           = direction * sum(e) / sum(|e|)   in [-1, 1]; 0 when the book did not change

TI uses mbp-1 trade records (action "T"). Databento puts the aggressor in `side`:
"B" buyer-initiated, "A" seller-initiated, "N" unknown (ignored).
    ti = direction * (buy volume - sell volume) / (buy volume + sell volume)   0 if no trades
TI and trade_volume are NaN when the quotes have no trade records (e.g. bbo-1s).
"""
import numpy as np
import pandas as pd

OBSERVATION = pd.Timedelta("3s")
BOOK = ["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]
TRADE_COLUMNS = {"action", "side", "size"}


def valid_book(quotes):
    """Top-of-book rows with a positive bid, an ask above the bid and known sizes."""
    bid, ask = quotes["bid_px_00"], quotes["ask_px_00"]
    ok = (bid > 0) & (ask > bid) & quotes["bid_sz_00"].notna() & quotes["ask_sz_00"].notna()
    return quotes.loc[ok, BOOK]


def ofi_increments(book):
    """Cont-Kukanov-Stoikov increment e for each row after the first (contracts)."""
    b, a, bs, as_ = (book[c].to_numpy(float) for c in BOOK)
    e = (np.where(b[1:] >= b[:-1], bs[1:], 0.0) - np.where(b[1:] <= b[:-1], bs[:-1], 0.0)
         - np.where(a[1:] <= a[:-1], as_[1:], 0.0) + np.where(a[1:] >= a[:-1], as_[:-1], 0.0))
    return pd.Series(e, index=book.index[1:])


def _trades(quotes):
    if not TRADE_COLUMNS <= set(quotes.columns):
        return None
    trades = quotes.loc[quotes["action"] == "T", ["side", "size"]]
    # Databento stores sizes as unsigned integers, so buy - sell would wrap around below zero
    return trades.assign(size=pd.to_numeric(trades["size"], errors="coerce").astype(float).fillna(0.0))


def orderflow_features(quotes, events, obs=OBSERVATION):
    """Add ofi_contracts, ofi, ti and trade_volume columns to a copy of events.

    quotes: sorted DatetimeIndex with bid/ask prices and sizes (mbp-1; trades optional).
    events: columns t0 (timestamp) and direction (+1 up-shock, -1 down-shock).
    All four are NaN when there is no valid quote at or before t0.
    """
    out = events.copy()
    book = valid_book(quotes)
    trades = _trades(quotes)
    n = len(out)
    ofi_c, ofi_n, ti, volume = (np.full(n, np.nan) for _ in range(4))
    for k, (t0, direction) in enumerate(zip(out["t0"], out["direction"].astype(float))):
        i = book.index.searchsorted(t0, side="right") - 1
        if i < 0:
            continue
        j = book.index.searchsorted(t0 + obs, side="right")
        e = ofi_increments(book.iloc[i:j])
        scale = e.abs().sum()
        ofi_c[k] = direction * e.sum()
        ofi_n[k] = direction * e.sum() / scale if scale > 0 else 0.0
        if trades is None:
            continue
        lo = trades.index.searchsorted(t0, side="right")
        hi = trades.index.searchsorted(t0 + obs, side="right")
        window = trades.iloc[lo:hi]
        buy = window.loc[window["side"] == "B", "size"].sum()
        sell = window.loc[window["side"] == "A", "size"].sum()
        volume[k] = buy + sell
        ti[k] = direction * (buy - sell) / (buy + sell) if buy + sell > 0 else 0.0
    out["ofi_contracts"], out["ofi"], out["ti"], out["trade_volume"] = ofi_c, ofi_n, ti, volume
    return out
