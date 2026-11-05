from dataclasses import asdict, replace
from pathlib import Path
import ast
import pytest
from isl.events import generate_event
from isl.models import Case, Contact, Event, Item, apply_event, ordered
from isl.reference import create_reference
from isl.repair import center_and_region, run_method
from isl.validation import validate
from test_constraints import task, world, item

METHODS = ['Fixed-PALR', 'Minimal-Repair', 'Frozen-Greedy']


class TickClock:
    def __init__(self, step=1000):
        self.value, self.step = 0, step

    def __call__(self):
        self.value += self.step
        return self.value


def fixture_case(kind='cancellation'):
    tasks = (task('a', deadline=30, utility=40), task('b', deadline=30, utility=30),
             task('c', deadline=30, utility=20), task('d', deadline=30, utility=10))
    instance = world(tasks, [Contact('ab', 'A', 'B', 0, 30)])
    reference = (item(tasks[0], 0), item(tasks[1], 10), item(tasks[2], 20))
    if kind == 'cancellation':
        event = Event('cancel', kind, 100010, 0.2, cancelled=('b',))
    elif kind == 'reward_update':
        event = Event('reward', kind, 100011, 0.8, rewards=(('d', 100),))
    else:
        event = Event('urgent', kind, 100012, 0.8, urgent=task('u', deadline=30, utility=100))
    return Case(instance, reference, event, 1)


def audit_result(case, result):
    assert result['status'] == 'feasible'
    instance = apply_event(case.base, case.event)
    plan = tuple(Item(**p) for p in result['plan'])
    initial = tuple(Item(**p) for p in result['initial_plan'])
    check = validate(instance, plan, frozen=case.frozen, cancelled=case.event.cancelled,
                     original_ids={p.task_id for p in case.reference}, budget=result['B'],
                     admissions=result['admissions_cumulative'], initial=initial, trace=result['trace'])
    assert check.feasible, check.errors
    assert all(t >= 0 for t in result['timings_ns'].values())
    assert sum(result['timings_ns'].values()) == result['total_ns']
    assert result['metrics']['U_exec'] == result['metrics']['U']


@pytest.mark.parametrize('kind', ['cancellation', 'reward_update', 'urgent_insertion'])
@pytest.mark.parametrize('method', METHODS)
def test_three_disturbances_and_basic_methods(kind, method):
    case = fixture_case(kind)
    result = run_method(case, method, clock=TickClock(), budget_ms=50)
    audit_result(case, result)
    assert case.base.task_map['d'].utility == 10
    assert case.reference[0] == item(case.base.tasks[0])


def test_reference_density_deadline_id_ties_and_earliest():
    tasks = [task('z', deadline=10, utility=10), task('a', deadline=10, utility=10),
             task('b', release=10, deadline=20, utility=10)]
    instance = world(tasks)
    plan, info = create_reference(instance)
    assert [(p.task_id, p.start) for p in plan] == [('a', 0), ('b', 10)]
    assert info['validation']['feasible'] and info['scheduled_count'] == 2
    assert info['terminal_scheduled_s']['B'] == 20


def test_fixed_replacement_is_used_on_reward_update():
    case = fixture_case('reward_update')
    result = run_method(case, B=2, clock=TickClock())
    audit_result(case, result)
    assert 'd' in {p['task_id'] for p in result['plan']}
    assert result['metrics']['N_drop'] == 1
    assert result['trace'][0]['removed'] == ['c']
    assert result['admissions_cumulative'] == 1


def test_minimal_does_not_replace_reward_update():
    case = fixture_case('reward_update')
    result = run_method(case, 'Minimal-Repair', clock=TickClock())
    assert result['plan'] == [asdict(p) for p in case.reference]


@pytest.mark.parametrize('method', METHODS)
def test_B_zero_forbids_urgent_and_counts_service_failure(method):
    case = fixture_case('urgent_insertion')
    result = run_method(case, method, B=0, clock=TickClock())
    audit_result(case, result)
    assert result['admissions_cumulative'] == 0
    assert not result['metrics']['strict_urgent_success']
    assert not result['metrics']['online_success']


@pytest.mark.parametrize('method', METHODS)
def test_urgent_is_included_in_admissions_and_success_priority(method):
    case = fixture_case('urgent_insertion')
    # Tight low-utility urgent overrides utility gain: service has first priority.
    case = replace(case, event=replace(case.event, urgent=task('u', deadline=20, utility=0)))
    result = run_method(case, method, B=1, clock=TickClock())
    audit_result(case, result)
    if method == 'Minimal-Repair':
        assert not result['metrics']['strict_urgent_success']
    else:
        assert result['metrics']['strict_urgent_success']
        assert result['admissions_cumulative'] == 1


