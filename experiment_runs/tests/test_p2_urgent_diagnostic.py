"""Hand-authored layered diagnostic cases; not part of the 67-event study."""
from dataclasses import replace
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_p2_urgent import enumerate_layers
from isl.models import Busy,Case,Contact,Event,Instance,Item,Task
from isl.p2_exact import context


def example():
    ordinary=Task('old','A','B',0,20,1,1,10)
    urgent=Task('urgent','A','B',0,5,1,1,50)
    base=Instance('diagnostic-test',('A','B','C'),(ordinary,),
                  (Contact('c','A','B',0,20),),(),20)
    return Case(base,(Item('old','A','B',10,12),),Event('e','urgent_insertion',130000,.8,urgent=urgent))


def test_excluded_but_physically_and_locally_feasible():
    case=example();ctx=context(case)
    result=enumerate_layers(case,ctx)
    assert case.event.urgent.id not in ctx['allowed']
    assert result['feasible_starts']['physical_calendar_all_immutable']==[0,1,2,3]
    assert result['feasible_starts']['physical_calendar_full_reference']==[0,1,2,3]


def test_no_early_physical_window_not_a_filter_only_failure():
    case=example();base=replace(case.base,contacts=(Contact('late','A','B',10,20),))
    case=replace(case,base=base)
    assert enumerate_layers(case,context(case))['feasible_start_counts']['physical']==0


@pytest.mark.parametrize('resource',['A','B'])
def test_background_on_either_endpoint_blocks_all(resource):
    case=example();case=replace(case,base=replace(case.base,calendar=(Busy(resource,0,5),)))
    result=enumerate_layers(case,context(case))['feasible_start_counts']
    assert result['physical']==4 and result['physical_and_calendar']==0


def test_frozen_blocks_remaining_starts():
    case=example();case=replace(case,reference=(Item('old','A','B',0,5),),frozen_count=1,
                              base=replace(case.base,tasks=(replace(case.base.tasks[0],data_bits=4),)))
    result=enumerate_layers(case,context(case))['feasible_start_counts']
    assert result['physical_and_calendar']==4
    assert result['physical_calendar_frozen']==0


def test_editable_blocker_can_be_removed_without_moving_exterior():
    case=example();case=replace(case,reference=(Item('old','A','B',0,5),),
                              base=replace(case.base,tasks=(replace(case.base.tasks[0],data_bits=4),)))
    result=enumerate_layers(case,context(case))['feasible_start_counts']
    assert result['physical_calendar_all_immutable']==4
    assert result['physical_calendar_full_reference']==0


def test_E_exterior_blocks_after_calendar_and_frozen_are_clear():
    case=example();a=Task('first','A','B',0,20,1,1,10);b=Task('second','A','B',0,20,2,1,10)
    base=replace(case.base,tasks=(a,b))
    urgent=replace(case.event.urgent,deadline=5,data_bits=4)
    case=replace(case,base=base,reference=(Item('first','A','B',0,2),Item('second','A','B',2,5)),
                 event=replace(case.event,urgent=urgent))
    ctx=context(case,w=0)
    result=enumerate_layers(case,ctx)['feasible_start_counts']
    assert result['physical_calendar_frozen']==1
    assert result['physical_calendar_all_immutable']==0
