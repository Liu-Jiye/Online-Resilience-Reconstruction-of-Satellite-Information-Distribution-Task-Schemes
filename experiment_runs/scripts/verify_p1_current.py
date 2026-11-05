"""Current P1 public entry after P2: strict scientific checks and verified progress transitions.

Derived from immutable verify_p1.py; original P1/P2 acceptances remain unchanged.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from p1_current_compat import verify_compatibility

from finalize_p1 import (ROOT, REPO, compare_windows, component_seeds, create_instance,
                         distribution, inward_window, instance_from_dict, Item, np,
                         synthetic_contacts, validate)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('--write-acceptance', type=Path, metavar='NEW_JSON', help='Save a new current-version receipt; never overwrite historical acceptance')
    args = parser.parse_args()
    run = args.run_directory.resolve()
    compatibility = verify_compatibility(REPO, run, ROOT/'protocol/P1_CURRENT_VERIFICATION.json')
    freeze, manifest = load(run/'protocol_freeze.json'), load(run/'manifest.json')
    for name, expected in manifest['source_sha256'].items():
        assert sha(REPO/name) == expected, name
    for mapping in (manifest['artifact_sha256'], freeze['evidence_sha256']):
        for name, expected in mapping.items():
            assert sha(run/name) == expected, name
    assert sha(ROOT/'scripts/finalize_p1.py') == freeze['finalizer_script_sha256']
    assert sha(ROOT/'configs/p1.json') == freeze['config_sha256']
    assert sha(ROOT/'protocol/P1_GENERATION_CONTRACT.md') == freeze['generation_contract_sha256']
    splits = {s: set() for s in ('train', 'validation', 'test')}
    groups = {}
    for name, expected in freeze['groups_sha256'].items():
        path = ROOT/f'reports/p1/{name}_groups.json'
        assert sha(path) == expected
        groups[name] = load(path)['groups']
        ids = [i for g in groups[name] for i in g['norad_ids']]
        assert len(ids) == len(set(ids)) == 320
        assert [g['split'] for g in groups[name]] == ['train']*6+['validation']*2+['test']*2
        for group in groups[name]:
            assert len(group['norad_ids']) == 32
            assert not set(group['norad_ids']) & set.union(*splits.values())
            splits[group['split']].update(group['norad_ids'])
    assert len(set.union(*splits.values())) == 640
    intersections = {f'{a}_{b}': sorted(splits[a]&splits[b])
                     for a, b in itertools.combinations(splits, 2)}
    assert not any(intersections.values())
    entries = load(run/'distributions.json')
    saved_audits = {a['instance_id']: a for a in load(run/'window_audits.json')}
    counts, audit_count = {}, 0
    with zipfile.ZipFile(run/'pilot_derived_instances.zip') as bundle:
        assert len(bundle.namelist()) == 250 and len(entries) == 150
        assert len({r['instance_id'] for r in entries}) == 150
        for row in entries:
            iid = row['instance_id']
            payload = bundle.read(iid+'.json')
            assert hashlib.sha256(payload).hexdigest() == row['sha256']
            data = json.loads(payload)
            instance = instance_from_dict(data['instance'])
            reference = tuple(Item(**p) for p in data['reference'])
            assert validate(instance, reference).feasible
            assert len(instance.satellites) == 32 and len(instance.tasks) == 100
            layer, split, seed = row['layer'], row['split'], row['seed']
            assert split in ('train', 'validation')
            assert (100000 <= seed <= 199999) if split == 'train' else (200000 <= seed <= 299999)
            counts[f'{layer}:{split}'] = counts.get(f'{layer}:{split}', 0)+1
            generated, metadata = create_instance(iid, instance.satellites, instance.contacts, seed)
            assert generated == instance and metadata['task_sampling'] == data['metadata']['task_sampling']
            assert all(row[k] == v for k, v in distribution(instance, reference, metadata).items())
            if layer == 'D1':
                contacts, _ = synthetic_contacts(instance.satellites, np.random.Generator(np.random.PCG64(component_seeds(seed)['contacts'])))
                assert contacts == instance.contacts
            else:
                name = {'D2-S':'starlink', 'D2-O':'oneweb'}[layer]
                group = next(g for g in groups[name] if g['group_id'] == row['group_id'])
                assert group['split'] == split and set(instance.satellites) == set(map(str, group['norad_ids']))
                assert -43200 <= row['offset_s'] <= 37800
                geometry = json.loads(bundle.read(iid+'.audit.json'))
                comparison = compare_windows(geometry['physical_5s'], geometry['physical_1s'])
                assert all(json.dumps(saved_audits[iid][k]) == json.dumps(v) for k, v in comparison.items())
                expected = set()
                for p in geometry['physical_5s']:
                    interval = inward_window(p['start'], p['end'])
                    if p['end']-p['start'] >= 10 and interval:
                        expected.update(((p['a'], p['b'], *interval), (p['b'], p['a'], *interval)))
                assert {(c.sender, c.receiver, c.start, c.end) for c in instance.contacts} == expected
                audit_count += 1
    assert counts == {f'{l}:{s}':25 for l in ('D1','D2-S','D2-O') for s in ('train','validation')}
    assert audit_count == len(saved_audits) == 100
    suites = ET.parse(run/'pytest.xml').getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in suites) == 125
    assert all(int(s.attrib.get(k, 0)) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    baseline = 'ef2bcb00b79e2cff330fa12cd8de827c2d7f507e'
    outside = subprocess.check_output(['git', 'diff', '--name-only', baseline, '--', '.', ':(exclude)experiment_runs'], cwd=REPO, text=True).splitlines()
    assert not outside, outside
    files = [p for p in run.iterdir() if p.is_file() and p.name != 'acceptance_manifest.json']
    files += [ROOT/'reports/P1_REPORT.md', Path(__file__).resolve(), ROOT/'scripts/verify_p1.py', ROOT/'scripts/p1_current_compat.py', ROOT/'protocol/P1_CURRENT_VERIFICATION.json', ROOT/'scripts/finalize_p1.py', ROOT/'status.json', ROOT/'README.md', ROOT/'STAGES.md']
    supplemental = {p.relative_to(REPO).as_posix():sha(p) for p in sorted(files)}
    result = {'passed':True, 'stage':'P1', 'run_id':run.name,
              'audited_at_utc':datetime.now(timezone.utc).isoformat(),
              'verification_version':'1.0-post-P2', 'compatibility':compatibility,
              'legacy_verifier_sha256':sha(ROOT/'scripts/verify_p1.py'),
              'current_source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              'global_unique_orbital_objects':640, 'split_object_counts':{k:len(v) for k,v in splits.items()},
              'global_split_intersections':intersections, 'instances_revalidated':150,
              'task_calendar_seed_reproductions':150, 'synthetic_contact_seed_reproductions':50,
              'geometry_comparisons_recomputed':100, 'counts':counts, 'pytest_passed':125,
              'outside_experiment_runs_changed_from_baseline':outside, 'baseline_commit':baseline,
              'original_GP_required_or_read':False, 'original_GP_propagation_repeated':False,
              'raw_snapshot_hash_validation':'Previously completed by independent_audit.json; public verifier does not read raw GP.',
              'file_sha256':supplemental}
    if args.write_acceptance:
        target=args.write_acceptance.resolve()
        assert target.is_relative_to((ROOT/'reports/p1').resolve()), 'Receipt must stay inside reports/p1/'
        assert target.parent != run and not target.exists(), 'Use a new receipt outside the historical run'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in result.items() if k!='file_sha256'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
