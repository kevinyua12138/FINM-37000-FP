import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features.orderflow import ofi_increments, orderflow_features  # noqa: E402

T0 = pd.Timestamp("2025-03-03 10:00:00", tz="America/Chicago")
COLS = ["bid_px_00", "bid_sz_00", "ask_px_00", "ask_sz_00", "action", "side", "size"]


def quotes(rows):
    """rows: (seconds after T0, bid_px, bid_sz, ask_px, ask_sz, action, side, size)"""
    index = pd.DatetimeIndex([T0 + pd.Timedelta(seconds=s) for s, *_ in rows])
    return pd.DataFrame([r[1:] for r in rows], columns=COLS, index=index)


def events(direction=1):
    return pd.DataFrame({"t0": [T0], "direction": [direction]})


# Book before t0, then three updates inside (t0, t0 + 3s] and one after it.
BOOK_ROWS = [
    (-1.0, 5000.00, 10, 5000.25, 10, "A", "N", 0),
    (0.5, 5000.00, 15, 5000.25, 10, "A", "N", 0),  # bid size 10 -> 15: e = +5
    (1.0, 5000.00, 15, 5000.25, 4, "C", "N", 0),   # ask size 10 -> 4:  e = +6
    (2.0, 5000.25, 3, 5000.50, 8, "A", "N", 0),    # bid and ask tick up: e = 3 + 4 = +7
    (4.0, 4999.00, 1, 4999.25, 900, "A", "N", 0),  # after the window: ignored
]


def test_hand_calculated_increments():
    book = quotes(BOOK_ROWS)[["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]]
    # last row: bid falls (-B_prev = -3) and ask falls (-A = -900)
    assert ofi_increments(book).tolist() == [5.0, 6.0, 7.0, -903.0]


def test_ofi_over_the_window_signed_by_direction():
    up = orderflow_features(quotes(BOOK_ROWS), events(+1)).iloc[0]
    assert up["ofi_contracts"] == 18.0 and up["ofi"] == 1.0
    down = orderflow_features(quotes(BOOK_ROWS), events(-1)).iloc[0]
    assert down["ofi_contracts"] == -18.0 and down["ofi"] == -1.0


def test_normalized_ofi_mixes_both_signs():
    rows = [(-1.0, 5000.00, 10, 5000.25, 10, "A", "N", 0),
            (1.0, 5000.00, 15, 5000.25, 10, "A", "N", 0),   # +5
            (2.0, 5000.00, 12, 5000.25, 10, "C", "N", 0)]   # -3
    out = orderflow_features(quotes(rows), events()).iloc[0]
    assert out["ofi_contracts"] == 2.0 and out["ofi"] == 2.0 / 8.0


def test_still_book_gives_zero_ofi():
    rows = [(-1.0, 5000.00, 10, 5000.25, 10, "A", "N", 0), (1.0, 5000.00, 10, 5000.25, 10, "M", "N", 0)]
    out = orderflow_features(quotes(rows), events()).iloc[0]
    assert out["ofi"] == 0.0 and out["ofi_contracts"] == 0.0


def test_trade_imbalance_window_and_sign():
    book = (5000.00, 10, 5000.25, 10)
    rows = [(-1.0, *book, "A", "N", 0),
            (0.0, *book, "T", "B", 100),  # at t0 exactly: outside (t0, t0 + 3s]
            (0.5, *book, "T", "B", 10),
            (1.0, *book, "T", "B", 2),
            (2.5, *book, "T", "A", 4),
            (3.0, *book, "T", "A", 4),    # at t0 + 3s: inside
            (3.0, *book, "T", "N", 50),   # unknown aggressor: ignored
            (3.5, *book, "T", "B", 100)]  # after the window
    out = orderflow_features(quotes(rows), events(-1)).iloc[0]
    assert out["trade_volume"] == 20.0
    assert np.isclose(out["ti"], -(12 - 8) / 20)


def test_no_trades_gives_zero_ti():
    out = orderflow_features(quotes(BOOK_ROWS), events()).iloc[0]
    assert out["ti"] == 0.0 and out["trade_volume"] == 0.0


def test_quotes_without_trade_columns_give_nan_ti():
    q = quotes(BOOK_ROWS).drop(columns=["action", "side", "size"])
    out = orderflow_features(q, events()).iloc[0]
    assert out["ofi"] == 1.0 and np.isnan(out["ti"]) and np.isnan(out["trade_volume"])


def test_crossed_quotes_are_skipped():
    rows = [(-1.0, 5000.00, 10, 5000.25, 10, "A", "N", 0),
            (1.0, 5000.50, 99, 5000.25, 99, "A", "N", 0),  # crossed: dropped
            (2.0, 5000.00, 15, 5000.25, 10, "A", "N", 0)]  # +5 against the last valid state
    assert orderflow_features(quotes(rows), events()).iloc[0]["ofi_contracts"] == 5.0


def test_no_quote_before_t0_gives_nan():
    out = orderflow_features(quotes(BOOK_ROWS[1:]), events()).iloc[0]
    assert np.isnan(out["ofi"]) and np.isnan(out["ti"])


def test_events_not_modified():
    ev = events()
    orderflow_features(quotes(BOOK_ROWS), ev)
    assert list(ev.columns) == ["t0", "direction"]


def test_unsigned_sizes_like_databento():
    # Databento delivers sizes as uint32; more selling than buying must not wrap around
    book = (5000.00, 10, 5000.25, 10)
    rows = [(-1.0, *book, "A", "N", 0), (0.5, *book, "T", "B", 2), (1.0, *book, "T", "A", 6),
            (2.0, 5000.00, 4, 5000.25, 10, "C", "N", 0)]
    q = quotes(rows).astype({"bid_sz_00": "uint32", "ask_sz_00": "uint32", "size": "uint32"})
    for direction in (1, -1):
        out = orderflow_features(q, events(direction)).iloc[0]
        assert np.isclose(out["ti"], direction * (2 - 6) / 8) and out["trade_volume"] == 8.0
        assert out["ofi_contracts"] == direction * -6.0  # bid size 10 -> 4
