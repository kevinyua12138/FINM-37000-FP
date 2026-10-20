"""Snapshot features for Databento mbp-1/mbp-10 books.

See docs/book_features.md for formulas, units, and missing-depth semantics.
No resampling or forward filling is performed; each row is independent.
"""

import numpy as np
import pandas as pd


def book_features(book: pd.DataFrame, *, levels: int = 10,
                  tick_size: float = 0.25) -> pd.DataFrame:
    """Return I_1, I_N, microprice, G, and DS aligned to the input index.

    Prices must be decoded price units (not raw fixed-point integers).
    Missing deeper columns produce NaN I_N/DS, while missing level-zero
    columns raise ValueError. Invalid observations are masked per row.
    """
    if isinstance(levels, bool) or not isinstance(levels, int) or not 1 <= levels <= 10:
        raise ValueError("levels must be an integer between 1 and 10")
    if not np.isfinite(tick_size) or tick_size <= 0:
        raise ValueError("tick_size must be finite and positive")
    if not book.columns.is_unique:
        raise ValueError("Input column names must be unique")
    names = [f"{side}_{kind}_{i:02d}" for i in range(levels)
             for side in ("bid", "ask") for kind in ("px", "sz")]
    missing_top = [name for name in names[:4] if name not in book]
    if missing_top:
        raise ValueError(f"Missing top-of-book columns: {missing_top}")

    def matrix(side, kind):
        columns = [f"{side}_{kind}_{i:02d}" for i in range(levels)]
        return book.reindex(columns=columns).apply(
            pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)

    bid, ask = matrix("bid", "px"), matrix("ask", "px")
    bq, aq = matrix("bid", "sz"), matrix("ask", "sz")
    # Databento's undefined price sentinel is also rejected by the tick check.
    valid_prices = (np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0)
                    & (bid < ask)
                    & np.isclose(bid / tick_size, np.round(bid / tick_size), rtol=0, atol=1e-6)
                    & np.isclose(ask / tick_size, np.round(ask / tick_size), rtol=0, atol=1e-6))
    valid_sizes = np.isfinite(bq) & np.isfinite(aq) & (bq >= 0) & (aq >= 0)
    valid = valid_prices & valid_sizes
    top_ok = valid[:, 0] & ((bq[:, 0] + aq[:, 0]) > 0)
    result = pd.DataFrame(np.nan, index=book.index,
                          columns=["I_1", "I_N", "microprice", "G", "DS"])
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        total = bq[:, 0] + aq[:, 0]
        imbalance = (bq[:, 0] - aq[:, 0]) / total
        mid = (bid[:, 0] + ask[:, 0]) / 2
        micro = (ask[:, 0] * bq[:, 0] + bid[:, 0] * aq[:, 0]) / total
        result["I_1"] = np.where(top_ok, imbalance, np.nan)
        result["microprice"] = np.where(top_ok, micro, np.nan)
        result["G"] = np.where(top_ok, micro - mid, np.nan)

        ordered = (np.diff(bid, axis=1) < 0).all(axis=1) & (np.diff(ask, axis=1) > 0).all(axis=1)
        depth_ok = valid.all(axis=1) & ordered & top_ok
        sum_bid, sum_ask = bq.sum(axis=1), aq.sum(axis=1)
        result["I_N"] = np.where(depth_ok, (sum_bid - sum_ask) / (sum_bid + sum_ask), np.nan)
        if levels >= 2:
            # Fit cumulative depth = intercept + slope * outward distance in ticks.
            def slope(prices, sizes):
                distance = np.abs(prices - prices[:, :1]) / tick_size
                cumulative = sizes.cumsum(axis=1)
                x = distance - distance.mean(axis=1, keepdims=True)
                y = cumulative - cumulative.mean(axis=1, keepdims=True)
                return (x * y).sum(axis=1) / (x * x).sum(axis=1)

            result["DS"] = np.where(depth_ok, slope(bid, bq) - slope(ask, aq), np.nan)
    return result
