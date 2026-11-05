"""P2 supplemental v2 CP-SAT reference; only urgent eligibility differs from v1.

The final domain permits simultaneous rescheduling inside E, so optimality is
not a claim about PALR's greedy one-replacement search or the continuous model.
"""
from dataclasses import asdict
from time import perf_counter_ns
from ortools.sat.python import cp_model
from .models import Item, ordered
from .repair_v2 import center_and_region
from .metrics import raw_metrics, selection_key
from .validation import validate


def context(case, w=5, B=2):
    instance = case.effective_instance()
    assert validate(case.base, case.reference).feasible
    center, indices, spans = center_and_region(case, instance, w)
    original = {p.task_id for p in case.reference}
    editable = {case.reference[i].task_id for i in indices}
    cancelled = set(case.event.cancelled)
    initial = ordered(p for p in case.reference if p.task_id not in cancelled)
    # P2 has exactly the three ordinary disturbances, no exogenous window loss.
    assert case.post_event_contacts is None
    unchanged = tuple(p for p in initial if p.task_id not in editable)
    allowed = {t.id for t in instance.tasks if t.id not in cancelled and
               (t.id in original or (case.event.urgent is not None and t.id == case.event.urgent.id)
                or any(t.release < b and a < t.deadline for a, b in spans))}
    return {'instance':instance, 'center':center, 'indices':indices, 'spans':spans,
            'original':original, 'editable':editable, 'cancelled':cancelled,
            'initial':initial, 'unchanged':unchanged, 'allowed':allowed, 'B':B, 'w':w}


def build_model(case, ctx, require_urgent=False):
    instance, B = ctx['instance'], ctx['B']
    model = cp_model.CpModel()
    resources = {s:[] for s in instance.satellites}
    for i, b in enumerate(instance.calendar):
        resources[b.resource].append(model.new_fixed_size_interval_var(b.start, b.end-b.start, f'busy_{i}'))
    present, starts, ends, alternatives = {}, {}, {}, {}
    fixed = {p.task_id:p for p in ctx['unchanged']}
    # Frozen cancelled items deliberately produce contradictory constraints and
    # an INFEASIBLE model, never a silently edited commitment.
    fixed.update({p.task_id:p for p in case.frozen})
    for t in instance.tasks:
        x = model.new_bool_var(f'x_{t.id}')
        s = model.new_int_var(0, instance.horizon, f's_{t.id}')
        e = model.new_int_var(0, instance.horizon+t.duration, f'e_{t.id}')
        model.add(e == s+t.duration)
        choices = []
        for k, c in enumerate(instance.contacts):
            if (c.sender, c.receiver) != (t.sender, t.receiver):
                continue
            left, right = max(t.release,c.start), min(t.deadline,c.end)-t.duration
            if left > right:
                continue
            y = model.new_bool_var(f'y_{t.id}_{k}')
            model.add(s >= left).only_enforce_if(y)
            model.add(s <= right).only_enforce_if(y)
            interval = model.new_optional_interval_var(s,t.duration,e,y,f'i_{t.id}_{k}')
            resources[t.sender].append(interval)
            resources[t.receiver].append(interval)  # the identical interval
            choices.append(y)
        model.add(sum(choices) == x)
        if t.id not in ctx['allowed']:
            model.add(x == 0)
        if t.id in fixed:
            model.add(x == 1)
            model.add(s == fixed[t.id].start)
            model.add(e == fixed[t.id].end)
        model.add(s == 0).only_enforce_if(x.Not())
        present[t.id], starts[t.id], ends[t.id] = x,s,e
        alternatives[t.id] = len(choices)
    for intervals in resources.values():
        model.add_no_overlap(intervals)
    new = [x for tid,x in present.items() if tid not in ctx['original']]
    model.add(sum(new) <= B)
    if require_urgent:
        model.add(present[case.event.urgent.id] == 1)
    utility = sum(t.utility*present[t.id] for t in instance.tasks)
    survivors = [p for p in case.reference if p.task_id not in ctx['cancelled']]
    drop = sum(1-present[p.task_id] for p in survivors)
    add = sum(new)
    movements = []
    for i,p in enumerate(survivors):
        d = model.new_int_var(0, instance.horizon, f'move_{i}')
        raw = model.new_int_var(0, instance.horizon, f'abs_{i}')
        model.add_abs_equality(raw, starts[p.task_id]-p.start)
        model.add(d == raw).only_enforce_if(present[p.task_id])
        model.add(d == 0).only_enforce_if(present[p.task_id].Not())
        movements.append(d)
    move_max = len(survivors)*instance.horizon
    w_add = move_max+1
    w_drop = (len(instance.tasks)+1)*w_add
    w_utility = (len(survivors)+1)*w_drop
    # Each multiplier strictly exceeds the full lower-priority range.
    objective = -utility*w_utility + drop*w_drop + add*w_add + sum(movements)
    model.minimize(objective)
    assert sum(t.utility for t in instance.tasks)*w_utility < 2**53
    assert not model.validate(), model.validate()
    return model, present, starts, ends, {'U':w_utility,'N_drop':w_drop,'N_add':w_add,'M_all':1}, alternatives


