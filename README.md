# Sweep or Snap Back? H1 continuation and H2 reversal

![When the fixed-threshold price shocks happen](shocks.png)

The triangles mark **38 shocks on January 10**. A shock is a 10-second midpoint
move **greater than 3.5 points (14 ticks)**. “99%” means the **99th percentile**
of historical move sizes, not a 99% return.

## Fixed threshold and timing

The 3.5-point cutoff is calculated **once**, using January 2, 3, 6, 7, and 8,
and stays fixed for the entire January 10–June 30 backtest. These five days are
calibration data only. A **session** means one trading day, 08:30–15:00 Chicago
time. **Three seconds** means the observation window after a shock; it does
not mean three sessions. There is no moving threshold in this version.

Check for shocks each second, with a 120-second cooldown. After a shock at `t0`,
observe through `t0 + 3 seconds`, enter at the first eligible quote at/after
`t0 + 3.1 seconds`, and exit 30 seconds after the actual entry.

## Refill ratio: one Mickey Mouse example

**Choose one price P immediately after the shock, at `t0`, and keep P fixed.**
Use the best ask for an up-shock and the best bid for a down-shock.

**RR = quantity at P three seconds later / quantity at P immediately after the shock.**

Both quantities refer to **the same price and the same side of the book**.
The denominator is measured at `t0`, not before the shock.

Imagine an upward price shock:

1. At `t0`, the best ask is **6004**, with **20 contracts**. Freeze P = 6004.
2. At `t0 + 3s`, the best ask is still **6004**, with **40 contracts**.
3. **RR = 40 / 20 = 2.0.** Depth at 6004 doubled. This is in the fast-refill group.

The available MBP-1 data shows only the best bid and ask. For the same example:

| Best ask three seconds later | Quantity used at fixed P = 6004 | RR |
|---|---|---|
| 6004, with 5 contracts | 5 | 5 / 20 = 0.25: slow |
| 6004, with 40 contracts | 40 | 40 / 20 = 2.0: fast |
| 6004.25 | 0: no ask remains at 6004 | 0: slow |
| 6003.75 | Unknown: 6004 is behind the best ask | Missing: no trade |

For a down-shock, reverse the price comparisons and use bids: a best bid below
P means zero at P; a best bid above P hides P deeper in the book.
A smaller **quantity at the same price** gives a smaller ratio, not automatically zero.
Zero is used only when the quote has moved past P in the shock direction.

Keep the existing cutoff: **RR < 0.5 is slow; RR >= 0.5 is fast**. Here “fast” is
our regime label for retaining at least half the post-shock displayed depth.
Unchanged depth gives RR = 1 and is classified fast. This ratio measures net
displayed depth, not the number of new orders or refill speed; trades and
cancellations can also change it.

**Skip an already recovered shock.** The pre-shock reference is the midpoint
at `t0 − 10s`. Check every valid quote update during the three-second observation:
for an up-shock, skip if midpoint reaches or falls below that reference;
for a down-shock, skip if midpoint reaches or rises above it. A recovery followed
by another move still causes a skip. A partial recovery alone does not.
For example, if midpoint rose from 6000 to 6004 and touches 6000 at +2 seconds,
there is no trade even if it is back at 6003 by +3 seconds.

## Two hypotheses and the 2 × 2 rule

Use quote **order-flow imbalance (OFI)** during `(t0, t0 + 3s]`, signed relative
to the shock. Positive supports continuation; negative supports reversal.
**Strong same-direction:** OFI > 0.05. **Reversing:** OFI < −0.05.
Values from −0.05 through +0.05 are neutral: no trade.

| | Strong same-direction flow | Reversing flow |
|---|---|---|
| **Slow refill: RR < 0.5** | **H1: follow** the shock | No trade |
| **Fast refill: RR >= 0.5** | No trade | **H2: fade** the shock |

H1 buys an up-shock and sells a down-shock. H2 does the opposite.
The refill cutoff (0.5), flow cutoff (0.05), execution timing, and costs are
unchanged from the prior run, as is the fixed 99th-percentile shock cutoff.
This revision changes the RR price/time anchor and excludes already recovered
shocks. No parameter search was performed. Unknown RR and recovered shocks
are excluded before the 2 × 2 classification. Results therefore apply to this
observable subset, not to every shock: MBP-1 often cannot measure the anchored
price after the market starts reversing.

## Backtest results

One ES contract, $50 per point. Buy at observed ask and sell at observed bid;
subtract $5 round-trip fees. No additional slippage. At most one open position;
H1 and H2 use mutually exclusive signals.

| Period | Strategy | Trades | Net profit | Mean net/trade | Win rate | Max drawdown |
|---|---|---:|---:|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 937 | **−$9,172.50** | −$9.79 | 44.18% | $12,900.00 |
| Jan 10–Jun 30 | H2 reversal | 6 | **$95.00** | $15.83 | 33.33% | $235.00 |
| May–June | H1 continuation | 112 | **−$847.50** | −$7.57 | 41.96% | $1,787.50 |
| May–June | H2 reversal | 0 | **$0.00** | — | — | $0.00 |

