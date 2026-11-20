"""Seal inputs, run paired methods, and independently audit outputs."""
import argparse
from collections import Counter
from dataclasses import asdict
import gzip
from hashlib import sha256
from itertools import product
import json
import os
from pathlib import Path
import platform
import random
import sys
from time import perf_counter_ns

import numpy as np

from isl.models import Item, canonical_json, case_from_dict, case_to_dict
from isl.p5.indexed import IndexedInstance
from isl.p5.online import rescore
from isl.p5.repair import center_and_region, run_method
from isl.palr_supplement import run_two_blocker
from isl.validation import validate
from palr_supplement_inputs import KINDS, certificate, legacy_cases, mechanism_cases, natural_bases

ROOT = Path(__file__).resolve().parents[1]
GRID = tuple(product((3, 5, 10), (1, 2, 3)))
BASELINES = {'Minimal-Repair': ('Minimal-Repair', 5, 5),
             'Frozen-Greedy': ('Frozen-Greedy', 5, 5),
             'Original-fixed': ('Fixed-PALR', 5, 2)}
ADAPTIVE = ('adaptive-w', 'adaptive-B', 'adaptive-joint')
CONTROLLED = {'legacy': legacy_cases, 'mechanism': mechanism_cases}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def write_record(stream, value):
    stream.write(canonical_json(value) + '\n')


