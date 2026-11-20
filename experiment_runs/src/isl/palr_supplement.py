"""Urgent two-removal extension of the archived P5 runtime."""
from hashlib import sha256
from pathlib import Path

from .models import Item, ordered
from .p3r.indexed import opportunities


def two_blocker_candidate(instance, plan, editable_ids, urgent, objective, guard):
    """Find the best two-removal insertion when the minimum is exactly two."""
    windows = opportunities(instance, urgent)
    if not windows:
        return None
    endpoints = {urgent.sender, urgent.receiver}
    occupied = [
        (p.start, p.end, p.task_id, p.task_id in editable_ids)
        for p in plan
        if endpoints.intersection((p.sender, p.receiver))
    ]
    for endpoint in endpoints:
        occupied.extend((a, b, None, False) for a, b in instance.by_resource[endpoint])

    best, best_key = None, None
    duration = urgent.duration
    for left, right in windows:
        guard()
        relevant = [
            (a - duration + 1, b, tid, editable)
            for a, b, tid, editable in occupied
            if a - duration + 1 <= right and left < b
        ]
        boundaries = {left}
        for a, b, _, _ in relevant:
            if left < a <= right:
                boundaries.add(a)
            if left < b <= right:
                boundaries.add(b)
        for start in sorted(boundaries):
            guard()
            active = [(tid, editable) for a, b, tid, editable in relevant if a <= start < b]
            if len(active) > 2 or any(not editable for _, editable in active):
                continue
            if len(active) < 2:
                return None
            removed = {tid for tid, _ in active}
            item = Item(urgent.id, urgent.sender, urgent.receiver, start, start + duration)
            candidate = ordered(tuple(p for p in plan if p.task_id not in removed) + (item,))
            key = (objective.key(candidate), start, tuple(sorted(removed)))
            if best_key is None or key < best_key:
                best, best_key = candidate, key
    return best


def _build_runtime():
    """Add a single guarded action to the same P5 search and audited acceptance."""
    source = Path(__file__).with_name('p5') / 'repair.py'
    data = source.read_text(encoding='utf-8')
    expected = 'fc0d844dc0eaea2096018cbda3e4cc4c1c7e997eaf8a198d3fbd544279da337d'
    if sha256(data.encode('utf-8')).hexdigest() != expected:
        raise RuntimeError('Archived P5 source differs from pinned supplement input')
    marker = '                while admissions < B:'
    addition = """                if case.event.urgent is not None and admissions < B:
                    candidate = two_blocker_candidate(
                        instance, plan, editable_ids, case.event.urgent, objective, timer.guard
                    )
                    if candidate is not None:
                        accept(candidate)
"""
    if data.count(marker) != 1:
        raise RuntimeError('P5 action insertion point is ambiguous')
    namespace = {'__package__': 'isl.p5', 'two_blocker_candidate': two_blocker_candidate}
    exec(compile(data.replace(marker, addition + marker), '<PALR two-blocker runtime>', 'exec'), namespace)
    return namespace['run_method']


run_two_blocker = _build_runtime()

