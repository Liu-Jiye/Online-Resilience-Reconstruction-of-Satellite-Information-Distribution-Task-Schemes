"""Differential tests against immutable P3, including malformed prior items."""
from dataclasses import replace
import random
import pytest
from test_repair import fixture_case, audit_result
from isl.p3.validation_indexed import validate as old_check
from isl.p3r.validation_indexed import validate as new_check
from isl.p3.repair_runtime import run_method as old_run
from isl.p3r.repair_runtime import run_method as new_run


@pytest.mark.parametrize('kind',['cancellation','urgent_insertion','reward_update'])
@pytest.mark.parametrize('w,B',[(3,0),(3,1),(5,1),(5,2),(10,3),(20,5)])
def test_exact_behavior(kind,w,B):
    case=fixture_case(kind)
    a=old_run(case,w=w,B=B,clock=lambda:0)
    b=new_run(case,w=w,B=B,clock=lambda:0)
    for key in a:
        if key!='version': assert a[key]==b[key],key
    audit_result(case,b)


def test_all_checker_fields_for_malformed_plans():
    case=fixture_case('reward_update'); rng=random.Random(20261112)
    for _ in range(600):
        plan=list(case.reference)
        p=rng.choice(plan)
        plan.insert(0,replace(p,task_id='unknown' if rng.random()<.5 else p.task_id,
                              sender=rng.choice(['A','B','C']),start=p.start-1))
        if rng.random()<.5: rng.shuffle(plan)
        kwargs=dict(frozen=case.frozen,unchanged=case.reference[-1:],cancelled=('b',))
        assert old_check(case.base,tuple(plan),**kwargs).to_dict()==new_check(case.base,tuple(plan),**kwargs).to_dict()


def test_expired_budget_does_not_become_success():
    r=new_run(fixture_case(),budget_ms=0)
    assert r['status']=='timeout' and not r['metrics']['online_success'] and r['metrics']['U_exec']==0
