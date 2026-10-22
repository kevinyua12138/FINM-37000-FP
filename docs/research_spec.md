# Frozen research specification

This implementation follows issues #3–#17 and the discussion on #5, #6, #8,
#9, #10 and #12. It incorporates the detector from `issue-5-shock-detector`,
the refill module from `issue-9-replenishment`, and the calendar, labels and
book features already on main. No threshold is selected by looking at test P&L.

## Sample and clock

- Databento GLBX.MDP3, `ES.v.0`, **mbp-1**. Process one full session at a time.
- Chicago 08:30 inclusive to 15:00 exclusive. Exclude calendar holidays and
  half-days entirely; the policy is consistent across training and testing.
- Develop on January–April 2025; evaluate the frozen rule on May–June 2025.
- The first five sessions are threshold history only. On every later day the
  shock threshold uses the previous five completed retained sessions. Updating
  this rolling statistic during May–June is part of the frozen algorithm.
- Raw receive timestamps retain the 100 ms timing. The one-second grid uses
  only the last quote at or before the grid timestamp. Never use an interval's
  ending quote at its starting timestamp.
- Reject invalid/off-tick/locked/crossed quotes. Preserve invalid rows as
  barriers. Quotes older than one second cannot fill a grid point. Ten-second
  shock windows cannot bridge missing seconds or contract changes.
- Exclude feature/holding windows containing invalid quotes, contract changes,
  or gaps longer than one second. Report these exclusions in coverage counts.
- Flag both scheduled roll dates and observed changes in `instrument_id` between
  consecutive retained sessions. This does not substitute scheduled rolls for
  the volume-based continuous contract mapping.

## Events and features

A shock is an absolute ten-second midpoint change strictly greater than the
past-five-session 99.5th percentile. The existing detector works in price points;
export `size_ticks` and `threshold_ticks` by dividing by 0.25. This conversion
does not change which events pass. Cooldown is 120 seconds from each accepted
shock, including shocks later rejected by feature-quality checks.

Observe features in `(t0, t0 + 3 seconds]`. The quote at `t0` initializes the
book state; it is not a new order-flow update in the observation window.

**OFI:** use the existing prototype's Cont-style best-quote increment:

```
e = 1[b >= b_prev] B - 1[b <= b_prev] B_prev
    - 1[a <= a_prev] A + 1[a >= a_prev] A_prev
OFI = shock_direction * sum(e) / sum(abs(e))
```

Set OFI to zero when there are no changes. Positive means flow in the shock
direction; negative means reversing flow. This is quote flow, not trade volume.

