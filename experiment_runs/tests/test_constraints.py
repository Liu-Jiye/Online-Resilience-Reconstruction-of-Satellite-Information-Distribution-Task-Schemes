from dataclasses import asdict, replace
from itertools import combinations
from fractions import Fraction
import json
import pytest
from isl.models import (Busy, Case, Contact, Event, Instance, Item, Task,
                        apply_event, case_from_dict, case_to_dict, inward_window, ordered, frozen_count)
from isl.validation import validate
from isl.placement import earliest
from isl.metrics import raw_metrics, scored_metrics, aggregate


def task(tid='t', sender='A', receiver='B', release=0, deadline=100, duration=10, utility=10):
    return Task(tid, sender, receiver, release, deadline, duration - 1, 1, utility)


def world(tasks=None, contacts=None, calendar=(), horizon=100):
    return Instance('unit', ('A', 'B', 'C', 'D'), tuple(tasks or [task()]),
                    tuple(contacts if contacts is not None else [Contact('ab', 'A', 'B', 0, horizon)]),
                    tuple(calendar), horizon)


def item(t, start=0):
    return Item(t.id, t.sender, t.receiver, start, start + t.duration)


@pytest.mark.parametrize('data,rate,expected', [(9, 1, 10), (1, 3, 2), (10, 3, 5),
    (10**20 + 1, 10**20, 3), (2 * 10**20, 10**20, 3)])
def test_exact_duration_rounding(data, rate, expected):
    assert Task('t', 'A', 'B', 0, 100, data, rate, 0).duration == expected


@pytest.mark.parametrize('field,value', [('rate_bps', 0), ('rate_bps', -1), ('data_bits', 0),
    ('data_bits', -1), ('utility', -1), ('utility', 1.2), ('rate_bps', float('nan')),
    ('sender', 'B'), ('release', 100), ('deadline', 0), ('id', ''), ('release', True)])
def test_invalid_task_rejected(field, value):
    with pytest.raises(ValueError):
        replace(task(), **{field: value})


@pytest.mark.parametrize('start,end,expected', [(0.1, 10.9, (1, 10)), (0, 10, (0, 10)),
                                              (0.1, 0.9, None), (1, 1, None)])
def test_contact_inward_rounding(start, end, expected):
    assert inward_window(start, end) == expected


@pytest.mark.parametrize('start,end', [(2, 1), (float('nan'), 10), (0, float('inf'))])
def test_bad_physical_window(start, end):
    with pytest.raises(ValueError):
        inward_window(start, end)


def test_duplicate_task_and_satellite_ids_rejected():
    with pytest.raises(ValueError):
        world([task(), task()])
    with pytest.raises(ValueError):
        replace(world(), satellites=('A', 'B', 'A'))


def test_right_boundary_and_touching_resources_legal():
    a, b = task('a'), task('b')
    instance = world([a, b], [Contact('ab', 'A', 'B', 0, 20)])
    assert validate(instance, (item(a, 0), item(b, 10))).feasible
    assert not validate(instance, (item(a, 11),)).feasible


@pytest.mark.parametrize('contacts', [[], [Contact('rev', 'B', 'A', 0, 100)],
    [Contact('short', 'A', 'B', 0, 9)],
    [Contact('part1', 'A', 'B', 0, 6), Contact('part2', 'A', 'B', 6, 12)]])
def test_no_direction_or_single_window_capacity(contacts):
    instance = world(contacts=contacts)
    assert not validate(instance, (item(task()),)).feasible
    assert earliest(instance, task(), ()) is None


@pytest.mark.parametrize('endpoints', [('C', 'B'), ('B', 'C'), ('A', 'C'), ('A', 'B')])
def test_both_endpoints_and_half_duplex_conflicts(endpoints):
    a, b = task('a'), task('b', *endpoints)
    instance = world([a, b], [Contact('ab', 'A', 'B', 0, 100), Contact('bc', *endpoints, 0, 100)])
    check = validate(instance, ordered((item(a), item(b, 5))))
    assert not check.feasible
    assert len(check.resource_pairs) == len({'A', 'B'} & set(endpoints))
    assert len(check.unique_task_pairs) == 1
    assert earliest(instance, b, (item(a),)).start == 10


def test_independent_transmissions_can_overlap():
    a, b = task('a'), task('b', 'C', 'D')
    instance = world([a, b], [Contact('ab', 'A', 'B', 0, 100), Contact('cd', 'C', 'D', 0, 100)])
    assert validate(instance, ordered((item(a), item(b)))).feasible


