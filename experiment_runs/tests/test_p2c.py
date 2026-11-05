import pytest
import sys
from pathlib import Path
from isl.p2c import construct
from isl.p2_exact_v2 import context
from isl.validation import validate

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from p2c_study import probe,independent_starts


@pytest.mark.parametrize('group,ordinal',[('direct',0),('single',0),('double',0),('triple',0),('outside',0),('hard',0),('hard',1),('hard',2)])
def test_constructed_reference_and_reproducibility(group,ordinal):
    case,meta=construct(100,group,ordinal)
    assert construct(100,group,ordinal)==(case,meta)
    assert len(case.reference)==20 and validate(case.base,case.reference).feasible
    if group=='outside':
        assert 'block-0' not in context(case,5,2)['editable']
        assert 'block-0' in context(case,20,2)['editable']
    if group in ('double','triple'):
        assert all(t.deadline-t.release==t.duration for t in case.base.tasks)


@pytest.mark.parametrize('group,cap',[('single',1),('double',2),('triple',3)])
def test_full_rescheduling_domain_certifies_minimum_drops(group,cap):
    case,_=construct(77,group,0)
    assert independent_starts(case,5)['min_drops']==cap
    assert probe(case,5,cap-1)[0]['status']=='INFEASIBLE'
    assert probe(case,5,cap)[0]['status']=='OPTIMAL'


def test_neighborhood_certificate_keeps_center_and_changes_editable_domain():
    case,_=construct(78,'outside',0)
    assert context(case,5,2)['center']==context(case,20,2)['center']
    assert probe(case,5,None)[0]['status']=='INFEASIBLE'
    assert probe(case,20,0)[0]['status']=='INFEASIBLE'
    assert probe(case,20,1)[0]['status']=='OPTIMAL'


@pytest.mark.parametrize('ordinal',[0,1,2])
def test_hard_controls_remain_impossible_in_wide_domain(ordinal):
    case,_=construct(79,'hard',ordinal)
    assert probe(case,20,None)[0]['status']=='INFEASIBLE'
