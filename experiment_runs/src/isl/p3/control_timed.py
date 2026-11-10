"""Exact enclosing response boundary, including dispatch; frozen label features unchanged."""
from time import perf_counter_ns
import numpy as np
from .control import features,rule_action
from .repair_runtime import run_method

def controlled(case,rule,model=None,threshold=.95,time_ratio=.8):
    start=perf_counter_ns()
    x,meta=features(case,start)
    action=rule_action(x,meta,rule); fallback=True
    if model is not None and perf_counter_ns()-start<50_000_000:
        actions=model['actions']
        matrix=np.asarray([x+[w,b] for w,b in actions])
        probs=model['classifier'].predict_proba(matrix)
        classes=list(model['classifier'].classes_)
        ps=probs[:,classes.index(1)] if 1 in classes else np.zeros(len(actions))
        predictions=np.column_stack([m.predict(matrix) for m in model['heads']])
        remaining=max(0.,50-(perf_counter_ns()-start)/1e6)
        valid=[i for i in range(len(actions)) if ps[i]>=threshold and predictions[i,4]<=remaining*time_ratio]
        if valid:
            chosen=min(valid,key=lambda i:(-predictions[i,0],predictions[i,1],predictions[i,2],predictions[i,3],-ps[i],i))
            action=tuple(actions[chosen]); fallback=False
        if meta['complete'] and meta['n_feas']==0 and not meta['urgent_opportunity']: action=(3,0)
    control_ns=perf_counter_ns()-start
    first_clock=[]
    def response_clock():
        now=perf_counter_ns()
        if not first_clock: first_clock.append(now)
        return now
    result=run_method(case,w=action[0],B=action[1],budget_ms=max(0.,50-control_ns/1e6),clock=response_clock)
    total=first_clock[0]-start+result['total_ns']
    # run_method's own final audit is inside total. Rescore the enclosing deadline.
    kernel_ns=result['total_ns']
    metrics=result['metrics']; ontime=total<=50_000_000
    metrics['within_budget']=ontime
    metrics['online_success']=bool(metrics['online_success'] and ontime)
    metrics['valid_output']=bool(metrics['valid_output'] and ontime)
    if not ontime: metrics['U_exec']=0; result['status']='timeout'
    metrics['L_total_ms']=total/1e6
    result.update(method='PALR-ET' if model else 'Rule-PALR',total_ns=total,budget_ms=50,
                  controller_features=x,controller_meta=meta,controller_fallback=fallback)
    result['timings_ns']['control_ns']+=total-kernel_ns
    result['controller_version']='P3-control-v1-exact-enclosing-clock'
    return result