def witness(case, ctx, plan):
    before, after = {p.task_id:p for p in ctx['initial']}, {p.task_id:p for p in plan}
    removed = sorted(k for k,p in before.items() if after.get(k) != p)
    added = [asdict(p) for k,p in sorted(after.items()) if before.get(k) != p]
    trace = [{'removed':removed,'added':[]}] if removed else []
    # Remove changed editable originals first, then insert final items once.
    for p in added:
        trace.append({'removed':[],'added':[p]})
    admissions = sum(p['task_id'] not in ctx['original'] for p in added)
    check = validate(ctx['instance'], plan, frozen=case.frozen, cancelled=case.event.cancelled,
                     unchanged=ctx['unchanged'], original_ids=ctx['original'], budget=ctx['B'],
                     admissions=admissions, initial=ctx['initial'], trace=trace)
    assert check.feasible, check.errors
    assert all(p.task_id in ctx['allowed'] for p in plan)
    return {'validation':check.to_dict(),'admissions_cumulative':admissions,
            'initial_plan':[asdict(p) for p in ctx['initial']], 'trace':trace}


def solve_exact(case, *, w=5, B=2, limit_s=30, seed=11):
    started = perf_counter_ns()
    deadline = started+int(limit_s*1e9)
    ctx = context(case,w,B)
    phases, artifacts = [], []
    final_plan, final_status, final_weights, final_alt = None,'UNKNOWN',None,None
    urgent_certificate = 'not_applicable'
    stages = [True,False] if case.event.urgent else [False]
    for require_urgent in stages:
        phase_start = perf_counter_ns()
        model,present,starts,ends,weights,alt = build_model(case,ctx,require_urgent)
        construction_ns = perf_counter_ns()-phase_start
        remaining = max(0.,(deadline-perf_counter_ns())/1e9-.02)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = seed
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.absolute_gap_limit = 0
        solver.parameters.relative_gap_limit = 0
        solver.parameters.log_search_progress = False
        model_bytes = model.proto.__str__().encode('utf-8')
        status = solver.solve(model) if remaining > 0 else cp_model.UNKNOWN
        status_name = solver.status_name(status)
        assert status_name in {'OPTIMAL','FEASIBLE','INFEASIBLE','UNKNOWN'}, solver.response_stats()
        feasible = status in (cp_model.OPTIMAL,cp_model.FEASIBLE)
        plan = ordered(Item(t.id,t.sender,t.receiver,solver.value(starts[t.id]),solver.value(ends[t.id]))
                       for t in ctx['instance'].tasks if feasible and solver.value(present[t.id])) if feasible else None
        details = {'phase':'urgent_required' if require_urgent else 'fallback_or_regular',
                   'status':status_name, 'require_urgent':require_urgent,
                   'model_construction_ns':construction_ns, 'solver_limit_s':remaining,
                   'solver_wall_s':solver.wall_time if remaining > 0 else 0.,
                   'objective':solver.objective_value if feasible else None,
                   'best_bound':solver.best_objective_bound if remaining > 0 else None,
                   'branches':solver.num_branches if remaining > 0 else 0,
                   'conflicts':solver.num_conflicts if remaining > 0 else 0,
                   'weights':weights, 'model_alternatives':alt,
                   'solver_parameters':str(solver.parameters)}
        phases.append(details)
        artifacts.append({'model_pbtxt':model_bytes, 'response_pbtxt':str(solver.response_proto).encode('utf-8') if remaining > 0 else b'not_solved',
                          'solver_stats':solver.response_stats() if remaining > 0 else 'not_solved'})
        if feasible:
            final_plan, final_status, final_weights, final_alt = plan,status_name,weights,alt
            if require_urgent: urgent_certificate = 'service_feasible'
            break
        if require_urgent:
            urgent_certificate = 'service_proven_infeasible' if status == cp_model.INFEASIBLE else 'service_unknown'
            # Only proven infeasibility licenses optimal fallback classification.
        else:
            final_status = status_name
    if case.event.urgent and urgent_certificate == 'service_unknown' and final_status == 'OPTIMAL':
        final_status = 'FEASIBLE'
    audit_start = perf_counter_ns()
    evidence = witness(case,ctx,final_plan) if final_plan is not None else None
    validation_ns = perf_counter_ns()-audit_start
    total_ns = perf_counter_ns()-started
    result = {'method':'CP-SAT-30s-local','version':'1.1-urgent-eligibility-v2','eligibility_version':'v2','event_id':case.event.id,'instance_id':case.base.id,
              'status':final_status,'urgent_certificate':urgent_certificate,'phases':phases,
              'w':w,'B':B,'limit_s':limit_s,'num_search_workers':1,'solver_seed':seed,
              'center_index':ctx['center'],'editable_indices':list(ctx['indices']),
              'candidate_spans':list(ctx['spans']),'allowed_task_ids':sorted(ctx['allowed']),
              'unchanged_outside_E':[asdict(p) for p in ctx['unchanged']],
              'plan':[asdict(p) for p in final_plan] if final_plan is not None else None,
              'metrics':raw_metrics(case,final_plan) if final_plan is not None else None,
              'selection_key':list(selection_key(case,final_plan)) if final_plan is not None else None,
              'certificate':evidence,'validation_ns':validation_ns,'total_ns':total_ns,
              'actual_total_exceeds_30s':total_ns > int(limit_s*1e9),
              'optimality_scope':'same discrete integer input, frozen fields, E-exterior commitments, candidate eligibility and final admission B; arbitrary scheduling within E; not PALR search reachability',
              'proven_optimal':final_status == 'OPTIMAL',
              'proven_infeasible':final_status == 'INFEASIBLE'}
    return result, artifacts