@pytest.mark.parametrize('resource', ['A', 'B'])
def test_calendar_blocks_both_endpoints(resource):
    instance = world(calendar=[Busy(resource, 0, 10), Busy(resource, 20, 30)])
    assert not validate(instance, (item(task(), 0),)).feasible
    assert validate(instance, (item(task(), 10),)).feasible
    assert earliest(instance, task(), ()).start == 10


@pytest.mark.parametrize('mutation', [lambda p: (), lambda p: (replace(p, start=1, end=11),),
    lambda p: (replace(p, sender='C'),), lambda p: (replace(p, task_id='other'),)])
def test_frozen_fields_preserved(mutation):
    p = item(task())
    check = validate(world(), mutation(p), frozen=(p,))
    assert not check.feasible and check.frozen_violations == 1


def test_duplicate_cancelled_and_wrong_duration_and_order():
    a, b = task('a'), task('b')
    instance = world([a, b])
    assert not validate(instance, (item(a), item(a))).feasible
    assert not validate(instance, (item(a),), cancelled=('a',)).feasible
    assert not validate(instance, (replace(item(a), end=9),)).feasible
    assert not validate(instance, (replace(item(a), start=0.0),)).feasible
    assert not validate(instance, (item(b, 10), item(a, 0))).feasible


def test_cumulative_admissions_cannot_reset_after_removal():
    t = task()
    instance = world()
    trace = [{'removed': [], 'added': [asdict(item(t))]},
             {'removed': ['t'], 'added': []},
             {'removed': [], 'added': [asdict(item(t, 10))]}]
    check = validate(instance, (item(t, 10),), original_ids=set(), budget=1,
                     admissions=2, initial=(), trace=trace)
    assert 'budget_exceeded' in check.errors
    assert 'trace_mismatch' not in check.errors
    forged = validate(instance, (item(t, 10),), original_ids=set(), budget=1,
                      admissions=1, initial=(), trace=trace)
    assert 'trace_mismatch' in forged.errors
    assert not validate(instance, (item(t),), original_ids=set(), budget=1).feasible


def test_trace_must_match_output_and_keep_frozen():
    p = item(task())
    assert not validate(world(), (p,), original_ids={'t'}, budget=2,
                        admissions=0, initial=(), trace=[]).feasible
    check = validate(world(), (p,), frozen=(p,), original_ids={'t'}, budget=2,
                     admissions=0, initial=(p,), trace=[{'removed': ['t'], 'added': [asdict(p)]}])
    assert 'invalid_trace_removal' in check.errors


def test_cancellation_and_forced_removal_excluded_from_drop():
    a, b, c = task('a'), task('b'), task('c')
    instance = world([a, b, c])
    case = Case(instance, (item(a), item(b, 10), item(c, 20)),
                Event('e', 'cancellation', 100001, 0.2, cancelled=('a',)))
    m = raw_metrics(case, (item(c, 25),), forced=('b',))
    assert (m['N_cancel'], m['N_forced'], m['N_drop'], m['N_surv'], m['M_all']) == (1, 1, 0, 1, 5)


def test_reward_utility_and_frozen_movement_denominators():
    a, b = task('a'), task('b')
    case = Case(world([a, b]), (item(a), item(b, 10)),
                Event('e', 'reward_update', 100002, 0.8, rewards=(('b', 90),)), 1)
    m = raw_metrics(case, (item(a), item(b, 20)))
    assert (m['U_raw'], m['M_all'], m['M_edit'], m['M_mean'], m['M_edit_mean']) == (100, 10, 10, 5, 10)


def test_late_unvalidated_and_service_failure_scoring_keeps_denominators():
    case = Case(world(), (), Event('e', 'urgent_insertion', 1, 0.2, urgent=task('urgent')))
    check = validate(case.base, ())
    rows = []
    for ns, validated in [(50, True), (51, True), (0, False)]:
        m = scored_metrics(case, (), check, ns, 50, validated)
        assert not m['online_success'] and not m['strict_urgent_success']
        assert m['U_exec'] == 0
        rows.append({'metrics': m})
    summary = aggregate(rows)
    assert summary['N_urgent'] == summary['N_applicable'] == 3
    assert summary['strict_feasible_numerator'] == 2
    assert summary['urgent_success_numerator'] == 0


