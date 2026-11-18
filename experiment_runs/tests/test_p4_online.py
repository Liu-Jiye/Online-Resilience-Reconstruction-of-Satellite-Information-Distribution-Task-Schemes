import pytest
from dataclasses import replace
from isl.p4.online import run_cp,enforce_wall
from isl.models import Item
from isl.validation import validate
from test_repair import fixture_case

@pytest.mark.parametrize('kind',['cancellation','reward_update','urgent_insertion'])
def test_cp_global_plan_and_admission_witness(kind):
    case=fixture_case(kind);r=run_cp(case,budget_ms=500)
    assert r['validated'],r
    check=validate(case.effective_instance(),tuple(Item(**p) for p in r['plan']),frozen=case.frozen,
                   cancelled=case.event.cancelled,original_ids={p.task_id for p in case.reference},budget=5,
                   admissions=r['admissions_cumulative'],initial=tuple(Item(**p) for p in r['initial_plan']),trace=r['trace'])
    assert check.feasible,check.errors
    if kind=='urgent_insertion':assert r['metrics']['service_success']

def test_unknown_has_no_fabricated_solution():
    r=run_cp(fixture_case(),budget_ms=0)
    assert not r['validated'] and not r['metrics']['online_success']

def test_full_call_overrun_cannot_retain_kernel_success():
    r=run_cp(fixture_case(),budget_ms=500)
    r=enforce_wall(r,50_000_001)
    assert r['status']=='timeout' and not r['metrics']['online_success'] and r['metrics']['U_exec']==0
