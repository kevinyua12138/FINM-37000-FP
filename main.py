"""Generate the project's 2025 ES calendar without an API key."""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from data.calendar import FIELDS, build_calendar  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-01", help="inclusive Chicago date")
    parser.add_argument("--end", default="2025-12-31", help="inclusive Chicago date")
    parser.add_argument("--output", type=Path, default=Path("data/processed/calendar_2025.csv"))
    parser.add_argument("--actual-roll-date", action="append", default=[],
                        help="resolved ES.v.0 transition date; repeat for multiple rolls")
    args = parser.parse_args(argv)
    try:
        rows = build_calendar(args.start, args.end, actual_roll_dates=args.actual_roll_date)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} calendar days to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
