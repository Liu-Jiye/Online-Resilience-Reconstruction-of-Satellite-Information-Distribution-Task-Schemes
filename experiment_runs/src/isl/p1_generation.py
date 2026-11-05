"""Predeclared training/validation pilots; no test performance access."""
from dataclasses import asdict
from math import ceil, floor
import numpy as np
from .models import Contact, Instance, Task, inward_window
from .calendar import build_calendar
from .placement import earliest, opportunities


def component_seeds(seed):
    children = np.random.SeedSequence(seed).spawn(4)
    return {name: int(child.generate_state(1, dtype=np.uint64)[0])
            for name, child in zip(('contacts', 'calendar', 'tasks', 'segment'), children)}


def synthetic_contacts(satellites, rng, horizon=5400):
    contacts, physical = [], []
    for i, a in enumerate(satellites):
        for b in satellites[i + 1:]:
            if rng.random() >= .2:
                continue
            intervals = []
            for _ in range(int(rng.integers(1, 5))):
                center = float(rng.uniform(0, horizon))
                length = float(rng.uniform(60, 600))
                intervals.append((max(0., center - length / 2), min(float(horizon), center + length / 2)))
            merged = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            for number, (start, end) in enumerate(merged):
                physical.append({'a': a, 'b': b, 'start': start, 'end': end})
                interval = inward_window(start, end)
                if interval:
                    left, right = interval
                    contacts.extend((Contact(f'{a}-{b}-{number}-f', a, b, left, right),
                                     Contact(f'{a}-{b}-{number}-r', b, a, left, right)))
    return tuple(contacts), physical


def generate_tasks(satellites, contacts, rng, horizon=5400, count=100):
    by_pair = {}
    for c in contacts:
        by_pair.setdefault((c.sender, c.receiver), []).append(c)
    pairs = sorted(by_pair)
    all_pairs = sorted((a, b) for a in satellites for b in satellites if a != b)
    tasks, details = [], []
    for i in range(count):
        use_contact = bool(rng.random() < .8)
        if use_contact and not pairs:
            # Explicit structural failure rather than silently altering mixture.
            raise ValueError('No contact pair available for contact-conditioned task draw')
        pair_set = pairs if use_contact else all_pairs
        sender, receiver = pair_set[int(rng.integers(len(pair_set)))]
        data = int(rng.choice([500_000_000, 1_000_000_000, 2_000_000_000, 4_000_000_000]))
        rate = int(rng.choice([50_000_000, 100_000_000, 200_000_000]))
        span = int(rng.choice([120, 300, 600]))
        if use_contact:
            windows = sorted(by_pair[(sender, receiver)], key=lambda c: (c.start, c.end, c.id))
            contact = windows[int(rng.integers(len(windows)))]
            anchor = float(rng.uniform(contact.start, contact.end))
            release = float(np.clip(anchor - span / 2, 0, horizon - span))
        else:
            anchor = None
            release = float(rng.uniform(0, horizon - span))
        task = Task(f't{i:03d}', sender, receiver, ceil(release), floor(release + span),
                    data, rate, int(rng.integers(10, 101)))
        tasks.append(task)
        details.append({'task_id': task.id, 'sampling_component': 'contact_pair' if use_contact else 'all_pair',
                        'nominal_span_s': span, 'physical_release_s': release, 'anchor_s': anchor})
    return tuple(tasks), details


def create_instance(instance_id, satellites, contacts, seed):
    seeds = component_seeds(seed)
    # The exogenous calendar is sampled before any demand.
    calendar, loads = build_calendar(satellites, 5400, seeds['calendar'], probability=.5, slot_s=60)
    tasks, task_meta = generate_tasks(satellites, contacts, np.random.Generator(np.random.PCG64(seeds['tasks'])))
    instance = Instance(instance_id, tuple(satellites), tasks, contacts, calendar, 5400)
    return instance, {'instance_seed': seed, 'component_seeds': seeds,
                      'background_actual_load_by_terminal': loads, 'task_sampling': task_meta}


def distribution(instance, reference, metadata):
    independently_window_feasible = [t.id for t in instance.tasks if opportunities(instance, t)]
    individually_calendar_feasible = [t.id for t in instance.tasks if earliest(instance, t, ()) is not None]
    scheduled_s = sum(p.end - p.start for p in reference) * 2
    terminal_time = len(instance.satellites) * instance.horizon
    busy_s = sum(b.end - b.start for b in instance.calendar)
    senders = {s: sum(t.sender == s for t in instance.tasks) for s in instance.satellites}
    receivers = {s: sum(t.receiver == s for t in instance.tasks) for s in instance.satellites}
    return {'instance_id': instance.id, 'scheduled_count': len(reference), 'task_count': len(instance.tasks),
        'contact_count_directed': len(instance.contacts),
        'window_only_feasible_count': len(independently_window_feasible),
        'single_task_calendar_feasible_count': len(individually_calendar_feasible),
        'window_only_feasible_fraction': len(independently_window_feasible) / len(instance.tasks),
        'single_task_calendar_feasible_fraction': len(individually_calendar_feasible) / len(instance.tasks),
        'scheduled_terminal_occupancy': scheduled_s / terminal_time,
        'scheduled_fraction_of_nonbackground_capacity': scheduled_s / max(1, terminal_time - busy_s),
        'background_actual_occupancy': busy_s / terminal_time,
        'combined_terminal_occupancy': (scheduled_s + busy_s) / terminal_time,
        'sender_demand_counts': senders, 'receiver_demand_counts': receivers,
        'max_sender_share': max(senders.values()) / len(instance.tasks),
        'max_receiver_share': max(receivers.values()) / len(instance.tasks),
        'contact_lengths_s': [c.end - c.start for c in instance.contacts if c.sender < c.receiver],
        'task_durations_s': [t.duration for t in instance.tasks],
        'task_window_spans_s': [t.deadline - t.release for t in instance.tasks],
        'utility_values': [t.utility for t in instance.tasks],
        'contact_pair_sampling_count': sum(t['sampling_component'] == 'contact_pair' for t in metadata['task_sampling'])}
