"""Same-domain online CP and full initial-reference offline CP sensitivity."""
from dataclasses import asdict
from time import perf_counter_ns
from ortools.sat.python import cp_model
from ..models import Item,ordered
from ..p2_exact_v2 import context,build_model
from ..p3r.validation_indexed import validate
from ..metrics import scored_metrics

def online_local(case,budget_ms=50):
    start=perf_counter_ns();ctx=context(case,5,2);deadline=start+int(budget_ms*1e6)
    phases=[];plan=();trace=[];admissions=0;check=None
    for require in ([True,False] if case.event.urgent else [False]):
        if perf_counter_ns()>=deadline:break
        b=perf_counter_ns();model,present,starts,ends,weights,alts=build_model(case,ctx,require)
        construction=perf_counter_ns()-b
        remaining=max(0.,(deadline-perf_counter_ns()-5_000_000)/1e9)
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=11;solver.parameters.max_time_in_seconds=remaining
        status=solver.solve(model) if remaining else cp_model.UNKNOWN
        phases.append(dict(require_urgent=require,status=solver.status_name(status),construction_ns=construction,solver_wall_s=solver.wall_time if remaining else 0.,weights=weights))
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            plan=ordered(Item(t.id,t.sender,t.receiver,solver.value(starts[t.id]),solver.value(ends[t.id])) for t in ctx['instance'].tasks if solver.value(present[t.id]))
            before={p.task_id:p for p in ctx['initial']};after={p.task_id:p for p in plan}
            removed=sorted(t for t,p in before.items() if after.get(t)!=p)
            added=[asdict(p) for t,p in sorted(after.items()) if before.get(t)!=p]
            trace=[dict(removed=removed,added=added)] if removed or added else []
            admissions=sum(p['task_id'] not in ctx['original'] for p in added)
            check=validate(ctx['instance'],plan,frozen=case.frozen,cancelled=case.event.cancelled,unchanged=ctx['unchanged'],original_ids=ctx['original'],budget=2,admissions=admissions,initial=ctx['initial'],trace=trace)
            assert check.feasible,check.errors
            break
        if not require or status!=cp_model.INFEASIBLE:break
    total=perf_counter_ns()-start
    return dict(method='CP-local',total_ns=total,budget_ms=budget_ms,w=5,B=2,status='feasible' if check else 'no_solver_solution',
        metrics=scored_metrics(case,plan,check,total,int(budget_ms*1e6),check is not None),plan=[asdict(p) for p in plan],
        initial_plan=[asdict(p) for p in ctx['initial']],trace=trace,admissions_cumulative=admissions,forced_removed=[],
        unchanged_outside_E=[asdict(p) for p in ctx['unchanged']],validated=check is not None,validation=check.to_dict() if check else None,phases=phases)

def reference_cp(instance,greedy,limit_s=30):
    start=perf_counter_ns();model=cp_model.CpModel();resources={s:[] for s in instance.satellites};present={};starts={}
    for i,b in enumerate(instance.calendar):resources[b.resource].append(model.new_fixed_size_interval_var(b.start,b.end-b.start,'busy'+str(i)))
    for task in instance.tasks:
        x=model.new_bool_var('x_'+task.id);s=model.new_int_var(0,instance.horizon,'s_'+task.id);ys=[]
        for c in instance.contacts:
            if (c.sender,c.receiver)!=(task.sender,task.receiver):continue
            left=max(task.release,c.start);right=min(task.deadline,c.end)-task.duration
            if left>right:continue
            y=model.new_bool_var('y_'+task.id+'_'+c.id);model.add(s>=left).only_enforce_if(y);model.add(s<=right).only_enforce_if(y)
            interval=model.new_optional_fixed_size_interval_var(s,task.duration,y,'i_'+task.id+'_'+c.id)
            resources[task.sender].append(interval);resources[task.receiver].append(interval);ys.append(y)
        model.add(sum(ys)==x);model.add(s==0).only_enforce_if(x.Not());present[task.id]=x;starts[task.id]=s
    for xs in resources.values():model.add_no_overlap(xs)
    model.maximize(sum(t.utility*present[t.id] for t in instance.tasks));assert not model.validate(),model.validate()
    before={p.task_id:p for p in greedy}
    for t in instance.tasks:model.add_hint(present[t.id],int(t.id in before));model.add_hint(starts[t.id],before[t.id].start if t.id in before else 0)
    construction=perf_counter_ns()-start
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=11
    solver.parameters.max_time_in_seconds=max(0.,limit_s-construction/1e9-.05)
    status=solver.solve(model) if solver.parameters.max_time_in_seconds>0 else cp_model.UNKNOWN
    plan=None
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        plan=ordered(Item(t.id,t.sender,t.receiver,solver.value(starts[t.id]),solver.value(starts[t.id])+t.duration) for t in instance.tasks if solver.value(present[t.id]))
        from ..validation import validate as independent
        assert independent(instance,plan).feasible
    return dict(status=solver.status_name(status),proven_optimal=status==cp_model.OPTIMAL,plan=[asdict(p) for p in plan] if plan is not None else None,
        objective=solver.objective_value if plan is not None else None,best_bound=solver.best_objective_bound if solver.parameters.max_time_in_seconds>0 else None,
        construction_ns=construction,total_ns=perf_counter_ns()-start,limit_s=limit_s,num_search_workers=1,seed=11,
        model_text=str(model.proto),response_text=str(solver.response_proto) if solver.parameters.max_time_in_seconds>0 else '',
        greedy_hint_utility=sum(instance.task_map[p.task_id].utility for p in greedy),objective_scope='initial reference utility only; not lexicographic repair optimality')
