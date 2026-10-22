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
| 6004, with 5 contracts | 5 | 5 / 20 = 0.25: middle, no trade |
| 6004, with 40 contracts | 40 | 40 / 20 = 2.0: fast |
| 6004.25 | 0: no ask remains at 6004 | 0: slow |
| 6003.75 | Unknown: 6004 is behind the best ask | Missing: no trade |

For a down-shock, reverse the price comparisons and use bids: a best bid below
P means zero at P; a best bid above P hides P deeper in the book.
A smaller **quantity at the same price** gives a smaller ratio, not automatically zero.
Zero is used only when the quote has moved past P in the shock direction.

Use separate cutoffs: **H1 needs RR < 0.25; H2 needs RR >= 1.50**.
H1 requires less than 25% of the post-shock depth to remain; H2 requires at
least 150% of that depth (a 50% increase). **0.25 <= RR < 1.50 means no trade**.
RR exactly 0.25 does not qualify for H1; exactly 1.50 qualifies for H2 if flow reverses.
Unchanged depth gives RR = 1 and now means no trade. This ratio measures net
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
| **Slow refill: RR < 0.25** | **H1: follow** the shock | No trade |
| **Fast refill: RR >= 1.50** | No trade | **H2: fade** the shock |

H1 buys an up-shock and sells a down-shock. H2 does the opposite.
The table shows the two extremes; the middle RR range is excluded regardless
of flow. Unknown RR and already recovered shocks are also excluded.
Results apply to this observable subset: MBP-1 often cannot measure the anchored
price after the market starts reversing. Changing cutoffs cannot recover those events.

## Choosing the two thresholds

We specified exactly **two candidates per strategy before computing this comparison**:
H1 below 0.25 or 0.50 (strict versus moderate depletion); H2 at least 1.00 or
1.50 (full post-shock depth versus a 50% increase).

**Selection rule:** choose the highest total net profit, including spread and fees,
using **January 10–April 30 only**, separately for each strategy. If tied, choose
the stricter cutoff: lower for H1, higher for H2. Freeze the choices for May–June.
No additional cutoffs were tried after seeing these outcomes.

| Strategy | Candidate rule | January–April trades | January–April net profit | Choice |
|---|---|---:|---:|---|
| H1 | RR < 0.25 | 823 | −$8,252.50 | Selected |
| H1 | RR < 0.50 | 825 | −$8,325.00 |  |
| H2 | RR >= 1.00 | 3 | $235.00 |  |
| H2 | RR >= 1.50 | 3 | $235.00 | Selected |

**Selected: H1 < 0.25; H2 >= 1.50.** H1 loses $72.50 less than the 0.50 candidate
in January–April, but remains unprofitable. The two H2 candidates select the
**same three trades**, so 1.50 wins only by the stated tie-break; there is no
evidence that it performs better than 1.00. These are exploratory settings,
not established optimal thresholds. The tiny H2 sample cannot validate a cutoff.

Only the RR cutoffs changed. The fixed 99th-percentile shock cutoff, same-price
RR calculation, recovery filter, OFI cutoffs, entry/exit timing, and costs stay fixed.
May–June was examined in earlier revisions, so it is **not a fresh untouched
holdout**, even though this comparison does not use it for threshold selection.

## Backtest results

One ES contract, $50 per point. Buy at observed ask and sell at observed bid;
subtract $5 round-trip fees. No additional slippage. At most one open position;
H1 and H2 use mutually exclusive signals.

| Period | Strategy | Trades | Net profit | Mean net/trade | Win rate | Max drawdown |
|---|---|---:|---:|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 934 | **−$9,132.50** | −$9.78 | 44.11% | $12,907.50 |
| Jan 10–Jun 30 | H2 reversal | 3 | **$235.00** | $78.33 | 33.33% | $42.50 |
| May–June | H1 continuation | 111 | **−$880.00** | −$7.93 | 41.44% | $1,787.50 |
| May–June | H2 reversal | 0 | **$0.00** | — | — | $0.00 |

