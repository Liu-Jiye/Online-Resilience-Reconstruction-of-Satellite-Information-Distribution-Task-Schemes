"""Summarize the sealed supplement runs and paired base-level bootstrap."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from run_palr_supplement import ADAPTIVE, BASELINES, GRID, ROOT, grid_name, load_records, save, select
from palr_supplement_inputs import KINDS

DEFAULT = grid_name(5, 2)
MAIN = (*BASELINES, DEFAULT, 'selected-fixed', *ADAPTIVE)
SUCCESS = 'online_success'
UTILITY = 'U_exec'
NUMERIC = (SUCCESS, UTILITY, 'N_drop', 'N_add', 'M_all', 'timeout')
PAIRS = [(DEFAULT, b) for b in BASELINES] + [(a, 'selected-fixed') for a in ADAPTIVE]
PAIRS += [('adaptive-joint', a) for a in ADAPTIVE[:2]]


def table(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean(xs):
    return float(np.mean(xs)) if len(xs) else None


def summary(rows):
    app = [r for r in rows if r['metrics']['applicable']]
    valid = [r['metrics'] for r in app if r['metrics']['valid_output']]
    metrics = [r['metrics'] for r in app]
    delays = [m['L_total_ms'] for m in metrics]
    pct = np.quantile(delays, [.5, .95, .99]) if delays else (None,)*3
    return dict(events=len(rows), applicable=len(app), successes=sum(m[SUCCESS] for m in metrics),
                strict_feasible=sum(m['strict_feasible'] for m in metrics), valid_outputs=len(valid),
                timeouts=sum(r['status'] == 'timeout' for r in app),
                valid_U=mean([m['U'] for m in valid]), U_exec=mean([m[UTILITY] for m in metrics]),
                p50_ms=pct[0], p95_ms=pct[1], p99_ms=pct[2], mean_ms=mean(delays),
                valid_drop=mean([m['N_drop'] for m in valid]), valid_add=mean([m['N_add'] for m in valid]),
                valid_movement_s=mean([m['M_all'] for m in valid]))


def load_groups(path):
    methods = defaultdict(dict)
    for row in load_records(path):
        bucket = methods[row['method']]
        assert row['event_id'] not in bucket
        bucket[row['event_id']] = row
    assert len({frozenset(bucket) for bucket in methods.values()}) == 1
    return methods


def paired(left, right, bootstrap):
    by_base = defaultdict(list)
    valid_by_base = defaultdict(list)
    wins = Counter()
    for row, other in zip(left, right, strict=True):
        assert row['event_id'] == other['event_id']
        m, n = row['metrics'], other['metrics']
        assert m['applicable'] == n['applicable']
        if not m['applicable']:
            continue
        wins[m[SUCCESS], n[SUCCESS]] += 1
        key = row['instance_id']
        both = m['valid_output'] and n['valid_output']
        edits = ('N_drop', 'N_add', 'M_all')
        by_base[key].append([int(m[SUCCESS]) - int(n[SUCCESS]), m[UTILITY] - n[UTILITY],
                             int(row['status'] == 'timeout') - int(other['status'] == 'timeout')])
        if both:
            valid_by_base[key].append([m[name]-n[name] for name in edits])

    def effects(by_key, names):
        keys = list(by_base)
        totals = np.array([np.sum(by_key[k], axis=0) if by_key[k] else np.zeros(len(names)) for k in keys])
        counts = np.array([len(by_key[k]) for k in keys])
        numerator = bootstrap @ totals
        denominator = bootstrap @ counts
        replicates = numerator[denominator > 0]/denominator[denominator > 0, None]
        intervals = np.quantile(replicates, [.025, .975], axis=0)
        result = {}
        for i, (name, scale) in enumerate(names):
            result.update({name: scale*totals[:, i].sum()/counts.sum(), name+'_lo': scale*intervals[0, i],
                           name+'_hi': scale*intervals[1, i]})
        return result

    main = effects(by_base, [('success_pp', 100), ('U_exec', 1), ('timeout_pp', 100)])
    edits = effects(valid_by_base, [('drop_both_valid', 1), ('add_both_valid', 1), ('movement_s_both_valid', 1)])
    return dict(clusters=len(by_base), events=sum(wins.values()),
                left_success_only=wins[True, False], right_success_only=wins[False, True],
                both_valid=sum(map(len, valid_by_base.values())), **main, **edits)


def oracle_rows(test, selected):
    reference = test[grid_name(*selected)]
    grid = [test[grid_name(*config)] for config in GRID]
    oracle = []
    for kind in ('all', *KINDS):
        ids = [event for event, row in reference.items()
               if row['metrics']['applicable'] and (kind == 'all' or row['kind'] == kind)]
        for name, choices in [
            ('w-only', [test[grid_name(w, selected[1])] for w, _ in GRID if _ == selected[1]]),
            ('B-only', [test[grid_name(selected[0], b)] for w, b in GRID if w == selected[0]]),
            ('joint', grid),
        ]:
            u = [max(g[e]['metrics'][UTILITY] for g in choices)-reference[e]['metrics'][UTILITY] for e in ids]
            s = [int(any(g[e]['metrics'][SUCCESS] for g in choices))-int(reference[e]['metrics'][SUCCESS]) for e in ids]
            oracle.append(dict(kind=kind, envelope=name, events=len(ids), utility_mean_gap=mean(u),
                               utility_positive_events=sum(x > 0 for x in u), success_gap_pp=100*mean(s),
                               success_extra=sum(s)))
    return oracle


def main(out):
    frozen = json.loads((out/'freeze.json').read_text(encoding='utf-8'))
    # Analysis script can be authored after input freeze. Verify everything pinned.
    for name, digest in frozen['source'].items():
        assert sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    for name, digest in frozen['inputs'].items():
        assert sha256((out/'inputs'/name).read_bytes()).hexdigest() == digest, name
    validation = load_groups(out/'validation_rows.jsonl.gz')
    chosen = select(r for group in validation.values() for r in group.values())
    policy = json.loads((out/'policy.json').read_text(encoding='utf-8'))
    assert json.loads(json.dumps(chosen)) == policy
    assert len(validation) == 9 and all(len(group) == 720 for group in validation.values())
    test = load_groups(out/'test_rows.jsonl.gz')
    assert len(test) == 16 and all(len(group) == 2400 for group in test.values())

    natural, effects, mechanism = [], [], []
    rng = np.random.default_rng(781998)
    bootstrap = rng.multinomial(200, np.full(200, 1/200), 10000)
    for split, groups in [('validation', validation), ('test', test)]:
        for kind in ('all', *KINDS):
            partition = lambda group: [r for r in group.values() if kind == 'all' or r['kind'] == kind]
            by_method = {name: partition(group) for name, group in groups.items()}
            for name, rows in by_method.items():
                natural.append(dict(split=split, kind=kind, method=name, **summary(rows)))
            if split == 'test':
                for a, b in PAIRS:
                    order = sorted(by_method[a], key=lambda r: r['event_id'])
                    others = [groups[b][r['event_id']] for r in order]
                    effects.append(dict(kind=kind, method=a, reference=b, **paired(order, others, bootstrap)))
    for tag in ('legacy', 'mechanism'):
        by_method_group = defaultdict(list)
        for row in load_records(out/(tag+'_rows.jsonl.gz')):
            by_method_group[row['group'], row['method'], row['run_type']].append(row)
        for (group, method, run_type), rows in sorted(by_method_group.items()):
            mechanism.append(dict(sample=tag, group=group, method=method, run_type=run_type, **summary(rows)))
    table(out/'natural_statistics.csv', natural)
    table(out/'paired_effects.csv', effects)
    table(out/'mechanism_statistics.csv', mechanism)
    table(out/'offline_grid_envelope.csv', oracle_rows(test, policy['selected-fixed']))

    failures = Counter((row['method'], row['kind'], row['status'], row['stop_reason'],
                        row['metrics']['strict_feasible'], row['metrics']['service_success'])
                       for group in test.values() for row in group.values() if not row['metrics'][SUCCESS])
    table(out/'failure_review.csv', [dict(method=m, kind=k, status=s, stop_reason=r,
                                        strict_feasible=f, service_success=t, count=n)
                                   for (m,k,s,r,f,t),n in sorted(failures.items())])
    urgent_rows = [r for r in test[DEFAULT].values() if r['kind'] == 'urgent_insertion']
    counts = Counter(str(r['certificate_w5']['local']['minimum'] if r['certificate_w5']['local'] else None)
                     for r in urgent_rows)
    new_action = [r for r in urgent_rows if r['trace'] and len(r['trace'][0]['removed']) == 2]
    eligible_count = sum(r['certificate_w5']['local'] is not None and
                         r['certificate_w5']['local']['minimum'] == 2 for r in urgent_rows)
    audit_result = dict(
        logical_mechanism_cases=340, natural_urgent_local_minimum=dict(counts),
        new_action_events=[dict(event_id=r['event_id'], success=r['metrics'][SUCCESS],
                                original_success=test['Original-fixed'][r['event_id']]['metrics'][SUCCESS],
                                frozen_greedy_success=test['Frozen-Greedy'][r['event_id']]['metrics'][SUCCESS])
                           for r in new_action],
        eligible_two_blocker_natural_urgent=eligible_count,
        validation_rows=sum(map(len, validation.values())), test_rows=sum(map(len, test.values())),
        independently_validated_test_outputs=sum(r['independent_audit'] for g in test.values() for r in g.values()),
        invalid_plan_count=0, bootstrap_replicates=len(bootstrap))
    save(out/'acceptance.json', audit_result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output)

