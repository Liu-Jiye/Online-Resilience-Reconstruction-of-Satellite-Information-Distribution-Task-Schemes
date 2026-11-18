"""Read frozen P4 summaries; no experiment rerun or changes to the repository."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = next(p for p in Path(__file__).resolve().parents if (p / 'experiment_runs').is_dir())
RUN = REPO / 'experiment_runs/reports/p4/P4-20261117'
OUT = Path(__file__).resolve().parent / 'recomputed'


def read_csv(name):
    with (RUN / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    rows = read_csv('seed_averaged_events.csv')
    manifest = json.loads((RUN / 'data/manifest.json').read_text(encoding='utf-8'))
    methods = sorted({r['method'] for r in rows})
    grouped = defaultdict(list)
    events = set()
    zero_baseline = defaultdict(int)
    for r in rows:
        k = (r['method'], r['layer'], r['base_id'])
        grouped[k].append(float(r['online_success']))
        event = (r['base_id'], r['scenario'], r['method'])
        if event in events:
            raise ValueError(('Duplicate seed-averaged event', event))
        events.add(event)
        if float(r['U_min']) == 0:
            zero_baseline[r['method']] += 1
    if len(events) != 96000 or len(grouped) != 8000:
        raise ValueError(('Unexpected sample counts', len(events), len(grouped)))
    if any(len(v) != 12 for v in grouped.values()):
        raise ValueError('Incomplete event cluster')
    layers = ['D1', 'D2-S', 'D2-O']
    arrays = {m: {} for m in methods}
    orbit = {}
    for layer in layers:
        bases = sorted([r for r in manifest['instances'] if r['layer'] == layer], key=lambda r: r['id'])
        for m in methods:
            arrays[m][layer] = np.array([np.mean(grouped[m, layer, b['id']]) for b in bases])
        if layer != 'D1':
            names = sorted({b['geometry']['group'] for b in bases})
            orbit[layer] = {g: np.array([i for i, b in enumerate(bases) if b['geometry']['group'] == g]) for g in names}
    # Use the exact frozen resampling sequence, including the initial base-only
    # draw, to check a published interval and add two explicitly secondary pairs.
    rng = np.random.Generator(np.random.PCG64(20261020))
    pairs = [('Validation-Best-Fixed', 'Rule-PALR'),
             ('Validation-Best-Fixed', 'Minimal-Repair'),
             ('Rule-PALR', 'Minimal-Repair')]
    bootstrap = {a + ' minus ' + b: [] for a, b in pairs}
    for _ in range(10000):
        sample = {l: rng.integers(0, len(arrays[methods[0]][l]), len(arrays[methods[0]][l])) for l in layers}
        for layer in layers[1:]:
            names = list(orbit[layer])
            selected = rng.integers(0, len(names), len(names))
            parts = []
            for k in selected:
                ids = orbit[layer][names[k]]
                parts.append(rng.choice(ids, len(ids), replace=True))
            sample[layer] = np.concatenate(parts)
        for a, b in pairs:
            value = sum(float(np.mean((arrays[a][l] - arrays[b][l])[sample[l]])) * len(sample[l]) / 1000 for l in layers)
            bootstrap[a + ' minus ' + b].append(value)
    comparisons = {}
    for a, b in pairs:
        key = a + ' minus ' + b
        point = sum(float(np.mean(arrays[a][l] - arrays[b][l])) * len(arrays[a][l]) / 1000 for l in layers)
        ci = np.percentile(bootstrap[key], [2.5, 97.5])
        comparisons[key] = dict(difference_percentage_points=100 * point, ci95_percentage_points=(100 * ci).tolist())
    official = json.loads((RUN / 'cluster_bootstrap.json').read_text(encoding='utf-8'))
    if not np.allclose(np.array(comparisons['Validation-Best-Fixed minus Rule-PALR']['ci95_percentage_points']) / 100,
                       official['results']['Validation-Best-Fixed']['difference_vs_rule_ci95'], atol=1e-12):
        raise ValueError('Published bootstrap interval mismatch')
    time_flips = defaultdict(int)
    with (RUN / 'per_event_results.csv').open(encoding='utf-8-sig', newline='') as f:
        raw_counts = defaultdict(int)
        for r in csv.DictReader(f):
            raw_counts[r['method']] += 1
            if r['service_success'] == 'True' and float(r['kernel_ms']) <= 50 < float(r['total_ms']):
                time_flips[r['method']] += 1
    evidence = ['seed_averaged_events.csv', 'per_event_results.csv', 'cluster_bootstrap.json',
                'main_table.csv', 'conditional_quality.csv', 'timing_table.csv', 'timing_components.csv', 'data/manifest.json']
    result = dict(
        assessment_date='2026-11-18', frozen_commit='a7eaff69672891c1ae3ea01df8ba80c1aa431134',
        activity='Read-only secondary analysis of frozen P4 evidence; no methods rerun, no parameter or sample changes.',
        checks=dict(seed_averaged_rows=len(rows), base_method_clusters=len(grouped), events_per_base_method=12,
                    published_best_fixed_vs_rule_interval_reproduced=True, main_raw_calls=sum(raw_counts.values())),
        paired_bootstrap=dict(seed=20261020, repetitions=10000, scheme='Frozen layer/group/base paired resampling; 12 events kept together',
                              comparisons=comparisons,
                              scope='Comparisons against Minimal are secondary descriptive audit results, not a new preregistered primary test; only two orbit groups per orbital layer.'),
        minimal_U_raw_zero_events_by_method=dict(zero_baseline),
        kernel_ontime_service_outputs_that_miss_full_call_deadline_by_method=dict(time_flips),
        main_raw_calls_by_method=dict(raw_counts),
        source_sha256={name: hashlib.sha256((RUN / name).read_bytes()).hexdigest() for name in evidence},
    )
    OUT.mkdir(exist_ok=True)
    (OUT / 'P0-P4评估复算证据.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
