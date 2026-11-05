from dataclasses import replace
import pytest
from isl.models import Busy,Case,Contact,Event,Instance,Item,Task
from isl.repair import run_method as run_v1
from isl.repair_v2 import run_method as run_v2
from isl.p2_exact import context as context_v1
from isl.p2_exact_v2 import context as context_v2,solve_exact
from isl.urgent_supplement import pressure_label


def fixture():
    t=Task('old','A','B',0,20,1,1,10)
    u=Task('urgent','A','B',0,5,1,1,50)
    ins=Instance('v2-test',('A','B','C'),(t,),(Contact('c','A','B',0,20),),(),20)
    return Case(ins,(Item('old','A','B',10,12),),Event('e','urgent_insertion',130000,.8,urgent=u))


def test_v2_recovers_early_direct_request_without_exterior_edits():
    case=fixture()
    assert not run_v1(case,budget_ms=1000)['metrics']['service_success']
    actual=run_v2(case,budget_ms=1000)
    assert actual['metrics']['service_success'] and actual['metrics']['N_drop']==0
    a,b=context_v1(case),context_v2(case)
    assert b['allowed']-a['allowed']=={'urgent'}
    assert all(a[k]==b[k] for k in a if k!='allowed')
    exact,_=solve_exact(case,limit_s=3)
    assert exact['urgent_certificate']=='service_feasible'


@pytest.mark.parametrize('restriction',['B0','calendar','frozen','E_exterior'])
def test_exemption_preserves_real_constraints(restriction):
    case=fixture();B=0 if restriction=='B0' else 2
    if restriction=='calendar':case=replace(case,base=replace(case.base,calendar=(Busy('B',0,5),)))
    if restriction=='frozen':
        # This reservation fills every urgent start and must remain immutable.
        t=replace(case.base.tasks[0],data_bits=4)
        case=replace(case,base=replace(case.base,tasks=(t,)),reference=(Item('old','A','B',0,5),),frozen_count=1)
    w=5
    if restriction=='E_exterior':
        a=Task('a','A','B',0,20,1,1,10);b=Task('b','A','B',0,20,2,1,10)
        case=replace(case,base=replace(case.base,tasks=(a,b)),
                     reference=(Item('a','A','B',0,2),Item('b','A','B',2,5)),
                     event=replace(case.event,urgent=replace(case.event.urgent,data_bits=4)))
        w=0
    result=run_v2(case,w=w,B=B,budget_ms=1000)
    assert result['validation']['feasible'] and not result['metrics']['service_success']
    exact,_=solve_exact(case,w=w,B=B,limit_s=3)
    assert exact['urgent_certificate']=='service_proven_infeasible'


def test_ordinary_candidates_keep_original_filter():
    case=fixture();extra=Task('extra','A','B',0,5,1,1,80)
    case=replace(case,base=replace(case.base,tasks=case.base.tasks+(extra,)))
    assert 'extra' not in context_v1(case)['allowed']
    assert 'extra' not in context_v2(case)['allowed']


def test_no_urgent_cases_preserve_v1_output():
    case=fixture();case=replace(case,event=Event('r','reward_update',130000,.8,rewards=(('old',20),)))
    assert run_v1(case,budget_ms=1000)['plan']==run_v2(case,budget_ms=1000)['plan']
    assert context_v1(case)==context_v2(case)


def test_pressure_minimum_counts_unique_conflicting_tasks():
    case=fixture()
    assert pressure_label(case)['category']=='direct_insert'
    t=replace(case.base.tasks[0],data_bits=4)
    blocked=replace(case,base=replace(case.base,tasks=(t,)),reference=(Item('old','A','B',0,5),))
    label=pressure_label(blocked)
    assert label['category']=='one_removal' and label['min_removals_w5']==1
    # One task overlaps both terminals; count the ID once.
    assert label['min_removals_w20']==1


def test_multiple_removal_and_wide_neighborhood_labels():
    case=fixture();u=replace(case.event.urgent,deadline=5,data_bits=4)
    a=Task('a','A','B',0,20,1,1,10);b=Task('b','A','B',0,20,2,1,10)
    case=replace(case,base=replace(case.base,tasks=(a,b)),reference=(Item('a','A','B',0,2),Item('b','A','B',2,5)),event=replace(case.event,urgent=u))
    assert pressure_label(case)['category']=='multiple_removals'
    assert pressure_label(case,w=0)['category']=='outside_neighborhood'
