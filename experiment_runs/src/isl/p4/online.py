"""Full-call deadline scoring and global online CP-SAT baseline."""
from dataclasses import asdict
from time import perf_counter_ns
from ortools.sat.python import cp_model
from ..models import Item,ordered
from ..metrics import scored_metrics
from ..p3r.validation_indexed import ValidationIndex,validate
from ..p2_exact_v2 import build_model

def enforce_wall(result,wall_ns):
    """Conservative P4 boundary includes method dispatch, metrics, evidence objects."""
    result['kernel_total_ns']=result['total_ns']
    result['total_ns']=wall_ns
    result['timing_boundary']='method_entry_through_return; excludes disk/JSON encoding and offline replay'
    m=result['metrics'];m['L_total_ms']=wall_ns/1e6;m['within_budget']=wall_ns<=50_000_000
    if not m['within_budget']:
        m.update(online_success=False,valid_output=False,U_exec=0)
        result['status']='timeout'
    return result

def run_cp(case,seed=11,budget_ms=50):
    start=perf_counter_ns();deadline=start+int(budget_ms*1e6)
    ins=case.effective_instance();index=ValidationIndex(ins)
    original={p.task_id for p in case.reference}
    initial=ordered(p for p in case.reference if p.task_id not in case.event.cancelled)
    assert validate(case.base,case.reference).feasible
    assert validate(index,initial,frozen=case.frozen,cancelled=case.event.cancelled).feasible
    ctx=dict(instance=ins,B=5,initial=initial,unchanged=case.frozen,original=original,cancelled=set(case.event.cancelled),
             allowed={t.id for t in ins.tasks if t.id not in case.event.cancelled})
    phases=[];plan=();trace=[];admissions=0;check=None
    # Solve service-required first; only a proven infeasible service licenses fallback.
    for urgent in ([True,False] if case.event.urgent else [False]):
        if perf_counter_ns()>=deadline:break
        b=perf_counter_ns()
        model,present,starts,ends,weights,alt=build_model(case,ctx,urgent)
        build_ns=perf_counter_ns()-b
        remaining=max(0.,(deadline-perf_counter_ns()-5_000_000)/1e9)
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.random_seed=seed;solver.parameters.max_time_in_seconds=remaining
        status=solver.solve(model) if remaining>0 else cp_model.UNKNOWN
        phases.append(dict(require_urgent=urgent,status=solver.status_name(status),model_construction_ns=build_ns,
                           solver_limit_s=remaining,solver_wall_s=solver.wall_time if remaining>0 else 0.,weights=weights))
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            plan=ordered(Item(t.id,t.sender,t.receiver,solver.value(starts[t.id]),solver.value(ends[t.id]))
                         for t in ins.tasks if solver.value(present[t.id]))
            before={p.task_id:p for p in initial};after={p.task_id:p for p in plan}
            removed=sorted(t for t in before if before[t]!=after.get(t))
            added=[asdict(after[t]) for t in sorted(after) if before.get(t)!=after[t]]
            trace=[dict(removed=removed,added=added)] if removed or added else []
            admissions=sum(p['task_id'] not in original for p in added)
            check=validate(index,plan,frozen=case.frozen,cancelled=case.event.cancelled,
                           original_ids=original,budget=5,admissions=admissions,initial=initial,trace=trace)
            assert check.feasible,check.errors
            break
        if not urgent or status!=cp_model.INFEASIBLE:break
    total=perf_counter_ns()-start
    metrics=scored_metrics(case,plan,check,total,int(budget_ms*1e6),check is not None)
    return dict(method='CP-SAT-50ms',version='P4-global-cp-v1',event_id=case.event.id,instance_id=case.base.id,
                status='timeout' if total>int(budget_ms*1e6) else 'feasible' if check else 'no_solver_solution',
                budget_ms=budget_ms,w=None,B=5,plan=[asdict(p) for p in plan],initial_plan=[asdict(p) for p in initial],
                trace=trace,admissions_cumulative=admissions,forced_removed=[],unchanged_outside_E=[],
                validated=check is not None,validation=check.to_dict() if check else None,
                total_ns=total,metrics=metrics,solver_seed=seed,phases=phases,
                optimality_scope='global editable suffix; no exact claim for UNKNOWN or timed-out results')