@pytest.mark.parametrize('method', METHODS)
def test_frozen_cancel_conflict_identified(method):
    case = fixture_case()
    case = replace(case, event=replace(case.event, cancelled=('a',)))
    result = run_method(case, method, clock=TickClock())
    assert result['status'] == 'frozen_conflict'
    assert not result['metrics']['online_success']
    assert result['metrics']['U_exec'] == 0


def test_frozen_endpoint_corruption_is_rejected_by_original_reference_check():
    case = fixture_case()
    corrupt = replace(case, reference=(replace(case.reference[0], receiver='C'),) + case.reference[1:])
    with pytest.raises(ValueError, match='invalid original reference'):
        run_method(corrupt)


@pytest.mark.parametrize('method', METHODS)
def test_all_frozen_urgent_can_use_free_gap_without_editing_frozen(method):
    t = task('a', deadline=30)
    case = Case(world([t]), (item(t),),
                Event('e', 'urgent_insertion', 100020, 0.2, urgent=task('u', deadline=30)), 1)
    result = run_method(case, method, B=1, clock=TickClock())
    audit_result(case, result)
    assert result['metrics']['strict_urgent_success']
    assert result['plan'][0] == asdict(item(t))


def test_empty_suffix_no_urgent_keeps_empty_plan():
    case = Case(world(), (), Event('e', 'cancellation', 100022, 0.2, applicable=False))
    result = run_method(case, clock=TickClock())
    assert result['status'] == 'not_applicable'
    assert not result['metrics']['online_success']


@pytest.mark.parametrize('method', METHODS)
def test_zero_budget_unvalidated_output_never_succeeds(method):
    result = run_method(fixture_case(), method, budget_ms=0, clock=TickClock())
    assert result['status'] == 'timeout'
    assert not result['validated'] and result['validation'] is None
    assert result['metrics']['U'] is None and result['metrics']['U_exec'] == 0


def test_final_validation_time_is_inside_response_budget(monkeypatch):
    import isl.repair as repair
    case = fixture_case()
    clock = TickClock()
    real = repair.validate

    def expensive_final(*args, **kwargs):
        result = real(*args, **kwargs)
        if kwargs.get('trace') is not None:
            # Baseline audit also has a trace; delay on second full trace check.
            expensive_final.calls += 1
            if expensive_final.calls == 2:
                clock.value += 100_000_000
        return result

    expensive_final.calls = 0
    monkeypatch.setattr(repair, 'validate', expensive_final)
    result = run_method(case, 'Minimal-Repair', clock=clock, budget_ms=50)
    assert result['status'] == 'timeout' and result['validation']['feasible']
    assert result['validated'] and not result['metrics']['online_success']
    assert result['metrics']['U_exec'] == 0
    assert result['timings_ns']['final_validation_ns'] >= 100_000_000


def test_mid_search_timeout_keeps_verified_incumbent():
    case = fixture_case('reward_update')
    result = run_method(case, budget_ms=0.04, clock=TickClock())
    assert result['status'] == 'timeout'
    assert result['validated'] and result['validation']['feasible']
    assert result['metrics']['U_exec'] == 0


def test_center_lower_median_and_frozen_clamp_and_fixed_original_scope():
    tasks = tuple(task(str(i), release=i * 10, deadline=i * 10 + 10) for i in range(7))
    instance = world(tasks)
    ref = tuple(item(t, i * 10) for i, t in enumerate(tasks))
    case = Case(instance, ref, Event('e', 'cancellation', 1, 0.8, cancelled=('1', '5')), 3)
    center, region, spans = center_and_region(case, instance, 1)
    assert center == 3 and region == (3, 4)
    assert (10, 20) in spans and (50, 60) in spans


def test_unplanned_reward_center_midpoint_and_no_window_fallback():
    case = fixture_case('reward_update')
    center, _, _ = center_and_region(case, apply_event(case.base, case.event), 0)
    assert center == 1  # feasible start [0,20], midpoint10 -> original position1
    base = replace(case.base, contacts=())
    fallback, _, _ = center_and_region(replace(case, base=base), base, 0)
    assert fallback == case.frozen_count


def test_PALR_never_edits_outside_E():
    case = fixture_case('reward_update')
    result = run_method(case, w=0, B=1, clock=TickClock())
    audit_result(case, result)
    # Unplanned d maps to index1: only b may be removed. Frozen a and c stay exact.
    assert result['editable_indices'] == [1]
    for p in (case.reference[0], case.reference[2]):
        assert asdict(p) in result['plan']


