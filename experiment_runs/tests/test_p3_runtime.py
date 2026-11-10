from dataclasses import replace
import random
import pytest
from isl.p3.indexed import IndexedInstance, Objective, earliest, opportunities
from isl.p3.repair_runtime import run_method
from isl.repair_v2 import run_method as legacy
from isl.placement import earliest as plain_earliest, opportunities as plain_opportunities
from isl.metrics import selection_key
from isl.models import Contact, ordered
from test_repair import fixture_case, audit_result


@pytest.mark.parametrize('kind',['cancellation','reward_update','urgent_insertion'])
@pytest.mark.parametrize('method',['Fixed-PALR','Minimal-Repair','Frozen-Greedy'])
@pytest.mark.parametrize('w,B',[(1,0),(3,1),(5,2),(20,5)])
def test_no_deadline_semantic_equivalence(kind,method,w,B):
    case=fixture_case(kind)
    old=legacy(case,method,w=w,B=B,clock=lambda:0)
    new=run_method(case,method,w=w,B=B,clock=lambda:0)
    for key in ('plan','initial_plan','trace','forced_removed','forced_reasons','admissions_cumulative',
                'editable_indices','candidate_spans','R_window_ids','R_resource_ids','n_feas_initial',
                'validation','metrics','status','unchanged_outside_E'):
        assert old[key]==new[key],key
    audit_result(case,new)


@pytest.mark.parametrize('end',[5,15])
def test_bulk_invalid_fallback_preserves_forced_and_frozen(end):
    case=replace(fixture_case(),post_event_contacts=(Contact('short','A','B',0,end),))
    old=legacy(case,clock=lambda:0)
    new=run_method(case,clock=lambda:0)
    for key in ('plan','trace','forced_removed','forced_reasons','status','metrics'):
        assert old[key]==new[key]


def test_endpoint_index_and_delta_key_all_edits():
    case=fixture_case('reward_update')
    ins=case.effective_instance(); indexed=IndexedInstance(ins); obj=Objective(case,indexed)
    for removed in list(case.reference)+[None]:
        reduced=tuple(p for p in case.reference if p!=removed)
        for t in ins.tasks:
            if any(p.task_id==t.id for p in reduced):
                continue
            assert opportunities(indexed,t)==plain_opportunities(ins,t)
            item=earliest(indexed,t,reduced)
            assert item==plain_earliest(ins,t,reduced)
            if item:
                candidate=ordered(reduced+(item,))
                assert obj.edit_key(obj.key(case.reference),removed,item)==selection_key(case,candidate)


def test_zero_budget_cannot_return_success():
    result=run_method(fixture_case(),budget_ms=0)
    assert result['status']=='timeout'
    assert not result['metrics']['online_success'] and result['metrics']['U_exec']==0


def test_independent_indexed_checker_matches_original_on_corruptions():
    from isl.validation import validate as original
    from isl.p3.validation_indexed import validate as indexed
    from isl.models import Busy
    rng=random.Random(20261110)
    case=fixture_case('reward_update')
    ins=replace(case.effective_instance(),calendar=(Busy('A',15,18),Busy('B',17,19),Busy('C',0,10)))
    for _ in range(400):
        plan=list(case.reference)
        if rng.random()<.5: plan.pop(rng.randrange(len(plan)))
        if rng.random()<.5: plan.append(rng.choice(case.reference))
        if plan:
            i=rng.randrange(len(plan)); p=plan[i]
            plan[i]=replace(p,start=p.start+rng.choice([-1,0,1,11]),
                            sender=rng.choice(['A','B','C']),receiver=rng.choice(['A','B','D']))
        if rng.random()<.5: plan.sort(key=lambda p:(p.start,p.task_id))
        kw=dict(frozen=case.frozen,cancelled=('b',) if rng.random()<.5 else (),
                unchanged=case.reference[-1:] if rng.random()<.5 else ())
        assert indexed(ins,tuple(plan),**kw).to_dict()==original(ins,tuple(plan),**kw).to_dict()
