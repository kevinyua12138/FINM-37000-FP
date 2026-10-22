"""Simple 2x2 ES backtest. Run: python backtest.py"""
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

HERE = Path(__file__).resolve().parent
SHOCK_THRESHOLD = 3.5  # 99th percentile from Jan 2, 3, 6, 7, 8; fixed thereafter.
H1_RR_MAX = 0.25  # RR strictly below this: depleted depth.
H2_RR_MIN = 1.5   # RR at least this: depth grew by 50%.
H1_CANDIDATES, H2_CANDIDATES = (0.25, 0.5), (1.0, 1.5)
FLOW_CUTOFF = 0.05  # More than 5% net quote-flow pressure.
POINT_VALUE = 50.0  # One ES contract.
ROUND_TRIP_FEE = 5.0
FOLLOW, FADE = "Slow / same", "Fast / reversing"
TRADE_SIGN = {FOLLOW: 1, FADE: -1}  # Relative to the initial price shock.


def regime(refill, flow, h1=H1_RR_MAX, h2=H2_RR_MIN):
    if pd.isna(refill) or pd.isna(flow) or abs(flow) <= FLOW_CUTOFF:
        return "Neutral / missing"
    if h1 <= refill < h2:
        return "Middle RR: skip"
    speed = "Fast" if refill >= h2 else "Slow"
    pressure = "same" if flow > FLOW_CUTOFF else "reversing"
    return f"{speed} / {pressure}"


def features(events, h1=H1_RR_MAX, h2=H2_RR_MIN):
    events = events.copy()
    for column in ["shock_time", "entry_time", "exit_time"]:
        events[column] = pd.to_datetime(events[column], utc=True)
    # Freeze the consumed-side best price at t0; never substitute another price's size.
    movement = events.direction * (events.best_price_after - events.anchor_price)
    events["depth_at_anchor_after"] = np.select(
        [movement.eq(0), movement.gt(0)], [events.best_depth_after, 0.0], default=np.nan)
    # A better best quote hides the anchor deeper in the book: MBP-1 cannot see it.
    events["refill_ratio"] = events.depth_at_anchor_after / events.depth_at_shock.where(events.depth_at_shock > 0)
    events["recovered"] = np.where(events.direction.eq(1),
        events.observation_min_mid <= events.pre_shock_mid,
        events.observation_max_mid >= events.pre_shock_mid)
    events["signed_ofi"] = events.direction * events.ofi_sum / events.ofi_abs_sum.where(events.ofi_abs_sum > 0)
    events.loc[events.ofi_abs_sum.eq(0), "signed_ofi"] = 0.0
    events["regime"] = [regime(r, f, h1, h2) for r, f in zip(events.refill_ratio, events.signed_ofi)]
    events.loc[events.refill_ratio.isna(), "regime"] = "Unknown RR: skip"
    events.loc[events.recovered, "regime"] = "Recovered: skip"
    return events


def backtest(events):
    trades, last_exit = [], None
    required = ["entry_time", "exit_time", "entry_bid", "entry_ask", "exit_bid",
                "exit_ask", "entry_bid_size", "entry_ask_size", "exit_bid_size",
                "exit_ask_size", "direction"]
    valid = events.dropna(subset=required).sort_values("entry_time")
    assert (valid.entry_time >= valid.shock_time + pd.Timedelta(seconds=3.1)).all()
    assert (valid.exit_time >= valid.entry_time + pd.Timedelta(seconds=30)).all()
    for row in valid.itertuples():
        if row.recovered or pd.isna(row.refill_ratio) or row.regime not in TRADE_SIGN:
            continue
        if last_exit is not None and row.entry_time <= last_exit:
            continue  # One open position for the combined strategy.
        side = TRADE_SIGN[row.regime] * row.direction
        entry_size = row.entry_ask_size if side == 1 else row.entry_bid_size
        exit_size = row.exit_bid_size if side == 1 else row.exit_ask_size
        if min(entry_size, exit_size) < 1:
            continue
        entry = row.entry_ask if side == 1 else row.entry_bid
        exit_price = row.exit_bid if side == 1 else row.exit_ask
        gross = side * (exit_price - entry) * POINT_VALUE
        move_ticks = side * ((row.exit_bid + row.exit_ask) -
                             (row.entry_bid + row.entry_ask)) / 2 / 0.25
        trades.append([row.regime, row.shock_time, row.entry_time, row.exit_time,
                       side, entry, exit_price, gross, ROUND_TRIP_FEE,
                       gross - ROUND_TRIP_FEE, move_ticks])
        last_exit = row.exit_time
    return pd.DataFrame(trades, columns=["regime", "shock_time", "entry_time",
                        "exit_time", "side", "entry_price", "exit_price",
                        "gross_profit", "fees", "net_profit", "move_ticks"])


