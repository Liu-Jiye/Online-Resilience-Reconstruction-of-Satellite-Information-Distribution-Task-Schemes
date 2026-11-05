"""P1 only: 150 pilots + 100 geometric scan audits, never repairs/test tasks."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / 'src'))
from isl.models import canonical_json
from isl.p1_sources import save_json
from isl.p1_orbits import build_contacts, compare_windows, epoch
from isl.p1_generation import component_seeds, synthetic_contacts, create_instance, distribution
from isl.reference import create_reference
from isl.validation import validate
from run_p0 import environment


def main():
    config = json.loads((ROOT / 'configs/p1.json').read_text(encoding='utf-8'))
    run_id = datetime.now(timezone.utc).strftime('P1-%Y%m%dT%H%M%SZ')
    output = ROOT / 'reports/p1' / run_id
    output.mkdir(parents=True, exist_ok=False)
    processed = ROOT / 'data/processed/p1' / run_id
    processed.mkdir(parents=True, exist_ok=False)
    save_json(output / 'config.json', config)
    actual_environment = environment()
    actual_environment['scope'] = 'P1 offline data/contact pilot only; no repair performance evaluation'
    save_json(output / 'environment.json', actual_environment)
    source_paths = list((ROOT / 'src').rglob('*.py')) + list((ROOT / 'tests').glob('*.py')) + list((ROOT / 'scripts').glob('*.py'))
    source_paths += [ROOT / 'configs/p1.json', ROOT / 'environment/requirements-p1.lock.txt',
                     ROOT / 'protocol/P1_GENERATION_CONTRACT.md']
    source_hashes = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_paths)}
    entries, audits, failures = [], [], []
    started = perf_counter()
    for layer in config['layers']:
        name = {'D2-S': 'starlink', 'D2-O': 'oneweb'}.get(layer)
        if name:
            orbital = json.loads((ROOT / f'data/processed/p1/{name}_eligible.json').read_text(encoding='utf-8'))
            origin = epoch(orbital['t_ref_utc'])
            rows = {int(row['NORAD_CAT_ID']): row for row in orbital['records']}
            groups = json.loads((ROOT / f'reports/p1/{name}_groups.json').read_text(encoding='utf-8'))['groups']
        for split in ('train', 'validation'):
            eligible_groups = [g for g in groups if g['split'] == split] if name else []
            for index in range(config['pilot_per_layer'][split]):
                seed = config['pilot_seed_starts'][layer][split] + index
                instance_id = f'{layer}-{split}-pilot-{index:03d}'
                seeds = component_seeds(seed)
                item_start = perf_counter()
                group_id, offset = None, None
                try:
                    if name:
                        group = eligible_groups[index % len(eligible_groups)]
                        group_id = group['group_id']
                        selected = [rows[cat] for cat in group['norad_ids']]
                        satellites = tuple(sorted(str(cat) for cat in group['norad_ids']))
                        rng = np.random.Generator(np.random.PCG64(seeds['segment']))
                        offset = int(rng.integers(-43200, 37801))
                        begin = perf_counter()
                        contacts, physical5 = build_contacts(selected, origin, offset, 5)
                        coarse_seconds = perf_counter() - begin
                        begin = perf_counter()
                        contacts1, physical1 = build_contacts(selected, origin, offset, 1)
                        fine_seconds = perf_counter() - begin
                        audit = compare_windows(physical5, physical1)
                        audit.update({'instance_id': instance_id, 'layer': layer, 'split': split,
                                      'group_id': group_id, 'offset_s': offset,
                                      'coarse_wall_s': coarse_seconds, 'fine_wall_s': fine_seconds,
                                      'coarse_directed_contacts': len(contacts), 'fine_directed_contacts': len(contacts1)})
                        # 1 s used only to audit geometry, never to tune plans.
                        audits.append(audit)
                        save_json(processed / (instance_id + '.audit.json'),
                                  {'physical_5s': physical5, 'physical_1s': physical1, 'comparison': audit})
                    else:
                        satellites = tuple(f'S{i:02d}' for i in range(32))
                        contacts, _ = synthetic_contacts(satellites, np.random.Generator(np.random.PCG64(seeds['contacts'])))
                    instance, metadata = create_instance(instance_id, satellites, contacts, seed)
                    reference, reference_info = create_reference(instance)
                    check = validate(instance, reference)
                    if not check.feasible or not reference:
                        raise ValueError('Invalid or empty reference: ' + repr(check.errors))
                    stats = distribution(instance, reference, metadata)
                    stats.update({'layer': layer, 'split': split, 'seed': seed, 'group_id': group_id,
                                  'offset_s': offset, 'generation_wall_s': perf_counter() - item_start,
                                  'reference_construction_ms': reference_info['construction_ns'] / 1e6})
                    metadata.update({'layer': layer, 'split': split, 'group_id': group_id,
                        't_ref_utc': origin.isoformat() if name else None, 'start_offset_s': offset,
                        'source_snapshot_sha256': json.loads((ROOT / config['source_directory'] / f'{name}.fetch.json').read_text())['sha256'] if name else None,
                        'field_provenance': {'orbital_elements': 'public_provider_GP_not_link_measurements' if name else 'not_used',
                            'contacts': 'derived_SGP4_TEME_spherical_geometry' if name else 'synthetic',
                            'tasks': 'synthetic', 'utility': 'synthetic', 'calendar': 'synthetic',
                            'terminal_and_rate_assumptions': 'synthetic'},
                        'test_performance_accessed': False})
                    payload = {'instance': asdict(instance), 'reference': [asdict(p) for p in reference],
                               'reference_info': reference_info, 'metadata': metadata}
                    path = processed / (instance_id + '.json')
                    save_json(path, payload)
                    stats['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                    entries.append(stats)
                except (ValueError, KeyError) as error:
                    failures.append({'instance_id': instance_id, 'layer': layer, 'split': split, 'seed': seed,
                                     'group_id': group_id, 'reason': str(error)})
                if (index + 1) % 5 == 0:
                    print(f'{layer} {split} {index+1}/25; attempts={len(entries)+len(failures)}; wall_s={perf_counter()-started:.1f}', flush=True)
    save_json(output / 'distributions.json', entries)
    save_json(output / 'failures.json', failures)
    save_json(output / 'window_audits.json', audits)
    summary = {'stage': 'P1', 'attempts': len(entries) + len(failures), 'valid_instances': len(entries),
               'failures': len(failures), 'test_instances_generated': 0, 'repair_method_calls': 0,
               'audit_instances': len(audits), 'wall_s': perf_counter() - started, 'layers': {}}
    for layer in config['layers']:
        subset = [row for row in entries if row['layer'] == layer]
        sparse = sum(row['scheduled_count'] < 10 for row in subset)
        info = {'count': len(subset), 'split_counts': {s: sum(row['split'] == s for row in subset) for s in ('train', 'validation')},
                'reference_below_10_count': sparse, 'reference_below_10_fraction': sparse / len(subset) if subset else None,
                'load_revision_triggered': sparse / len(subset) > .8 if subset else True}
        for metric in ('scheduled_count', 'window_only_feasible_fraction', 'single_task_calendar_feasible_fraction',
                       'scheduled_terminal_occupancy', 'background_actual_occupancy', 'combined_terminal_occupancy',
                       'max_sender_share', 'max_receiver_share', 'reference_construction_ms'):
            values = [row[metric] for row in subset]
            info[metric] = {'mean': float(np.mean(values)), 'min': min(values), 'p50': float(np.median(values)),
                            'p95': float(np.quantile(values, .95)), 'max': max(values)} if values else None
        summary['layers'][layer] = info
    save_json(output / 'summary.json', summary)
    # Derived demand/calendar/contact/reference only, never GP/OMM records.
    archive = output / 'pilot_derived_instances.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(processed.glob('*.json')):
            bundle.write(path, path.name)
    manifest = {'run_id': run_id, 'stage': 'P1', 'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_sha256': source_hashes, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'raw_snapshots_not_redistributed': True, 'derived_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'processed_directory': processed.relative_to(ROOT).as_posix(),
        'artifact_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()},
        'test_performance_accessed': False, 'next_stages_executed': []}
    manifest['snapshot_sha256'] = {name: json.loads((ROOT / config['source_directory'] / f'{name}.fetch.json').read_text())['sha256']
                                  for name in ('starlink', 'oneweb')}
    save_json(output / 'manifest.json', manifest)
    print(json.dumps({'run_id': run_id, 'summary': summary}, ensure_ascii=False), flush=True)
    if failures or len(entries) != 150 or len(audits) != 100:
        raise SystemExit('P1 incomplete: inspect all recorded failures; do not silently resample.')
    if any(row['load_revision_triggered'] for row in summary['layers'].values()):
        raise SystemExit('Pilot sparse-load trigger: user decision required before protocol freeze.')


if __name__ == '__main__':
    main()
