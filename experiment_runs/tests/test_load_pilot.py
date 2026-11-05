from dataclasses import replace
import numpy as np
import pytest
from isl.models import Task,Contact,Busy,Instance,Item
from isl.load_pilot import demand_family,transform_family,indexed_reference,Diagnostics,select_train,validate_selection
from isl.load_pilot_independent import BitAudit
from isl.reference import create_reference

CONFIG={'opportunity_attempt_cap':500,'hot_seed_tag':91001,'demand_uniform_seed_tag':91002,'hot_satellites':4}


def base():
    sats=tuple(f'S{i}' for i in range(6))
    contacts=tuple(Contact(f'{a}-{b}',a,b,0,5400) for a in sats for b in sats if a!=b)
    return Instance('test-load',sats,(),contacts,(Busy('S0',100,160),),5400)


def test_h0_preserves_original_tasks_and_nested_prefixes():
    b=base();raw,meta=demand_family(b,123,CONFIG)
    tasks,hot,sampling=transform_family(b,raw,meta,456,0.,CONFIG)
    assert tasks==raw and len(tasks)==1000 and len(hot)==4
    assert tasks[:100]==tasks[:200][:100]==tasks[:500][:100]


def test_hot_branches_are_nested_and_preserve_task_attributes():
    b=base();raw,meta=demand_family(b,123,CONFIG)
    low,hot,a=transform_family(b,raw,meta,456,.5,CONFIG);high,hot2,z=transform_family(b,raw,meta,456,.8,CONFIG)
    assert hot==hot2
    for t,l,h,x,y in zip(raw,low,high,a,z):
        assert not x['hot_branch'] or y['hot_branch']
        assert (l.id,l.data_bits,l.rate_bps,l.utility)==(h.id,h.data_bits,h.rate_bps,h.utility)==(t.id,t.data_bits,t.rate_bps,t.utility)
        if x['hot_branch']:assert l==h
        if y['hot_branch']:assert {h.sender,h.receiver}&set(hot)


def test_cached_reference_matches_original_and_independent_reference():
    b=base();raw,meta=demand_family(b,123,CONFIG);ins=replace(b,tasks=raw[:60])
    p=indexed_reference(ins)
    assert p==create_reference(ins)[0]==BitAudit(ins,()).reference_plan()


@pytest.mark.parametrize('frozen',[0,1,2])
def test_interval_and_bit_diagnostics_match_bruteforce(frozen):
    t=Task('new','A','B',0,30,4,1,1)
    tasks=(Task('x','A','C',0,10,9,1,2),Task('y','C','B',12,22,9,1,2))
    ins=Instance('diag',('A','B','C'),tasks,(Contact('ab','A','B',0,30),), (Busy('A',25,30),),30)
    ref=(Item('x','A','C',0,10),Item('y','C','B',12,22))
    a=Diagnostics(ins,ref).inspect(t,frozen);b=BitAudit(ins,ref).inspect(t,frozen);assert a==b
    counts=[];editable=[]
    for start in range(0,26):
        if start+t.duration>25:continue
        ids={p.task_id for p in ref if {p.sender,p.receiver}&{'A','B'} and start<p.end and p.start<start+t.duration}
        counts.append(len(ids))
        if not ids&{p.task_id for p in ref[:frozen]}:editable.append(len(ids))
    assert a['fixed_reference_min_blockers']==min(counts)
    assert a['editable_min_blockers']==(min(editable) if editable else None)


def test_no_window_and_calendar_block_are_distinct():
    b=base();task=Task('n','S0','S1',100,110,9,1,1)
    assert Diagnostics(b,()).inspect(task)['category']=='calendar_blocked'
    assert Diagnostics(replace(b,contacts=()),()).inspect(task)['category']=='no_physical'


def test_blocker_id_is_not_double_counted_for_both_endpoints():
    b=base();p=Item('old','S0','S1',0,10);t=Task('n','S0','S1',0,10,9,1,1)
    assert Diagnostics(b,(p,)).inspect(t)['fixed_reference_min_blockers']==1


def test_training_selection_never_falls_back_on_validation():
    config={'layers':['D1'],'per_layer_split':1,'task_counts':[100,200,500],'hot_probabilities':[0.],
            'selection':{'minimum_window_fraction':.65,'minimum_calendar_fraction':.3,'maximum_opportunity_decline_vs_default':.1,'minimum_high_minus_medium':.1,
                         'medium':{'competition_fraction':[.1,.35],'minimum_blocked_count':5,'minimum_probe_blocked_fraction':.1},
                         'high':{'competition_fraction':[.25,.7],'minimum_blocked_count':15,'minimum_probe_blocked_fraction':.25}}}
    rows=[]
    for split in ('train','validation'):
        for n,c in [(100,.02),(200,.15 if split=='train' else .01),(500,.4)]:
            rows.append({'split':split,'layer':'D1','N':n,'h':0.,'status':'valid','opportunity_probe_count':20,'window_fraction':.8,'calendar_fraction':.5,
                'competition_fraction':c,'blocked_count':n*c,'opportunity_probe_blocked_fraction':c,'scheduled_count':50,'scheduled_terminal_occupancy':.01,
                'hot_terminal_occupancy':.01,'actual_hot_endpoint_share':.25,'unplanned_calendar_feasible_count':n*c})
    training=select_train(rows,config);assert training['selected_from_train']['medium']=={'N':200,'h':0.}
    result=validate_selection(rows,training,config)
    assert not result['new_layers']['medium']['frozen'] and not result['validation_fallback_performed']
