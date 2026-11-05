"""P0 utility for explicit background calendars, not a P1 dataset generator."""
import numpy as np
from .models import Busy


def build_calendar(satellites, horizon, seed, probability=0.5, slot_s=60):
    if not 0 <= probability <= 1 or type(horizon) is not int or horizon < 1 or type(slot_s) is not int or slot_s < 1:
        raise ValueError('invalid calendar parameters')
    rng = np.random.Generator(np.random.PCG64(seed))
    busy = []
    for satellite in sorted(satellites):
        begin = None
        for start in range(0, horizon, slot_s):
            if rng.random() < probability:
                if begin is None:
                    begin = start
            elif begin is not None:
                busy.append(Busy(satellite, begin, start))
                begin = None
        if begin is not None:
            busy.append(Busy(satellite, begin, horizon))
    return tuple(busy), {s: sum(b.end - b.start for b in busy if b.resource == s) / horizon
                         for s in sorted(satellites)}
