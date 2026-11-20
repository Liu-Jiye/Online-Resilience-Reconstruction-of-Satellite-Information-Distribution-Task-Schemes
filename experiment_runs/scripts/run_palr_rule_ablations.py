"""Paired repeat of the three P5 A5 rule ablations with optimized operators."""
import argparse
import gzip
import hashlib
import json
import platform
import random
from collections import Counter
from pathlib import Path

from p5_runner import OUT, P3, P4, ROOT, audit, base_data, cases, load, save, sha
from isl.models import canonical_json
from isl.palr_adaptive_operators import ARMS, pilot_kernel, run
from isl.palr_adaptive_rules import MODES, run_controlled
from run_palr_adaptive_rerun import CONFIG, MANIFEST, METRICS, summarize_comparison

METHODS = ('fixed', 'operator_only', *MODES)
SUBSET = OUT / 'subsets.json'
RULE = P3 / 'frozen_parameters.json'
SOURCES = (CONFIG, MANIFEST, SUBSET, RULE, Path(__file__),
           ROOT / 'scripts/run_palr_adaptive_rerun.py',
           *sorted((ROOT / 'src/isl').rglob('*.py')))


def measure(case, method, config, rule):
    if method in MODES:
        result, arm = run_controlled(case, method, rule, config['policy'], config['budget_ms'])
    else:
        name = 'adaptive' if method == 'operator_only' else method
        result, arm = run(case, name, config['policy'], config['budget_ms'])
    audit(case, result)
    return dict(
        arm=arm, w=result['w'], B=result['B'], status=result['status'],
        stop_reason=result['stop_reason'], metrics={key: result['metrics'][key] for key in METRICS},
        plan_sha256=hashlib.sha256(canonical_json(result['plan']).encode()).hexdigest(),
    )


def collect(dest, smoke):
    config = load(CONFIG)
    rule = load(RULE)['parameters']['default']['rule']
    manifest = {entry['id']: entry for entry in load(MANIFEST)['instances']}
    base_ids = load(SUBSET)['ablation_300']
    assert len(set(base_ids)) == len(base_ids) == 300
    if smoke:
        base_ids = base_ids[:4]
    dest.mkdir(parents=True, exist_ok=True)
    evidence = dest / 'events.jsonl.gz'
    if evidence.exists():
        raise FileExistsError('Choose a fresh output directory')
    save(dest / 'freeze.json', dict(sources={path.relative_to(ROOT).as_posix(): sha(path) for path in SOURCES},
                                  base_ids=base_ids, smoke=smoke, platform=platform.platform(),
                                  python=platform.python_version(), methods=METHODS))
    for arm in ARMS:
        pilot_kernel(arm)
    warm = cases(base_data(config['previous_small_samples'][0]))
    for index in range(20):
        for method in METHODS:
            measure(warm[index % len(warm)][1], method, config, rule)
    rng = random.Random(config['seed'])
    temp = evidence.with_suffix('.part')
    with gzip.open(temp, 'wt', encoding='utf-8') as handle:
        for index, ident in enumerate(base_ids, 1):
            entry = manifest[ident]
            assert sha(P4 / 'data' / f'{ident}.zip') == entry['archive_sha256']
            for scenario, (_, case) in enumerate(cases(base_data(ident))):
                order = rng.sample(METHODS, len(METHODS))
                row = dict(base=ident, layer=entry['layer'], group=entry['geometry'].get('group', 'D1'),
                           scenario=scenario, event=case.event.kind, order=order,
                           methods={method: measure(case, method, config, rule) for method in order})
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
            if index % 25 == 0 or index == len(base_ids):
                print(f'{index}/{len(base_ids)} bases', flush=True)
    temp.replace(evidence)


def summarize(dest):
    freeze = load(dest / 'freeze.json')
    for path, expected in freeze['sources'].items():
        assert sha(ROOT / path) == expected, path
    config = load(CONFIG)
    evidence = dest / 'events.jsonl.gz'
    with gzip.open(evidence, 'rt', encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle]
    assert len(rows) == len({(row['base'], row['scenario']) for row in rows}) == 12 * len(freeze['base_ids'])
    assert all(set(row['methods']) == set(METHODS) for row in rows)
    applicable = [row for row in rows if row['methods']['fixed']['metrics']['applicable']]
    previous = set(config['previous_small_samples'])
    scopes = dict(all=applicable, holdout=[row for row in applicable if row['base'] not in previous])
    scopes.update({name: [row for row in applicable if row['event'] == name]
                   for name in sorted({row['event'] for row in applicable})})
    results = {}
    for scope, group in scopes.items():
        if not group:
            continue
        results[scope] = {}
        for method in MODES:
            comparisons = {}
            for comparator in ('fixed', 'operator_only'):
                result = summarize_comparison(group, comparator, config, candidate=method)
                result['latency_passed'] = (
                    result['faster_share_ci95'][0] > config['minimum_event_share']
                    and result['mean_reduction_ci95'][0] >= config['minimum_mean_reduction'])
                comparisons[comparator] = result
            counts = Counter((row['methods'][method]['w'], row['methods'][method]['B']) for row in group)
            results[scope][method] = dict(comparisons=comparisons,
                                          actions={f'w{width}/B{budget}': count
                                                   for (width, budget), count in sorted(counts.items())})
    save(dest / 'acceptance.json', dict(events=len(rows), calls=len(rows)*len(METHODS),
                                      evidence_sha256=sha(evidence), results=results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('run', 'summarize'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    if args.phase == 'run':
        collect(args.output, args.smoke)
    summarize(args.output)
