import pytest
from isl.models import Item
from isl.validation import validate
from isl.p3.control import features,rule_action
from isl.p3.control_timed import controlled
from isl.p3.search import run_puct,run_alns
from test_repair import fixture_case

RULE=dict(r_low=.25,FR_high=.8,q_low=.2,q_high=.5,n_high=5,r_high=.6)


def test_rule_fallback_preserves_urgent_opportunity():
    x=[1,.8,.6,0,10,.7,.5,.1,.01,0,.1,.5]
    assert rule_action(x,dict(complete=True,urgent_opportunity=False),RULE)[1]==0
    assert rule_action(x,dict(complete=True,urgent_opportunity=True),RULE)[1]==1


@pytest.mark.parametrize('kind',['cancellation','reward_update','urgent_insertion'])
@pytest.mark.parametrize('method',[run_puct,run_alns])
def test_search_outputs_freeze_budget_trace_and_limits(kind,method):
    case=fixture_case(kind);r=method(case)
    assert r['B']==5
    if r['validated']:
        check=validate(case.effective_instance(),tuple(Item(**p) for p in r['plan']),frozen=case.frozen,
                       cancelled=case.event.cancelled,original_ids={p.task_id for p in case.reference},budget=5,
                       admissions=r['admissions_cumulative'],initial=tuple(Item(**p) for p in r['initial_plan']),trace=r['trace'])
        assert check.feasible,check.errors
    assert r['admissions_cumulative']<=5
    assert sum(r['timings_ns'].values())==r['total_ns']
    if method==run_puct:
        assert r['search_stats']['simulations']<=40 and r['search_stats']['max_depth']<=12
    else:assert r['search_stats']['iterations']<=200
    if r['total_ns']>50_000_000:assert not r['metrics']['online_success']


def test_controller_counts_feature_and_final_audit_cost():
    r=controlled(fixture_case(),RULE)
    assert r['total_ns']==sum(r['timings_ns'].values())
    assert r['timings_ns']['control_ns']>0
    assert r['budget_ms']==50
