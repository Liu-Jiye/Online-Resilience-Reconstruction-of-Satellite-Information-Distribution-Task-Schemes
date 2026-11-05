from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import pytest
from isl.p1_orbits import (EARTH_KM, build_contacts, compare_windows, epoch, scan_runs,
                           screen, split_groups, visible)
from isl.p1_generation import component_seeds, create_instance, synthetic_contacts
from isl.p1_sources import download_once
from isl.reference import create_reference
from isl.validation import validate


@pytest.fixture
def tmp_path():
    cache = Path(__file__).resolve().parents[1] / '.cache'
    cache.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='p1-unit-', dir=cache) as directory:
        yield Path(directory)


def record(cat=100001):
    # Artificial unit orbit, not a live snapshot or a pilot/test instance.
    return {'OBJECT_NAME': 'UNIT', 'OBJECT_ID': '2024-001A', 'EPOCH': '2024-01-01T00:00:00.000000',
        'MEAN_MOTION': 15., 'ECCENTRICITY': .001, 'INCLINATION': 53., 'RA_OF_ASC_NODE': 40.,
        'ARG_OF_PERICENTER': 20., 'MEAN_ANOMALY': 0., 'EPHEMERIS_TYPE': 0, 'CLASSIFICATION_TYPE': 'U',
        'NORAD_CAT_ID': cat, 'ELEMENT_SET_NO': 999, 'REV_AT_EPOCH': 1, 'BSTAR': 0.,
        'MEAN_MOTION_DOT': 0., 'MEAN_MOTION_DDOT': 0.}


def test_earth_occultation_and_distance_predicate():
    a = np.array([[7000., 0, 0]])
    assert visible(a, np.array([[7000., 1000., 0]])).item()
    assert not visible(a, np.array([[-7000., 0, 0]])).item()
    assert not visible(a, np.array([[7000., 6000., 0]])).item()
    assert not visible(np.array([[EARTH_KM + 100, 0., 0.]]), np.array([[EARTH_KM + 100, 1000., 0.]])).item()


def test_crossing_refinement_conservative_and_clipped_endpoints():
    times = np.arange(0, 21, 5.)
    truth = lambda t: 3.123 <= t <= 16.789
    intervals = scan_runs(times, np.array([truth(t) for t in times]), truth)
    start, end = intervals[0]
    assert 3.123 <= start <= 3.223 and 16.689 <= end <= 16.789
    assert scan_runs(times, np.ones(5, dtype=bool), truth) == [(0., 20.)]
    assert scan_runs(times, np.zeros(5, dtype=bool), truth) == []


def test_fine_scan_can_detect_subcoarse_window():
    truth = lambda t: 1 <= t <= 3
    coarse = scan_runs(np.arange(0, 11, 5.), np.array([False, False, False]), truth)
    fine = scan_runs(np.arange(0, 11, 1.), np.array([truth(t) for t in range(11)]), truth)
    assert not coarse and len(fine) == 1
    audit = compare_windows([], [{'a': 'a', 'b': 'b', 'start': fine[0][0], 'end': fine[0][1], 'retained_geometric': False}])
    assert len(audit['missed_at_5s']) == 1 and audit['missed_retained_at_5s'] == 0


def test_screen_dedup_filters_counts_and_epoch_preserved():
    normal = record()
    old = {**normal, 'EPOCH': '2023-12-31T12:00:00'}
    bad_motion = {**record(100002), 'MEAN_MOTION': -1}
    bad_e = {**record(100003), 'ECCENTRICITY': .02}
    bad_height = {**record(100004), 'MEAN_MOTION': 1}
    bad_age = {**record(100005), 'EPOCH': '2023-12-01T00:00:00'}
    eligible, origin, report = screen([normal, old, bad_motion, bad_e, bad_height, bad_age])
    assert eligible == [normal]
    assert normal['EPOCH'] == '2024-01-01T00:00:00.000000'
    counts = report['counts']
    assert counts['duplicate_records_removed'] == 1
    assert counts['excluded_mean_motion'] == counts['excluded_eccentricity'] == counts['excluded_perigee'] == counts['excluded_epoch_age'] == 1


def test_320_unique_objects_and_split_isolation_and_shuffle_seed():
    rows = [record(cat) for cat in range(100000, 100400)]
    groups = split_groups(rows, 100010)
    assert groups == split_groups(list(reversed(rows)), 100010)
    assert [g['split'] for g in groups] == ['train'] * 6 + ['validation'] * 2 + ['test'] * 2
    assert all(len(g['norad_ids']) == 32 for g in groups)
    assert len({cat for g in groups for cat in g['norad_ids']}) == 320
    with pytest.raises(ValueError, match='user decision'):
        split_groups(rows[:319], 100010)


def test_synthetic_generation_reproducible_directions_and_bounds():
    satellites = tuple(f'S{i:02d}' for i in range(32))
    seeds = component_seeds(100100)
    assert len(set(seeds.values())) == 4
    contacts, _ = synthetic_contacts(satellites, np.random.Generator(np.random.PCG64(seeds['contacts'])))
    a, meta = create_instance('unit', satellites, contacts, 100100)
    b, meta_b = create_instance('unit', satellites, contacts, 100100)
    assert a == b and meta == meta_b
    assert len(a.tasks) == 100 and a.horizon == 5400
    windows = {(c.sender, c.receiver, c.start, c.end) for c in contacts}
    assert all((b, a, start, end) in windows for a, b, start, end in windows)
    assert all(0 <= t.release < t.deadline <= 5400 for t in a.tasks)
    assert set(t.data_bits for t in a.tasks) <= {500_000_000, 1_000_000_000, 2_000_000_000, 4_000_000_000}
    reference, _ = create_reference(a)
    assert reference and validate(a, reference).feasible


def test_real_sgp4_pipeline_same_orbits_reject_identical_positions_as_no_link():
    # Coincident unit orbits must not manufacture a 5000 km distance failure;
    # test the actual TEME path with nearby distinct orbital phases instead.
    a, b = record(), {**record(100002), 'MEAN_ANOMALY': 1.}
    contacts5, physical5 = build_contacts([a, b], epoch(a['EPOCH']), 0, 5, horizon=60)
    contacts1, physical1 = build_contacts([a, b], epoch(a['EPOCH']), 0, 1, horizon=60)
    assert len(contacts5) == len(contacts1) == 2
    assert physical5 == physical1
    assert contacts5[0].start == 0 and contacts5[0].end == 60


def test_download_uses_verified_cache_without_network(tmp_path, monkeypatch):
    import hashlib,json
    payload = b'[{"unit":1}]'
    (tmp_path / 'unit.json').write_bytes(payload)
    (tmp_path / 'unit.fetch.json').write_text(json.dumps({'status':'downloaded','filename':'unit.json',
                                                         'sha256':hashlib.sha256(payload).hexdigest()}))
    import isl.p1_sources as sources
    monkeypatch.setattr(sources, 'urlopen', lambda *a, **kw: pytest.fail('cache must not fetch network'))
    assert download_once(tmp_path, 'unit', 'https://unused.example', expect_json=True)['status'] == 'downloaded'
    (tmp_path / 'unit.json').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        download_once(tmp_path, 'unit', 'https://unused.example', expect_json=True)
