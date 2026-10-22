"""Synthetic mbp-1 days and shocks shared by the integration tests (not a test file)."""
import numpy as np
import pandas as pd

TZ = "America/Chicago"
IN_DAYS, OUT_DAYS = ["2025-03-04", "2025-03-05"], ["2025-05-06", "2025-05-07"]
CFG = {
    "study": {"in_sample": ["2025-01-01", "2025-04-30"], "out_of_sample": ["2025-05-01", "2025-06-30"],
              "refill_column": "refill_best", "pressure_column": "ofi",
              "refill_cutoff": "median", "pressure_cutoff": "median"},
    "backtest": {"horizon_s": 30, "fee_per_side_usd": 2.0, "point_value_usd": 50.0},
    "shocks": {"window_s": 10, "quantile": 0.995, "history_days": 5, "cooldown_s": 120},
}


def synthetic_day(day, jump_ticks, drift_ticks, refill):
    """Quotes every 0.5 s from 10:00 to 10:20. At 10:05:00 the ask is swept `jump_ticks`
    up; the new best ask then holds `refill` contracts (400 before), buyers keep trading,
    and the price drifts `drift_ticks` over the next 60 s."""
    times = pd.Timestamp(f"{day} 10:00:00", tz=TZ) + pd.to_timedelta(np.arange(2400) * 0.5, unit="s")
    shock = pd.Timestamp(f"{day} 10:05:00", tz=TZ)
    after = (times - shock).total_seconds().to_numpy()
    ticks = np.where(after >= 0, jump_ticks + np.round(drift_ticks * np.clip(after, 0, 60) / 60), 0)
    bid = 5000.00 + 0.25 * ticks
    ask_sz = np.where(after < 0, 400, np.where(after < 1, 30, refill))
    trade = (after > 0) & (after <= 3)
    return pd.DataFrame({
        "bid_px_00": bid, "ask_px_00": bid + 0.25, "bid_sz_00": 300, "ask_sz_00": ask_sz,
        "instrument_id": 42, "action": np.where(trade, "T", "A"),
        "side": np.where(trade, "B", "N"), "size": np.where(trade, 5, 0),
    }, index=times)


def shocks_for(days):
    t0 = [pd.Timestamp(f"{d} 10:05:01", tz=TZ) for d in days]
    return pd.DataFrame({"t0": t0, "date": days, "direction": 1, "size": 3.0,
                         "threshold": 2.5, "instrument_id": 42})


def write_events_csv(path):
    """Slow refill + continuation on the first day of each period, fast refill + reversal
    on the second. Returns the path of the built event table."""
    from events.build import build_events

    quotes = {IN_DAYS[0]: synthetic_day(IN_DAYS[0], 12, 8, 60), IN_DAYS[1]: synthetic_day(IN_DAYS[1], 12, -8, 390),
              OUT_DAYS[0]: synthetic_day(OUT_DAYS[0], 12, 8, 50), OUT_DAYS[1]: synthetic_day(OUT_DAYS[1], 12, -8, 380)}
    events = build_events(shocks_for(IN_DAYS + OUT_DAYS), quotes.get, ["2025-04-03", "2025-04-10"])
    events.to_csv(path, index=False)
    return path


def write_cutoffs(path, pressure_cutoff=-1.0):
    path.write_text("refill_column: refill_best\nrefill_rule: median\nrefill_cutoff: 0.5\n"
                    f"pressure_column: ofi\npressure_rule: median\npressure_cutoff: {pressure_cutoff}\n")
    return path
