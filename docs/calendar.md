# 2025 ES roll and event calendar (issue #4)

Run from the repository root with Python 3.9 or newer. No dependencies, network
access, Databento API key, or paid data request are needed for this command:

```sh
python3 main.py
python3 main.py --start 2025-01-01 --end 2025-06-30 --output data/processed/calendar_h1.csv
python3 -m unittest discover -s tests -v
```

The default output is `data/processed/calendar_2025.csv`. Generated files are
ignored by Git under the existing `data/*` rule. The command overwrites its
chosen output. Dates are inclusive; all 365 dates, including weekends, are
retained so downstream joins do not silently lose observations. Only 2025 is
supported; invalid dates, reversed ranges, and unsupported years fail explicitly.
CSV boolean values are `True` and `False`.

## Flag definitions

| Column | Meaning |
| --- | --- |
| date | Chicago calendar date, YYYY-MM-DD |
| is_weekend | Saturday or Sunday |
| is_roll_day | CME's published quarterly U.S. equity index roll date |
| is_actual_roll_day | A transition date supplied by the caller from the resolved ES.v.0 mapping |
| is_holiday / holiday_name | ES holiday or special mourning day and its name; does **not** imply a full Globex closure |
| is_half_day | Scheduled early close, including abbreviated holiday sessions; does **not** mean exactly half of 08:30–15:00 |
| is_cpi_day | Actual BLS CPI release date |
| is_nfp_day | Actual BLS Employment Situation release date |
| is_fomc_day | Scheduled FOMC policy announcement day, the second meeting day |
| is_macro_day | CPI, NFP, or FOMC announcement day |

Independent flags preserve overlapping events. For example July 3 is both an
NFP release day and an early-close day. October 13 and November 11 are not ES
holiday flags: a generic federal holiday calendar is inappropriate here.
January 9 is flagged as a holiday and early close: CME equities closed at
08:30 CT, so there is no usable 08:30–15:00 project window that day.

This is a **day-label calendar**, not a complete exchange session scheduler.
Do not treat `is_holiday` as `market_closed`, use these flags to infer exact close
times, or automatically discard all holiday data. Good Friday has no project
RTH window, while several other holidays have abbreviated futures trading.
Exact intraday holiday filtering and unscheduled outages require exchange
session records. CPI/NFP generally occur before the configured RTH window;
the flags label the whole date, not an event exclusion window. FOMC minutes
and the first meeting day are not announcement flags.

## Join flags onto downloaded observations

For the team's regular-hours data, convert UTC timestamps to Chicago **before**
joining on date. The API also accepts aware ISO timestamps and aware datetimes:

```python
# From the repository root, or after adding src to your Python path:
import sys
sys.path.insert(0, "src")
from data.calendar import flags_for_day, build_calendar

print(flags_for_day("2025-06-12T00:30:00Z"))  # Chicago date June 11: CPI day

# With a pandas frame df containing ts_event:
import pandas as pd
calendar = pd.DataFrame(build_calendar()).set_index("date")
df["calendar_date"] = (
    pd.to_datetime(df["ts_event"], utc=True)
    .dt.tz_convert("America/Chicago").dt.strftime("%Y-%m-%d")
)
df = df.join(calendar, on="calendar_date", validate="many_to_one")
```

The date API rejects naive timestamps instead of guessing their timezone.
Plain dates are interpreted as Chicago dates. Overnight Globex trading needs
a separate exchange trade-date mapping; Chicago midnight is appropriate only
for the current project's daytime observations. Restrict input to 2025 and
check for missing calendar joins if working with other years.

## Roll convention and dependency on issue #2

CME's scheduled roll dates are March 17, June 16, September 15, and December 15.
These are not the expiration dates and are not asserted to be the actual
transitions of the configured **volume-based** Databento `ES.v.0` series.
The calendar is available before downloading data. Once issue #2's downloads
and Databento symbology mapping are available, pass each date where the resolved
instrument changes as `actual_roll_dates` to the Python API, or repeat
`--actual-roll-date YYYY-MM-DD` on the command line. The supplied dates flag
`is_actual_roll_day` independently of `is_roll_day`. No actual transitions are
invented; without supplied mapping dates that column is all False. If actual
rolls matter to the analysis, supply the mapping before interpreting this column.

## Sources and historical corrections

The static 2025 schedule is maintained in `src/data/calendar.py`, making runs
reproducible and reviewable offline. Consult these primary sources when updating:

- [CME equity index roll dates](https://www.cmegroup.com/trading/equity-index/rolldates.html).
- [CME Globex holiday schedules](https://www.cmegroup.com/trading-hours.html): use the 2025 date and equity index product, rather than the current year's table or a trading-floor/settlement schedule. Early-close flags cover January 9/20, February 17, May 26, June 19, July 3/4, September 1, November 27/28, and December 24.
- [CME January 9 mourning-day announcement](https://www.cmegroup.com/media-room/press-releases/2025/12/30/cme_group_announcestradinghoursforusnationaldayofmourningtohonor.html).
- [BLS actual 2025 release calendar](https://www.bls.gov/schedule/2025/): the shutdown moved September CPI to October 24 and September payrolls to November 20. November releases occurred December 18 (CPI) and December 16 (payrolls). No October CPI or standalone October Employment Situation release occurred; do not use a first-Friday heuristic or the originally planned release dates.
- [Federal Reserve meeting and policy statement calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm).

These labels describe the realized historical calendar. They are not a
point-in-time schedule suitable for simulating what traders knew before
shutdown rescheduling announcements. Tests cover year completeness, known
events, overlapping flags, scheduled versus actual rolls, Chicago dates across
winter/summer UTC offsets, invalid inputs, and the command-line CSV output.
