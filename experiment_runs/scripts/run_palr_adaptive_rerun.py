"""Reproduce the paired PALR operator comparison on the sealed P4 and P5 inputs."""
import argparse
import csv
import gzip
import hashlib
import inspect
import json
import platform
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

from p5_runner import OUT, P4, ROOT, audit, base_data, cases, load, save, sha
from isl.models import canonical_json
from isl.palr_adaptive_operators import ARMS, pilot_kernel, run

CONFIG = ROOT / 'configs/palr_adaptive_rerun.json'
MANIFEST = P4 / 'data/manifest.json'
P5_SUBSET = OUT / 'subsets.json'
METHODS = ('fixed', 'adaptive', 'cached_fixed', 'static')
METRICS = ('applicable', 'strict_feasible', 'online_success', 'valid_output',
           'U', 'U_exec', 'L_total_ms', 'N_add', 'N_drop', 'M_all')


def run_case(case, method, config):
    name = config['policy']['default'] if method == 'static' else method
    result, arm = run(case, name, config['policy'], config['budget_ms'])
    audit(case, result)
    return dict(
        arm=arm, status=result['status'], stop_reason=result['stop_reason'],
        metrics={key: result['metrics'][key] for key in METRICS},
        plan_sha256=hashlib.sha256(canonical_json(result['plan']).encode()).hexdigest(),
    )


def collect(dest, limit=None):
    config = load(CONFIG)
    manifest = load(MANIFEST)['instances']
    if limit:
        manifest = manifest[:limit]
    dest.mkdir(parents=True, exist_ok=True)
    freeze = dict(
        config_sha256=sha(CONFIG), script_sha256=sha(__file__),
        collector_sha256=collector_hash(),
        source_sha256={path.relative_to(ROOT).as_posix(): sha(path)
                       for path in sorted((ROOT / 'src/isl').rglob('*.py'))},
        p4_manifest_sha256=sha(MANIFEST), p5_subset_sha256=sha(P5_SUBSET),
        methods=METHODS, bases=len(manifest), smoke=limit is not None,
        python=platform.python_version(), numpy=np.__version__,
        machine=platform.machine(), platform=platform.platform(),
    )
    if (dest / 'events.jsonl.gz').exists():
        raise FileExistsError('Choose an empty destination for a new timing run')
    save(dest / 'freeze.json', freeze)
    for arm in ARMS:
        pilot_kernel(arm)
    warm_id = config['previous_small_samples'][0]
    warm = cases(base_data(warm_id))
    for iteration in range(20):
        for method in METHODS:
            run_case(warm[iteration % len(warm)][1], method, config)
    rng = random.Random(config['seed'])
    temp = dest / 'events.jsonl.gz.part'
    with gzip.open(temp, 'wt', encoding='utf-8') as handle:
        for index, entry in enumerate(manifest, 1):
            ident = entry['id']
            assert sha(P4 / 'data' / f'{ident}.zip') == entry['archive_sha256'], ident
            sample = cases(base_data(ident))
            assert len(sample) == 12
            for scenario, (_, case) in enumerate(sample):
                order = rng.sample(METHODS, len(METHODS))
                measured = {method: run_case(case, method, config) for method in order}
                row = dict(base=ident, layer=entry['layer'], group=entry['geometry'].get('group', 'D1'),
                           scenario=scenario, event=case.event.kind, order=order, methods=measured)
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
            if index % 50 == 0 or index == len(manifest):
                handle.flush()
                print(f'{index}/{len(manifest)} base instances', flush=True)
    temp.replace(dest / 'events.jsonl.gz')
    summarize(dest)


def collector_hash():
    source = '\n'.join(inspect.getsource(function) for function in (run_case, collect))
    return hashlib.sha256(source.encode()).hexdigest()


