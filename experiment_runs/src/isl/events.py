"""Protocol events only. No P1 dataset or orbit generator is run here."""
from math import ceil
from fractions import Fraction
import numpy as np
from .models import Event, Task, frozen_count


def generate_event(instance, reference, kind, ratio, q, seed):
    """Independent PCG64 event seed; stable IDs and unchanged caller objects."""
    if not 0 <= q <= 1:
        raise ValueError('intensity outside [0,1]')
    rng = np.random.Generator(np.random.PCG64(seed))
    n = frozen_count(reference, ratio)
    frozen_ids = {p.task_id for p in reference[:n]}
    event_id = f'{instance.id}:{kind}:FR={ratio}:q={q}:seed={seed}'
    if kind == 'cancellation':
        editable = sorted(p.task_id for p in reference[n:])
        count = min(len(editable), max(1, ceil(Fraction(str(q)) * len(editable))))
        chosen = tuple(sorted(str(t) for t in rng.choice(editable, count, replace=False))) if editable else ()
        return Event(event_id, kind, seed, q, cancelled=chosen, applicable=bool(editable))
    if kind == 'reward_update':
        eligible = sorted(t.id for t in instance.tasks if t.id not in frozen_ids)
        # Exact ceil(30%); no test-dependent adjustment. Python round = ties-to-even.
        count = ceil(Fraction(3, 10) * len(eligible))
        chosen = sorted(str(t) for t in rng.choice(eligible, count, replace=False)) if count else []
        rewards = []
        for tid in chosen:
            sign = int(rng.choice([-1, 1]))
            value = round(instance.task_map[tid].utility * (1 + sign * Fraction(str(q))))
            rewards.append((tid, max(1, value)))
        return Event(event_id, kind, seed, q, rewards=tuple(rewards))
    if kind != 'urgent_insertion' or q not in (0.2, 0.8):
        raise ValueError('urgent protocol supports q=0.2/0.8 only')
    pairs = sorted({(c.sender, c.receiver) for c in instance.contacts})
    if rng.random() < 0.8 and pairs:
        sender, receiver = pairs[int(rng.integers(len(pairs)))]
    else:
        all_pairs = sorted((a, b) for a in instance.satellites for b in instance.satellites if a != b)
        if not all_pairs:
            raise ValueError('urgent request requires at least two satellites')
        sender, receiver = all_pairs[int(rng.integers(len(all_pairs)))]
    values = sorted(t.utility for t in instance.tasks)
    if not values:
        raise ValueError('urgent utility requires a nonempty base task set')
    middle = len(values) // 2
    median = Fraction(values[middle]) if len(values) % 2 else Fraction(values[middle - 1] + values[middle], 2)
    # Task utility is integer; round even only where the exact 5*median is half-integer.
    urgent = Task('urgent:' + event_id, sender, receiver, 0, 600 if q == 0.2 else 120,
                  int(rng.choice([500_000_000, 1_000_000_000, 2_000_000_000, 4_000_000_000])),
                  int(rng.choice([50_000_000, 100_000_000, 200_000_000])), round(5 * median))
    return Event(event_id, kind, seed, q, urgent=urgent)
