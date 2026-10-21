# Implementation and figure plan — 2026-10-21

This is a proposed coordination plan and implementation record, not minutes of
a meeting. Owners below are suggested from the existing team roles; no GitHub
assignments or messages have been made on their behalf.

| Week / work | Proposed owner | Deliverable |
|---|---|---|
| Week 1: #8 order flow; #9 refill | Kevin / Simon | Formula review, tested features; retain the existing refill branch |
| Week 1: #10 event study | Simon | Regime definition, counts and in-sample average paths |
| Week 2: #11 statistics | Jackie | Day-clustered table and regression |
| Week 2: #12 execution engine | Kevin | Trade list, realistic spread/fees and metrics |
| Week 3: #13 held-out evaluation | Kevin / Simon | Frozen-rule May–June evaluation and coverage audit |
| Week 3: #14 sensitivity checks | Jackie / Simon | One robustness table with all predeclared scenarios |
| Week 3: #15 logistic extension | Jackie | Training-only fit, held-out AUC/calibration/backtest |
| Week 4: #16 optional depth sample | Kevin | Obtain approved mbp-10 sample; compare I_5/I_10 and RR_10 |
| Week 4: #17 write-up | Yash / Simon | Findings, limitations, reproducible commands and figures |

The current implementation supplies the code and results for team review;
this schedule describes remaining review/presentation responsibilities rather
than claiming four weeks of meetings occurred.

## Figures for the final write-up

1. Coverage and exclusions table: dates, raw/invalid records, shocks and usable events.
2. In-sample mean price paths by the four refill/flow regimes.
3. Regime return table at 5, 30 and 120 seconds, with day-clustered uncertainty.
4. Development and held-out cumulative P&L, clearly separated.
5. Sensitivity table for timing, costs, refill cutoff, direction and special days.
6. Held-out logistic calibration plot alongside AUC and model P&L.
7. Optional mbp-10 comparison, only after real depth data is available.

See `docs/research_spec.md` for the frozen definitions and `results/full_2025/`
for generated tables. Automated implementation does not establish that a strategy
is profitable or that its market-mechanism interpretation is correct.
