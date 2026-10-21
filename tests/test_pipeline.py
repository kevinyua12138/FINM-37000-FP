"""Hand-calculated execution, timing, missing-data and leakage regression tests."""
import copy
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
import yaml

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data.clean import clean_quotes, second_grid
from features.orderflow import orderflow_updates, window_flow
from events.study import enrich_events
from events.shocks import moves
from backtest import assign_regimes, simulate, metrics
from analysis import clustered_mean

T=pd.Timestamp('2025-03-03 10:00:00',tz='America/Chicago')
CFG=yaml.safe_load((Path(__file__).resolve().parents[1]/'config.yaml').read_text())


def quotes(seconds, bids=None):
    n=len(seconds)
    if bids is None: bids=np.full(n,5000.)
    return pd.DataFrame(dict(bid_px_00=bids,ask_px_00=np.asarray(bids)+.25,
        bid_sz_00=np.full(n,10),ask_sz_00=np.full(n,10),instrument_id=np.ones(n,dtype=int),
        action=['A']*n,side=['B']*n,size=np.ones(n)),index=T+pd.to_timedelta(seconds,unit='s'))


def event():
    return pd.DataFrame([dict(t0=T,date='2025-03-03',direction=1,size=2.,threshold=1.,instrument_id=1)])


def test_grid_is_asof_and_stale_quotes_are_missing():
    q=clean_quotes(quotes([0.2,1.2,4.2],[5000,5001,5002]))
    g=second_grid(q)
    assert g.loc[T+pd.Timedelta('1s'),'mid']==5000.125
    assert np.isnan(g.loc[T+pd.Timedelta('3s'),'mid'])


def test_clean_rejects_off_tick_crossed_and_out_of_hours():
    q=quotes([0,1,2,3],[5000,5000.1,5001,5002])
    q.iloc[2,q.columns.get_loc('ask_px_00')]=4999
    q.index=pd.DatetimeIndex([T,T+pd.Timedelta('1s'),T+pd.Timedelta('2s'),T.normalize()+pd.Timedelta('7h')])
    out=clean_quotes(q)
    assert out.valid.tolist()==[True,False,False]


def test_invalid_quote_breaks_shock_window():
    q=quotes(np.arange(30),np.full(30,5000.))
    q.iloc[15,q.columns.get_loc('ask_px_00')]=4999
    g=second_grid(clean_quotes(q)); change=moves(g)
    assert change.iloc[16:26].isna().all()


def test_ofi_and_trade_imbalance_have_correct_signs():
    q=quotes([0,1,2]); q.bid_sz_00=[10,20,20]; q.ask_sz_00=[10,10,5]
    q.action=['A','T','T']; q.side=['B','B','A']; q['size']=[0,6,2]
    updates=orderflow_updates(q)
    assert updates.ofi_update.tolist()==[0,10,5]
    assert window_flow(updates,1)['ofi']==1
    assert window_flow(updates,1)['ti']==.5
    assert window_flow(updates,-1)['ofi']==-1
    assert window_flow(updates,-1)['ti']==-.5


def test_no_trades_is_neutral_but_unavailable_trade_fields_are_missing():
    q=quotes([0,1])
    assert window_flow(orderflow_updates(q),1)['ti']==0
    assert np.isnan(window_flow(orderflow_updates(q.drop(columns='action')),1)['ti'])


def test_regime_requires_reversing_flow_and_handles_zero_refill_median():
    ev=pd.DataFrame(dict(refill_ratio=[0,0,.8,.8,0,np.nan],ofi=[.2,-.2,.2,-.2,0,.2]))
    assert assign_regimes(ev).signal.tolist()==[1,0,0,-1,0,0]


def test_regime_decisions_do_not_change_when_future_events_are_added():
    a=pd.DataFrame(dict(refill_ratio=[0,.7],ofi=[.2,-.1]))
    b=pd.concat([a,pd.DataFrame(dict(refill_ratio=[100],ofi=[1]))])
    assert assign_regimes(a).signal.tolist()==assign_regimes(b).signal.iloc[:2].tolist()


def trading_events():
    ev=event(); ev['signal']=1; ev['regime']='slow / same'
    ev['entry_time']=T+pd.Timedelta('3.1s'); ev['exit_time_30']=T+pd.Timedelta('33.1s')
    ev['entry_bid']=5000.;ev['entry_ask']=5000.25
    ev['exit_bid_30']=5001.;ev['exit_ask_30']=5001.25
    return ev


def test_long_and_short_pnl_spread_is_counted_once():
    ev=trading_events(); long=simulate(ev,CFG).iloc[0]
    assert long.gross_pnl==37.5 and long.net_pnl==32.5 and long.mid_pnl==50
    short=simulate(ev,CFG,signal=-1).iloc[0]
    assert short.gross_pnl==-62.5 and short.net_pnl==-67.5


def test_slippage_and_fees():
    tr=simulate(trading_events(),CFG,fee=5,slip_ticks=1).iloc[0]
    assert tr.net_pnl==37.5-10-25


def test_no_overlapping_positions():
    ev=trading_events(); second=ev.copy();second['entry_time']+=pd.Timedelta('10s')
    assert len(simulate(pd.concat([ev,second]),CFG))==1