def summarize_comparison(rows, comparator, config, candidate='adaptive'):
    rng = np.random.default_rng(config['seed'])
    by_layer = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: np.zeros(4))))
    outcome = {}
    for method in (comparator, candidate):
        records = [row['methods'][method] for row in rows]
        values = [record['metrics'] for record in records]
        valid = [value for value in values if value['valid_output']]
        outcome[method] = dict(
            online_success=sum(value['online_success'] for value in values),
            strict_feasible=sum(value['strict_feasible'] for value in values),
            valid_output=len(valid), timeout=sum(record['status'] == 'timeout' for record in records),
            u_exec=float(np.mean([value['U_exec'] for value in values])),
            conditional_u=float(np.mean([value['U'] for value in valid])) if valid else None,
            mean_ms=float(np.mean([value['L_total_ms'] for value in values])),
            latency_quantiles_ms=np.quantile([value['L_total_ms'] for value in values], [.5, .95, .99]).tolist(),
        )
    differences = 0
    for row in rows:
        fixed = row['methods'][comparator]
        adaptive = row['methods'][candidate]
        differences += fixed['plan_sha256'] != adaptive['plan_sha256']
        fixed_ms = fixed['metrics']['L_total_ms']
        adaptive_ms = adaptive['metrics']['L_total_ms']
        win = adaptive_ms <= (1 - config['minimum_event_reduction']) * fixed_ms
        by_layer[row['layer']][row['group']][row['base']] += (win, 1, fixed_ms, adaptive_ms)

    totals = np.zeros(4)
    draws = np.zeros((10000, 4))
    for groups in by_layer.values():
        values_by_group = [np.stack(list(bases.values())) for bases in groups.values()]
        original_count = sum(len(values) for values in values_by_group)
        totals += sum(values.sum(axis=0) for values in values_by_group)
        layer_draws = np.zeros_like(draws)
        sampled_bases = np.zeros(len(draws))
        for selected in rng.integers(0, len(groups), (len(groups), len(draws))):
            for group_number, values in enumerate(values_by_group):
                mask = selected == group_number
                sample = rng.integers(0, len(values), (np.count_nonzero(mask), len(values)))
                layer_draws[mask] += values[sample].sum(axis=1)
                sampled_bases[mask] += len(values)
        draws += layer_draws * (original_count / sampled_bases)[:, None]
    result = dict(
        events=len(rows), faster_10pct=int(totals[0]), faster_share=float(totals[0] / totals[1]),
        faster_share_ci95=np.quantile(draws[:, 0] / draws[:, 1], [.025, .975]).tolist(),
        mean_reduction=float(1 - totals[3] / totals[2]),
        mean_reduction_ci95=np.quantile(1 - draws[:, 3] / draws[:, 2], [.025, .975]).tolist(),
        different_plans=differences, methods=outcome,
    )
    result['passed'] = bool(
        result['faster_share_ci95'][0] > config['minimum_event_share']
        and result['mean_reduction_ci95'][0] >= config['minimum_mean_reduction']
        and differences == 0 and all(outcome[comparator][key] == outcome[candidate][key]
                                    for key in ('online_success', 'valid_output', 'timeout', 'u_exec'))
    )
    return result


def summarize(dest):
    config = load(CONFIG)
    freeze = load(dest / 'freeze.json')
    assert sha(CONFIG) == freeze['config_sha256']
    assert sha(MANIFEST) == freeze['p4_manifest_sha256']
    assert sha(P5_SUBSET) == freeze['p5_subset_sha256']
    if 'collector_sha256' in freeze:
        assert collector_hash() == freeze['collector_sha256']
    with gzip.open(dest / 'events.jsonl.gz', 'rt', encoding='utf-8') as handle:
        all_rows = [json.loads(line) for line in handle]
    assert len({(row['base'], row['scenario']) for row in all_rows}) == len(all_rows) == freeze['bases'] * 12
    for row in all_rows:
        assert set(row['methods']) == set(METHODS)
        assert len({value['metrics']['applicable'] for value in row['methods'].values()}) == 1
    rows = [row for row in all_rows if row['methods']['fixed']['metrics']['applicable']]
    previous = set(config['previous_small_samples'])
    assert len(previous) == 216
    p5 = set(load(P5_SUBSET)['ablation_300'])
    groups = dict(p4_all=rows)
    if not freeze['smoke']:
        groups.update(
            p4_holdout=[row for row in rows if row['base'] not in previous],
            p5_all=[row for row in rows if row['base'] in p5],
            p5_holdout=[row for row in rows if row['base'] in p5 and row['base'] not in previous],
        )
    groups.update({value: [row for row in rows if row[field] == value]
                   for field in ('event', 'layer') for value in sorted({row[field] for row in rows})})
    results = {name: summarize_comparison(group, 'fixed', config) for name, group in groups.items()}
    results['vs_cached_fixed'] = summarize_comparison(rows, 'cached_fixed', config)
    results['vs_static'] = summarize_comparison(rows, 'static', config)
    passed = not freeze['smoke'] and all(results[key]['passed'] for key in
                                         ('p4_all', 'p4_holdout', 'p5_all', 'p5_holdout'))
    with (dest / 'failure_review.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(('base', 'scenario', 'event', 'method', 'status', 'stop_reason', 'latency_ms'))
        for row in all_rows:
            for method, result in row['methods'].items():
                if result['metrics']['applicable'] and not result['metrics']['online_success']:
                    writer.writerow((row['base'], row['scenario'], row['event'], method, result['status'],
                                     result['stop_reason'], result['metrics']['L_total_ms']))
    summary = dict(passed=passed, run_events=len(all_rows), applicable_events=len(rows),
                   evidence_sha256=sha(dest / 'events.jsonl.gz'), analysis_script_sha256=sha(__file__),
                   results=results)
    save(dest / 'acceptance.json', summary)
    print(json.dumps({name: [result['faster_10pct'], result['events'],
                            result['mean_reduction'], result['different_plans']]
                      for name, result in results.items()}), flush=True)
    print(f'passed={passed}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('run', 'summarize'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--smoke', type=int)
    args = parser.parse_args()
    if args.phase == 'run':
        collect(args.output, args.smoke)
    else:
        summarize(args.output)
