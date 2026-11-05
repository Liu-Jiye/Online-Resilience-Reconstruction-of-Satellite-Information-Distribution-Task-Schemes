"""Frozen GP -> screened SGP4/TEME objects -> geometric contacts."""
from datetime import datetime, timezone
from math import pi
import numpy as np
from sgp4.api import Satrec, jday
from sgp4.omm import initialize
from .models import Contact, inward_window

EARTH_KM = 6378.137


def epoch(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def jd_pair(time):
    return jday(time.year, time.month, time.day, time.hour, time.minute, time.second + time.microsecond / 1e6)


def satellite(record):
    sat = Satrec()
    initialize(sat, record)
    return sat


def propagate(sat, origin, seconds):
    values = np.asarray(seconds, dtype=np.float64)
    jd, fr = jd_pair(origin)
    errors, positions, _ = sat.sgp4_array(np.full(values.shape, jd), fr + values / 86400)
    if np.any(errors) or not np.all(np.isfinite(positions)) or np.any(np.linalg.norm(positions, axis=1) <= EARTH_KM):
        raise ValueError('SGP4 error, nonfinite state or position inside Earth')
    return positions


def screen(records):
    counts = {'input': len(records)}
    invalid, latest = [], {}
    for row in records:
        try:
            cat = int(row['NORAD_CAT_ID'])
            when = epoch(row['EPOCH'])
        except (KeyError, ValueError, TypeError):
            invalid.append(row.get('NORAD_CAT_ID'))
            continue
        if cat not in latest or when > epoch(latest[cat]['EPOCH']):
            latest[cat] = row
    counts['invalid_identity_epoch'] = len(invalid)
    counts['duplicate_records_removed'] = len(records) - len(invalid) - len(latest)
    counts['unique_latest'] = len(latest)
    if not latest:
        raise ValueError('No valid epoch')
    stamps = sorted(epoch(row['EPOCH']).timestamp() for row in latest.values())
    origin = datetime.fromtimestamp(float(np.median(stamps)), tz=timezone.utc)
    excluded = {k: [] for k in ('mean_motion', 'eccentricity', 'perigee', 'epoch_age', 'sgp4_or_earth')}
    eligible = []
    perigees = []
    for cat, row in sorted(latest.items()):
        try:
            motion, eccentricity = float(row['MEAN_MOTION']), float(row['ECCENTRICITY'])
            if not np.isfinite(motion) or motion <= 0:
                excluded['mean_motion'].append(cat)
                continue
            if not np.isfinite(eccentricity) or not 0 <= eccentricity < .02:
                excluded['eccentricity'].append(cat)
                continue
            n = motion * 2 * pi / 86400
            height = (398600.8 / n ** 2) ** (1 / 3) * (1 - eccentricity) - EARTH_KM
            if not 300 <= height <= 2000:
                excluded['perigee'].append(cat)
                continue
            if abs((epoch(row['EPOCH']) - origin).total_seconds()) > 72 * 3600:
                excluded['epoch_age'].append(cat)
                continue
            # Whole permitted 24 h band, then every actual contact computation
            # independently checks every propagated sample at 5 s / 1 s.
            propagate(satellite(row), origin, np.arange(-43200, 43201, 60, dtype=float))
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            excluded['sgp4_or_earth'].append({'norad_id': cat, 'error': str(error)})
            continue
        eligible.append(row)
        perigees.append(height)
    counts.update({f'excluded_{key}': len(value) for key, value in excluded.items()})
    counts['eligible'] = len(eligible)
    return eligible, origin, {'counts': counts, 'excluded': excluded, 't_ref_utc': origin.isoformat(),
        'median_epoch_population': 'deduplicated_records_with_parseable_epoch_before_orbit_filters',
        'screening_step_s': 60, 'screening_relative_band_s': [-43200, 43200],
        'mu_km3_s2': 398600.8, 'earth_radius_km': EARTH_KM,
        'perigee_eligible_min_km': min(perigees) if perigees else None,
        'perigee_eligible_max_km': max(perigees) if perigees else None}


def split_groups(eligible, seed):
    if len(eligible) < 320:
        raise ValueError(f'Only {len(eligible)} eligible objects; protocol revision requires user decision')
    ranked = sorted(eligible, key=lambda row: int(row['NORAD_CAT_ID']))
    order = np.random.Generator(np.random.PCG64(seed)).permutation(len(ranked))[:320]
    chosen = [ranked[int(i)] for i in order]
    groups = []
    for index in range(10):
        split = 'train' if index < 6 else 'validation' if index < 8 else 'test'
        rows = chosen[index * 32:(index + 1) * 32]
        groups.append({'group_id': f'g{index:02d}', 'split': split,
                       'norad_ids': [int(row['NORAD_CAT_ID']) for row in rows]})
    assert len({cat for g in groups for cat in g['norad_ids']}) == 320
    return groups


def visible(a, b, clearance=100., distance=5000.):
    delta = b - a
    denom = np.sum(delta * delta, axis=-1)
    lam = np.clip(-np.sum(a * delta, axis=-1) / np.maximum(denom, 1e-30), 0, 1)
    nearest = a + lam[..., None] * delta
    return (np.sum(nearest * nearest, axis=-1) > (EARTH_KM + clearance) ** 2) & (denom <= distance ** 2)


def scan_runs(times, mask, refine):
    """Coarse true runs, binary-refined crossing; preserve physical intervals."""
    edges = np.flatnonzero(mask[1:] != mask[:-1])
    bounds = []
    for index in edges:
        left, right = float(times[index]), float(times[index + 1])
        initial = bool(mask[index])
        while right - left > .1:
            middle = (left + right) / 2
            if bool(refine(middle)) == initial:
                left = middle
            else:
                right = middle
        # Choose the known-visible bracket side: conservatism to <=0.1 s.
        bounds.append(left if initial else right)
    if mask[0]:
        bounds.insert(0, float(times[0]))
    if mask[-1]:
        bounds.append(float(times[-1]))
    return list(zip(bounds[::2], bounds[1::2]))


def build_contacts(records, origin, offset_s, step_s=5, horizon=5400):
    if step_s not in (1, 5):
        raise ValueError('P1 contact audit supports step1/5 only')
    rows = sorted(records, key=lambda r: int(r['NORAD_CAT_ID']))
    sats = [satellite(row) for row in rows]
    times = np.arange(0, horizon + 1, step_s, dtype=float)
    positions = np.asarray([propagate(sat, origin, times + offset_s) for sat in sats])
    contacts, physical = [], []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            mask = visible(positions[i], positions[j])
            if not np.any(mask):
                continue
            def refine(t):
                a = propagate(sats[i], origin, np.array([offset_s + t]))[0]
                b = propagate(sats[j], origin, np.array([offset_s + t]))[0]
                return visible(a, b)
            a_id, b_id = str(rows[i]['NORAD_CAT_ID']), str(rows[j]['NORAD_CAT_ID'])
            for number, (start, end) in enumerate(scan_runs(times, mask, refine)):
                physical.append({'a': a_id, 'b': b_id, 'start': start, 'end': end,
                                 'retained_geometric': end - start >= 10})
                interval = inward_window(start, end)
                if end - start < 10 or interval is None:
                    continue
                a, b = interval
                contacts.extend((Contact(f'{a_id}-{b_id}-{number}-f', a_id, b_id, a, b),
                                 Contact(f'{a_id}-{b_id}-{number}-r', b_id, a_id, a, b)))
    return tuple(contacts), physical


def compare_windows(coarse, fine):
    """One-to-one overlap matching per undirected pair; report all misses."""
    matched, missing, extra = [], [], []
    pairs = sorted({(r['a'], r['b']) for r in coarse + fine})
    for pair in pairs:
        c = [r for r in coarse if (r['a'], r['b']) == pair]
        f = [r for r in fine if (r['a'], r['b']) == pair]
        used = set()
        for right in f:
            candidates = [(max(0, min(left['end'], right['end']) - max(left['start'], right['start'])), k)
                          for k, left in enumerate(c) if k not in used]
            overlap, k = max(candidates, default=(0, -1))
            if overlap <= 0:
                missing.append(right)
                continue
            used.add(k)
            left = c[k]
            matched.append({'pair': list(pair), 'start_error_s': abs(left['start'] - right['start']),
                            'end_error_s': abs(left['end'] - right['end']),
                            'coarse_retained': left['retained_geometric'], 'fine_retained': right['retained_geometric'],
                            'coarse_discrete': inward_window(left['start'], left['end']),
                            'fine_discrete': inward_window(right['start'], right['end'])})
        extra.extend(left for k, left in enumerate(c) if k not in used)
    return {'coarse_physical_windows': len(coarse), 'fine_physical_windows': len(fine),
            'matched': matched, 'missed_at_5s': missing, 'extra_at_5s': extra,
            'missed_retained_at_5s': sum(r['retained_geometric'] for r in missing),
            'retention_disagreements': sum(r['coarse_retained'] != r['fine_retained'] for r in matched),
            'discrete_disagreements': sum(r['coarse_discrete'] != r['fine_discrete'] for r in matched),
            'max_boundary_error_s': max((max(r['start_error_s'], r['end_error_s']) for r in matched), default=0)}
