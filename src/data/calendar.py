"""Offline ES calendar flags for Chicago calendar dates in 2025.

Schedules and conventions are documented in docs/calendar.md. This module
labels days; it does not filter ticks or infer volume-based contract rolls.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")


def _dates(values):
    return frozenset(date.fromisoformat(f"2025-{value}") for value in values.split())


ROLL_DATES = _dates("03-17 06-16 09-15 12-15")
CPI_DATES = _dates("01-15 02-12 03-12 04-10 05-13 06-11 07-15 08-12 09-11 10-24 12-18")
NFP_DATES = _dates("01-10 02-07 03-07 04-04 05-02 06-06 07-03 08-01 09-05 11-20 12-16")
FOMC_DATES = _dates("01-29 03-19 05-07 06-18 07-30 09-17 10-29 12-10")
HOLIDAYS = {
    date(2025, 1, 1): "New Year's Day",
    date(2025, 1, 9): "National Day of Mourning",
    date(2025, 1, 20): "Martin Luther King Jr. Day",
    date(2025, 2, 17): "Presidents Day",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 26): "Memorial Day",
    date(2025, 6, 19): "Juneteenth",
    date(2025, 7, 4): "Independence Day",
    date(2025, 9, 1): "Labor Day",
    date(2025, 11, 27): "Thanksgiving",
    date(2025, 12, 25): "Christmas",
}
# Early-close dates, including shortened holiday sessions. A half-day flag
# means an early close, not necessarily half of the project's RTH window.
HALF_DAYS = _dates("01-09 01-20 02-17 05-26 06-19 07-03 07-04 09-01 11-27 11-28 12-24")
FIELDS = (
    "date", "is_weekend", "is_roll_day", "is_actual_roll_day", "is_holiday",
    "holiday_name", "is_half_day", "is_cpi_day", "is_nfp_day", "is_fomc_day",
    "is_macro_day",
)


def chicago_date(value):
    """Interpret dates literally and convert aware timestamps to Chicago.

    Naive timestamps are rejected: callers must explicitly supply a timezone.
    Plain ISO dates are already Chicago dates and require no conversion.
    """
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone or UTC offset")
        value = value.astimezone(CHICAGO).date()
    if not isinstance(value, date):
        raise TypeError("Expected a date, aware datetime, or ISO date/timestamp")
    if value.year != 2025:
        raise ValueError("Calendar supports 2025 only")
    return value


def flags_for_day(value, *, actual_roll_dates=()):
    """Return independent boolean flags; overlapping events retain all flags.

    actual_roll_dates must come from the team's resolved Databento ES.v.0
    mapping. Empty input means no observed rolls were supplied, not that the
    continuous contract did not roll.
    """
    day = chicago_date(value)
    actual = {chicago_date(item) for item in actual_roll_dates}
    cpi, nfp, fomc = day in CPI_DATES, day in NFP_DATES, day in FOMC_DATES
    return dict(zip(FIELDS, (
        day.isoformat(), day.weekday() >= 5, day in ROLL_DATES, day in actual,
        day in HOLIDAYS, HOLIDAYS.get(day, ""), day in HALF_DAYS,
        cpi, nfp, fomc, cpi or nfp or fomc,
    )))


def build_calendar(start="2025-01-01", end="2025-12-31", *, actual_roll_dates=()):
    """Build an inclusive range, retaining weekends and holidays for joins."""
    start, end = chicago_date(start), chicago_date(end)
    if start > end:
        raise ValueError("Start must be on or before end")
    actual = tuple(chicago_date(item) for item in actual_roll_dates)
    return [flags_for_day(start + timedelta(days=i), actual_roll_dates=actual)
            for i in range((end - start).days + 1)]