def metrics(trades):
    pnl = trades.net_profit
    equity = pd.concat([pd.Series([0.0]), pnl.cumsum()], ignore_index=True)
    # Resample entire trading days to allow within-day dependence.
    days = pd.DataFrame()
    if len(trades):
        days = trades.groupby(trades.entry_time.dt.tz_convert("America/Chicago").dt.date).move_ticks.agg(["sum", "count"])
    low, high = np.nan, np.nan
    if len(days) >= 2:
        draws = np.random.default_rng(0).integers(0, len(days), (5000, len(days)))
        means = days["sum"].to_numpy()[draws].sum(axis=1) / days["count"].to_numpy()[draws].sum(axis=1)
        low, high = np.quantile(means, [0.025, 0.975])
    return {"trades": len(trades), "gross": trades.gross_profit.sum(),
            "fees": trades.fees.sum(), "net": pnl.sum(), "mean_trade": pnl.mean(),
            "win_pct": (pnl > 0).mean() * 100,
            "max_drawdown": (equity.cummax() - equity).max(),
            "mean_move_ticks": trades.move_ticks.mean(), "move_ci_low": low, "move_ci_high": high}


def compare_thresholds(raw):
    # Only January–April selects thresholds; May–June never enters this comparison.
    train = raw[raw.split.eq("train")]
    rows = []
    for rule, cell, cutoffs in [("H1", FOLLOW, H1_CANDIDATES), ("H2", FADE, H2_CANDIDATES)]:
        for cutoff in cutoffs:
            events = features(train, h1=cutoff if rule == "H1" else H1_RR_MAX,
                              h2=cutoff if rule == "H2" else H2_RR_MIN)
            trades = backtest(events[events.regime.eq(cell)])
            rows.append({"rule": rule, "RR_cutoff": cutoff, "trades": len(trades),
                         "net_profit": trades.net_profit.sum()})
    return pd.DataFrame(rows)


