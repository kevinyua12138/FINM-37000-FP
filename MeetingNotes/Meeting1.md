# Meeting 1 Notes

**Date:** 8/5/2026
**Attendees:** Kevin Yuan, Simon Jung, Yash Jain
**Format:** Zoom
**Planning doc:** [Project Planning (Google Doc)](https://docs.google.com/document/d/1exdinACcTy6LiyJnKnL4mMNBgRLTm0W7uG71DeE795Q/edit?usp=sharing)

## What we did

- Went over our proposal and finalized the market: equity index futures (E-mini S&P 500, ES).
- Agreed to communicate through a weekly Zoom check-in.
- Checked that everyone could set up the virtual environment and run Databento.
- Then spent the rest of the meeting on why equities fit this strategy.

## Why equities (ES)

All of us agreed on two points:

1. ES is liquid, so a shock is cleanly measured. In a thinly traded market, every large order would look like a shock.
2. Costs are well defined. ES trades in 0.25-point ticks worth $12.50, and the spread is almost always one tick, so spread and fees are easy to account for.

Summary of what the points were from the meeting:

- **Kevin:** The same idea could apply to metals and energy, where news tends to cause big shocks. A possible extension later of how this strategy could be applied in nay market.
- **Yash (me):** The S&P 500 is very diversified, and the implied correlation of its constituents is currently low. So large ES moves may come more often from individual traders than from a genuine market-wide move, which clouds the signal.
- **Simon:** We do not need a specific conclusion or a concrete correlation yet. It is fine to refine the analysis later.

## We wrapped up with an example:

1. A big buyer arrives and fulfills a lot of asks. The mid price jumps up since the ask price goes up, which is a shock.
2. Contracts waiting to be sold: 400 before the shock, 124 a few seconds after. Refill ratio = 124 / 400 = 0.31, so sellers are not coming back.
3. Order flow imbalance (OFI) is +0.64, so there is a sustained buying pressure.
4. A positive shock with a sustained low refill ratio and sustained buying pressure means we expect the price of ES futures to continue rising, so we buy ES futures.
