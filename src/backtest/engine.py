"""Backtest engine with spread and fees (issue #12).

One contract per follow/fade shock. Trades never overlap, because the 120 s cooldown is
longer than the holding period. Entry crosses the spread at the first quote at or after
t0 + 3.1 s (buy at the ask, sell at the bid) and exit crosses it again `horizon_s` later.
    side        = +1 long / -1 short: follow trades with the shock, fade against it
    pnl_usd     = side * (exit_px - entry_px) * $50 - 2 * fee_per_side
    pnl_mid_usd = side * (exit_mid - entry_mid) * $50      (no spread, no fees)
    break-even cost = mean pnl_mid_usd, the round-trip cost per contract (spread + fees)
                      at which the strategy would make exactly zero

Usage (from the repo root, after `python src/events/study.py`):
    python src/backtest/engine.py   # -> results/in_sample/{trades,backtest_summary}.csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analysis.stats import clustered_mean, to_markdown  # noqa: E402

POINT_VALUE_USD = 50.0


def make_trades(events, horizon_s=30, fee_per_side_usd=2.0, point_value_usd=POINT_VALUE_USD):
    """Trade list for events with a regime column. Shocks without usable quotes are dropped."""
    ev = events[events["regime"].isin(["follow", "fade"])]
    bid_x, ask_x = ev[f"exit_bid_{horizon_s}s"].to_numpy(float), ev[f"exit_ask_{horizon_s}s"].to_numpy(float)
    bid_e, ask_e = ev["entry_bid"].to_numpy(float), ev["entry_ask"].to_numpy(float)
    side = np.where(ev["regime"] == "follow", 1, -1) * ev["direction"].to_numpy(int)
    entry_px = np.where(side > 0, ask_e, bid_e)
    exit_px = np.where(side > 0, bid_x, ask_x)
    pnl_mid = side * ((bid_x + ask_x) / 2 - (bid_e + ask_e) / 2) * point_value_usd
    pnl_spread = side * (exit_px - entry_px) * point_value_usd
    trades = pd.DataFrame({
        "t0": ev["t0"].to_numpy(), "date": ev["date"].to_numpy(), "regime": ev["regime"].to_numpy(),
        "direction": ev["direction"].to_numpy(), "side": side,
        "entry_px": entry_px, "exit_px": exit_px,
        "pnl_mid_usd": pnl_mid,
        "spread_cost_usd": pnl_mid - pnl_spread,
        "fees_usd": np.full(len(ev), 2 * fee_per_side_usd),
        "pnl_usd": pnl_spread - 2 * fee_per_side_usd,
    })
    return trades.dropna(subset=["entry_px", "exit_px", "pnl_mid_usd"]).sort_values("t0").reset_index(drop=True)


def max_drawdown(pnl):
    """Largest peak-to-trough fall of cumulative P&L (a positive number of dollars)."""
    equity = np.concatenate([[0.0], np.cumsum(np.asarray(pnl, float))])
    return float(np.max(np.maximum.accumulate(equity) - equity))


def summarize(trades, trading_days=None):
    """Headline numbers for one trade list. trading_days: days in the period (for daily stats)."""
    if trades.empty:
        return pd.Series({"trades": 0})
    net = clustered_mean(trades["pnl_usd"].to_numpy(), trades["date"].to_numpy())
    daily = trades.groupby("date")["pnl_usd"].sum()
    if trading_days is not None:
        daily = daily.reindex(sorted(set(trading_days) | set(daily.index)), fill_value=0.0)
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else np.nan
    return pd.Series({
        "trades": len(trades),
        "trade_days": trades["date"].nunique(),
        "follow_trades": int((trades["regime"] == "follow").sum()),
        "fade_trades": int((trades["regime"] == "fade").sum()),
        "hit_rate_pct": 100 * (trades["pnl_usd"] > 0).mean(),
        "mean_pnl_usd": net["mean"],
        "t_day_clustered": net["t"],
        "median_pnl_usd": trades["pnl_usd"].median(),
        "total_pnl_usd": trades["pnl_usd"].sum(),
        "mean_spread_cost_usd": trades["spread_cost_usd"].mean(),
        "fees_per_trade_usd": trades["fees_usd"].mean(),
        "break_even_cost_usd": trades["pnl_mid_usd"].mean(),
        "daily_sharpe_annualized": sharpe,
        "max_drawdown_usd": max_drawdown(trades["pnl_usd"]),
    })


def plot_cumulative(trade_lists, path):
    """Cumulative net P&L per trade for each labelled trade list (e.g. in- and out-of-sample)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4))
    offset = 0
    for (label, trades), color in zip(trade_lists.items(), ["#2a6fdb", "#d9480f", "#6b7280"]):
        x = np.arange(offset, offset + len(trades))
        ax.plot(x, trades["pnl_usd"].cumsum(), color=color, label=f"{label} ({len(trades)} trades)")
        offset += len(trades)
    ax.axhline(0.0, color="#6b7280", linewidth=1)
    ax.set_title("Cumulative P&L after spread and fees, 1 contract per trade", loc="left")
    ax.set_xlabel("trade number")
    ax.set_ylabel("USD")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main(argv=None):
    import yaml

    parser = argparse.ArgumentParser(description="In-sample backtest with spread and fees.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--events", type=Path, default=Path("results/in_sample/events.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/in_sample"))
    parser.add_argument("--fig-dir", type=Path, default=Path("figures/issue12"))
    args = parser.parse_args(argv)

    bt = yaml.safe_load(args.config.read_text())["backtest"]
    events = pd.read_csv(args.events)
    trades = make_trades(events, bt["horizon_s"], bt["fee_per_side_usd"], bt["point_value_usd"])
    summary = summarize(trades, events["date"].astype(str).unique())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    trades.to_csv(args.out_dir / "trades.csv", index=False)
    summary.to_frame("in_sample").to_csv(args.out_dir / "backtest_summary.csv")
    (args.out_dir / "backtest_summary.md").write_text(to_markdown(summary.to_frame("in_sample"), 2))
    plot_cumulative({"in-sample": trades}, args.fig_dir / "cumulative_pnl_in_sample.png")
    print(summary.round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
