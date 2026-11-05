"""Protocol v1 event metrics, with explicit applicability and failure scoring."""


def raw_metrics(case, plan, forced=()):
    instance = case.effective_instance()
    before = {p.task_id: p for p in case.reference}
    after = {p.task_id: p for p in plan}
    surviving = set(before) - set(case.event.cancelled) - set(forced)
    kept = surviving & set(after)
    editable = kept - {p.task_id for p in case.frozen}
    drop, add = len(surviving - set(after)), len(set(after) - set(before))
    move = sum(abs(after[t].start - before[t].start) for t in kept)
    move_edit = sum(abs(after[t].start - before[t].start) for t in editable)
    denominator = max(1, len(surviving))
    return {
        'U_raw': sum(instance.task_map[t].utility for t in after if t in instance.task_map),
        'N_cancel': len(set(before) & set(case.event.cancelled)),
        'N_forced': len(set(before) & set(forced)), 'N_surv': len(surviving),
        'N_drop': drop, 'N_add': add, 'N_sym': drop + add,
        'D_drop': drop / denominator, 'D_add': add / denominator, 'D_sym': (drop + add) / denominator,
        'K': len(kept), 'K_edit': len(editable), 'M_all': move, 'M_mean': move / max(1, len(kept)),
        'M_edit': move_edit, 'M_edit_mean': move_edit / max(1, len(editable)),
        'M_norm': move_edit / (instance.horizon * max(1, len(editable))),
    }


def selection_key(case, plan, forced=()):
    m = raw_metrics(case, plan, forced)
    urgent_success = case.event.urgent is None or any(p.task_id == case.event.urgent.id for p in plan)
    return (not urgent_success, -m['U_raw'], m['N_drop'], m['N_add'], m['M_all'])


def scored_metrics(case, plan, check, total_ns, deadline_ns, validated, forced=(), minimal_plan=None):
    raw = raw_metrics(case, plan, forced)
    feasible = bool(validated and check is not None and check.feasible)
    ontime = total_ns <= deadline_ns
    service = case.event.urgent is None or any(p.task_id == case.event.urgent.id for p in plan)
    raw.update({
        'applicable': case.event.applicable, 'strict_feasible': feasible,
        'service_success': feasible and service,
        'strict_urgent_success': (feasible and service) if case.event.urgent else None,
        'within_budget': ontime, 'online_success': case.event.applicable and feasible and service and ontime,
        'valid_output': case.event.applicable and feasible and ontime,
        'U': raw['U_raw'] if feasible else None,
        'U_exec': raw['U_raw'] if case.event.applicable and feasible and ontime else 0,
        'L_total_ms': total_ns / 1e6,
        'V_window': len(check.window_ids) if check else None,
        'V_resource': len(check.resource_pairs) if check else None,
        'V_resource_unique_task_pairs': len(check.unique_task_pairs) if check else None,
        'V_calendar': check.calendar_conflicts if check else None,
        'V_frozen': check.frozen_violations if check else None,
        'V_budget': int(any(e in {'budget_exceeded', 'trace_mismatch', 'missing_trace_evidence',
                                  'missing_admission_evidence'} for e in check.errors)) if check else None,
    })
    if minimal_plan is not None:
        baseline = raw_metrics(case, minimal_plan, forced)['U_raw']
        raw.update({'U_min': baseline,
                    'delta_U': raw['U_raw'] - baseline if feasible else None,
                    'normalized_delta_U': (raw['U_raw'] - baseline) / max(1, baseline) if feasible else None})
    return raw


def aggregate(rows):
    """Counts retain failures and distinguish N/A; no statistical inference in P0."""
    applicable = [r for r in rows if r['metrics']['applicable']]
    urgent = [r for r in applicable if r['metrics']['strict_urgent_success'] is not None]
    valid = [r for r in applicable if r['metrics']['valid_output']]
    count = len(applicable)
    return {
        'total_events': len(rows), 'N_applicable': count, 'N_na': len(rows) - count,
        'strict_feasible_numerator': sum(r['metrics']['strict_feasible'] for r in applicable),
        'online_success_numerator': sum(r['metrics']['online_success'] for r in applicable),
        'urgent_success_numerator': sum(r['metrics']['strict_urgent_success'] for r in urgent),
        'N_urgent': len(urgent), 'valid_output_numerator': len(valid),
        'U_exec_mean': sum(r['metrics']['U_exec'] for r in applicable) / count if count else None,
        'conditional_U_mean': sum(r['metrics']['U'] for r in valid) / len(valid) if valid else None,
        'conditional_U_denominator': len(valid),
    }
