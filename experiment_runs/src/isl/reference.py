from time import perf_counter_ns
from .models import ordered
from .placement import earliest
from .validation import validate


def create_reference(instance):
    start = perf_counter_ns()
    plan = ()
    for task in sorted(instance.tasks, key=lambda t: t.density_key):
        item = earliest(instance, task, plan)
        if item is not None:
            candidate = ordered(plan + (item,))
            check = validate(instance, candidate)
            if not check.feasible:
                raise AssertionError(check.errors)
            plan = candidate
    check = validate(instance, plan)
    elapsed = perf_counter_ns() - start
    busy = {s: sum(p.end - p.start for p in plan if s in (p.sender, p.receiver))
            for s in instance.satellites}
    gaps = {}
    for s in instance.satellites:
        intervals = sorted([(p.start, p.end) for p in plan if s in (p.sender, p.receiver)]
                           + [(b.start, b.end) for b in instance.calendar if b.resource == s])
        end, free = 0, []
        for a, b in intervals:
            if a > end:
                free.append((end, a))
            end = max(end, b)
        if end < instance.horizon:
            free.append((end, instance.horizon))
        gaps[s] = free
    return plan, {'construction_ns': elapsed, 'scheduled_count': len(plan),
                  'terminal_scheduled_s': busy, 'terminal_free_intervals': gaps,
                  'validation': check.to_dict()}