January 10–April 30 alone: H1 had 825 trades and **−$8,325.00** net; H2 had 6 trades and **$95.00** net. The full-period rows include these development observations. The script also prints gross profit and total fees.

![Regime counts and profit](results.png)

**Checking the predicted price direction (before costs):**

| Period | Hypothesis | Mean favorable move | 95% day-bootstrap interval | Active days |
|---|---|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 0.82 ticks | [-0.69, 2.41] ticks | 97 |
| Jan 10–Jun 30 | H2 reversal | 2.92 ticks | [-7.50, 14.50] ticks | 6 |
| May–June | H1 continuation | 0.86 ticks | [-0.96, 2.69] ticks | 35 |
| May–June | H2 reversal | — | — | 0 |

A dash means no estimate is available because there were no trades.

**H1 continuation:** −$9,172.50 net over the full period (937 trades), and −$847.50 in May–June (112 trades). The May–June interval includes zero, so it does not establish a positive mean move in the predicted direction.

**H2 reversal:** $95.00 net over the full period (6 trades), and $0.00 in May–June (0 trades). There were no May–June trades, so the hypothesis cannot be tested in that period. The six full-period trades have a wide interval spanning zero: insufficient evidence for H2.

## Metrics and calculations

- **Net profit:** `side × (exit price − entry price) × $50 − $5` per trade;
  side is +1 for a buy and −1 for a sell. Execution prices already include spread.
- **Win rate:** percentage of trades with positive net profit.
- **Max drawdown:** largest peak-to-trough fall in cumulative realized net profit,
  starting from zero; it excludes unrealized intratrade losses.
- **Favorable price move:** midpoint change over the holding period in the trade’s
  predicted direction, divided by 0.25 to express ticks. Positive supports H1/H2.
- **95% interval:** 5,000 bootstrap resamples of entire active trading days,
  using seed 0. An interval spanning zero is inconclusive about mean direction.
  A positive mean move can still be unprofitable after spread and fees.

OFI uses the following quote changes for each update. Add the bid and ask
contributions to get `e`, then calculate
`OFI = shock_direction × sum(e) / sum(abs(e))`, or zero if the denominator is zero.

| Price change | Bid contribution | Ask contribution |
|---|---|---|
| Rises | Current bid quantity | Previous ask quantity |
| Unchanged | Current − previous bid quantity | Previous − current ask quantity |
| Falls | Negative previous bid quantity | Negative current ask quantity |

`shock_direction` is +1 for an up-shock, −1 for a down-shock. OFI is in [-1, 1].
A threshold of 0.05 requires net pressure greater than 5% of total absolute
quote-flow activity. This is not the static bid-versus-ask quantity ratio.

## Run and data

```sh
python -m pip install pandas numpy matplotlib
python backtest.py
```

Five files, no subfolders: `backtest.py`, `events.csv`, `README.md`, `results.png`,
and the requested `shocks.png` illustration. The script recalculates RR and OFI
and the recovery filter from the included observations, prints results, and updates
`results.png`. The shock illustration is included separately.

The CSV keeps `anchor_price` and `depth_at_shock` at t0, `best_price_after`
and `best_depth_after` at +3 seconds, and `pre_shock_mid` plus the minimum/maximum
midpoint across the observation window. These let the script calculate the
same-price RR and detect even a temporary full recovery. OFI uses the saved
`ofi_sum` and `ofi_abs_sum`. Entry/exit quotes support the profit calculation.

Validation independently checked all 943 trades, shock calibration, quote-side prices, fees, timing and non-overlap. Synthetic cases check both price directions, hidden versus depleted depth, and a recovery that occurs before the window ends. A raw-quote audit checks every event on January 10.

The calibration uses five sessions; the backtest covers the remaining **117 full sessions**. There are **3,900 detected shocks**, **3,897 valid feature events** (3,329 January–April; 568 May–June), and **3,861 events with complete execution windows**. Across all events, 45 are excluded for recovery; another 1,736 have unknown RR. These exclusion counts do not overlap. Of 952 qualifying H1/H2 events, 9 lack valid execution windows, leaving **943 trades**.

The May–June 2×2 feature-event counts are 115 slow/same, 1 slow/reversing, 0 fast/same and 0 fast/reversing, plus 191 neutral events, 253 unknown-RR exclusions, and 8 recovered-shock exclusions. These counts precede execution exclusions.

Data: local Databento GLBX.MDP3 ES.v.0 MBP-1 quotes. Holidays and half-days are
excluded. Invalid/crossed quotes, contract changes, gaps over one second, and
insufficient displayed execution size exclude affected trades. No new paid
download was needed. `events.csv` contains prepared observations and execution
quotes; reproducing the full raw-data scan is outside this small script.

This is an exploratory revision prompted by previously seen results. May–June
is shown separately, but is **not a new untouched holdout**. More trades do not
by themselves establish an edge. The earlier fixed-old-price definition and
pipeline remain in [Git history](https://github.com/kevinyua12138/FINM-37000-FP/tree/0f95fc222aeceb2eae059e0e16135ef1f3881bbc).
