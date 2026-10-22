"""Show subsequent price paths for high versus low three-second refill."""
from pathlib import Path
import argparse
import json

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path('results/full_2025'))
    args=parser.parse_args()
    events=pd.read_csv(args.results/'events.csv')
    cutoff=json.loads((args.results/'frozen_config.json').read_text())['research']['refill_cutoff']
    plt.style.use('seaborn-v0_8-whitegrid')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),sharey=True)
    times=list(range(0,121,5)); columns=[f'path_{h}' for h in times]
    for ax,split,title in zip(axes,['train','test'],['January–April: development','May–June: held out']):
        sample=events[events.split.eq(split)].dropna(subset=['refill_ratio',*columns])
        for high,color,label in [(False,'#38658b','Low refill'),(True,'#c74636','High refill')]:
            g=sample[sample.refill_ratio.ge(cutoff).eq(high)]
            if len(g):ax.plot(times,g[columns].mean(),color=color,lw=2,label=f'{label} (n={len(g)})')
        ax.axhline(0,color='gray',lw=.8);ax.axvline(30,color='gray',ls=':',lw=1)
        ax.set(title=title,xlabel='Seconds after actual entry')
        ax.legend()
    axes[0].set_ylabel('Mean price move in the shock direction (ticks)')
    fig.suptitle(f'After the three-second observation: does high refill predict reversal?  RR cutoff = {cutoff:g}',fontsize=13)
    fig.text(.5,.01,'Negative = reversal. Complete 120-second paths only; excludes costs. High-refill test curve is ONE event, insufficient for inference.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,.94));fig.savefig(args.results/'refill_paths.png',dpi=170)
    # Keep sample sizes visible: one RR-only trade is not comparable evidence to hundreds.
    table=pd.read_csv(args.results/'simple_rules.csv')
    table=table[table.split.eq('test')]
    labels=[f"{row.rule.replace('_',' ')} (n={row.trades})" for row in table.itertuples()]
    fig,ax=plt.subplots(figsize=(11,4.5))
    bars=ax.barh(labels,table.net_pnl_usd,color='#b84a48')
    ax.bar_label(bars,labels=[f"-${abs(x):,.2f}" if x<0 else f"${x:,.2f}" for x in table.net_pnl_usd],padding=5)
    ax.set_xlim(min(table.net_pnl_usd.min()*1.25,0),max(table.net_pnl_usd.max()*1.25,0))
    ax.axvline(0,color='black',lw=.8);ax.invert_yaxis()
    ax.set(title='May–June 2025: refill-rule backtests',xlabel='Net P&L ($), one ES contract, 30-second holding period')
    fig.text(.5,.01,'Observed bid/ask plus $5 round-trip fees. RR-only has one trade: insufficient evidence for the hypothesis.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1));fig.savefig(args.results/'simple_rules.png',dpi=170)



if __name__=='__main__':main()
