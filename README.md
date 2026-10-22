# Sweep or Snap Back? H1 continuation and H2 reversal

![When the fixed-threshold price shocks happen](shocks.png)

The triangles mark **19 shocks on January 10**. A shock is a 10-second midpoint
move **greater than 4 points (16 ticks)**. “99.5%” means the **99.5th percentile**
of historical move sizes, not a 99.5% return.

## Fixed threshold and timing

The 4-point cutoff is calculated **once**, using January 2, 3, 6, 7, and 8,
and stays fixed for the entire January 10–June 30 backtest. These five days are
calibration data only. A **session** means one trading day, 08:30–15:00 Chicago
time. **Three seconds** means the observation window after a shock; it does
not mean three sessions. There is no moving threshold in this version.

Check for shocks each second, with a 120-second cooldown. After a shock at `t0`,
observe through `t0 + 3 seconds`, enter at the first eligible quote at/after
`t0 + 3.1 seconds`, and exit 30 seconds after the actual entry.

## A more generous refill ratio, with examples

**RR = current best-quote quantity after observation / best-quote quantity before the shock.**

- For an **up-shock**, compare ask quantity at `t0 + 3s` with ask quantity at `t0 − 10s`.
- For a **down-shock**, compare bid quantities at those times.
- The quote prices **may differ**. RR < 0.5 is slow; RR >= 0.5 is fast.

| Quantity before | Quantity after | RR | Classification |
|---:|---:|---:|---|
| 100 contracts | 20 contracts | 0.20 | Slow: 20% of the original depth is displayed |
| 100 contracts | 60 contracts | 0.60 | Fast: 60% is displayed |
| 100 contracts | 140 contracts | 1.40 | Fast: displayed depth exceeds its original size |

For example, an up-shock can move the ask from 6000 to 6004. If ask quantity
changes from 100 to 60, the **new RR is 0.60**. The old measure would generally
record zero because it required quantity at the old 6000 price. We relaxed
that price requirement while keeping the 0.5 cutoff.

This is a **displayed-depth recovery proxy**. A different price level can already
have resting orders, so it does not prove that new orders refilled the consumed
level. The interpretation changes along with the definition; it is not merely
a lower cutoff for the old measure.

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
For example, an up-shock with RR=0.20 and OFI=+0.12 triggers H1 (buy);
RR=0.60 and OFI=−0.10 triggers H2 (sell). RR=0.60 with OFI=+0.12 does not trade.
The 0.5 refill and 0.05 flow cutoffs were fixed before this revised run, without
searching for the most profitable combination.

## Backtest results

One ES contract, $50 per point. Buy at observed ask and sell at observed bid;
subtract $5 round-trip fees. No additional slippage. At most one open position;
H1 and H2 use mutually exclusive signals.

| Period | Strategy | Trades | Net profit | Mean net/trade | Win rate | Max drawdown |
|---|---|---:|---:|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 124 | **$2,092.50** | $16.88 | 50.81% | $1,520.00 |
| Jan 10–Jun 30 | H2 reversal | 629 | **$-12,670.00** | $-20.14 | 43.56% | $16,505.00 |
| May–June | H1 continuation | 13 | **$-327.50** | $-25.19 | 38.46% | $647.50 |
| May–June | H2 reversal | 52 | **$-2,435.00** | $-46.83 | 34.62% | $2,462.50 |

January 10–April 30 alone: H1 had 111 trades and **+$2,420** net; H2 had 577 trades and **−$10,235** net. The full-period rows include these development observations. The script also prints gross profit and total fees.

![Regime counts and profit](results.png)

**Checking the predicted price direction (before costs):**

| Period | Hypothesis | Mean favorable move | 95% day-bootstrap interval | Active days |
|---|---|---:|---:|---:|
| Jan 10–Jun 30 | H1 continuation | 3.05 ticks | [1.18, 4.86] ticks | 44 |
| Jan 10–Jun 30 | H2 reversal | 0.05 ticks | [-2.06, 2.15] ticks | 86 |
| May–June | H1 continuation | -0.50 ticks | [-5.31, 4.13] ticks | 11 |
| May–June | H2 reversal | -2.23 ticks | [-5.07, 0.17] ticks | 24 |

**H1:** positive over the full period, driven by January–April, but the May–June mean move is negative and its interval includes zero. The continuation hypothesis does not hold up convincingly in the later sample, which has only 13 trades.

**H2:** the broader rule now produces **629 full-period trades and 52 May–June trades**, compared with one May–June trade in the previous version. The new mean-move intervals include zero, and net profits are negative. More observations do not establish profitable reversal. The fixed shock threshold and OFI cutoff also changed, so the versions differ in more than refill alone.

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

Validation checked the fixed calibration threshold, all 753 trades, signal selection,
quote-side executions, timing, costs, and non-overlapping positions. On 686 shared
shocks, quote features and execution prices match the earlier full-day pipeline.

Five files, no subfolders: `backtest.py`, `events.csv`, `README.md`, `results.png`,
and the requested `shocks.png` illustration. The script recalculates RR and OFI
from the included quantities and flow sums, prints results, and updates
`results.png`. The shock illustration is included separately.

The calibration uses five sessions; the backtest covers the remaining **117 full sessions**. There are **2,890 detected shocks**, **2,888 valid feature events** (2,533 January–April; 355 May–June), and **2,860 events with complete execution windows**. Four qualifying H2 events lack valid execution windows, leaving **753 trades** across H1 and H2.

Among the 355 May–June events, the broader RR is fast in 282 cases; the old fixed-price proxy is fast in only two on these same shocks. With the ±0.05 flow criterion, the 2×2 counts are 13 slow/same, 16 slow/reversing, 70 fast/same and 54 fast/reversing, plus 202 neutral events. H2 executes 52 of its 54 qualifying events.

Data: local Databento GLBX.MDP3 ES.v.0 MBP-1 quotes. Holidays and half-days are
excluded. Invalid/crossed quotes, contract changes, gaps over one second, and
insufficient displayed execution size exclude affected trades. No new paid
download was needed. `events.csv` contains prepared observations and execution
quotes; reproducing the full raw-data scan is outside this small script.

This is an exploratory revision prompted by previously seen results. May–June
is shown separately, but is **not a new untouched holdout**. More trades do not
by themselves establish an edge. The earlier fixed-old-price definition and
pipeline remain in [Git history](https://github.com/kevinyua12138/FINM-37000-FP/tree/0f95fc222aeceb2eae059e0e16135ef1f3881bbc).
