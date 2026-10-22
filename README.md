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

**RR = current best-quote quantity after observation / best-quote quantity before the shock.**

Imagine an upward price shock:

1. **Before the shock** (`t0 − 10s`): the best ask is 6000 with **100 contracts**.
2. **After observing for three seconds** (`t0 + 3s`): the best ask is now 6004 with **60 contracts**.
3. **RR = 60 / 100 = 0.60 = 60%.** Since RR >= 0.5, classify this as **fast refill**.

If order flow is also reversing (OFI < −0.05), this qualifies for **H2: sell**.
Fast refill by itself is not enough to trigger a trade.

For an up-shock use ask quantities; for a down-shock use bid quantities.
RR < 0.5 is slow and RR >= 0.5 is fast. Quote prices may differ. This measures
**displayed-depth recovery**, not necessarily newly submitted orders: the new
price level may already have had resting orders. The old fixed-price measure
would generally be zero in this example because the ask moved away from 6000.

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
unchanged from the prior run. Only the shock percentile changes from 99.5 to 99;
no search for the most profitable percentile was performed.

## Backtest results

One ES contract, $50 per point. Buy at observed ask and sell at observed bid;
subtract $5 round-trip fees. No additional slippage. At most one open position;
H1 and H2 use mutually exclusive signals.

| Period | Strategy | Trades | Net profit | Mean net/trade | Win rate | Max drawdown |
|---|---|---:|---:|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 172 | **$565.00** | $3.28 | 41.28% | $3,250.00 |
| Jan 10–Jun 30 | H2 reversal | 861 | **−$10,242.50** | −$11.90 | 44.72% | $10,595.00 |
| May–June | H1 continuation | 18 | **−$540.00** | −$30.00 | 27.78% | $540.00 |
| May–June | H2 reversal | 109 | **−$2,082.50** | −$19.11 | 42.20% | $2,607.50 |

January 10–April 30 alone: H1 had 154 trades and **$1,105.00** net; H2 had 752 trades and **−$8,160.00** net. The full-period rows include these development observations. The script also prints gross profit and total fees.

![Regime counts and profit](results.png)

**Checking the predicted price direction (before costs):**

| Period | Hypothesis | Mean favorable move | 95% day-bootstrap interval | Active days |
|---|---|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 1.87 ticks | [-2.04, 6.10] ticks | 61 |
| Jan 10–Jun 30 | H2 reversal | 0.65 ticks | [-0.28, 1.62] ticks | 99 |
| May–June | H1 continuation | -0.89 ticks | [-4.83, 1.70] ticks | 14 |
| May–June | H2 reversal | -0.06 ticks | [-1.20, 1.25] ticks | 33 |

**H1 continuation:** $565.00 net over the full period (172 trades), and −$540.00 in May–June (18 trades). The May–June interval includes zero, so it does not establish a positive mean move in the predicted direction.

**H2 reversal:** −$10,242.50 net over the full period (861 trades), and −$2,082.50 in May–June (109 trades). The May–June interval includes zero, so it does not establish a positive mean move in the predicted direction.

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
python -m pip install pandas matplotlib
python backtest.py
```

Validation independently checked all 1,033 trades, the fixed 99th-percentile
calibration, signals, execution timing, prices, costs, and non-overlap. The
features and fills match the prior run on 1,039 shared shocks.

Five files, no subfolders: `backtest.py`, `events.csv`, `README.md`, `results.png`,
and the requested `shocks.png` illustration. The script recalculates RR and OFI
from the included quantities and flow sums, prints results, and updates
`results.png`. The shock illustration is included separately.

The calibration uses five sessions; the backtest covers the remaining **117 full sessions**. There are **3,900 detected shocks**, **3,897 valid feature events** (3,329 January–April; 568 May–June), and **3,861 events with complete execution windows**. Of 1,038 qualifying H1/H2 events, 5 lack valid execution windows, leaving **1,033 trades**.

The May–June 2×2 feature-event counts are 18 slow/same, 32 slow/reversing, 98 fast/same and 111 fast/reversing, plus 309 neutral events. These counts precede execution exclusions.

Data: local Databento GLBX.MDP3 ES.v.0 MBP-1 quotes. Holidays and half-days are
excluded. Invalid/crossed quotes, contract changes, gaps over one second, and
insufficient displayed execution size exclude affected trades. No new paid
download was needed. `events.csv` contains prepared observations and execution
quotes; reproducing the full raw-data scan is outside this small script.

This is an exploratory revision prompted by previously seen results. May–June
is shown separately, but is **not a new untouched holdout**. More trades do not
by themselves establish an edge. The earlier fixed-old-price definition and
pipeline remain in [Git history](https://github.com/kevinyua12138/FINM-37000-FP/tree/0f95fc222aeceb2eae059e0e16135ef1f3881bbc).
