"""Plot actual ES prices and detected shocks for one completed session."""
import argparse
import json
from pathlib import Path
import sys

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from events.shocks import detect_day, moves


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',default='2025-01-10')
    parser.add_argument('--results',type=Path,default=Path('results/full_2025'))
    args=parser.parse_args()
    provenance=json.loads((args.results/'provenance.json').read_text())
    cfg=json.loads((args.results/'frozen_config.json').read_text())
    cache=Path('data/processed')/provenance['code_sha256'][:12]
    info=json.loads((cache/f'{args.date}_info.json').read_text())
    grid=pd.read_parquet(cache/f'{args.date}_grid.parquet')
    tick=cfg['research']['tick_size']; shock=cfg['shocks']
    window=pd.Timedelta(seconds=shock['window_s'])
    events=detect_day(grid,info['threshold_points'],window=window,cooldown=pd.Timedelta(seconds=shock['cooldown_s']))
    change=moves(grid,window).abs()/tick; threshold=info['threshold_points']/tick
    plt.style.use('seaborn-v0_8-whitegrid')
    fig,(ax,bx)=plt.subplots(2,1,figsize=(13,7),sharex=True,gridspec_kw={'height_ratios':[1.3,1]})
    ax.plot(grid.index,grid.mid,color='#38658b',lw=.8,label='ES midpoint')
    for sign,color,marker,label in [(1,'#c74636','^','Upward shock'),(-1,'#6d4ab0','v','Downward shock')]:
        e=events[events.direction.eq(sign)]
        ax.scatter(e.t0,[grid.loc[t,'mid'] for t in e.t0],c=color,marker=marker,s=50,zorder=4,label=f'{label} (n={len(e)})')
        bx.scatter(e.t0,e['size']/tick,c=color,marker=marker,s=38,zorder=4)
    ax.set_ylabel('ES midpoint (index points)');ax.legend(loc='best',ncol=3)
    bx.plot(change.index,change,color='#38658b',lw=.65)
    bx.axhline(threshold,color='#be5029',ls='--',lw=1.5,label=f'Past-five-session 99.5th percentile: {threshold:g} ticks')
    bx.set(ylabel='Absolute 10-second move (ticks)',xlabel=f'{args.date} · Chicago time');bx.legend(loc='upper right')
    bx.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M',tz=grid.index.tz))
    fig.suptitle(f'Where the 99.5th-percentile price shocks happened · {len(events)} detected events',fontsize=16,weight='bold',y=.98)
    fig.text(.5,.925,'Threshold uses the previous five completed sessions only. One-second grid; 120-second cooldown.',ha='center',fontsize=10,color='#555555')
    fig.tight_layout(rect=(0,0,1,.90))
    fig.savefig(args.results/f'shocks_{args.date}.png',dpi=170)
    events.to_csv(args.results/f'shocks_{args.date}.csv',index=False)
    print(f'{len(events)} shocks; threshold {threshold:g} ticks ({info["threshold_points"]:g} points)')


if __name__=='__main__': main()
