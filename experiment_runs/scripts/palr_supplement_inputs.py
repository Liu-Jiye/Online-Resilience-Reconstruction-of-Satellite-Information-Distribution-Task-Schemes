"""Predetermined mechanism and D1 inputs for the two-blocker supplement."""
import random

import numpy as np

from isl.events import generate_event
from isl.load_pilot import indexed_reference
from isl.models import Busy, Case, Contact, Event, Instance, Item, Task, frozen_count, ordered
from isl.p1_generation import component_seeds, create_instance, synthetic_contacts
from isl.p2c import GROUPS, construct
from isl.validation import validate

KINDS = ('cancellation', 'urgent_insertion', 'reward_update')
GROUP_NAMES = ('direct', 'single', 'double_same', 'double_cross', 'triple', 'outside', 'hard')


def legacy_cases():
    index = 0
    for group, count in GROUPS:
        for ordinal in range(count):
            case, meta = construct(index, group, ordinal)
            yield case, group, meta
            index += 1


def mechanism_cases():
    for index in range(140):
        group = GROUP_NAMES[index // 20]
        seed = 781000 + index
        rng = random.Random(seed)
        sender, receiver, x, y, f, g, a, b = rng.sample([f'S{i}' for i in range(8)], 8)
        start = rng.randrange(230, 490)
        slack = rng.randrange(3, 14)
        duration = rng.randrange(36, 59)
        tasks, contacts, reference = [], [], []
        calendar = [Busy(a, start + 5, start + 20),
                    Busy(sender, start + duration + slack + 11, start + duration + slack + 18)]

        def planned(tid, pair, left, right):
            rate = rng.choice((300, 800, 1300))
            tasks.append(Task(tid, *pair, left, right, (right-left-1)*rate, rate, rng.randrange(10, 80)))
            contacts.append(Contact('C-' + tid, *pair, left, right))
            reference.append(Item(tid, *pair, left, right))

        planned('frozen-background', (f, g), start-100, start-94)
        frozen = 1
        hard_type = None
        if group == 'single':
            planned('block-1', (x, sender), start+slack+2, start+slack+9)
        if group in ('double_same', 'double_cross', 'triple'):
            planned('block-1', (x, sender), start+slack+2, start+slack+8)
            pair = (sender, y) if group == 'double_same' else (receiver, y)
            planned('block-2', pair, start+slack+10, start+slack+19)
        if group == 'triple':
            planned('block-3', (sender, y), start+slack+21, start+slack+27)
        if group == 'outside':
            planned('block-remote', (x, receiver), start-49, start+slack+5)
            for i in range(13):
                planned(f'parallel-{i}', (f, g), start-44+4*i, start-41+4*i)
        if group == 'hard':
            hard_type = ('calendar', 'frozen', 'contact')[index % 3]
            if hard_type == 'calendar':
                calendar.append(Busy(receiver, start+slack+3, start+slack+6))
            if hard_type == 'frozen':
                planned('frozen-block', (receiver, y), start+slack+3, start+slack+6)
                frozen = 2
        for i in range(rng.randrange(14, 20)):
            left = start + duration + slack + 22 + i*6
            planned(f'tail-{i}', (f, g), left, left + rng.randrange(2, 6))
        if hard_type != 'contact':
            contacts.append(Contact('urgent-contact', sender, receiver, start, start+duration+slack))
        ident = f'TWO-mechanism-{index:03d}'
        base = Instance(ident, (sender, receiver, x, y, f, g, a, b),
                        tuple(tasks), tuple(contacts), tuple(calendar), 1000)
        urgent = Task('urgent', sender, receiver, start-3, start+duration+slack+2,
                      (duration-1)*500, 500, 1000)
        event = Event(ident + ':urgent', 'urgent_insertion', seed, .8, urgent=urgent)
        case = Case(base, ordered(reference), event, frozen)
        assert validate(base, case.reference).feasible
        yield case, group, dict(hard_type=hard_type, seed=seed)


def natural_bases(split):
    start, count = (782000, 60) if split == 'validation' else (783000, 200)
    satellites = tuple(f'S{i:02d}' for i in range(32))
    for seed in range(start, start+count):
        rng = np.random.default_rng(component_seeds(seed)['contacts'])
        contacts, _ = synthetic_contacts(satellites, rng)
        base, _ = create_instance(f'TWO-D1-{seed}', satellites, contacts, seed)
        reference = indexed_reference(base)
        assert reference and validate(base, reference).feasible
        cases = []
        for kind in KINDS:
            for ratio in (0., .6):
                for intensity in (.2, .8):
                    event_seed = int(np.random.SeedSequence([seed, 781931, len(cases)]).generate_state(1, dtype=np.uint64)[0])
                    event = generate_event(base, reference, kind, ratio, intensity, event_seed)
                    cases.append(Case(base, reference, event, frozen_count(reference, ratio)))
        yield seed, cases


def certificate(case, editable_ids):
    """Independent brute force over integer seconds with all retained tasks fixed."""
    urgent = case.event.urgent
    endpoints = {urgent.sender, urgent.receiver}
    effective = case.effective_instance()
    windows = [(c.start, c.end) for c in effective.contacts
               if (c.sender, c.receiver) == (urgent.sender, urgent.receiver)]
    busy = [(b.start, b.end) for b in effective.calendar if b.resource in endpoints]
    fixed = tuple(p for p in case.reference if p not in case.frozen)
    relevant = [p for p in case.reference if endpoints.intersection((p.sender, p.receiver))]
    frozen_ids = {p.task_id for p in case.frozen}
    assert all(p.task_id not in frozen_ids for p in fixed)
    best = {}
    usable = 0
    for start in range(urgent.release, urgent.deadline - urgent.duration + 1):
        end = start + urgent.duration
        if not any(a <= start and end <= b for a, b in windows):
            continue
        if any(start < b and a < end for a, b in busy):
            continue
        blockers = sorted(p.task_id for p in relevant if start < p.end and p.start < end)
        if frozen_ids.intersection(blockers):
            continue
        usable += 1
        for name, domain in (('without_neighborhood', None), ('local', editable_ids)):
            if domain is not None and not domain.issuperset(blockers):
                continue
            if name not in best or len(blockers) < best[name]['minimum']:
                best[name] = dict(minimum=len(blockers), start=start, blockers=blockers)
    return dict(legal_starts_ignoring_editable_reference=usable,
                local=best.get('local'), without_neighborhood=best.get('without_neighborhood'))

