# Imbalance and microprice features (issue #7)

`src/features/imbalance.py` provides vectorized, row-local snapshot features for
Databento decoded `mbp-1` or `mbp-10` DataFrames. It uses pandas and numpy from
`requirements.txt` and performs no downloads. Each input row produces one output
row with the same index (including duplicate labels). The input is not modified.

## Definitions for team review

Issue #7 names features but leaves the equations open. This implementation uses
the following explicit conventions; in particular DS is a proposed definition
for review, not a claim that there is a universal depth-slope convention.
Let b_i/a_i be bid/ask prices and B_i/A_i their displayed quantities, with i=0
at the best quote, m=(b_0+a_0)/2, and N=`levels` (default 10).

| Output | Formula | Units / sign |
| --- | --- | --- |
| I_1 | (B_0 - A_0) / (B_0 + A_0) | [-1, 1]; positive means more bid quantity |
| I_N | (sum B_i - sum A_i) / (sum B_i + sum A_i), first N levels | [-1, 1]; positive means more bid depth |
| microprice | (a_0 B_0 + b_0 A_0) / (B_0 + A_0) | Price units; opposite-price weighting |
| G | microprice - m | Price units; positive is above midpoint |
| DS | bid depth slope - ask depth slope | Contracts per tick; positive means bid depth accumulates faster |

For each side, regress cumulative quantity through each level on outward price
distance from that side's best quote, measured in ticks, **with an intercept**.
The OLS coefficient is the side's depth slope. Actual price distances are used,
so gaps in the ladder are supported. DS requires at least two levels. With two
adjacent levels DS equals B_1-A_1 contracts per tick. Quantities at the best quote
affect the intercept, not the slope. DS is not normalized or shock-direction
signed. This convention is deliberately distinct from I_N and should be agreed
with teammates before downstream regime analysis.

## Inputs and invalid data

Columns follow the existing download/notebook convention: `bid_px_00`,
`ask_px_00`, `bid_sz_00`, `ask_sz_00`, and similarly `01` through `09` for depth.
Prices must already be decoded into ordinary price units, not Databento's raw
fixed-point integer representation. ES tick size defaults to 0.25.

- Top-of-book columns are required; absent columns raise ValueError.
- Missing deeper columns produce NaN I_N and DS. Available top features remain
  valid. Use `levels=1` for mbp-1 to get I_N=I_1; DS is then NaN. No depth is
  fabricated, zero-filled, or silently reduced to fewer levels.
- Nonfinite/nonpositive/off-tick prices, locked/crossed books, negative or
  nonfinite quantities, and zero total best-quote quantity invalidate that row's
  top features and depth features. A single zero side quantity is allowed.
- Invalid/missing deeper observations and nonmonotonic/duplicate ladder prices
  invalidate depth features only. Zero individual deeper quantities are allowed.
- Non-numeric values are treated as missing. Invalid N (outside 1–10) or tick
  sizes raise ValueError. No resampling, forward fill, event window aggregation,
  trading-hour filtering, or contract stitching is performed here.

## Usage

From the repository root:

```python
import sys
sys.path.insert(0, "src")
from features import book_features

# df is the team's cleaned decoded snapshot frame; no time-column requirement.
features = book_features(df, levels=1)  # mbp-1
# For real depth data, request exactly the available intended depth:
depth_features = book_features(depth_df, levels=10)
# Positional assignment preserves duplicate timestamps without a many-to-many join.
with_features = df.copy()
with_features[features.columns] = features.to_numpy()
```

These are book snapshots, not trade-flow measures or the eventual three-second
event summaries. The issue #3 cleaning pipeline is not present on main at the
time of this change, so the interface uses the existing Databento schema and
validates book rows locally. No paid data is needed to run the synthetic tests:

```sh
python3 -m unittest discover -s tests -v
```

Tests cover hand-calculated values, balanced books, unequal level spacing,
full ten-level books, missing depth, invalid quotes/sizes, zero quantities,
index alignment, empty frames, and parameter/schema errors.