def main():
    events = pd.read_csv(HERE / "events.csv")
    assert events.threshold_points.eq(SHOCK_THRESHOLD).all()
    assert (events.shock_points > SHOCK_THRESHOLD).all()
    print("January–April threshold comparison (net profit after spread and fees):")
    print(compare_thresholds(events).to_string(index=False))
    print(f"Selected H1: RR < {H1_RR_MAX}; H2: RR >= {H2_RR_MIN}")
    events = features(events)
    rows, test_trades, all_trades = [], None, None
    groups = [("H1 follow", FOLLOW), ("H2 fade", FADE)]
    for split, period in [("all", "Jan10-Jun30"), ("train", "Jan10-Apr30"), ("test", "May-Jun")]:
        sample = events if split == "all" else events[events.split.eq(split)]
        print(f"\n{period}: event counts BEFORE execution exclusions")
        cells = [FOLLOW, "Slow / reversing", "Fast / same", FADE, "Middle RR: skip", "Neutral / missing", "Unknown RR: skip", "Recovered: skip"]
        print(sample.regime.value_counts().reindex(cells, fill_value=0).to_string())
        trades = backtest(sample)
        for name, cell in groups:
            selected = trades[trades.regime.eq(cell)]
            rows.append({"period": period, "rule": name, **metrics(selected)})
        if split == "test":
            test_trades = trades
        if split == "all":
            all_trades = trades
    print("\nProfit in dollars; positive midpoint move supports each hypothesis:")
    print(pd.DataFrame(rows).round(2).to_string(index=False, na_rep="—"))

    # One image: regime counts and net profit paths for the original test period.
    plt.style.use("seaborn-v0_8-whitegrid")
    fig = plt.figure(figsize=(13, 9))
    layout = fig.add_gridspec(2, 2, width_ratios=[1, 1.5])
    axes = [fig.add_subplot(layout[0, 0]), fig.add_subplot(layout[0, 1])]
    full_axis = fig.add_subplot(layout[1, :])
    counts = events[events.split.eq("test")].regime.value_counts()
    cells = [[f"n={counts.get(cell, 0)}\n{action}" for cell, action in row]
             for row in [[(FOLLOW, "H1: FOLLOW"), ("Slow / reversing", "NO TRADE")],
                         [("Fast / same", "NO TRADE"), (FADE, "H2: FADE")]]]
    axes[0].axis("off")
    table = axes[0].table(cellText=cells, rowLabels=[f"Slow\nRR < {H1_RR_MAX:g}", f"Fast\nRR >= {H2_RR_MIN:g}"],
                          colLabels=["Same direction\nOFI > 0.05", "Reversing\nOFI < -0.05"],
                          cellLoc="center", bbox=[0.18, 0.22, 0.82, 0.65])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table[1, 0].set_facecolor("#dbe9f5")
    table[2, 1].set_facecolor("#ffead3")
    neutral = counts.get("Neutral / missing", 0)
    unknown, recovered = counts.get("Unknown RR: skip", 0), counts.get("Recovered: skip", 0)
    middle = counts.get("Middle RR: skip", 0)
    axes[0].set_title("2 × 2 extreme regimes · May–June")
    axes[0].text(0.5, 0.17, f"No trade: {middle} middle RR, {neutral} neutral,\n{unknown} unknown RR, {recovered} recovered.\nCounts precede execution checks.",
                 transform=axes[0].transAxes, ha="center", va="top", fontsize=9)
    for ax, trades, start, title in [(axes[1], test_trades, "2025-04-30", "May–June: cumulative net profit"),
                                     (full_axis, all_trades, "2025-01-09", "January 10–June 30: cumulative net profit")]:
        days = pd.date_range(start, "2025-06-30", tz="UTC")
        for (name, cell), color in zip(groups, ["#356aa0", "#d57936"]):
            t = trades[trades.regime.eq(cell)]
            daily = t.groupby(t.exit_time.dt.normalize()).net_profit.sum()
            label = f"{name}: ${t.net_profit.sum():,.2f} (n={len(t)})" if len(t) else f"{name}: no trades"
            ax.plot(days, daily.reindex(days, fill_value=0).cumsum(), color=color,
                    label=label, lw=2)
        ax.set_title(title)
        ax.yaxis.set_major_formatter(StrMethodFormatter("${x:,.0f}"))
        ax.tick_params(axis="x", rotation=25)
        ax.legend(fontsize=9)
    full_axis.axvline(pd.Timestamp("2025-05-01", tz="UTC"), color="gray", ls=":", lw=1)
    fig.suptitle("Sweep or Snap Back? · H1 continuation and H2 reversal")
    fig.text(0.5, 0.01, f"Fixed 99th-percentile cutoff: {SHOCK_THRESHOLD:g} points · 3-second observation · 30-second hold\n"
             "One ES contract · observed spread + $5 fees · same post-shock price for RR · skip recovery within 3 seconds", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.09, 1, 0.95))
    fig.savefig(HERE / "results.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
