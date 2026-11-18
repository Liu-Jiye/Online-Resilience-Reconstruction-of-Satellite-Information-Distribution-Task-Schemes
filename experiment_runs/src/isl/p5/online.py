"""P5 enclosing clocks and frozen rule ablations; no offline oracle at inference."""
from dataclasses import asdict
from time import perf_counter_ns
from ..models import Item,ordered
from ..metrics import scored_metrics,selection_key
from ..p3r.validation_indexed import validate
from ..p3r.control import rule_action
from ..p3r.indexed import IndexedInstance,earliest,opportunities
from ..p3r.repair_runtime import center_and_region
from .repair import run_method
from .search import run_puct,run_alns

def rescore(case,result,total_ns,budget_ms):
    result['kernel_total_ns']=result['total_ns'];result['total_ns']=total_ns;result['budget_ms']=budget_ms
    m=result['metrics'];ontime=total_ns<=budget_ms*1e6
    m.update(within_budget=ontime,L_total_ms=total_ns/1e6)
    if not ontime:m.update(online_success=False,valid_output=False,U_exec=0);result['status']='timeout'
    result['timing_boundary']='P5 full Python dispatch through return; excludes disk/encoding/offline replay'
    return result

def features(case,start,budget_ms):
    instance=IndexedInstance(case.effective_instance())
    plan=tuple(p for p in case.reference if p.task_id not in case.event.cancelled)
    _,indices,spans=center_and_region(case,instance,5)
    original={p.task_id for p in case.reference};editable={case.reference[i].task_id for i in indices}
    frozen={p.task_id for p in case.frozen};current={p.task_id for p in plan}
    candidates=[t for t in instance.tasks if t.id not in current and t.id not in frozen and t.id not in case.event.cancelled
                and (t.id not in original or t.id in editable) and
                ((case.event.urgent and t.id==case.event.urgent.id) or any(t.release<b and a<t.deadline for a,b in spans))]
    n=0;complete=True
    for t in candidates:
        if perf_counter_ns()-start>=budget_ms*900000:complete=False;break
        n+=earliest(instance,t,plan) is not None
    urgent=bool(case.event.urgent and earliest(instance,case.event.urgent,case.frozen) is not None)
    remaining=max(0.,1-(perf_counter_ns()-start)/max(1,budget_ms*1e6))
    affected=set(case.event.cancelled)|{k for k,_ in case.event.rewards}
    pool=[t for t in instance.tasks if t.id not in case.event.cancelled and t.id not in frozen
        and (t.id not in original or t.id in editable) and
        ((case.event.urgent and t.id==case.event.urgent.id) or any(t.release<b and a<t.deadline for a,b in spans))]
    load=sum(b.end-b.start for b in instance.calendar)+2*sum(p.end-p.start for p in plan)
    x=[('cancellation','urgent_insertion','reward_update').index(case.event.kind),case.event.intensity,
        case.frozen_count/max(1,len(case.reference)),n,len(candidates),remaining,
        load/(len(instance.satellites)*instance.horizon),
        sum(max(0,t.deadline-t.release-t.duration) for t in candidates)/max(1,len(candidates))/instance.horizon,
        (case.event.urgent.deadline-case.event.urgent.release-case.event.urgent.duration)/instance.horizon if case.event.urgent else 0.,
        len(affected)/max(1,len(instance.tasks)),sum(t.duration/(t.deadline-t.release) for t in instance.tasks)/max(1,len(instance.tasks)),
        len(pool)/max(1,len(instance.tasks))]
    return x,dict(n_feas=n,complete=complete,urgent_opportunity=urgent)

def controlled(case,rule,mode='joint',budget_ms=50):
    start=perf_counter_ns();x,meta=features(case,start,budget_ms)
    if mode=='no_time':x[5]=1.
    action=rule_action(x,meta,rule)
    if mode=='B_only':action=(5,action[1])
    if mode=='w_only':action=(action[0],2)
    control_ns=perf_counter_ns()-start
    r=run_method(case,w=action[0],B=action[1],budget_ms=max(0.,budget_ms-control_ns/1e6))
    r.update(controller_features=x,controller_meta=meta,controller_mode=mode)
    r['timings_ns']['control_ns']+=control_ns
    r['total_ns']+=control_ns
    return r

