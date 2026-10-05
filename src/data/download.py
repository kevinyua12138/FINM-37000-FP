import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

import databento as db
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import src/finm37000


def get_client():
    try:
        from finm37000 import get_databento_api_key, temp_env
    except ImportError:
        return db.Historical()  # falls back to the DATABENTO_API_KEY env variable

    with temp_env(DATABENTO_API_KEY=get_databento_api_key()):
        return db.Historical()


def download_day(client, cfg, day, dry_run=False):
    d, s = cfg["data"], cfg["session"]
    start = pd.Timestamp(f"{day} {s['download_start']}", tz=s["timezone"])
    end = pd.Timestamp(f"{day} {s['download_end']}", tz=s["timezone"])
    request = dict(
        dataset=d["dataset"],
        symbols=[d["symbol"]],
        stype_in=d["stype_in"],
        schema=d["schema"],
        start=start,
        end=end,
    )

    path = Path(d["raw_dir"]) / f"ES_{d['schema']}_{day}.dbn.zst"
    if path.exists():
        print(f"{path} already exists, skipping")
        return path

    cost = client.metadata.get_cost(**request)
    print(f"{day} {d['schema']} {start:%H:%M}-{end:%H:%M %Z}: ${cost:.2f}")
    if dry_run:
        return None
    if cost > d["max_cost_usd"]:
        raise SystemExit(f"${cost:.2f} is over the ${d['max_cost_usd']:.2f} limit")

    path.parent.mkdir(parents=True, exist_ok=True)
    client.timeseries.get_range(**request, path=path)

    log = path.parent / "download_log.csv"
    is_new = not log.exists()
    with open(log, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "schema", "cost_usd", "downloaded_at"])
        writer.writerow([day, d["schema"], round(cost, 4), datetime.now().isoformat(timespec="seconds")])

    print(f"saved {path}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download one day of ES data from Databento")
    parser.add_argument("date", type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="only print the cost")
    args = parser.parse_args()

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    download_day(get_client(), cfg, args.date, args.dry_run)
