# Meeting 3 Notes

**Date:** 10/19/2026
**Attendees:** Kevin Yuan, Simon Jung, Jackie Guo, Yash Jain
**Next meeting:** Wednesday 10/21/2026, 7 PM, in person at the library

## What we did

- Checked in on where the project stands after phase 2. The forward-return labels (#6) and the imbalance and microprice features (#7) are merged, and Kevin's shock detector (#5) is open for review as PR #23.
- Agreed that our ideas so far have been fairly broad, and that it is time to make them concrete: fixed definitions, a fixed timeline, and a fixed list of the graphs that will end up in our final write-up.
- Agreed to put together a concrete timeline for the rest of the project, so that every member has an issue and a PR open well before each class, with enough time left for the rest of the team to review it.
- Went through the remaining open issues (#8 to #17) and their dependencies to see what can be worked on right away and what has to wait for earlier pieces.
- Set up an in-person meeting on Wednesday 10/21 at 7 PM in the library to go over the exact plan below and lock it in.

## Proposed timeline (to be finalized on Wednesday 10/21)

- **Oct 19 to 25 (Part 3):** Review and merge PR #23. Every member opens a PR on one open issue by Saturday 10/24, so there is time for review before class. Issues: #5, #8, #9.
- **Oct 26 to Nov 1 (Part 4):** Event study and 2x2 regime table on January to April 2025 (in-sample), with day-clustered statistics. Start the backtest. Issues: #10, #11, #12.
- **Nov 2 to 8:** Freeze the trading rules, run the out-of-sample test once on May to June 2025, and build the robustness table. Issues: #13, #14.
- **Nov 9 onward:** Write up the results, figures and limitations in the README. Stretch goals only if time allows. Issues: #17, then #15 and #16.

Proposed owners for Part 3 (to confirm on Wednesday):

- **Kevin:** #5 shock detector (PR #23 is already open).
- **Simon:** #8 order-flow features (trade imbalance and OFI), building on his #7 work.
- **Yash (me):** #9 liquidity replenishment (refill ratio and half-life), building on the #6 prototype.
- **Jackie:** open. Options are starting the #10 event-study plotting code on the prototype events, or #16 (mbp-10 depth), which would also help with the refill ratio problem below.
- **Everyone:** review PR #23 before Wednesday. Issue #7 can be closed, since PR #22 is merged.

## Graphs we will show

1. **Shocks per day:** a bar chart from the detector output (#5), to check that shocks are not bunched into a few days. In the #6 prototype, 56 of the 78 shocks fell on a single day (9/16).
2. **Average price path after a shock, by regime:** our main figure (#10). The mid-price move in the shock direction from the shock out to 120 seconds, with one line for each cell of the 2x2 table and a confidence band. Above zero means the move continued, below zero means it reversed.
3. **2x2 regime table:** the number of shocks and the mean 30-second return in each cell, with day-clustered t-stats (#10, #11).
4. **Refill ratio and half-life distributions:** histograms (#9). This one needs fixing first. With mbp-1 data the prototype refill ratio was 0 for 76 of the 78 shocks, so the median split put no shocks in the "slow refill" group. We need a new definition (Simon's open item from Meeting 2) before the 2x2 table means anything.
5. **OFI against the 30-second forward return:** a scatter plot with a fitted line (#8, #11), to see whether stronger same-direction pressure goes with continuation.
6. **Backtest P&L:** cumulative P&L after the spread and fees, in-sample next to out-of-sample, plus the break-even cost (#12, #13).
7. **Robustness table:** the headline result across different thresholds, horizons and cooldowns (#14).

## To decide on Wednesday

- The timeline above and who owns which issue.
- The refill ratio definition, given that mbp-1 only shows the best level (or whether we move to mbp-10).
- How to split slow/fast refill and strong/weak pressure: the median, or fixed cutoffs chosen on the in-sample data.
- The exact in-sample and out-of-sample split (January to April and May to June 2025, per #13).
- Which of the graphs above go in the final README.
