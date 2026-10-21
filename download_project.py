"""Download full regular sessions, checking the TOTAL cost before fetching data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from data.download import get_client, fetch, trading_days


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2025, 1, 2))
    parser.add_argument('--end', type=date.fromisoformat, default=date(2025, 6, 30))
    parser.add_argument('--budget', type=float, default=0.0)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    cfg = yaml.safe_load(Path('config.yaml').read_text())
    d, s = cfg['data'], cfg['session']
    days = trading_days(args.start, args.end)
    base = dict(dataset=d['dataset'], symbols=[d['symbol']], stype_in=d['stype_in'], schema=d['schema'])
    client = get_client()
    # The entire interval includes overnight/weekends and therefore bounds the RTH subset.
    cost = client.metadata.get_cost(**base, start=pd.Timestamp(args.start, tz=s['timezone']),
                                   end=pd.Timestamp(args.end, tz=s['timezone']) + pd.Timedelta(days=1))
    print(f'Total upper-bound estimate: ${cost:.4f}; {len(days)} full sessions', flush=True)
    if args.dry_run:
        return
    if cost > args.budget:
        raise SystemExit(f'Estimate exceeds the ${args.budget:.2f} total budget.')
    root = Path(d['raw_dir'])
    root.mkdir(parents=True, exist_ok=True)
    manifest = dict(start=str(args.start), end=str(args.end), schema=d['schema'],
                    estimated_upper_bound_usd=cost, budget_usd=args.budget, days=[str(x) for x in days])
    (root / 'project_download.json').write_text(json.dumps(manifest, indent=2))

    def one(day):
        path = root / f"ES_{d['schema']}_{day}.dbn.zst"
        if not path.exists():
            request = dict(base, start=pd.Timestamp(f"{day} {s['download_start']}", tz=s['timezone']),
                           end=pd.Timestamp(f"{day} {s['download_end']}", tz=s['timezone']))
            fetch(get_client(), request, path)
        print(f'{day}: {path.stat().st_size / 1e6:.1f} MB ready', flush=True)
        return dict(date=str(day), file=path.name, bytes=path.stat().st_size)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(one, days))
    pd.DataFrame(rows).to_csv(root / 'project_files.csv', index=False)


if __name__ == '__main__':
    main()
