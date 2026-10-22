"""Small, explicit tables and plots for issues #10–#15. No parameter search."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, brier_score_loss
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from backtest import assign_regimes, simulate, metrics


def clustered_mean(values, days):
    """Intercept-only OLS, day-clustered SE with finite-cluster correction."""
    frame = pd.DataFrame({'y': np.asarray(values, float), 'day': np.asarray(days)}).dropna()
    n, g = len(frame), frame.day.nunique()
    mean = frame.y.mean()
    if g < 2 or n < 2:
        return dict(n=n, clusters=g, mean=mean, se=np.nan, t=np.nan, p=np.nan, lo=np.nan, hi=np.nan)
    scores = (frame.y - mean).groupby(frame.day).sum()
    se = np.sqrt(g/(g-1) * (scores**2).sum() / n**2)
    t = mean / se if se > 0 else np.nan
    critical = student_t.ppf(.975, g-1)
    return dict(n=n, clusters=g, mean=mean, se=se, t=t,
                p=2*student_t.sf(abs(t), g-1), lo=mean-critical*se, hi=mean+critical*se)


def regression_table(train):
    x = train[['ofi', 'refill_ratio', 'I_1', 'size_ticks']].copy()
    x['ofi_x_refill'] = x.ofi * x.refill_ratio
    frame = pd.concat([train[['date', 'y_30s']], x], axis=1).replace([np.inf,-np.inf],np.nan).dropna()
    if len(frame) <= len(x.columns)+1 or frame.date.nunique() < 2:
        return pd.DataFrame(columns=['term','coefficient_bp','cluster_se','t','p'])
    fit = sm.OLS(frame.y_30s * 1e4, sm.add_constant(frame[x.columns], has_constant='add')).fit(
        cov_type='cluster', cov_kwds={'groups':frame.date}, use_t=True)
    return pd.DataFrame(dict(term=fit.params.index, coefficient_bp=fit.params.values,
                             cluster_se=fit.bse.values, t=fit.tvalues.values, p=fit.pvalues.values))


def model_evaluation(train, test, cfg, days, output):
    columns = ['ofi','refill_ratio','I_1','G','size_ticks']
    # TI is also reported, but excluding it here makes the model usable with missing trade fields.
    a = train.dropna(subset=columns+['y_30s'])
    b = test.dropna(subset=columns+['y_30s']).copy()
    target = a.y_30s.gt(0).astype(int)  # zero returns are explicitly the non-continuation class
    if len(a) < 20 or target.nunique() < 2 or b.empty:
        return {'status':'insufficient training/test observations'}
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000, random_state=0))
    model.fit(a[columns], target)
    p = model.predict_proba(b[columns])[:,1]
    y = b.y_30s.gt(0).astype(int)
    b['probability'] = p
    b['signal'] = np.select([p >= cfg['research']['model_follow_probability'],
                             p <= cfg['research']['model_fade_probability']], [1,-1], default=0)
    trades = simulate(b, cfg)
    trades.to_csv(output/'model_trades.csv', index=False)
    b[['t0','date','y_30s','probability','signal']].to_csv(output/'model_predictions.csv', index=False)
    calibration = b.assign(bin=pd.cut(p, np.linspace(0,1,6), include_lowest=True), outcome=y)
    calibration = calibration.groupby('bin', observed=False).agg(n=('probability','size'),
                    predicted=('probability','mean'), observed=('outcome','mean'))
    calibration.to_csv(output/'model_calibration.csv')
    scaler, logistic = model.steps[0][1], model.steps[1][1]
    (output/'frozen_model.json').write_text(json.dumps(dict(features=columns, mean=scaler.mean_.tolist(),
        scale=scaler.scale_.tolist(), coefficients=logistic.coef_[0].tolist(),
        intercept=float(logistic.intercept_[0]), C=1.0), indent=2))
    fig, ax = plt.subplots(figsize=(6,4))
    ax.plot([0,1],[0,1], '--', color='gray')
    ax.plot(calibration.predicted, calibration.observed, 'o-')
    ax.set(xlabel='Predicted continuation probability', ylabel='Observed continuation frequency',
           title='Logistic model: held-out calibration', xlim=(0,1), ylim=(0,1))
    fig.tight_layout(); fig.savefig(output/'model_calibration.png', dpi=160); plt.close(fig)
    return dict(status='evaluated', train_events=len(a), test_events=len(b),
                auc=roc_auc_score(y,p) if y.nunique()==2 else None,
                brier=brier_score_loss(y,p), **metrics(trades, days))


def evaluate(events, coverage, cfg, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    r = cfg['research']
    ev = assign_regimes(events, r['refill_cutoff'], r['ofi_cutoff'])
    ev['split'] = np.where(ev.date <= r['train_end'], 'train', 'test')
    ev.to_csv(output/'events.csv', index=False)
    coverage.to_csv(output/'coverage.csv', index=False)
    train, test = ev[ev.split.eq('train')], ev[ev.split.eq('test')]
    all_metrics, all_trades, tables, daily_rows = [], [], [], []
    for name, sample in [('train',train),('test',test)]:
        days = coverage.loc[coverage.date.le(r['train_end']) if name=='train' else coverage.date.ge(r['test_start']), 'date']
        trades = simulate(sample,cfg,horizon=r['horizon_s'])
        trades['split'] = name; all_trades.append(trades)
        all_metrics.append(dict(split=name, **metrics(trades, days),
                                **{'net_'+k:v for k,v in clustered_mean(trades.net_pnl,trades.date).items()}))
        daily = trades.groupby('date').net_pnl.sum().reindex(days,fill_value=0).rename('net_pnl').reset_index()
        daily['split']=name; daily['cumulative_pnl']=daily.net_pnl.cumsum(); daily_rows.append(daily)
        for regime, group in sample.groupby('regime'):
            for h in [5,30,120]:
                tables.append(dict(split=name, regime=regime, horizon_s=h,
                                   **clustered_mean(group[f'y_{h}s']*1e4,group.date)))
    metrics_df = pd.DataFrame(all_metrics); metrics_df.to_csv(output/'metrics.csv',index=False)
    pd.concat(all_trades).to_csv(output/'trades.csv',index=False)
    pd.DataFrame(tables).to_csv(output/'regime_table.csv',index=False)
    pd.concat(daily_rows).to_csv(output/'daily_pnl.csv',index=False)
    regression_table(train).to_csv(output/'regression.csv',index=False)
    test_days = coverage.loc[coverage.date.ge(r['test_start']),'date']
    checks = [('base',{}),('horizon_5s',{'horizon':5}),('horizon_120s',{'horizon':120}),
              ('fees_0_per_side',{'fee':0}),('fees_5_per_side',{'fee':5}),
              ('slippage_1_tick_per_side',{'slip_ticks':1}),('latency_500ms',{'latency_suffix':'_lag500'}),
              ('always_follow',{'signal':1}),('always_fade',{'signal':-1})]
    robust = []
    for label, kwargs in checks:
        trades = simulate(test,cfg,**kwargs)
        robust.append(dict(check=label,**metrics(trades,test_days)))
    for label, subset in [('exclude_macro_days',test[~test.is_macro_day]),
                          ('exclude_roll_days',test[~(test.is_roll_day|test.is_actual_roll_day)]),
                          ('up_shocks',test[test.direction.eq(1)]),('down_shocks',test[test.direction.eq(-1)])]:
        robust.append(dict(check=label,**metrics(simulate(subset,cfg),test_days)))
    for cutoff in [.25,.75]:
        subset = assign_regimes(test,cutoff,r['ofi_cutoff'])
        robust.append(dict(check=f'refill_cutoff_{cutoff}',**metrics(simulate(subset,cfg),test_days)))
    pd.DataFrame(robust).to_csv(output/'robustness.csv',index=False)
    model = model_evaluation(train,test,cfg,test_days,output)
    (output/'model_metrics.json').write_text(json.dumps(model,indent=2,default=float))

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, axes = plt.subplots(1,2,figsize=(12,4))
    for ax,daily,name in zip(axes,daily_rows,['Development: Jan–Apr','Held out: May–Jun']):
        ax.plot(pd.to_datetime(daily.date),daily.cumulative_pnl,color='#2364aa')
        ax.axhline(0,color='gray',lw=.8); ax.set(title=name,ylabel='Cumulative net P&L ($)')
        ax.tick_params(axis='x',rotation=30)
    fig.suptitle('One ES contract · observed bid/ask · $2.50 per side · no added slippage')
    fig.tight_layout(); fig.savefig(output/'equity.png',dpi=170); plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,5))
    for name,g in train.groupby('regime'):
        if name=='neutral / missing': continue
        times=list(range(0,121,5)); means=[g.get(f'path_{h}',pd.Series(dtype=float)).mean() for h in times]
        ax.plot(times,means,label=f"{name} (n={g['path_120'].notna().sum()})")
    ax.axhline(0,color='gray',lw=.8); ax.set(xlabel='Seconds after actual entry',ylabel='Mean move in shock direction (ticks)',
                                         title='Development sample only: average price path')
    ax.legend(); fig.tight_layout(); fig.savefig(output/'event_paths.png',dpi=170); plt.close(fig)
    simple_rule_comparison(train, test, coverage, cfg, output)
    write_report(output, metrics_df, model, coverage, ev)
    return metrics_df


def write_report(output, summary, model, coverage, events):
    def number(value):
        return f"{value:,.2f}" if pd.notna(value) else "not estimable"
    rows = []
    for x in summary.to_dict('records'):
        rows.append(f"| {x['split']} | {x['trades']} | ${number(x['gross_pnl_usd'])} | "
                    f"${number(x['net_pnl_usd'])} | ${number(x['mean_net_usd'])} | "
                    f"{x['win_rate']:.1%} | ${number(x['max_drawdown_usd'])} |")
    test = summary[summary.split.eq('test')].iloc[0]
    outcome = 'positive' if test.net_pnl_usd > 0 else 'negative' if test.net_pnl_usd < 0 else 'zero'
    lines = [
        '# Backtest results: ES shock continuation / reversal', '',
        f"The frozen rule produced **{outcome} held-out net P&L of ${number(test.net_pnl_usd)}** "
        f"over {int(test.trades)} trades in May–June 2025.", '',
        'These are historical simulated executions, not live fills. One ES contract; '
        'buy at observed ask, sell at observed bid; illustrative $2.50 fee per side; '
        'zero additional slippage in the base case. See the slippage stress test.', '',
        '| Period | Trades | Gross P&L after spread | Net P&L | Mean net/trade | Win rate | Max drawdown |',
        '|---|---:|---:|---:|---:|---:|---:|', *rows, '',
        f"Held-out mean net/trade 95% day-clustered interval: "
        f"[${number(test.net_lo)}, ${number(test.net_hi)}], "
        f"t = {number(test.net_t)}, p = {number(test.net_p)}. "
        f"There are {int(test.net_clusters)} trading-day clusters with trades.", '',
        f"Held-out break-even round-trip fee after the observed spread: "
        f"${number(test.breakeven_roundtrip_fee_usd)} per contract. "
        'A negative figure means gross performance already loses after spread.', '',
        '![Cumulative net P&L](equity.png)', '',
        '## Data and exclusions', '',
        f"{len(coverage)} full regular sessions, {coverage.date.min()} to {coverage.date.max()}; "
        f"{int(coverage.raw_rows.sum()):,} input records after regular-hours filtering. "
        f"{int(coverage.invalid_rows.sum()):,} invalid rows were retained as barriers. "
        f"{int(coverage.detected_events.sum()):,} detected shocks; {len(events):,} events "
        f"with valid feature windows; {int(events.y_30s.notna().sum()):,} with valid 30-second labels.", '',
        'The first five retained sessions are history only. Holidays/half-days are excluded. '
        'Coverage and event counts are saved per day. Further exclusions arise from missing '
        'features/quotes, insufficient displayed execution size, no-trade regimes and overlapping positions.', '',
        '## Event study and model', '',
        'The average paths below use development events with complete 120-second paths. '
        'Positive means price continues in the shock direction. Counts and day-clustered '
        'uncertainty at each horizon are in `regime_table.csv`. The regression is development-only.', '',
        '![Development event paths](event_paths.png)', '',
        f"Logistic model status: {model['status']}.",
    ]
    if model['status']=='evaluated':
        lines += [f"Held-out AUC: {number(model['auc'])}; Brier score: {number(model['brier'])}; "
                  f"net P&L: ${number(model['net_pnl_usd'])} across {model['trades']} trades. "
                  'The scaler and coefficients use January–April only. '
                  'AUC measures discrimination, not profitability.', '',
                  '![Held-out model calibration](model_calibration.png)', '']
    simple = pd.read_csv(output/'simple_rules.csv')
    lines += ['## Your simple rules: held-out comparison', '',
              'All rules use 99.5th-percentile 10-second shocks, observe the book for three seconds, '
              'enter after 100 ms, and hold for 30 seconds. High refill means RR >= 0.5. '
              'The comparison tests high refill alone and in combination with book imbalance or order flow.', '',
              '| Rule | Trades | Net P&L | Mean net/trade | 95% clustered interval |',
              '|---|---:|---:|---:|---|']
    for x in simple[simple.split.eq('test')].to_dict('records'):
        lines.append(f"| {x['rule']} | {x['trades']} | ${number(x['net_pnl_usd'])} | "
                     f"${number(x['mean_net_usd'])} | [${number(x['net_lo'])}, ${number(x['net_hi'])}] |")
    lines += ['', '![Simple rule comparison](simple_rules.png)', '',
              'See `simple_rules.csv` and `simple_rule_trades.csv`. '
              'These parallel hypotheses were specified before the held-out evaluation; '
              'the best realized result is not a newly validated strategy.', '']
    lines += [
        '## Interpretation and limitations', '',
        '- Refill is the team’s mbp-1 proxy, partly a price-recovery measure; hidden depth is unobserved.',
        '- Zero added slippage and displayed quote fills can be optimistic. The robustness table '
        'includes one tick per side, slower entry, different fees and always-follow/fade baselines.',
        '- Filtering stale/invalid windows can select more liquid observations; counts are disclosed.',
        '- Six months and one instrument do not establish a durable trading edge or causal mechanism. '
        'Clustered uncertainty and sensitivity results must accompany the headline P&L.',
        '- The test data were used for this frozen evaluation. Any strategy chosen from its '
        'sensitivity results requires a new holdout.',
        '- Real mbp-10 evaluation remains optional and unrun: depth data had a nonzero quoted price. '
        'No depth measurements or market performance have been fabricated.', '',
        '## Files and reproduction', '',
        '`events.csv`, `trades.csv`, `metrics.csv`, `daily_pnl.csv`, `coverage.csv`, '
        '`regime_table.csv`, `regression.csv`, `robustness.csv`, '
        '`model_predictions.csv`, `model_trades.csv`, `model_metrics.json`, '
        '`model_calibration.csv`, `frozen_model.json`, `frozen_config.json` and `provenance.json`.', '',
        'From the repository root: `python run_backtest.py --output results/full_2025`. '
        'This requires the private raw data; quotes are not committed. '
        'See `../../docs/research_spec.md` for setup, formulas, sources and assumptions.',
    ]
    (output/'README.md').write_text('\n'.join(lines)+'\n')


def simple_rule_comparison(train, test, coverage, cfg, output):
    """Compare the three refill-based hypotheses without tuning on test returns."""
    r = cfg['research']
    rows, trade_lists = [], []
    for split, ev in [('train',train), ('test',test)]:
        days = coverage.loc[coverage.date.le(r['train_end']) if split=='train' else coverage.date.ge(r['test_start']), 'date']
        fast = ev.refill_ratio.ge(r['refill_cutoff'])
        slow = ev.refill_ratio.lt(r['refill_cutoff'])
        rules = {
            'existing_refill_and_flow': ev.signal,
            'high_refill_fade': np.where(fast,-1,0),
            'refill_and_book_imbalance': np.select([slow & ev.I_1.gt(0),fast & ev.I_1.lt(0)],[1,-1],default=0),
        }
        for rule, signal in rules.items():
            trades = simulate(ev,cfg,signal=signal)
            trades['rule'],trades['split']=rule,split
            trade_lists.append(trades)
            rows.append(dict(rule=rule,split=split,**metrics(trades,days),
                             **{'net_'+k:v for k,v in clustered_mean(trades.net_pnl,trades.date).items()}))
    table=pd.DataFrame(rows)
    table.to_csv(output/'simple_rules.csv',index=False)
    pd.concat(trade_lists,ignore_index=True).to_csv(output/'simple_rule_trades.csv',index=False)
    heldout=table[table.split.eq('test')]
    fig,ax=plt.subplots(figsize=(10,5))
    labels=[x.replace('_',' ') for x in heldout.rule]
    ax.barh(labels,heldout.net_pnl_usd,color=np.where(heldout.net_pnl_usd>=0,'#237a57','#b84a48'))
    ax.axvline(0,color='black',lw=.8)
    ax.set(xlabel='Net simulated P&L ($), one ES contract',title='May–June 2025: simple rule comparison (30s holding period)')
    ax.invert_yaxis();fig.tight_layout();fig.savefig(output/'simple_rules.png',dpi=170);plt.close(fig)
