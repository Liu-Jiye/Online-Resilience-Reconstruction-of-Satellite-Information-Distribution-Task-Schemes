"""Online-only indexes. Full validation remains in isl.validation."""
from collections import defaultdict
from ..models import Item


class IndexedInstance:
    def __init__(self, instance):
        self.original = instance
        self.id = instance.id
        self.tasks = instance.tasks
        self.contacts = instance.contacts
        self.calendar = instance.calendar
        self.horizon = instance.horizon
        self.satellites = instance.satellites
        self.task_map = {t.id: t for t in instance.tasks}
        self.by_pair = defaultdict(list)
        self.by_resource = defaultdict(list)
        for c in instance.contacts:
            self.by_pair[c.sender, c.receiver].append(c)
        for b in instance.calendar:
            self.by_resource[b.resource].append((b.start, b.end))
        self.windows = {}
        self.last_plan = None
        self.plan_by_resource = None

    def occupied(self, plan, sender, receiver):
        if plan is not self.last_plan:
            by_resource = defaultdict(list)
            for p in plan:
                by_resource[p.sender].append((p.start, p.end))
                by_resource[p.receiver].append((p.start, p.end))
            self.last_plan = plan
            self.plan_by_resource = by_resource
        # Duplicate an interval occupying both endpoints only once, matching
        # the original routine (duplicates would not change earliest either).
        return sorted(set(self.plan_by_resource[sender] + self.plan_by_resource[receiver]
                          + self.by_resource[sender] + self.by_resource[receiver]))


def opportunities(instance, task):
    if not isinstance(instance, IndexedInstance):
        from ..placement import opportunities as plain
        return plain(instance, task)
    if task.id not in instance.windows:
        instance.windows[task.id] = sorted(
            (max(task.release, c.start), min(task.deadline, c.end) - task.duration)
            for c in instance.by_pair[task.sender, task.receiver]
            if max(task.release, c.start) + task.duration <= min(task.deadline, c.end))
    return instance.windows[task.id]


def earliest(instance, task, plan, check_deadline=lambda: None):
    if not isinstance(instance, IndexedInstance):
        from ..placement import earliest as plain
        return plain(instance, task, plan, check_deadline)
    occupied = instance.occupied(plan, task.sender, task.receiver)
    for left, latest in opportunities(instance, task):
        check_deadline()
        start = left
        for a, b in occupied:
            check_deadline()
            if b <= start:
                continue
            if a >= start + task.duration:
                break
            start = b
            if start > latest:
                break
        if start <= latest:
            return Item(task.id, task.sender, task.receiver, start, start + task.duration)
    return None


class Objective:
    def __init__(self, case, instance, forced=()):
        self.tasks = instance.task_map
        self.before = {p.task_id: p for p in case.reference}
        self.surviving = set(self.before) - set(case.event.cancelled) - set(forced)
        self.urgent = case.event.urgent.id if case.event.urgent else None

    def key(self, plan):
        ids = {p.task_id for p in plan}
        return (bool(self.urgent and self.urgent not in ids),
                -sum(self.tasks[p.task_id].utility for p in plan),
                len(self.surviving - ids), len(ids - self.before.keys()),
                sum(abs(p.start - self.before[p.task_id].start) for p in plan
                    if p.task_id in self.surviving))

    def edit_key(self, key, removed, added):
        service, neg_u, drop, add, move = key
        if removed is not None:
            tid = removed.task_id
            neg_u += self.tasks[tid].utility
            drop += tid in self.surviving
            add -= tid not in self.before
            if tid in self.surviving:
                move -= abs(removed.start - self.before[tid].start)
            if tid == self.urgent:
                service = True
        tid = added.task_id
        neg_u -= self.tasks[tid].utility
        drop -= tid in self.surviving
        add += tid not in self.before
        if tid in self.surviving:
            move += abs(added.start - self.before[tid].start)
        if tid == self.urgent:
            service = False
        return service, neg_u, drop, add, move
