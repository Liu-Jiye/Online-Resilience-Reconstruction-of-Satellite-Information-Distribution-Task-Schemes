"""Independent full-plan checker. Never imports search or placement routines."""
from dataclasses import asdict, dataclass
from collections import defaultdict
from ..models import Item


class ValidationIndex:
    """Checker-owned static indexes, built online and independent of placement."""
    def __init__(self, instance):
        self.original = instance
        self.task_map = instance.task_map
        self.contacts_by_pair = {}
        self.calendar_by_resource = {}
        for contact in instance.contacts:
            self.contacts_by_pair.setdefault((contact.sender, contact.receiver), []).append(contact)
        for i, busy in enumerate(instance.calendar):
            self.calendar_by_resource.setdefault(busy.resource, []).append((i,busy))
        self.calendar_pairs = {}

    def __getattr__(self, name):
        return getattr(self.original, name)

    def calendar_for(self, sender, receiver):
        key=(sender,receiver)
        if key not in self.calendar_pairs:
            self.calendar_pairs[key]=sorted(dict(self.calendar_by_resource.get(sender, []) + self.calendar_by_resource.get(receiver, [])).items())
        return self.calendar_pairs[key]


@dataclass(frozen=True)
class Check:
    feasible: bool
    errors: tuple[str, ...]
    window_ids: tuple[str, ...]
    resource_pairs: tuple[tuple[str, int, int], ...]
    unique_task_pairs: tuple[tuple[str, str], ...]
    frozen_violations: int
    calendar_conflicts: int

    def to_dict(self):
        return asdict(self)


def validate(instance, plan, *, frozen=(), cancelled=(), original_ids=None,
             budget=None, admissions=None, initial=None, trace=None, unchanged=()):
    """Audit fields, physics, commitments and optionally replay accepted edits.

    With a budget, cumulative admissions evidence is mandatory; final N_add alone
    cannot prove the operation budget. A supplied trace starts at initial and
    records each accepted remove/add, including re-admission of a removed item.
    """
    errors, windows, resource_pairs, task_pairs = [], set(), [], set()
    if not isinstance(instance, ValidationIndex):
        instance = getattr(instance, 'validation_index', None) or ValidationIndex(instance)
    tasks = instance.task_map
    contacts_by_pair = instance.contacts_by_pair
    by_resource = defaultdict(set)
    exact_items = defaultdict(list)
    for j, item in enumerate(plan):
        exact_items[item.task_id].append(item)
        by_resource[item.sender].add(j)
        by_resource[item.receiver].add(j)
    ids = [p.task_id for p in plan]
    calendar_conflicts = 0
    frozen_violations = 0
    if len(set(ids)) != len(ids):
        errors.append('duplicate_task')
    if list(plan) != sorted(plan, key=lambda p: (p.start, p.task_id)):
        errors.append('plan_order')
    for i, p in enumerate(plan):
        t = tasks.get(p.task_id)
        if t is None:
            errors.append('unknown_task:' + p.task_id)
            continue
        if p.task_id in cancelled:
            errors.append('cancelled:' + p.task_id)
        if (p.sender, p.receiver) != (t.sender, t.receiver):
            errors.append('endpoints:' + p.task_id)
        if type(p.start) is not int or type(p.end) is not int:
            errors.append('noninteger_time:' + p.task_id)
            if not isinstance(p.start, (int, float)) or not isinstance(p.end, (int, float)):
                continue
        expected = 1 + (t.data_bits + t.rate_bps - 1) // t.rate_bps
        if p.end - p.start != expected:
            errors.append('duration:' + p.task_id)
        if not (0 <= p.start < p.end <= instance.horizon
                and p.start >= t.release and p.end <= t.deadline):
            errors.append('task_window:' + p.task_id)
        if not any(c.sender == t.sender and c.receiver == t.receiver
                   and c.start <= p.start and p.end <= c.end for c in contacts_by_pair.get((t.sender, t.receiver), ())):
            windows.add(p.task_id)
        relevant_calendar = instance.calendar_for(p.sender, p.receiver)
        for _, b in relevant_calendar:
            if b.resource in (p.sender, p.receiver) and p.start < b.end and b.start < p.end:
                calendar_conflicts += 1
                errors.append('calendar:' + p.task_id + ':' + b.resource)
        # Include unknown prior items too: the original checks them against later items.
        for j in sorted(by_resource[p.sender] | by_resource[p.receiver]):
            if j >= i: break
            q = plan[j]
            if p.start < q.end and q.start < p.end:
                for resource in sorted({p.sender, p.receiver} & {q.sender, q.receiver}):
                    resource_pairs.append((resource, j, i))
                    task_pairs.add(tuple(sorted((q.task_id, p.task_id))))
    for p in frozen:
        if sum(q == p for q in exact_items[p.task_id]) != 1:
            frozen_violations += 1
    frozen_ids = {p.task_id for p in frozen}
    actual_order = [p.task_id for p in plan if p.task_id in frozen_ids]
    if actual_order != [p.task_id for p in frozen] and not frozen_violations:
        frozen_violations = len(frozen)
    if windows:
        errors.append('contact_window')
    if resource_pairs:
        errors.append('resource_overlap')
    if frozen_violations:
        errors.append('frozen_changed')
    if any(sum(q == p for q in exact_items[p.task_id]) != 1 for p in unchanged):
        errors.append('outside_neighborhood_changed')
    if budget is not None:
        if type(budget) is not int or budget < 0 or original_ids is None:
            errors.append('invalid_budget_context')
        elif type(admissions) is not int or admissions < 0:
            errors.append('missing_admission_evidence')
        elif initial is None or trace is None:
            errors.append('missing_trace_evidence')
        else:
            if admissions > budget or len(set(ids) - set(original_ids)) > admissions:
                errors.append('budget_exceeded')
            if trace is not None:
                state = {p.task_id: p for p in (initial or ())}
                if not set(state) <= set(original_ids) or not validate(
                        instance, initial, frozen=frozen, cancelled=cancelled, unchanged=unchanged).feasible:
                    errors.append('invalid_trace_initial')
                count = 0
                for step in trace:
                    for tid in step['removed']:
                        if tid not in state or tid in frozen_ids:
                            errors.append('invalid_trace_removal')
                        state.pop(tid, None)
                    for raw in step['added']:
                        item = Item(**raw)
                        if item.task_id in state or item.task_id in frozen_ids:
                            errors.append('invalid_trace_addition')
                        state[item.task_id] = item
                        count += item.task_id not in original_ids
                    intermediate = tuple(sorted(state.values(), key=lambda p: (p.start, p.task_id)))
                    if not validate(instance, intermediate, frozen=frozen, cancelled=cancelled,
                                    unchanged=unchanged).feasible:
                        errors.append('invalid_trace_intermediate')
                if count != admissions or sorted(state.values(), key=lambda p: (p.start, p.task_id)) != list(plan):
                    errors.append('trace_mismatch')
    return Check(not errors, tuple(errors), tuple(sorted(windows)), tuple(resource_pairs),
                 tuple(sorted(task_pairs)), frozen_violations, calendar_conflicts)