def upgrade(case,rule,search,threshold,stats,seed):
    start=perf_counter_ns()
    first=run_method(case,w=5,B=2,budget_ms=10)
    first_wall=perf_counter_ns()-start
    first=rescore(case,first,first_wall,10)
    tm=case.effective_instance().task_map
    reference_u=sum(tm[p.task_id].utility for p in case.reference if p.task_id not in case.event.cancelled)
    # Reuse a verified incumbent even if the 10ms phase returned late; its full
    # cost is still charged to the shared50ms. Late whole call never scores.
    service=first['validated'] and first['metrics']['service_success']
    ratio=first['metrics']['U_raw']/max(1,reference_u) if first['validated'] else 0.
    trigger=(bool(case.event.urgent) and not service) or ratio<threshold
    remaining=max(0.,50-(perf_counter_ns()-start)/1e6)
    chosen=first;second=None
    if trigger and remaining>0:
        if search=='PUCT':second=run_puct(case,temperature=.5,density_mean=stats['mean'],density_std=stats['std'],seed=seed,budget_ms=remaining,warm=first if first['validated'] else None)
        else:second=run_alns(case,seed=seed,budget_ms=remaining,warm=first if first['validated'] else None)
        if second['validated'] and (not first['validated'] or selection_key(case,tuple(Item(**p) for p in second['plan']))<selection_key(case,tuple(Item(**p) for p in first['plan']))):chosen=second
    result=dict(chosen)
    # Main scoring refers to the shared outer deadline, not either phase.
    check=validate(case.effective_instance(),tuple(Item(**p) for p in result['plan']),frozen=case.frozen,cancelled=case.event.cancelled) if result['validated'] else None
    total=perf_counter_ns()-start
    result['metrics']=scored_metrics(case,tuple(Item(**p) for p in result['plan']),check,total,50_000_000,result['validated'],result['forced_removed'])
    result['total_ns']=total
    result.update(upgrade_triggered=trigger,upgrade_threshold=threshold,first_phase_ns=first_wall,
        first_phase_over_10ms=first_wall>10_000_000,search_phase_started=second is not None,
        phases=[first]+([second] if second is not None else []),B=5,budget_ms=50)
    return result

def execute(case,spec,rule,stats):
    start=perf_counter_ns();name=spec['name'];budget=spec.get('budget_ms',50);seed=spec.get('seed',11)
    if name in ('Rule-PALR','B-only','w-only','No-time'):
        r=controlled(case,rule,mode={'Rule-PALR':'joint','B-only':'B_only','w-only':'w_only','No-time':'no_time'}[name],budget_ms=budget)
    elif name.startswith('Upgrade-'):
        r=upgrade(case,rule,name.split('-')[1],spec['threshold'],stats,seed)
    elif name.startswith('PUCT'):
        r=run_puct(case,temperature=.5,density_mean=stats['mean'],density_std=stats['std'],seed=seed,
            budget_ms=budget,B=spec.get('B',5),local_w=spec.get('local_w'),simulations=spec.get('simulations',40))
    elif name.startswith('ALNS'):
        r=run_alns(case,seed=seed,budget_ms=budget,B=spec.get('B',5),local_w=spec.get('local_w'))
    elif name=='CP-local':
        from .solver import online_local
        r=online_local(case,budget_ms=budget)
    else:
        kwargs={k:spec[k] for k in ('w','B','ignore_window','ignore_receiver','insertion_only','random_ties') if k in spec}
        r=run_method(case,method='Minimal-Repair' if name=='Minimal-Repair' else 'Fixed-PALR',budget_ms=budget,seed=seed,**kwargs)
    r['method']=name
    return rescore(case,r,perf_counter_ns()-start,budget)