def test_missing_exit_does_not_create_free_trade():
    ev=trading_events();ev['exit_bid_30']=np.nan
    assert simulate(ev,CFG).empty


def test_metrics_include_initial_loss_and_zero_trade_days():
    tr=simulate(trading_events(),CFG,signal=-1)
    out=metrics(tr,['2025-03-03','2025-03-04'])
    assert out['max_drawdown_usd']==67.5 and out['days']==2
    assert out['breakeven_roundtrip_fee_usd']==-62.5


def test_empty_strategy_has_zero_pnl_and_no_fake_win_rate():
    ev=trading_events();ev['signal']=0
    out=metrics(simulate(ev,CFG),['2025-03-03'])
    assert out['trades']==0 and out['net_pnl_usd']==0 and np.isnan(out['win_rate'])


def test_cluster_standard_error_is_based_on_days():
    out=clustered_mean([1,1,3,3],['a','a','b','b'])
    assert out['mean']==2 and out['se']==pytest.approx(1)
    assert out['clusters']==2


def test_entry_horizon_starts_at_actual_fill_and_features_ignore_future():
    secs=np.round(np.arange(-11,125.1,.2),8)
    q=clean_quotes(quotes(secs))
    out=enrich_events(q,event(),CFG).iloc[0]
    assert out.entry_time==T+pd.Timedelta('3.2s')
    assert out.exit_time_30==T+pd.Timedelta('33.2s')
    later=q.copy(); later.loc[later.index>T+pd.Timedelta('3s'),'bid_sz_00']=999
    check=enrich_events(later,event(),CFG).iloc[0]
    assert out.ofi==check.ofi and out.refill_ratio==check.refill_ratio


def test_feature_window_rejects_contract_switch():
    q=clean_quotes(quotes(np.arange(-11,130,.5)))
    q.loc[q.index>=T+pd.Timedelta('1s'),'instrument_id']=2
    assert enrich_events(q,event(),CFG).empty


def test_exit_rejects_stale_gap():
    secs=np.arange(-11,130,.5); secs=secs[(secs<20)|(secs>25)]
    out=enrich_events(clean_quotes(quotes(secs)),event(),CFG).iloc[0]
    assert 'y_30s' not in out or pd.isna(out.y_30s)


def test_execution_requires_displayed_quantity():
    ev=trading_events();ev['entry_ask_size']=0
    assert simulate(ev,CFG).empty


def test_depth_does_not_fabricate_unseen_levels():
    from features.depth import depth_features
    q=quotes([-10,3])
    for i in range(1,10):
        q[f'bid_px_{i:02d}']=5000-i*.25
        q[f'ask_px_{i:02d}']=5000.25+i*.25
        q[f'bid_sz_{i:02d}']=10
        q[f'ask_sz_{i:02d}']=10
    out=depth_features(q,event()).iloc[0]
    assert out.RR_10==1 and out.I_5==0 and out.I_10==0
    for i in range(10):
        q.iloc[1,q.columns.get_loc(f'ask_px_{i:02d}')]-=.25
        q.iloc[1,q.columns.get_loc(f'bid_px_{i:02d}')]-=.25
    assert np.isnan(depth_features(q,event()).RR_10.iloc[0])


def test_full_report_outputs_on_small_fixture(tmp_path):
    from analysis import evaluate
    a=trading_events()
    a['max_eaten_depth']=100.;a['max_trade_size']=10.
    a['refill_ratio']=0.; a['ofi']=.2; a['I_1']=.1; a['G']=.0125; a['size_ticks']=8.
    a['is_macro_day']=False;a['is_roll_day']=False;a['is_actual_roll_day']=False
    for h in [5,30,120]: a[f'y_{h}s']=.001
    for h in range(0,121,5):a[f'path_{h}']=h*.1
    b=a.copy(); b['date']='2025-05-01'; b['t0']=pd.Timestamp('2025-05-01 10:00',tz='America/Chicago')
    for col in ['entry_time','exit_time_30']:b[col]+=pd.Timedelta('59D')
    coverage=pd.DataFrame({'date':['2025-03-03','2025-05-01'], 'raw_rows':[10,10], 'invalid_rows':[0,0], 'detected_events':[1,1]})
    result=evaluate(pd.concat([a,b],ignore_index=True),coverage,CFG,tmp_path)
    assert result.net_pnl_usd.tolist()==[32.5,32.5]
    for name in ['events.csv','trades.csv','robustness.csv','regression.csv','equity.png','event_paths.png']:
        assert (tmp_path/name).stat().st_size>0



def test_big_order_features_only_use_three_second_window():
    q=clean_quotes(quotes(np.arange(-11,130,.5)))
    q.loc[T+pd.Timedelta('2s'),'ask_sz_00']=200
    q.loc[T+pd.Timedelta('4s'),'ask_sz_00']=9999
    q.loc[T+pd.Timedelta('1s'),['action','size']]=['T',50]
    q.loc[T+pd.Timedelta('5s'),['action','size']]=['T',9999]
    out=enrich_events(q,event(),CFG).iloc[0]
    assert out.max_eaten_depth==200 and out.max_trade_size==50