@pytest.mark.parametrize('kind', ['cancellation', 'reward_update', 'urgent_insertion'])
def test_PCG64_event_reproducibility_and_no_frozen_updates(kind):
    case = fixture_case()
    # Urgent protocol deadline600 requires horizon5400, independent of fixture times.
    instance = replace(case.base, horizon=5400)
    first = generate_event(instance, case.reference, kind, 0.6, 0.8, 100090)
    second = generate_event(instance, case.reference, kind, 0.6, 0.8, 100090)
    assert first == second
    assert 'a' not in first.cancelled
    assert 'a' not in dict(first.rewards)
    if kind == 'cancellation':
        assert len(first.cancelled) == 2
    elif kind == 'reward_update':
        assert len(first.rewards) == 1  # ceil(.3*3)
    else:
        assert first.urgent.release == 0 and first.urgent.deadline == 120


def test_cancellation_no_editable_is_NA_not_resampled():
    case = fixture_case()
    event = generate_event(case.base, case.reference, 'cancellation', 1, 0.8, 100091)
    assert not event.applicable and event.cancelled == ()


@pytest.mark.parametrize('method', METHODS)
def test_deterministic_methods_same_plan_trace_and_metrics(method):
    case = fixture_case('reward_update')
    one = run_method(case, method, clock=TickClock())
    two = run_method(case, method, clock=TickClock())
    assert one == two


def test_checker_has_no_search_imports():
    tree = ast.parse((Path(__file__).parents[1] / 'src/isl/validation.py').read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any('placement' in name or 'repair' in name or 'reference' in name for name in imports)


@pytest.mark.parametrize('params', [{'B': 6}, {'B': -1}, {'B': 1.5}, {'w': -1},
                                  {'budget_ms': float('nan')}, {'method': 'not implemented'}])
def test_invalid_parameters_not_silently_clipped(params):
    with pytest.raises(ValueError):
        run_method(fixture_case(), **params)


@pytest.mark.parametrize('method', METHODS)
def test_lost_frozen_window_returns_conflict(method):
    case = replace(fixture_case('reward_update'), post_event_contacts=())
    result = run_method(case, method, clock=TickClock())
    assert result['status'] == 'frozen_conflict'
    assert not result['metrics']['strict_feasible']
    assert result['metrics']['U_exec'] == 0


@pytest.mark.parametrize('method', METHODS)
def test_external_invalid_editable_task_removed_separately_from_active_drop(method):
    case = fixture_case('reward_update')
    case = replace(case, post_event_contacts=(Contact('ab-shrunk', 'A', 'B', 0, 20),))
    result = run_method(case, method, B=0, clock=TickClock())
    assert result['status'] == 'feasible'
    assert result['forced_removed'] == ['c']
    assert result['metrics']['N_forced'] == 1
    assert result['metrics']['N_drop'] == 0
    assert result['metrics']['N_surv'] == 2


def test_reward_updates_scheduled_and_unscheduled_same_event_values():
    case = fixture_case('reward_update')
    case = replace(case, event=replace(case.event, rewards=(('b', 0), ('d', 90))))
    for method in METHODS:
        result = run_method(case, method, clock=TickClock())
        expected = sum(case.effective_instance().task_map[p['task_id']].utility for p in result['plan'])
        assert expected == result['metrics']['U']


def test_no_window_and_resource_rejections_are_distinct_at_baseline():
    case = fixture_case('reward_update')
    extra = task('no-contact', 'C', 'D')
    case = replace(case, base=replace(case.base, tasks=case.base.tasks + (extra,)))
    result = run_method(case, clock=TickClock())
    assert result['candidate_census_complete']
    assert result['R_window_ids'] == ['no-contact']
    assert result['R_resource_ids'] == ['d']
    assert result['n_feas_initial'] == 0


def test_successful_urgent_minimal_can_have_lower_utility_than_PALR_without_losing_freeze():
    case = fixture_case('urgent_insertion')
    case = replace(case, event=replace(case.event, urgent=task('u', 'C', 'D', deadline=30)),
                   base=replace(case.base, contacts=case.base.contacts + (Contact('cd', 'C', 'D', 0, 30),)))
    for method in METHODS:
        result = run_method(case, method, B=1, clock=TickClock())
        assert result['metrics']['strict_urgent_success']
        assert result['admissions_cumulative'] == 1
        assert asdict(case.frozen[0]) in result['plan']
