"""Two strategies on prepared ES events. Run: python backtest.py"""
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

HERE = Path(__file__).resolve().parent
POINT_VALUE = 50.0  # One ES contract: $50 per index point.
ROUND_TRIP_FEE = 5.0
REFILL_CUTOFF = 0.5


def backtest(events, strategy):
    trades, last_exit = [], None
    for row in events.itertuples():
        if strategy == "Order-book imbalance":
            if pd.isna(row.book_imbalance) or row.book_imbalance == 0:
                continue
            side = 1 if row.book_imbalance > 0 else -1
        else:
            if pd.isna(row.refill_ratio) or row.refill_ratio < REFILL_CUTOFF:
                continue
            side = -row.direction  # Trade against the initial shock.
        if last_exit is not None and row.entry_time <= last_exit:
            continue  # At most one position per strategy.
        entry_size = row.entry_ask_size if side == 1 else row.entry_bid_size
        exit_size = row.exit_bid_size if side == 1 else row.exit_ask_size
        if min(entry_size, exit_size) < 1:
            continue
        entry = row.entry_ask if side == 1 else row.entry_bid
        exit_price = row.exit_bid if side == 1 else row.exit_ask
        gross = side * (exit_price - entry) * POINT_VALUE
        trades.append([strategy, row.shock_time, row.entry_time, row.exit_time,
                       side, entry, exit_price, gross, ROUND_TRIP_FEE,
                       gross - ROUND_TRIP_FEE])
        last_exit = row.exit_time
    return pd.DataFrame(trades, columns=["strategy", "shock_time", "entry_time",
                        "exit_time", "side", "entry_price", "exit_price",
                        "gross_profit", "fees", "net_profit"])


def main():
    events = pd.read_csv(HERE / "events.csv")
    for column in ["shock_time", "entry_time", "exit_time"]:
        events[column] = pd.to_datetime(events[column], utc=True)
    required = ["entry_time", "exit_time", "entry_bid", "entry_ask", "exit_bid",
                "exit_ask", "entry_bid_size", "entry_ask_size", "exit_bid_size",
                "exit_ask_size", "direction"]
    events = events.dropna(subset=required).sort_values("entry_time")
    assert (events.entry_time >= events.shock_time + pd.Timedelta(seconds=3.1)).all()
    assert (events.exit_time >= events.entry_time + pd.Timedelta(seconds=30)).all()
    strategies = ["Order-book imbalance", "High-refill reversal"]
    results = [backtest(events, name) for name in strategies]
    summary = pd.DataFrame([
        {"strategy": name, "trades": len(t), "gross_profit": t.gross_profit.sum(),
         "fees": t.fees.sum(), "net_profit": t.net_profit.sum(),
         "win_rate_pct": (t.net_profit > 0).mean() * 100}
        for name, t in zip(strategies, results)
    ])
    print(summary.round(2).to_string(index=False))

    # Two graphs in one image; the profit table is printed above.
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    colors = ["#356aa0", "#d57936"]
    days = pd.date_range("2025-04-30", "2025-06-30", tz="UTC")
    for name, t, color in zip(strategies, results, colors):
        daily = t.groupby(t.exit_time.dt.normalize()).net_profit.sum()
        equity = daily.reindex(days, fill_value=0).cumsum()
        axes[0].plot(days, equity, label=f"{name} (n={len(t)})", color=color, lw=2)
    axes[0].set_title("Cumulative net profit")
    axes[0].legend(fontsize=9)
    axes[0].tick_params(axis="x", rotation=25)
    bars = axes[1].bar(["Book imbalance", "High-refill reversal"], summary.net_profit, color=colors)
    labels = [f"${p:,.2f}\nn={n}" for p, n in zip(summary.net_profit, summary.trades)]
    axes[1].bar_label(bars, labels=labels, padding=6)
    axes[1].margins(y=0.25)
    axes[1].set_title("Total net profit")
    for ax in axes:
        ax.axhline(0, color="gray", lw=0.8)
        ax.yaxis.set_major_formatter(StrMethodFormatter("${x:,.0f}"))
    fig.suptitle("Two trading strategies · May–June 2025")
    fig.text(0.5, 0.01, "One ES contract · 30-second hold · observed spread + $5 fees\n"
             "High-refill reversal: only one trade, insufficient evidence.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.09, 1, 0.95))
    fig.savefig(HERE / "results.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
