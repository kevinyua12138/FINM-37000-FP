"""Run the project: python run_backtest.py --output results/full_2025."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from data.calendar import flags_for_day, build_calendar
from data.clean import load_day, second_grid
from events.shocks import moves, detect_day
from events.study import enrich_events
from analysis import evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/full_2025'))
    parser.add_argument('--wait-data',action='store_true',help='Wait for an active download_project.py run.')
    parser.add_argument('--rebuild',action='store_true')
    args=parser.parse_args()
    cfg=yaml.safe_load((ROOT/'config.yaml').read_text()); r,s=cfg['research'],cfg['shocks']
    raw=Path(cfg['data']['raw_dir']); processed=Path('data/processed'); processed.mkdir(parents=True,exist_ok=True)
    args.output.mkdir(parents=True,exist_ok=True)
    # Freeze the complete specification before reading any returns.
    (args.output/'frozen_config.json').write_text(json.dumps(cfg,indent=2))
    code_files=[ROOT/'config.yaml',ROOT/'run_backtest.py',*sorted((ROOT/'src').rglob('*.py'))]
    digest=hashlib.sha256(b''.join(p.read_bytes() for p in code_files)).hexdigest()
    cache=processed/digest[:12]; cache.mkdir(exist_ok=True)
    (args.output/'provenance.json').write_text(json.dumps(dict(code_sha256=digest,
        base_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        schema=cfg['data']['schema'], source='Databento GLBX.MDP3 ES.v.0, full RTH sessions'),indent=2))
    # Require every expected regular session; never silently call a partial sample complete.
    days=[d['date'] for d in build_calendar(r['train_start'],r['test_end'])
          if not (d['is_weekend'] or d['is_holiday'] or d['is_half_day'])]
    if not days: raise SystemExit('No data. Run download_project.py or supply full-session mbp-1 files.')
    history=deque(maxlen=s['history_days']); frames=[]; coverage=[]; previous_inst=None
    for day in days:
        path=raw/f"ES_{cfg['data']['schema']}_{day}.dbn.zst"
        waited=0
        while not path.exists() and args.wait_data and waited<7200:
            time.sleep(10); waited+=10
        if not path.exists(): raise SystemExit(f'Missing required full-session data: {path}')
        event_path,grid_path,info_path=[cache/f'{day}_{suffix}' for suffix in ['events.parquet','grid.parquet','info.json']]
        if not args.rebuild and all(p.exists() for p in [event_path,grid_path,info_path]):
            grid=pd.read_parquet(grid_path); events=pd.read_parquet(event_path); info=json.loads(info_path.read_text())
        else:
            q=load_day(path)
            if q.empty: raise SystemExit(f'Empty expected trading session: {day}')
            grid=second_grid(q,r['max_stale_s'])
            threshold=pd.concat(list(history)).quantile(s['quantile']) if len(history)==s['history_days'] else np.nan
            events=detect_day(grid,threshold,window=pd.Timedelta(seconds=s['window_s']),cooldown=pd.Timedelta(seconds=s['cooldown_s']))
            detected=len(events)
            events=enrich_events(q,events,cfg) if detected else pd.DataFrame()
            inst=int(q.instrument_id.iloc[-1])
            flags=flags_for_day(day,actual_roll_dates=[day] if previous_inst is not None and previous_inst!=inst else [])
            for key,value in flags.items():
                if len(events): events[key]=value
            info=dict(date=day,raw_rows=len(q),invalid_rows=int((~q.valid).sum()),grid_rows=len(grid),
                      valid_seconds=int(grid.mid.notna().sum()),detected_events=detected,usable_events=len(events),
                      threshold_points=float(threshold),last_instrument_id=inst,
                      labelled_30s=int(events.get('y_30s',pd.Series(dtype=float)).notna().sum()),
                      first_quote=str(q.index[0]),last_quote=str(q.index[-1]),raw_bytes=path.stat().st_size,
                      **{k:v for k,v in flags.items() if k!='date'})
            grid.to_parquet(grid_path); events.to_parquet(event_path); info_path.write_text(json.dumps(info,indent=2))
            del q
        history.append(moves(grid,pd.Timedelta(seconds=s['window_s'])).abs().dropna())
        previous_inst=info['last_instrument_id']; coverage.append(info)
        if not events.empty: frames.append(events)
        print(f"{day}: {info['raw_rows']:,} rows; {info['detected_events']} shocks; {info['usable_events']} usable",flush=True)
    if not frames: raise SystemExit('No events after history and data-quality filters.')
    result=evaluate(pd.concat(frames,ignore_index=True),pd.DataFrame(coverage),cfg,args.output)
    print(result.to_string(index=False))
    print(f'Results saved to {args.output}')


if __name__=='__main__': main()