def load_records(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def grid_name(w, budget):
    return f'two-w{w}-B{budget}'


def local_ids(case, w=5):
    _, indices, _ = center_and_region(case, IndexedInstance(case.effective_instance()), w)
    return {case.reference[i].task_id for i in indices}


def dispatch(case, method, policy, clock=perf_counter_ns):
    start = clock()
    if method in BASELINES:
        kernel = run_method
        label, w, b = BASELINES[method]
    else:
        kernel = run_two_blocker
        label = 'Fixed-PALR'
        action = policy[method]
        w, b = action[case.event.kind] if method in ADAPTIVE else action
    remaining = max(0., 50 - (clock()-start)/1e6)
    row = kernel(case, label, w=w, B=b, budget_ms=remaining, clock=clock)
    row = rescore(case, row, clock()-start, 50)
    row.update(method=method, kind=case.event.kind,
               timing_boundary='full supplement dispatch through kernel return')
    return row


def audit(case, row):
    if not row['validated']:
        assert not row['metrics']['valid_output'] and row['metrics']['U_exec'] == 0
        if row['validation'] is not None:
            raise AssertionError(row['validation'])
        return False
    restored = lambda items: tuple(Item(**p) for p in items)
    plan = restored(row['plan'])
    check = validate(case.effective_instance(), plan, frozen=case.frozen,
                     cancelled=case.event.cancelled,
                     original_ids={p.task_id for p in case.reference}, budget=row['B'],
                     admissions=row['admissions_cumulative'], initial=restored(row['initial_plan']),
                     trace=row['trace'], unchanged=restored(row['unchanged_outside_E']))
    if not check.feasible:
        raise AssertionError((case.event.id, row['method'], check))
    return True


def select(rows):
    utility, success = Counter(), Counter()
    for row in rows:
        kind = row['kind']
        config = (row['w'], row['B'])
        for key in ((kind, config), ('all', config)):
            utility[key] += row['metrics']['U_exec']
            success[key] += row['metrics']['online_success']

    def choose(kind, grid):
        return min(grid, key=lambda config: (-utility[kind, config], -success[kind, config], *config))

    w, b = choose('all', GRID)
    return {'selected-fixed': (w, b),
            'adaptive-w': {k: choose(k, [c for c in GRID if c[1] == b]) for k in KINDS},
            'adaptive-B': {k: choose(k, [c for c in GRID if c[0] == w]) for k in KINDS},
            'adaptive-joint': {k: choose(k, GRID) for k in KINDS}}


def seal(out):
    inputs = out / 'inputs'
    inputs.mkdir()
    for tag, generator in CONTROLLED.items():
        with gzip.open(inputs / (tag+'.jsonl.gz'), 'wt', encoding='utf-8') as stream:
            for case, group, meta in generator():
                write_record(stream, dict(case=case_to_dict(case), group=group, meta=meta))
    for split in ('validation', 'test'):
        with gzip.open(inputs / (split+'.jsonl.gz'), 'wt', encoding='utf-8') as stream:
            for seed, cases in natural_bases(split):
                shared = case_to_dict(cases[0])
                events = [dict(event=asdict(c.event), frozen_count=c.frozen_count) for c in cases]
                write_record(stream, dict(seed=seed, base=shared['base'], reference=shared['reference'], events=events))
    tracked_inputs = sorted((ROOT/'src/isl').rglob('*.py')) + sorted(Path(__file__).parent.glob('*palr_supplement*.py'))
    tracked_inputs.append(ROOT/'protocol/PALR_TWO_BLOCKER_SUPPLEMENT.md')
    save(out/'freeze.json', dict(
        inputs={f.name: sha256(f.read_bytes()).hexdigest() for f in sorted(inputs.iterdir())},
        source={p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in tracked_inputs},
        environment=dict(python=sys.version, numpy=np.__version__, platform=platform.platform(),
                         processor=os.environ.get('PROCESSOR_IDENTIFIER', platform.processor()),
                         cpu_count=os.cpu_count()),
        timing=dict(budget_ms=50, process_count=1, order_seed=781777, cpu_affinity='OS default')))
    print('All inputs sealed', flush=True)


def controlled(out, tag, rng, grid_policy):
    default = grid_name(5, 2)
    expected = {'direct': 0, 'single': 1, 'double': 2, 'double_same': 2,
                'double_cross': 2, 'triple': 3, 'outside': None, 'hard': None}
    totals = Counter()
    with gzip.open(out/(tag+'_rows.jsonl.gz'), 'wt', encoding='utf-8') as results:
        for raw in load_records(out/'inputs'/(tag+'.jsonl.gz')):
            case, group = case_from_dict(raw['case']), raw['group']
            ids = local_ids(case)
            witness = certificate(case, ids)
            local = witness['local']
            k = local['minimum'] if local else None
            assert k == expected[group], (case.base.id, group, witness)
            if group == 'outside':
                assert witness['without_neighborhood']['minimum'] == 1
                assert certificate(case, local_ids(case, 20))['local']['minimum'] == 1
            if group == 'hard':
                assert witness['without_neighborhood'] is None
                assert witness['legal_starts_ignoring_editable_reference'] == 0
            methods = [*BASELINES, default]
            rng.shuffle(methods)
            for method in methods:
                row = dispatch(case, method, grid_policy)
                row['independent_audit'] = audit(case, row)
                row.update(group=group, certificate=witness, run_type='wall_clock')
                write_record(results, row)
                totals[method, group] += row['metrics']['online_success']
            # A logical clock isolates mechanism regressions from host scheduling.
            for method in ('Original-fixed', default):
                row = dispatch(case, method, grid_policy, clock=lambda: 0)
                assert audit(case, row)
                expected_success = k in ((0, 1, 2) if method == default else (0, 1))
                assert row['metrics']['online_success'] == expected_success
                if k == 2 and method == default:
                    first = row['trace'][0]
                    assert len(first['removed']) == 2 and [p['task_id'] for p in first['added']] == [case.event.urgent.id]
                    zero_policy = {default: (5, 0)}
                    zero = dispatch(case, default, zero_policy, clock=lambda: 0)
                    assert not zero['trace'] and not zero['metrics']['online_success'] and audit(case, zero)
                row.update(group=group, certificate=witness, run_type='logical_clock', independent_audit=True)
                write_record(results, row)
    print(tag, sorted(totals.items()), flush=True)


def natural(out, split, rng, policy):
    methods = list(policy) if split == 'validation' else [*BASELINES, *policy]
    with gzip.open(out/(split+'_rows.jsonl.gz'), 'wt', encoding='utf-8') as results:
        for index, raw in enumerate(load_records(out/'inputs'/(split+'.jsonl.gz')), 1):
            for event in raw['events']:
                case = case_from_dict(dict(base=raw['base'], reference=raw['reference'], **event))
                rng.shuffle(methods)
                witness = certificate(case, local_ids(case)) if split == 'test' and case.event.urgent else None
                for method in methods:
                    row = dispatch(case, method, policy)
                    row['independent_audit'] = audit(case, row)
                    row['certificate_w5'] = witness
                    write_record(results, row)
            if index % 20 == 0:
                print(split, index, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--mechanism-only', action='store_true')
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(781777)
    grid_policy = {grid_name(w, b): (w, b) for w, b in GRID}
    seal(out)
    warm = next(natural_bases('validation'))[1]
    # Discard all warm-up calls and use only the sealed runs.
    for case in warm:
        for method in (*BASELINES, grid_name(5, 2)):
            dispatch(case, method, grid_policy)
    for tag in CONTROLLED:
        controlled(out, tag, rng, grid_policy)
    if args.mechanism_only:
        return
    natural(out, 'validation', rng, grid_policy)
    policy = select(load_records(out/'validation_rows.jsonl.gz'))
    save(out/'policy.json', policy)
    print('Validation configuration frozen', policy, flush=True)
    natural(out, 'test', rng, {**grid_policy, **policy})


if __name__ == '__main__':
    main()