def test_serialization_roundtrip_preserves_plan_and_metrics():
    t = task()
    case = Case(world(), (item(t),), Event('e', 'reward_update', 100000, 0.2, rewards=(('t', 12),)))
    restored = case_from_dict(json.loads(json.dumps(case_to_dict(case))))
    assert restored == case
    assert raw_metrics(restored, restored.reference) == raw_metrics(case, case.reference)


def test_frozen_ratio_exact_floor():
    assert frozen_count(tuple(range(50)), 0.58) == 29
    with pytest.raises(ValueError):
        frozen_count((), 1.1)


def test_renaming_preserves_feasibility():
    instance = world()
    p = item(task())
    rename = {'A': 'Z', 'B': 'Y', 'C': 'X', 'D': 'W'}
    new = replace(instance, satellites=tuple(rename[s] for s in instance.satellites),
                  tasks=(replace(task(), id='renamed', sender='Z', receiver='Y'),),
                  contacts=(replace(instance.contacts[0], sender='Z', receiver='Y'),))
    assert validate(instance, (p,)).feasible == validate(new, (replace(p, task_id='renamed', sender='Z', receiver='Y'),)).feasible


def test_tiny_exhaustive_relaxation_monotonicity():
    """Finite unit fixture, not a CP-SAT certificate or P2 experiment."""
    a, b = task('a', deadline=8, duration=3), task('b', deadline=8, duration=3)
    tight = world([a, b], [Contact('ab', 'A', 'B', 1, 7)], [Busy('B', 3, 4)], 8)
    relaxed = replace(tight, contacts=(Contact('ab', 'A', 'B', 0, 8),), calendar=())
    for size in (0, 1, 2):
        choices = [item(t, start) for t in (a, b) for start in range(6)]
        for selected in combinations(choices, size):
            plan = ordered(selected)
            if validate(tight, plan).feasible:
                assert validate(relaxed, plan).feasible


def test_placement_matches_independent_integer_enumeration():
    """Adversarial receiver/calendar boundaries, including release in busy slot."""
    for seed in range(60):
        # Fixed arithmetic variations, no dataset generation or test split.
        t = task(deadline=30, duration=3 + seed % 6, release=seed % 5)
        blocker = task('blocker', 'C', 'B', deadline=30, duration=4)
        instance = world([t, blocker], [Contact('ab', 'A', 'B', 0, 12),
            Contact('ab2', 'A', 'B', 15, 30), Contact('cb', 'C', 'B', 0, 30)],
            [Busy('A', 8, 10), Busy('B', 19, 22)], 30)
        plan = (item(blocker, seed % 5),)
        exhaustive = [s for s in range(30) if validate(instance, ordered(plan + (item(t, s),))).feasible]
        found = earliest(instance, t, plan)
        assert (found.start if found else None) == (min(exhaustive) if exhaustive else None)


def test_trace_rejects_illegal_intermediate_plan_even_if_final_is_valid():
    a, b = task('a'), task('b')
    instance = world([a, b])
    trace = [{'removed': [], 'added': [asdict(item(a)), asdict(item(b))]},
             {'removed': ['b'], 'added': []}]
    result = validate(instance, (item(a),), original_ids=set(), budget=2,
                      admissions=2, initial=(), trace=trace)
    assert 'invalid_trace_intermediate' in result.errors


def test_unchanged_outside_neighborhood_is_audited_independently():
    t = task()
    assert not validate(world(), (item(t, 10),), unchanged=(item(t),)).feasible


def test_background_calendar_merging_actual_load_and_seed():
    from isl.calendar import build_calendar
    busy, loads = build_calendar(('A', 'B'), 125, 100000, probability=1)
    assert busy == (Busy('A', 0, 125), Busy('B', 0, 125))
    assert loads == {'A': 1, 'B': 1}
    assert build_calendar(('A', 'B'), 125, 100000, probability=0) == ((), {'A': 0, 'B': 0})
    assert build_calendar(('B', 'A'), 5400, 100001) == build_calendar(('A', 'B'), 5400, 100001)


@pytest.mark.parametrize('params', [{'probability': -0.1}, {'probability': 1.1}, {'slot_s': 0}])
def test_invalid_background_calendar(params):
    from isl.calendar import build_calendar
    with pytest.raises(ValueError):
        build_calendar(('A', 'B'), 100, 100000, **params)
