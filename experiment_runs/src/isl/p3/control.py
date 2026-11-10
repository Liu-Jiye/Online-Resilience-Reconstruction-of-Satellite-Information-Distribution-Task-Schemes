"""Single-decision timed rule/ET controllers; no offline answers at inference."""
from time import perf_counter_ns
import numpy as np
from ..models import Item
from ..validation import validate
from ..metrics import scored_metrics
from .indexed import IndexedInstance, earliest, opportunities
from .repair_runtime import run_method, center_and_region

FEATURES=('kind','q','FR','n_feas','n_candidates','remaining','terminal_load','window_slack',
          'urgent_slack','affected_fraction','duration_window_ratio','pool_fraction')


def features(case,start=None):
    start=perf_counter_ns() if start is None else start
    instance=IndexedInstance(case.effective_instance())
    plan=tuple(p for p in case.reference if p.task_id not in case.event.cancelled)
    _,indices,spans=center_and_region(case,instance,5)
    original={p.task_id for p in case.reference}; editable={case.reference[i].task_id for i in indices}
    frozen={p.task_id for p in case.frozen}; current={p.task_id for p in plan}
    pool=[t for t in instance.tasks if t.id not in case.event.cancelled and t.id not in frozen
          and (t.id not in original or t.id in editable)
          and ((case.event.urgent and t.id==case.event.urgent.id)
               or any(t.release<b and a<t.deadline for a,b in spans))]
    candidates=[t for t in pool if t.id not in current]
    n_feas=0; complete=True
    for t in candidates:
        if perf_counter_ns()-start>=45_000_000:
            complete=False; break
        n_feas+=earliest(instance,t,plan) is not None
    urgent_opportunity=bool(case.event.urgent and earliest(instance,case.event.urgent,case.frozen) is not None)
    affected=set(case.event.cancelled) | {k for k,_ in case.event.rewards}
    fr=case.frozen_count/max(1,len(case.reference))
    remaining=max(0.,1-(perf_counter_ns()-start)/50_000_000)
    load=sum(b.end-b.start for b in instance.calendar)+2*sum(p.end-p.start for p in plan)
    values=[('cancellation','urgent_insertion','reward_update').index(case.event.kind),case.event.intensity,fr,
            n_feas,len(candidates),remaining,load/(len(instance.satellites)*instance.horizon),
            sum(max(0,t.deadline-t.release-t.duration) for t in candidates)/max(1,len(candidates))/instance.horizon,
            (case.event.urgent.deadline-case.event.urgent.release-case.event.urgent.duration)/instance.horizon if case.event.urgent else 0.,
            len(affected)/max(1,len(instance.tasks)),
            sum(t.duration/(t.deadline-t.release) for t in instance.tasks)/len(instance.tasks),len(pool)/len(instance.tasks)]
    return values,dict(n_feas=n_feas,complete=complete,urgent_opportunity=urgent_opportunity)


def rule_action(x,meta,rule):
    _,q,fr,n,_,r,*_=x
    if r<rule['r_low'] or fr>=rule['FR_high'] or q<=rule['q_low']: action=(3,1)
    elif q>=rule['q_high'] and n>=rule['n_high'] and r>=rule['r_high']: action=(10,3)
    else: action=(5,2)
    if n==0 and meta['complete']: action=(action[0],0)
    if meta['urgent_opportunity'] and action[1]==0: action=(action[0],1)
    return action


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
    result=run_method(case,w=action[0],B=action[1],budget_ms=max(0.,50-control_ns/1e6))
    total=control_ns+result['total_ns']
    # run_method's own final audit is inside total. Rescore the enclosing deadline.
    metrics=result['metrics']; ontime=total<=50_000_000
    metrics['within_budget']=ontime
    metrics['online_success']=bool(metrics['online_success'] and ontime)
    metrics['valid_output']=bool(metrics['valid_output'] and ontime)
    if not ontime: metrics['U_exec']=0; result['status']='timeout'
    metrics['L_total_ms']=total/1e6
    result.update(method='PALR-ET' if model else 'Rule-PALR',total_ns=total,budget_ms=50,
                  controller_features=x,controller_meta=meta,controller_fallback=fallback)
    result['timings_ns']['control_ns']+=control_ns
    return result
