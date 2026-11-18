"""Two predetermined single-head controllers; models only choose bounded actions."""
from time import perf_counter_ns
import numpy as np
from .control import features,rule_action
from .indexed import IndexedInstance,earliest
from .repair_runtime import run_method

ACTIONS=((3,1),(5,1),(5,2),(10,3))
PARAMS=dict(n_estimators=32,max_depth=6,min_samples_leaf=5,random_state=20261112,n_jobs=1)


def controlled(case,rule,model,mode):
    if mode not in ('action','deviation'): raise ValueError(mode)
    start=perf_counter_ns()
    x,meta=features(case,start)
    rule_choice=rule_action(x,meta,rule)
    action=rule_choice;invoked=False;prediction=None
    direct_failed=False
    if case.event.urgent:
        ins=IndexedInstance(case.effective_instance())
        baseline=tuple(p for p in case.reference if p.task_id not in case.event.cancelled)
        direct_failed=earliest(ins,case.event.urgent,baseline) is None
    difficult=direct_failed or meta['n_feas']>=3
    # Reserve at least 35 ms for repair and its full final check.
    if difficult and perf_counter_ns()-start<=15_000_000:
        model_x=list(x);model_x[5]=1.0
        prediction=int(model.predict(np.asarray([model_x]))[0]);invoked=True
        if perf_counter_ns()-start<=15_000_000 and prediction>=0:
            action=ACTIONS[prediction]
    control_ns=perf_counter_ns()-start
    first=[]
    def enclosing_clock():
        now=perf_counter_ns()
        if not first:first.append(now)
        return now
    result=run_method(case,w=action[0],B=action[1],budget_ms=max(0.,50-control_ns/1e6),clock=enclosing_clock)
    kernel_ns=result['total_ns'];total=first[0]-start+kernel_ns
    metrics=result['metrics'];ontime=total<=50_000_000
    metrics['within_budget']=ontime
    metrics['online_success']=bool(metrics['online_success'] and ontime)
    metrics['valid_output']=bool(metrics['valid_output'] and ontime)
    if not ontime:metrics['U_exec']=0;result['status']='timeout'
    metrics['L_total_ms']=total/1e6
    result['timings_ns']['control_ns']+=total-kernel_ns
    result.update(method='Sparse-ET-'+mode,total_ns=total,budget_ms=50,
        controller_features=x,controller_meta=meta,controller_invoked=invoked,
        controller_prediction=prediction,controller_fallback=action==rule_choice,
        direct_insertion_failed=direct_failed,controller_version='P3R-sparse-v1')
    return result