January 10–April 30 alone: H1 had 823 trades and **−$8,252.50** net; H2 had 3 trades and **$235.00** net. The full-period rows include these development observations. The script also prints gross profit and total fees.

![Regime counts and profit](results.png)

**Checking the predicted price direction (before costs):**

| Period | Hypothesis | Mean favorable move | 95% day-bootstrap interval | Active days |
|---|---|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 0.82 ticks | [-0.70, 2.42] ticks | 97 |
| Jan 10–Jun 30 | H2 reversal | 7.67 ticks | [-2.00, 27.00] ticks | 3 |
| May–June | H1 continuation | 0.83 ticks | [-1.02, 2.68] ticks | 35 |
| May–June | H2 reversal | — | — | 0 |

A dash means no estimate is available because there were no trades.

**H1 continuation:** −$9,132.50 net over the full period (934 trades), and −$880.00 in May–June (111 trades). The May–June interval includes zero, so it does not establish a positive mean move in the predicted direction.

**H2 reversal:** $235.00 net over the full period (3 trades), and $0.00 in May–June (0 trades). There were no May–June trades, so the hypothesis cannot be tested in that period. The 3 full-period trades have a wide interval spanning zero: insufficient evidence for H2.

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
  A positive mean move can still be unprofitable after spread and fees. These
  intervals describe the selected rules and do not adjust for threshold selection.

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

`H1_RR_MAX` and `H2_RR_MIN` at the top of the script document the fixed selected
cutoffs. `H1_CANDIDATES` and `H2_CANDIDATES` document the complete comparison.

Five files, no subfolders: `backtest.py`, `events.csv`, `README.md`, `results.png`,
and the requested `shocks.png` illustration. The script reproduces the four-candidate January–April comparison, recalculates
RR, OFI and the recovery filter, prints results, and updates
`results.png`. The shock illustration is included separately.

The CSV keeps `anchor_price` and `depth_at_shock` at t0, `best_price_after`
and `best_depth_after` at +3 seconds, and `pre_shock_mid` plus the minimum/maximum
midpoint across the observation window. These let the script calculate the
same-price RR and detect even a temporary full recovery. OFI uses the saved
`ofi_sum` and `ofi_abs_sum`. Entry/exit quotes support the profit calculation.

Validation independently checked all 937 trades, shock calibration, quote-side prices, fees, timing and non-overlap. Checks cover all four candidate results, training-only selection, tie-breaking, exact RR boundaries and the no-trade middle range. The preceding revision also audited same-price quantities and observation-window extrema against raw quotes on January 10; those CSV observations are unchanged.

The calibration uses five sessions; the backtest covers the remaining **117 full sessions**. There are **3,900 detected shocks**, **3,897 valid feature events** (3,329 January–April; 568 May–June), and **3,861 events with complete execution windows**. Across all events, 45 are excluded for recovery; another 1,736 have unknown RR. These exclusion counts do not overlap. Of 946 qualifying H1/H2 events, 9 lack valid execution windows, leaving **937 trades**.

The May–June 2×2 feature-event counts are 114 slow/same, 0 slow/reversing, 0 fast/same and 0 fast/reversing, plus 2 middle-RR events, 191 neutral events, 253 unknown-RR exclusions, and 8 recovered-shock exclusions. These counts precede execution exclusions.

Data: local Databento GLBX.MDP3 ES.v.0 MBP-1 quotes. Holidays and half-days are
excluded. Invalid/crossed quotes, contract changes, gaps over one second, and
insufficient displayed execution size exclude affected trades. No new paid
download was needed. `events.csv` contains prepared observations and execution
quotes; reproducing the full raw-data scan is outside this small script.

This is an exploratory revision prompted by previously seen results. May–June
is shown separately, but is **not a new untouched holdout**. More trades do not
by themselves establish an edge. The earlier fixed-old-price definition and
pipeline remain in [Git history](https://github.com/kevinyua12138/FINM-37000-FP/tree/0f95fc222aeceb2eae059e0e16135ef1f3881bbc).
