from importlib import import_module
from test_repair import fixture_case
from isl.p3r.sparse_control import ACTIONS

sparse=import_module('isl.p3r.sparse_control')
RULE=dict(r_low=.35,FR_high=.8,q_low=.2,q_high=.5,n_high=8,r_high=.7)

class Model:
    def __init__(self,prediction): self.prediction=prediction;self.calls=0
    def predict(self,x):
        self.calls+=1
        assert x.shape==(1,12) and x[0,5]==1
        return [self.prediction]

def setup_features(monkeypatch,n):
    x=[0,.8,0,n,4,1.,0,0,0,0,0,0]
    monkeypatch.setattr(sparse,'features',lambda case,start:(list(x),dict(n_feas=n,complete=True,urgent_opportunity=False)))

def test_easy_event_never_predicts(monkeypatch):
    setup_features(monkeypatch,0);m=Model(3)
    r=sparse.controlled(fixture_case(),RULE,m,'action')
    assert m.calls==0 and not r['controller_invoked'] and r['B']==0

def test_difficult_state_predicts_one_action(monkeypatch):
    setup_features(monkeypatch,3);m=Model(1)
    r=sparse.controlled(fixture_case(),RULE,m,'action')
    assert m.calls==1 and r['controller_invoked']
    assert (r['w'],r['B'])==ACTIONS[1]
    assert sum(r['timings_ns'].values())==r['total_ns']
    assert r['metrics']['within_budget']==(r['total_ns']<=50_000_000)

def test_unknown_recommendation_preserves_rule(monkeypatch):
    setup_features(monkeypatch,3);m=Model(-1)
    r=sparse.controlled(fixture_case(),RULE,m,'deviation')
    assert m.calls==1 and r['controller_fallback'] and (r['w'],r['B'])==(5,2)

def test_insufficient_budget_never_predicts(monkeypatch):
    setup_features(monkeypatch,3);m=Model(3)
    ticks=iter([0,16_000_000,16_000_000]+[16_000_000+i*1_000_000 for i in range(1,1000)])
    monkeypatch.setattr(sparse,'perf_counter_ns',lambda:next(ticks))
    r=sparse.controlled(fixture_case(),RULE,m,'action')
    assert m.calls==0 and not r['controller_invoked']
