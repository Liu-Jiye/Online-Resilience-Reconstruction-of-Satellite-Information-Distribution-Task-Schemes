"""Crash-resumable P3 generation. No repair algorithm or test performance access."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from isl.models import canonical_json
from isl.p1_generation import component_seeds, synthetic_contacts, create_instance
from isl.p1_orbits import build_contacts, epoch
from isl.load_pilot import demand_family, transform_family, indexed_reference
from isl.load_pilot_independent import BitAudit
from isl.events import generate_event


def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(canonical_json(value) + '\n', encoding='utf-8')
    temp.replace(p)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=5000, help='development check only; full manifest needs5000')
    args = parser.parse_args()
    cfg = load(ROOT / 'configs/p3_v1.json')
    lc = load(ROOT / 'configs/load_pilot_v1.json')
    out = ROOT / 'reports/p3/P3-20261110/data'
    out.mkdir(parents=True, exist_ok=True)
    orbit = {}
    source_hashes = {}
    for name in ('starlink', 'oneweb'):
        ep = ROOT / f'data/processed/p1/{name}_eligible.json'
        gp = ROOT / f'reports/p1/{name}_groups.json'
        e, groups = load(ep), load(gp)['groups']
        orbit[name] = (e, groups)
        source_hashes[str(ep.relative_to(ROOT))] = sha(ep)
        source_hashes[str(gp.relative_to(ROOT))] = sha(gp)
        ids = [{n for g in groups if g['split'] == split for n in g['norad_ids']}
               for split in ('train', 'validation', 'test')]
        assert [len(x) for x in ids] == [192, 64, 64]
        assert all(not (ids[i] & ids[j]) for i in range(3) for j in range(i))
    for p in sorted((ROOT / 'src/isl').glob('*.py')) + [Path(__file__), ROOT/'configs/p3_v1.json', ROOT/'configs/load_pilot_v1.json']:
        source_hashes[str(p.relative_to(ROOT))] = sha(p)
    frozen = out / 'generation_sources.json'
    if frozen.exists():
        assert load(frozen) == source_hashes, 'generation source changed during resume'
    else:
        save(frozen, source_hashes)
    scenarios = [(k, fr, q) for k in cfg['kinds'] for fr in cfg['FR'] for q in cfg['q']]
    all_rows, global_index = [], 0
    for split, counts in cfg['counts'].items():
        seed = cfg['seed_start'][split]
        for layer, count in counts.items():
            for index in range(count):
                if global_index >= args.limit:
                    return
                ident = f'P3-{split}-{layer}-{index:04d}'
                shard = out / f'{ident}.zip'
                receipt = out / f'{ident}.json'
                if receipt.exists():
                    row = load(receipt)
                    assert row['archive_sha256'] == sha(shard)
                else:
                    began = time.perf_counter_ns()
                    try:
                        seeds = component_seeds(seed)
                        if layer == 'D1':
                            sats = tuple(f'S{i:02d}' for i in range(32))
                            contacts, _ = synthetic_contacts(sats, np.random.Generator(np.random.PCG64(seeds['contacts'])))
                            geometry = {'type': 'synthetic', 'contact_probability': .2}
                        else:
                            name = 'starlink' if layer == 'D2-S' else 'oneweb'
                            e, groups = orbit[name]
                            eligible_groups = [g for g in groups if g['split'] == split]
                            group = eligible_groups[index % len(eligible_groups)]
                            selected_ids = set(group['norad_ids'])
                            records = [r for r in e['records'] if int(r['NORAD_CAT_ID']) in selected_ids]
                            assert len(records) == 32
                            offset = int(np.random.Generator(np.random.PCG64(seeds['segment'])).integers(-43200, 37801))
                            contacts, _ = build_contacts(records, epoch(e['t_ref_utc']), offset, 5)
                            sats = tuple(str(n) for n in sorted(selected_ids))
                            geometry = {'type': name, 'group': group['group_id'], 'offset_s': offset, 'step_s': 5}
                        base, metadata = create_instance(ident, sats, contacts, seed)
                        raw, details = demand_family(base, seeds['tasks'], lc)
                        assert tuple(raw[:100]) == base.tasks
                        medium, hot, _ = transform_family(base, raw, details, seed, .8, lc)
                        variants = [('default', base), ('N500-h0.8', replace(base, id=ident+'-N500-h0.8', tasks=medium[:500]))]
                        entries, ref_counts = {}, {}
                        temp = shard.with_suffix('.zip.tmp')
                        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
                            for label, ins in variants:
                                ref = indexed_reference(ins)
                                assert ref == BitAudit(ins, ()).reference_plan(), 'independent reference disagreement'
                                assert ref, 'empty reference; protocol requires explicit decision'
                                events = []
                                for si, (kind, fr, q) in enumerate(scenarios):
                                    es = int(np.random.SeedSequence([seed, cfg['event_seed_tag'], si]).generate_state(1, dtype=np.uint64)[0])
                                    event = generate_event(ins, ref, kind, fr, q, es)
                                    events.append({'scenario_index': si, 'FR': fr, 'q': q, 'event': asdict(event)})
                                payload = canonical_json({'instance': asdict(ins), 'reference': [asdict(p) for p in ref],
                                    'events': events, 'metadata': {'instance_seed': seed, 'component_seeds': seeds,
                                    'geometry': geometry, 'split': split, 'layer': layer, 'load': label,
                                    'training_scenario': global_index % 12 if split == 'train' else None,
                                    'hot_satellites': hot if label != 'default' else [],
                                    'reference_crosscheck': 'independent_bitset_exact_match'}}).encode()
                                name = label + '.json'
                                z.writestr(name, payload)
                                entries[name] = hashlib.sha256(payload).hexdigest()
                                ref_counts[label] = len(ref)
                        temp.replace(shard)
                        row = {'id': ident, 'global_index': global_index, 'seed': seed, 'split': split, 'layer': layer,
                               'geometry': geometry, 'entries_sha256': entries, 'archive_sha256': sha(shard),
                               'reference_counts': ref_counts, 'generation_ns': time.perf_counter_ns() - began}
                        save(receipt, row)
                    except Exception as error:
                        save(out / f'FAILED-{ident}.json', {'id': ident, 'seed': seed, 'error': repr(error), 'policy': 'stop_without_resampling'})
                        raise
                all_rows.append(row)
                global_index += 1
                seed += 1
                if global_index % 25 == 0:
                    print(json.dumps({'generated': global_index, 'total': 5000, 'last': ident}), flush=True)
    assert len(all_rows) == 5000
    assert len({r['seed'] for r in all_rows}) == 5000
    save(out / 'manifest.json', {'complete': True, 'base_scenes': 5000, 'paired_variants': 10000,
        'test_scenes_generated': 0, 'source_sha256': source_hashes, 'instances': all_rows,
        'all_reference_bitset_checks_passed': True})
    print('P3 input generation complete', flush=True)


if __name__ == '__main__':
    main()