**TI:** within the window, use `action == 'T'` trades, with `side == 'B'` as buy
aggressor and `side == 'A'` as sell aggressor. TI is shock-direction-signed
`(buy_volume - sell_volume) / (buy_volume + sell_volume)`. No known-side trades
means zero. Missing trade fields means NaN, never fabricated volume. Unknown-side
trades are excluded. [Databento schema reference](https://databento.com/docs/schemas-and-data-formats).

**RR and half-life:** retain the team's #9 implementation. X is the eaten-side
best price at `t0 - 10s`; D_pre is its displayed size. RR is D(end)/D_pre. While
the best price equals X, use its displayed size; when price moves past X in the
shock direction, use zero; when it returns through X, use D_pre. Half-life is
the first elapsed time RR reaches 0.5; no recovery within three seconds is
right-censored, reported as missing rather than as zero. A zero denominator
invalidates RR. The discussion's numerical example, 250/400, is 0.625.

This **mbp-1 proxy partly measures price recovery**. It cannot establish actual
order replenishment at hidden levels or distinguish new orders from the price
returning to existing liquidity. Do not interpret it as direct evidence of an
information-driven versus liquidity-driven shock.

Snapshot I_1 and G use the existing `book_features` at the observation endpoint,
signed by shock direction. `depth_features` separately supports real mbp-10
I_5/I_10 and aggregate refill over the ten pre-shock price levels. Unseen levels
outside the current ten-level ladder are NaN. It is not used to fabricate depth
from mbp-1.

## Rule and execution

The cutoffs are fixed by interpretation, not fitted medians: fast refill means
RR >= 0.5. Same-direction flow means OFI > 0; reversing flow means OFI < 0.

| Refill / flow | Same direction | Reversing |
|---|---|---|
| Slow (RR < 0.5) | Follow the shock | No trade |
| Fast (RR >= 0.5) | No trade | Fade the shock |

Zero OFI or invalid RR means no trade. In particular, a zero median RR does not
make zero recovery count as fast refill.

Enter one ES contract at the first valid quote at or after `t0 + 3.1s`.
The 5/30/120-second horizons start at the **actual entry timestamp**, including
any delay to the available quote. This also corrects the original label helper's
use of the scheduled timestamp when its next quote arrived later.

Buy at the ask, sell at the bid, and use the opposite side at exit. Displayed
quantity must cover the one contract. Use a $50 multiplier per price point and
an illustrative $2.50 fee per side ($5 round trip). The spread is already in
the executed prices and is not subtracted again. Base-case added slippage is
zero; show one tick per side as a stress scenario. There is no queue model,
market impact, or guarantee that these quotes would have been executable live.

Allow only one position at a time. Ignore signals whose entry is at or before
the current position's exit. Do not force trades through missing/stale exits.

## Statistics, robustness, and the model

- Regime tables: counts, mean signed midpoint return in basis points, day-clustered
  standard errors, t-statistics and 95% confidence intervals. No independence
  assumption for multiple shocks on the same day. Fewer than two days gives no SE.
- In-sample OLS: signed 30s return on OFI, RR, their interaction, I_1, and shock
  size; standard errors clustered by day. Association is not causal identification.
- Backtest: trade list, midpoint/gross/net dollar P&L, win rate, drawdown from an
  initial zero P&L, and daily P&L Sharpe including zero-trade sessions. The latter
  is a diagnostic ratio, not a return-on-capital Sharpe. No arbitrary capital or
  percentage return is invented.
- Break-even round-trip fee equals mean gross P&L after observed spread, before
  fees and additional slippage. A negative value means spread alone is too costly.
- Predeclared sensitivity table: 5/30/120s horizons, 100/500ms latency, $0/$2.50/$5
  per-side fees, one tick slippage per side, RR cutoffs .25/.5/.75, excluding macro
  or roll days, upward/downward shocks, and always-follow/always-fade baselines.
  These are sensitivity descriptions, not candidates for picking a new winner on
  the held-out data. Re-testing a newly chosen strategy needs a new holdout.
- Logistic model: standardize OFI, RR, I_1, G, size using training observations
  only; fit fixed L2 logistic regression (C=1). Outcome is positive signed 30s
  return; zero returns are non-continuation. Follow if p >= .55, fade if p <= .45,
  otherwise no trade. Report held-out AUC, Brier score, five-bin calibration and
  cost-aware P&L. Missing features/labels are excluded and counts are reported.
- The rule/config and model coefficients are saved. No hyperparameter search.

## Running it

```
python -m pip install -r requirements.txt
python -m pytest -q
python download_project.py --dry-run
python download_project.py --budget 0
python run_backtest.py --output results/full_2025
```

Use `DATABENTO_API_KEY` or `~/.databento_api_key`; never put a key in this repo.
The downloader checks a total-cost upper bound before downloading. Default
budget is $0. Existing complete files are reused and interrupted `.part` files
are retried. It streams daily requests with bounded concurrency. Private raw
quotes and derived Parquet caches stay under ignored `data/`; only derived event
and trade summaries are committed. The run requires every expected regular
session and saves a code digest, coverage, frozen configuration and figures.

## Simple refill comparisons

Alongside the existing refill/OFI rule, report two predeclared alternatives at
30 seconds, using the same shock detector and three-second observation:

1. **High-refill fade:** fade only when RR >= 0.5; otherwise stay out.
2. **Refill plus book imbalance:** follow when RR < 0.5 and endpoint book
   imbalance points in the shock direction; fade when RR >= 0.5 and it opposes
   the shock. Otherwise stay out.

“High refill” refers to RR, not an additional large-order-size filter. The
99.5th percentile defines the ten-second price shock, not the refill ratio or
a literal 99.5% price move. The alternative rule results are saved in
`simple_rules.csv` and `simple_rule_trades.csv`. No choice among these rules is
made using held-out P&L; an isolated positive result needs independent validation.

The OFI increment follows [Cont, Kukanov and Stoikov, The Price Impact of Order
Book Events](https://arxiv.org/abs/1011.6402). The project's normalization by
sum of absolute increments and its shock-direction sign are additional explicit
conventions. Their equity-market evidence does not establish profitability for
this ES futures strategy.
