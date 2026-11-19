"""Check resampling invariants and ratio/paired estimands, not generated answers."""
import numpy as np
from p6_bootstrap import plans,normalize,ratio,interval

def fixture():
    ids=['d1','s1','s2','s3','s4','o1','o2']
    m={i:dict(layer='D1' if i=='d1' else 'D2-S' if i.startswith('s') else 'D2-O',group='D1' if i=='d1' else 'g0' if i in ['s1','s2','s3','o1'] else 'g1') for i in ids}
    return ids,m

def test_hierarchy_and_fixed_layer_weights_with_unequal_groups():
    ids,m=fixture();ids,l,g,b,h=plans(ids,m,300)
    w=normalize(h,l)
    for ix in l.values():assert np.allclose(w[:,ix].sum(1),len(ix))
    assert np.any(h[:,g['D2-S']['g0']].sum(1)==0)
    assert np.any(h[:,g['D2-S']['g1']].sum(1)==0)
    group0=h[:,g['D2-S']['g0']].sum(1)
    group1=h[:,g['D2-S']['g1']].sum(1)
    assert np.allclose(group0/3+group1,2)
    assert not np.array_equal(b,h)

def test_paired_identity_and_identical_draws():
    ids,m=fixture();a=plans(ids,m,50);b=plans(ids,m,50)
    assert np.array_equal(a[-1],b[-1])
    w=normalize(a[-1],a[1]);x=np.arange(len(ids),dtype=float)
    assert np.all(w@x-w@x==0)
    assert np.allclose((w@(x+3))/(w@np.ones(len(x)))-(w@x)/(w@np.ones(len(x))),3)

def test_ratio_of_sums_and_zero_denominator():
    assert float(ratio(9,10))==.9
    assert float(ratio(9,10))!=np.mean([0,1])
    v=ratio(np.array([0,5]),np.array([0,10]));assert np.isnan(v[0]) and v[1]==.5
    r=interval(v);assert r['undefined_replicates']==1 and r['defined_replicates']==1

def test_failure_zero_and_conditioned_quality_differ():
    u=np.array([10.,0.,30.]);valid=np.array([1.,0.,1.]);n=np.ones(3)
    assert ratio(u.sum(),n.sum())==40/3
    assert ratio(u.sum(),valid.sum())==20
