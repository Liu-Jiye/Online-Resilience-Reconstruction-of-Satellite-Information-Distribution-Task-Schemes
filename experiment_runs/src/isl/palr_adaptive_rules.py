"""P5 parameter ablations with the optimized PALR search operators."""
from time import perf_counter_ns

from .p3r.control import rule_action
from .p3r.indexed import IndexedInstance, earliest
from .p5.online import rescore
from .p5.repair import center_and_region
from .palr_adaptive_operators import CachedEvent, context, pilot_kernel

MODES = ('B_only', 'w_only', 'joint')


def choose(case, mode, rule, start, budget_ms):
    if mode not in MODES:
        raise ValueError(f'Unknown rule ablation {mode}')
    intensity = case.event.intensity
    frozen_ratio = case.frozen_count / max(1, len(case.reference))
    can_expand = (frozen_ratio < rule['FR_high'] and intensity > rule['q_low']
                  and intensity >= rule['q_high'])
    count, complete, urgent = 0, False, False
    if can_expand or mode != 'w_only':
        instance = IndexedInstance(case.effective_instance())
        cancelled = set(case.event.cancelled)
        plan = tuple(item for item in case.reference if item.task_id not in cancelled)
        _, _, spans = center_and_region(case, instance, 5)
        excluded = {item.task_id for item in case.reference} | cancelled
        urgent_task = case.event.urgent
        threshold = rule['n_high'] if can_expand else 1
        complete = True
        for task in instance.tasks:
            if task.id in excluded:
                continue
            if task != urgent_task and not any(task.release < right and left < task.deadline
                                               for left, right in spans):
                continue
            if perf_counter_ns() - start >= budget_ms * 900000:
                complete = False
                break
            if earliest(instance, task, plan) is not None:
                count += 1
                if count >= threshold:
                    break
        if mode != 'w_only' and count == 0 and complete and urgent_task is not None:
            urgent = earliest(instance, urgent_task, case.frozen) is not None
    remaining = max(0., 1 - (perf_counter_ns() - start) / max(1, budget_ms * 1e6))
    width, admissions = rule_action(
        (None, intensity, frozen_ratio, count, None, remaining),
        {'complete': complete, 'urgent_opportunity': urgent}, rule,
    )
    if mode == 'B_only':
        width = 5
    if mode == 'w_only':
        admissions = 2
    return width, admissions


def run_controlled(case, mode, rule, policy, budget_ms=50):
    start = perf_counter_ns()
    cached = CachedEvent(case)
    width, admissions = choose(cached, mode, rule, start, budget_ms)
    arm = policy.get(context(case), policy['default'])
    result = pilot_kernel(arm)(cached, w=width, B=admissions,
                               budget_ms=max(0., budget_ms - (perf_counter_ns() - start) / 1e6))
    return rescore(case, result, perf_counter_ns() - start, budget_ms), arm
