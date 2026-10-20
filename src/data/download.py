import argparse
import csv
import sys
import time
from datetime import date, datetime
from pathlib import Path

# Run as a script, Python puts src/data/ first on sys.path, where calendar.py (#4) shadows
# the standard-library calendar module that pandas imports. Swap it for src/, which also
# lets us import src/finm37000 and data.calendar.
SRC = Path(__file__).resolve().parents[1]
sys.path = [str(SRC)] + [p for p in sys.path if Path(p).resolve() != SRC / "data"]

import databento as db  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

RETRIES = 4  # after a failed download, wait 5, 10, 20, then 40 s before trying again


def get_client():
    try:
        from finm37000 import get_databento_api_key, temp_env
    except ImportError:
        return db.Historical()  # falls back to the DATABENTO_API_KEY env variable

    with temp_env(DATABENTO_API_KEY=get_databento_api_key()):
        return db.Historical()


def download_day(client, cfg, day, dry_run=False, schema=None):
    d, s = cfg["data"], cfg["session"]
    schema = schema or d["schema"]
    start = pd.Timestamp(f"{day} {s['download_start']}", tz=s["timezone"])
    end = pd.Timestamp(f"{day} {s['download_end']}", tz=s["timezone"])
    request = dict(
        dataset=d["dataset"],
        symbols=[d["symbol"]],
        stype_in=d["stype_in"],
        schema=schema,
        start=start,
        end=end,
    )

    path = Path(d["raw_dir"]) / f"ES_{schema}_{day}.dbn.zst"
    if path.exists():
        print(f"{path} already exists, skipping")
        return path

    cost = client.metadata.get_cost(**request)
    print(f"{day} {schema} {start:%H:%M}-{end:%H:%M %Z}: ${cost:.2f}")
    if dry_run:
        return None
    if cost > d["max_cost_usd"]:
        raise SystemExit(f"${cost:.2f} is over the ${d['max_cost_usd']:.2f} limit")

    path.parent.mkdir(parents=True, exist_ok=True)
    fetch(client, request, path)

    log = path.parent / "download_log.csv"
    is_new = not log.exists()
    with open(log, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "schema", "cost_usd", "downloaded_at"])
        writer.writerow([day, schema, round(cost, 4), datetime.now().isoformat(timespec="seconds")])

    print(f"saved {path}")
    return path


def fetch(client, request, path, retries=RETRIES, wait=5.0):
    """Stream one request to `path`, retrying broken or failed downloads.

    When a stream breaks, Databento leaves a half-written file behind, which the next
    run would skip as already downloaded. So data goes to a `.part` file that only gets
    its final name once the download completes.
    """
    part = path.with_name(path.name + ".part")
    for attempt in range(retries + 1):
        part.unlink(missing_ok=True)  # Databento will not overwrite an existing file
        try:
            client.timeseries.get_range(**request, path=part)
        except (db.BentoError, OSError) as err:  # broken stream, 5xx/429, network error
            part.unlink(missing_ok=True)
            bad_request = isinstance(err, db.BentoClientError) and err.http_status != 429
            if bad_request or attempt == retries:
                raise
            delay = wait * 2**attempt
            print(f"  download failed ({err}); retry {attempt + 1}/{retries} in {delay:.0f}s")
            time.sleep(delay)
        else:
            part.replace(path)
            return


def trading_days(start, end):
    """Weekdays from start to end (inclusive), skipping holidays flagged by the #4 calendar."""
    from data.calendar import build_calendar

    rows = build_calendar(start.isoformat(), end.isoformat())
    return [
        date.fromisoformat(r["date"]) for r in rows if not (r["is_weekend"] or r["is_holiday"])
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download ES data from Databento, one file per day")
    parser.add_argument("date", type=date.fromisoformat, help="YYYY-MM-DD (first day with --end)")
    parser.add_argument("--end", type=date.fromisoformat, help="last day; downloads every trading day")
    parser.add_argument("--schema", help="override config.yaml, e.g. bbo-1s for shock detection")
    parser.add_argument("--dry-run", action="store_true", help="only print the cost")
    args = parser.parse_args()

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    client = get_client()
    for day in trading_days(args.date, args.end) if args.end else [args.date]:
        download_day(client, cfg, day, args.dry_run, args.schema)
