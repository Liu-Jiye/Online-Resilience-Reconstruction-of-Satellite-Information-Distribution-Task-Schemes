from dataclasses import replace
import pytest
from isl.models import Task,Contact,Instance,Item,Event,Case,ordered
from isl.validation import validate
from isl.p5.repair import run_method
from isl.p5.online import execute
from isl.p5.solver import reference_cp
from isl.p5.search import run_puct,run_alns
from isl.p5.data import window_case,anomaly_case

RULE=dict(r_low=.35,FR_high=.8,q_low=.2,q_high=.5,n_high=8,r_high=.7)
STATS=dict(mean=1.,std=1.)

def fixture():
    tasks=(Task('a','A','B',0,60,900,100,10),Task('b','C','B',0,60,900,100,20))
    ins=Instance('p5-test',('A','B','C'),tasks,(Contact('ab','A','B',0,60),Contact('cb','C','B',0,60)),horizon=60)
    ref=(Item('a','A','B',0,10),)
    return Case(ins,ref,Event('event','reward_update',10,.8,rewards=(('b',40),)))

def test_receiver_relaxation_must_fail_final_check():
    c=fixture();r=run_method(c,ignore_receiver=True,insertion_only=True,budget_ms=1000)
    assert not r['validated'];assert not r['metrics']['online_success'];assert 'resource_overlap' in r['validation']['errors']

def test_window_relaxation_must_fail_final_check():
    c=fixture();ins=replace(c.base,contacts=(c.base.contacts[0],));c=replace(c,base=ins)
    r=run_method(c,ignore_window=True,budget_ms=1000)
    assert not r['validated'];assert 'contact_window' in r['validation']['errors']

@pytest.mark.parametrize('method',['PUCT','ALNS'])
def test_local_search_cannot_remove_outside_E(method):
    c=fixture();c=replace(c,frozen_count=1)
    f=run_puct if method=='PUCT' else run_alns
    r=f(c,local_w=0,B=2,budget_ms=100)
    assert r['validated'];assert c.reference[0] in tuple(Item(**p) for p in r['plan'])
    assert validate(c.effective_instance(),tuple(Item(**p) for p in r['plan']),frozen=c.frozen).feasible

@pytest.mark.parametrize('flags',[{},dict(insertion_only=True),dict(random_ties=True)])
def test_original_commitments_and_budget(flags):
    c=fixture();r=run_method(c,B=1,budget_ms=1000,**flags)
    assert r['validated'];assert r['admissions_cumulative']<=1
    assert validate(c.effective_instance(),tuple(Item(**p) for p in r['plan']),original_ids={'a'},budget=1,
        admissions=r['admissions_cumulative'],initial=tuple(Item(**p) for p in r['initial_plan']),trace=r['trace']).feasible

@pytest.mark.parametrize('name',['Upgrade-PUCT','Upgrade-ALNS'])
def test_upgrade_has_single_outer_budget_and_retains_audit(name):
    c=fixture();r=execute(c,dict(name=name,threshold=1.1,seed=11),RULE,STATS)
    assert r['budget_ms']==50;assert r['total_ns']>=r['first_phase_ns'];assert r['B']==5
    assert r['metrics']['within_budget']==(r['total_ns']<=50_000_000)
    assert not r['metrics']['online_success'] or r['validated']

def test_cp_reference_has_no_B5_limit():
    c=fixture();r=reference_cp(c.base,c.reference,2)
    assert r['status']=='OPTIMAL';assert r['objective']==30;assert validate(c.base,tuple(Item(**p) for p in r['plan'])).feasible

@pytest.mark.parametrize('index',[0,1])
def test_frozen_anomaly_detected(index):
    c,_=anomaly_case(fixture(),index);r=run_method(c,budget_ms=1000)
    assert r['status']=='frozen_conflict';assert not r['metrics']['online_success']

def test_window_change_preserves_frozen():
    c=replace(fixture(),frozen_count=1);changed,meta=window_case(c,10,p=1.,shorten=.9)
    assert validate(changed.effective_instance(),changed.frozen,frozen=changed.frozen).feasible

def test_unmodified_fork_equivalent_without_deadline_pressure():
    from isl.p3r.repair_runtime import run_method as original
    c=fixture();a=original(c,budget_ms=1000);b=run_method(c,budget_ms=1000)
    for key in ('plan','trace','admissions_cumulative','unchanged_outside_E','forced_removed'):assert a[key]==b[key]

@pytest.mark.parametrize('budget',[5,10,20,50,100])
def test_budget_sensitive_enclosing_clock(budget):
    c=fixture();r=execute(c,dict(name='Rule-PALR',budget_ms=budget),RULE,STATS)
    assert r['budget_ms']==budget
    assert r['metrics']['within_budget']==(r['total_ns']<=budget*1e6)
