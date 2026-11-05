from dataclasses import replace
from itertools import product
import pytest
from isl.models import (Busy, Case, Contact, Event, Instance, Item, Task,
                        case_to_dict, case_from_dict, ordered)
from isl.p2_exact import context, solve_exact, witness
from isl.metrics import selection_key
from isl.validation import validate


def small_case(kind='reward_update', frozen=0, calendar=()):
    tasks = (Task('a','A','B',0,8,1,1,5), Task('b','C','B',0,8,1,1,6),
             Task('c','A','C',0,8,2,1,9))
    contacts = tuple(Contact(t.id,t.sender,t.receiver,0,8) for t in tasks)
    base = Instance('tiny',('A','B','C'),tasks,contacts,calendar,8)
    ref = (Item('a','A','B',0,2),)
    urgent = Task('urgent','A','B',0,8,1,1,20) if kind == 'urgent_insertion' else None
    event = Event('e',kind,130000,.2, cancelled=('a',) if kind=='cancellation' else (), urgent=urgent)
    return Case(base,ref,event,frozen)


def brute(case,w,B,require_urgent=False):
    ctx = context(case,w,B)
    instance = ctx['instance']
    possibilities = []
    for t in instance.tasks:
        possibilities.append([None]+[Item(t.id,t.sender,t.receiver,s,s+t.duration)
                                     for s in range(t.release,t.deadline-t.duration+1)])
    best = None
    for choices in product(*possibilities):
        plan = ordered(p for p in choices if p is not None)
        if any(p.task_id not in ctx['allowed'] for p in plan):continue
        if len({p.task_id for p in plan}-ctx['original'])>B:continue
        if require_urgent and not any(p.task_id==case.event.urgent.id for p in plan):continue
        if not validate(instance,plan,frozen=case.frozen,cancelled=case.event.cancelled,
                        unchanged=ctx['unchanged']).feasible:continue
        key = selection_key(case,plan)
        if best is None or key<best:best=key
    return best


@pytest.mark.parametrize('kind',['reward_update','cancellation','urgent_insertion'])
@pytest.mark.parametrize('B',[0,1,2])
def test_exact_matches_independent_bruteforce(kind,B):
    case=small_case(kind)
    result,_=solve_exact(case,w=5,B=B,limit_s=3)
    assert result['status']=='OPTIMAL'
    plan=tuple(Item(**p) for p in result['plan'])
    assert selection_key(case,plan)==brute(case,5,B)
    assert result['certificate']['validation']['feasible']
    if kind=='urgent_insertion' and B==0:
        assert result['phases'][0]['status']=='INFEASIBLE'
        assert result['urgent_certificate']=='service_proven_infeasible'
        assert not result['proven_infeasible']


def test_frozen_and_outside_E_preserve_exact_fields():
    case=small_case(frozen=1)
    result,_=solve_exact(case,w=0,B=2,limit_s=3)
    assert Item(**result['plan'][0])==case.frozen[0]
    assert result['selection_key']==list(brute(case,0,2))
    case=small_case()
    # A reward at b maps center to first editable; w=0 leaves later original fixed.
    second=Item('b','C','B',4,6)
    case=replace(case,reference=case.reference+(second,),event=replace(case.event,rewards=(('a',7),)))
    result,_=solve_exact(case,w=0,B=2,limit_s=3)
    assert as_item(second) in result['plan']


def as_item(item):
    return {'task_id':item.task_id,'sender':item.sender,'receiver':item.receiver,'start':item.start,'end':item.end}


def test_receiver_calendar_and_single_window_no_accumulation():
    case=small_case(calendar=(Busy('B',2,8),))
    result,_=solve_exact(case,w=5,B=2,limit_s=3)
    assert result['selection_key']==list(brute(case,5,2))
    # Two separate windows of length 2 cannot carry duration 3.
    task=Task('a','A','B',0,8,2,1,5)
    base=Instance('single',('A','B'),(task,),
                  (Contact('x','A','B',0,2),Contact('y','A','B',4,6),Contact('reverse','B','A',0,8)),(),8)
    case=Case(base,(),Event('u','urgent_insertion',130000,.2,urgent=replace(task,id='urgent')))
    result,_=solve_exact(case,limit_s=3)
    assert result['urgent_certificate']=='service_proven_infeasible' and result['plan']==[]


def test_cancelled_frozen_is_proven_model_infeasible():
    case=small_case('cancellation',frozen=1)
    result,_=solve_exact(case,limit_s=3)
    assert result['status']=='INFEASIBLE' and result['plan'] is None


def test_zero_limit_unknown_never_infeasible():
    result,_=solve_exact(small_case(),limit_s=0)
    assert result['status']=='UNKNOWN' and not result['proven_optimal'] and not result['proven_infeasible']


def test_rounding_ceil_duration_exact_right_endpoint():
    t=Task('t','A','B',0,3,3,2,10)
    urgent=replace(t,id='urgent')
    ins=Instance('round',('A','B'),(t,),(Contact('c','A','B',0,3),),(),3)
    case=Case(ins,(),Event('e','urgent_insertion',130000,.2,urgent=urgent))
    result,_=solve_exact(case,limit_s=3)
    assert result['status']=='OPTIMAL' and result['plan']==[as_item(Item('urgent','A','B',0,3))]


def test_serialization_rename_and_relaxation():
    case=small_case('urgent_insertion')
    result,_=solve_exact(case,B=1,limit_s=3)
    replay,_=solve_exact(case_from_dict(case_to_dict(case)),B=1,limit_s=3)
    assert result['selection_key']==replay['selection_key']
    relaxed,_=solve_exact(case,B=2,limit_s=3)
    assert tuple(relaxed['selection_key'])<=tuple(result['selection_key'])
    def name(x):return 'renamed:'+x
    base=case.base
    renamed=replace(base,satellites=tuple(map(name,base.satellites)),
                    tasks=tuple(replace(t,id=name(t.id),sender=name(t.sender),receiver=name(t.receiver)) for t in base.tasks),
                    contacts=tuple(replace(c,id=name(c.id),sender=name(c.sender),receiver=name(c.receiver)) for c in base.contacts))
    ref=tuple(replace(p,task_id=name(p.task_id),sender=name(p.sender),receiver=name(p.receiver)) for p in case.reference)
    urgent=replace(case.event.urgent,id=name(case.event.urgent.id),sender=name(case.event.urgent.sender),receiver=name(case.event.urgent.receiver))
    renamed_case=Case(renamed,ref,replace(case.event,urgent=urgent))
    renamed_result,_=solve_exact(renamed_case,B=1,limit_s=3)
    assert result['selection_key']==renamed_result['selection_key']
