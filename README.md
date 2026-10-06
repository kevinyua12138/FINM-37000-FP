# Sweep or Snap Back? Order-Book Regimes and Short-Horizon Price Impact in E-mini S&P 500 Futures

FINM 37000 group project. Team: Kevin Yuan (Tech Leader), Yash Jain (Communications Leader), Simon Jung (Design Leader).

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
