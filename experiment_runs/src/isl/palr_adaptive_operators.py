"""PALR operator selection using the archived P5 repair and validation contract."""
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns

from .p5 import repair
from .p5.indexed import earliest, opportunities
from .p5.online import rescore

P5_SOURCE_SHA256 = 'fc0d844dc0eaea2096018cbda3e4cc4c1c7e997eaf8a198d3fbd544279da337d'
ARMS = ('reuse', 'prune', 'ranked')


def best_edit(pool, plan, removals, instance, objective, timer, direct_cache, mode):
    incumbent = objective.key(plan)
    best, best_key, best_order = None, incumbent, None
    present = {item.task_id for item in plan}
    direct = {task.id: direct_cache[task.id] for task in pool if task.id in direct_cache}
    reduced_plans = {}
    active = [task for task in pool if task.id not in present and opportunities(instance, task)]
    jobs = []
    for index, removed in enumerate([*removals, None]):
        timer.guard()
        loss = instance.task_map[removed.task_id].utility if removed else 0
        for task_index, task in enumerate(active):
            service = bool(incumbent[0] or (removed and removed.task_id == objective.urgent))
            bound = (service and task.id != objective.urgent, incumbent[1] + loss - task.utility)
            if mode == 'reuse' or bound <= incumbent[:2]:
                jobs.append((bound, (index, task_index), removed, task))
    if mode.startswith('ranked'):
        jobs.sort(key=lambda job: (job[0], job[1]))
    for bound, order, removed, task in jobs:
        timer.guard()
        if mode != 'reuse' and bound > best_key[:2]:
            if mode.startswith('ranked'):
                break
            continue
        if task.id not in direct:
            direct[task.id] = earliest(instance, task, plan, timer.guard)
        added = direct[task.id]
        if removed and (task.sender in (removed.sender, removed.receiver)
                        or task.receiver in (removed.sender, removed.receiver)):
            slots = opportunities(instance, task)
            possible_overlap = any(left < removed.end and latest + task.duration > removed.start
                                   for left, latest in slots)
            if possible_overlap and (added is None or added.end > removed.start):
                if removed not in reduced_plans:
                    reduced_plans[removed] = tuple(item for item in plan if item != removed)
                added = earliest(instance, task, reduced_plans[removed], timer.guard)
        if added is None:
            continue
        key = objective.edit_key(incumbent, removed, added)
        if key < best_key or (best_order is not None and key == best_key and order < best_order):
            best, best_key, best_order = (removed, added), key, order
    if best is None:
        return None
    removed, added = best
    return repair.ordered(tuple(item for item in plan if item != removed) + (added,))


@lru_cache
def pilot_kernel(mode):
    path = Path(repair.__file__)
    source = path.read_text(encoding='utf-8')
    if sha256(source.encode('utf-8')).hexdigest() != P5_SOURCE_SHA256:
        raise RuntimeError('Archived P5 repair source hash mismatch')
    source = source.replace('    unchanged = ()', '    unchanged = ()\n    direct_cache = {}', 1)
    old = '                    elif earliest(instance, task, plan, timer.guard) is None:'
    assert source.count(old) == 1
    source = source.replace(old, '                    elif cache_direct(direct_cache, instance, task, plan, timer.guard) is None:')
    begin = source.index('                while admissions < B:')
    end = source.index("                stop_reason = 'admission_budget_exhausted'", begin)
    source = source[:begin] + """                while admissions < B:
                    timer.guard()
                    removals = sorted((item for item in plan if item.task_id in editable_ids),
                                      key=lambda item: item.task_id)
                    candidate = best_edit(pool, plan, removals, instance, objective, timer, direct_cache, mode)
                    if candidate is None:
                        break
                    accept(candidate)
                    direct_cache.clear()
""" + source[end:]
    namespace = dict(repair.__dict__, mode=mode,
                     best_edit=best_edit, cache_direct=cache_direct)
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace['run_method']


def cache_direct(cache, instance, task, plan, guard):
    cache[task.id] = earliest(instance, task, plan, guard)
    return cache[task.id]

class CachedEvent:
    """Cache the effective instance within a single measured call."""

    def __init__(self, case):
        self.case = case
        self.effective = None

    def __getattr__(self, name):
        return getattr(self.case, name)

    def effective_instance(self):
        if self.effective is None:
            base, event = self.case.base, self.case.event
            task_ids = set(base.task_map)
            rewards = dict(event.rewards)
            if not set(event.cancelled) <= task_ids or not rewards.keys() <= task_ids:
                raise ValueError('event references unknown task')
            if event.urgent is not None and event.urgent.id in task_ids:
                raise ValueError('urgent ID collision')
            tasks = tuple(replace(task, utility=rewards[task.id])
                          if task.id in rewards else task for task in base.tasks)
            if event.urgent is not None:
                tasks += (event.urgent,)
            contacts = self.case.post_event_contacts
            self.effective = replace(base, tasks=tasks, contacts=base.contacts if contacts is None else contacts)
        return self.effective


def context(case):
    return f'{case.event.kind}/{int(case.event.intensity >= .5)}'


def run(case, method, policy, budget_ms=50):
    start = perf_counter_ns()
    arm = policy.get(context(case), policy['default']) if method == 'adaptive' else method
    online_case = case if arm == 'fixed' else CachedEvent(case)
    kernel = repair.run_method if arm in ('fixed', 'cached_fixed') else pilot_kernel(arm)
    result = kernel(online_case, w=5, B=2,
                    budget_ms=max(0, budget_ms - (perf_counter_ns() - start) / 1e6))
    return rescore(case, result, perf_counter_ns() - start, budget_ms), arm
