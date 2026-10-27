# Sweep or Snap Back? Order-Book Regimes and Short-Horizon Price Impact in E-mini S&P 500 Futures

FINM 37000 group project. Team: Kevin Yuan (Tech Leader), Yash Jain (Communications Leader), Simon Jung (Design Leader).

## Hypotheses and what the backtests showed

A shock is a 10-second move in the ES mid price above the 99.5th percentile of 10-second moves over the previous five trading days, with a 120-second cooldown. We then watch the book for 3 seconds:

- **Refill** = size at the best quote on the side that got hit, divided by that size before the shock (#27). Slow if below 0.5.
- **Pressure** = order-flow imbalance (OFI) over those 3 seconds, signed so positive means pushing in the shock's direction, scaled to [-1, 1]. Strong above 0.05, reversing below -0.05, no trade in between.

**H1:** slow refill + strong pressure → the move continues over the next 30 seconds, so we follow it.
**H2:** fast refill + reversing pressure → the move reverses over the next 30 seconds, so we fade it.
**H3:** following H1 and fading H2 (enter 3.1 s after the shock, cross the spread, hold 30 s, $2.50 a side in fees) makes money out of sample.

In-sample (January 2 to June 30, 2025, PR #28), neither H1 nor H2 showed up. Follow shocks actually drifted back, -0.60 bp over 30 s (t = -0.53), and fade shocks reversed only 0.24 bp (t = -0.76), where positive means the move kept going. The backtest lost $16.45 per trade over 652 trades (t = -2.74): the move it caught before costs was worth $3.11 a trade, against about $19.55 in spread and fees. Simon's fixed-threshold version agrees: H1 lost $9,132.50 over 934 trades, and H2's $847.50 came from only 8 trades. Whatever the book tells us after a shock is much smaller than the cost of trading on it.

## Initial topic plan

**Question:** When the E-mini S&P 500 futures contract (ES, traded on CME Globex) makes a sudden large move, can the order book in the next few seconds tell us whether the move will continue or reverse?

**Idea:** An information-driven move leaves the eaten liquidity missing and order flow keeps pushing (continuation). A temporary liquidity squeeze refills quickly and order flow flips (reversal).

**Method:**
1. Detect 10-second shocks above the past-5-day 99.5th percentile (120-second cooldown).
2. Watch the book for 3 seconds and measure order-flow imbalance and liquidity replenishment.
3. Sort shocks into a 2×2 regime table (refill slow/fast × pressure strong/weak). When the two signals disagree, no trade.
4. Backtest at a 30-second horizon, crossing the spread.

**Hypotheses:**
- **H1:** strong same-direction order flow + slow refill → price continues over the next 30 seconds.
- **H2:** fast refill + reversing order flow → price reverses over the next 30 seconds.
- **H3:** a rule that follows H1 shocks and fades H2 shocks is profitable out-of-sample after paying the spread and fees.

**Data:** Databento GLBX.MDP3, ES front month (`ES.v.0`), mbp-1 for January–June 2025, regular hours only. mbp-10 depth data is a stretch goal.
- Settings (dataset, symbol, schema, session hours, cost cap) live in [`config.yaml`](config.yaml).
- Download code: [`src/data/download.py`](src/data/download.py). Raw files go to `data/raw/` and each download is logged in `data/raw/download_log.csv`.
- A first look at one day of data: [`notebooks/01_first_look.py`](notebooks/01_first_look.py).
- Running the download needs a Databento API key (`DATABENTO_API_KEY`) and installing `requirements.txt`. Usage: `python src/data/download.py 2025-03-03` (add `--dry-run` to only print the cost).

Exact thresholds and feature definitions are still open at the moment, we will work as a team, following the Design Lead to formalize these.

## Meeting notes

Weekly notes are in [`MeetingNotes/`](MeetingNotes/).

## Contact and communication

| Member | Email | GitHub |
|---|---|---|
| Kevin Yuan | kevinyua@uchicago.edu | [kevinyua12138](https://github.com/kevinyua12138) |
| Simon Jung | simonjung@uchicago.edu | [simonfromseoul](https://github.com/simonfromseoul) |
| Yash Jain | yashjain@uchicago.edu | [yashjain12](https://github.com/yashjain12) |

Note: Simon and Yash have been made collaborators on this GitHub repository, so we push branches straight into Kevin's repository instead of working from forks. Changes still go through pull requests that Kevin merges.

## Roll and calendar flags (issue #4)

Generate 2025 ES roll, holiday, early-close, CPI, NFP, and FOMC day flags:

```sh
python3 main.py
python3 -m unittest discover -s tests -v
```

This offline command writes `data/processed/calendar_2025.csv`; it requires no
API key or third-party packages. Use `--start` and `--end` to select a date range.
See [calendar documentation](docs/calendar.md) for joining flags onto downloaded
data, source references, holiday semantics, and supplying actual `ES.v.0` roll
dates. CME scheduled rolls and Databento volume-based transitions are separate.

## Imbalance and microprice features (issue #7)

`from features import book_features` (with `src` on the Python path) computes
`I_1`, `I_N`, microprice, gap `G`, and depth slope `DS` from decoded Databento
snapshot columns. Use `levels=1` for mbp-1 and `levels=10` for mbp-10; unavailable
depth features remain missing. See [formulas and usage](docs/book_features.md).
Run `python3 -m unittest discover -s tests -v` to verify the features and calendar.

## Shock detector (issue #5)

A shock is a 10-second move in the ES mid price larger than the 99.5th percentile of
10-second moves over the previous 5 trading days, with a 120-second cooldown after each
shock. Settings are under `shocks:` in [`config.yaml`](config.yaml).

Finding shocks only needs one quote per second, so the detector reads Databento's small
`bbo-1s` schema instead of full `mbp-1` days:

```sh
python src/data/download.py 2025-01-02 --end 2025-06-30 --schema bbo-1s --dry-run  # cost check
python src/data/download.py 2025-01-02 --end 2025-06-30 --schema bbo-1s
python src/events/shocks.py   # writes data/processed/shocks.csv
```

`--end` downloads every trading day in the range (weekends and holidays from the #4
calendar are skipped). The first 5 days only build the threshold, so download at least 6.
Each row of `shocks.csv` is one shock: `t0`, `date`, `direction` (+1 up, -1 down), `size`
and `threshold` (index points), and `instrument_id`. The mid at second t is the last quote
at or before t, so a shock at `t0` uses no later data. `python src/events/shocks.py
--schema mbp-1` runs the same detector on mbp-1 files.
