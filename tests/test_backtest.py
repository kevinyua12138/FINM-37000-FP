import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backtest.engine import make_trades, max_drawdown, summarize  # noqa: E402

T0 = pd.Timestamp("2025-03-03 10:00:00", tz="America/Chicago")


def events():
    """An up-shock we follow, an up-shock we fade, and one we skip."""
    return pd.DataFrame({
        "t0": [T0, T0 + pd.Timedelta("5min"), T0 + pd.Timedelta("10min")],
        "date": ["2025-03-03", "2025-03-03", "2025-03-04"],
        "direction": [1, 1, -1],
        "regime": ["follow", "fade", "no trade"],
        "entry_bid": [5000.00, 5000.00, 5000.00], "entry_ask": [5000.25, 5000.25, 5000.25],
        "exit_bid_30s": [5001.00, 4999.25, 4990.00], "exit_ask_30s": [5001.25, 4999.50, 4990.25],
    })


def test_follow_buys_the_ask_and_sells_the_bid():
    trade = make_trades(events(), fee_per_side_usd=2.0).iloc[0]
    assert trade["side"] == 1 and trade["entry_px"] == 5000.25 and trade["exit_px"] == 5001.00
    assert trade["pnl_usd"] == 0.75 * 50 - 4.0          # 3 ticks after the spread, minus fees
    assert trade["pnl_mid_usd"] == 50.0 and trade["spread_cost_usd"] == 12.5


def test_fade_sells_the_bid_and_buys_back_at_the_ask():
    trade = make_trades(events(), fee_per_side_usd=2.0).iloc[1]
    assert trade["side"] == -1 and trade["entry_px"] == 5000.00 and trade["exit_px"] == 4999.50
    assert trade["pnl_usd"] == 0.5 * 50 - 4.0
    assert trade["pnl_mid_usd"] == 37.5 and trade["spread_cost_usd"] == 12.5


def test_no_trade_rows_and_missing_quotes_are_skipped():
    ev = events()
    ev.loc[1, "exit_bid_30s"] = np.nan
    trades = make_trades(ev)
    assert trades["regime"].tolist() == ["follow"]


def test_summary_and_break_even_cost():
    trades = make_trades(events(), fee_per_side_usd=2.0)
    s = summarize(trades)
    assert s["trades"] == 2 and s["hit_rate_pct"] == 100.0
    assert s["mean_pnl_usd"] == (33.5 + 21.0) / 2
    assert s["break_even_cost_usd"] == (50.0 + 37.5) / 2   # mid-to-mid P&L per round trip
    assert s["max_drawdown_usd"] == 0.0


def test_max_drawdown():
    assert max_drawdown([10.0, -30.0, 5.0, -10.0]) == 35.0
    assert max_drawdown([-5.0]) == 5.0


def test_empty_trade_list():
    assert summarize(make_trades(events().assign(regime="no trade")))["trades"] == 0


def test_built_events_follow_the_continuation_and_fade_the_reversal(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from events.study import assign_regimes, read_events
    from synthetic import write_cutoffs, write_events_csv
    import yaml

    ev = read_events(write_events_csv(tmp_path / "events.csv")).iloc[:2]
    ev = assign_regimes(ev, yaml.safe_load(write_cutoffs(tmp_path / "cutoffs.yaml").read_text()))
    trades = make_trades(ev)
    assert trades["regime"].tolist() == ["follow", "fade"] and (trades["pnl_usd"] > 0).all()
    assert summarize(trades)["break_even_cost_usd"] > 12.5 + 4.0
