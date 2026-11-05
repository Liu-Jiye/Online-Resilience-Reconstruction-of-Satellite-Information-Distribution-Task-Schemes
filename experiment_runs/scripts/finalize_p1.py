"""Offline P1 evidence audit, distribution tables/figures and freeze manifest."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
from importlib.metadata import metadata as package_metadata
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / 'src'))
from isl.models import Busy, Contact, Instance, Item, Task
from isl.p1_sources import save_json
from isl.p1_orbits import compare_windows, inward_window
from isl.p1_generation import component_seeds, create_instance, synthetic_contacts, distribution
from isl.validation import validate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def instance_from_dict(raw):
    return Instance(raw['id'], tuple(raw['satellites']), tuple(Task(**t) for t in raw['tasks']),
                    tuple(Contact(**c) for c in raw['contacts']), tuple(Busy(**b) for b in raw['calendar']), raw['horizon'])


def audit(run):
    manifest, config = load(run / 'manifest.json'), load(run / 'config.json')
    for name, expected in manifest['source_sha256'].items():
        assert sha(REPO / name) == expected, 'source hash: ' + name
    for name, expected in manifest['artifact_sha256'].items():
        assert sha(run / name) == expected, 'artifact hash: ' + name
    raw_dir = ROOT / config['source_directory']
    group_reports = {name: load(ROOT / f'reports/p1/{name}_groups.json') for name in ('starlink', 'oneweb')}
    for name, expected in manifest['snapshot_sha256'].items():
        assert sha(raw_dir / f'{name}.json') == expected
        groups = group_reports[name]['groups']
        all_ids = [cat for g in groups for cat in g['norad_ids']]
        assert len(all_ids) == len(set(all_ids)) == 320
        assert all(len(g['norad_ids']) == 32 for g in groups)
        assert [g['split'] for g in groups] == ['train'] * 6 + ['validation'] * 2 + ['test'] * 2
        original = {int(row['NORAD_CAT_ID']): row for row in load(raw_dir / f'{name}.json')}
        eligible = load(ROOT / f'data/processed/p1/{name}_eligible.json')['records']
        assert all(row == original[int(row['NORAD_CAT_ID'])] for row in eligible)
    entries = load(run / 'distributions.json')
    geometries = load(run / 'window_audits.json')
    counts, groups_used = {}, {}
    aggregate_audits = {}
    instances = {}
    with zipfile.ZipFile(run / 'pilot_derived_instances.zip') as bundle:
        assert len(bundle.namelist()) == 250
        for row in entries:
            iid = row['instance_id']
            payload = bundle.read(iid + '.json')
            assert hashlib.sha256(payload).hexdigest() == row['sha256']
            data = json.loads(payload)
            instance = instance_from_dict(data['instance'])
            instances[iid] = data
            ref = tuple(Item(**p) for p in data['reference'])
            assert len(instance.satellites) == 32 and len(instance.tasks) == 100 and ref
            assert validate(instance, ref).feasible
            split, layer, seed = row['split'], row['layer'], row['seed']
            assert split in {'train', 'validation'}
            assert (100000 <= seed <= 199999) if split == 'train' else (200000 <= seed <= 299999)
            counts[(layer, split)] = counts.get((layer, split), 0) + 1
            generated, metadata = create_instance(iid, instance.satellites, instance.contacts, seed)
            assert generated == instance
            assert metadata['task_sampling'] == data['metadata']['task_sampling']
            recomputed = distribution(instance, ref, metadata)
            assert all(row[key] == value for key, value in recomputed.items()), 'distribution mismatch'
            if layer == 'D1':
                contact_seed = component_seeds(seed)['contacts']
                contacts, _ = synthetic_contacts(instance.satellites, np.random.Generator(np.random.PCG64(contact_seed)))
                assert contacts == instance.contacts
            else:
                name = {'D2-S': 'starlink', 'D2-O': 'oneweb'}[layer]
                group = next(g for g in group_reports[name]['groups'] if g['group_id'] == row['group_id'])
                assert group['split'] == split
                assert set(instance.satellites) == {str(cat) for cat in group['norad_ids']}
                assert -43200 <= row['offset_s'] <= 37800
                key = (layer, split, row['group_id'])
                groups_used[key] = groups_used.get(key, 0) + 1
                geometry = json.loads(bundle.read(iid + '.audit.json'))
                comparison = compare_windows(geometry['physical_5s'], geometry['physical_1s'])
                saved = next(a for a in geometries if a['instance_id'] == iid)
                assert all(saved[k] == v or json.dumps(saved[k]) == json.dumps(v) for k, v in comparison.items())
                # Every published direction must come from a retained, inward
                # rounded physical coarse interval. This also checks reverse links.
                expected = set()
                for p in geometry['physical_5s']:
                    interval = inward_window(p['start'], p['end'])
                    if p['end'] - p['start'] >= 10 and interval:
                        expected.update(((p['a'], p['b'], *interval), (p['b'], p['a'], *interval)))
                assert {(c.sender, c.receiver, c.start, c.end) for c in instance.contacts} == expected
    assert counts == {(layer, split): 25 for layer in ('D1','D2-S','D2-O') for split in ('train','validation')}
    assert len(geometries) == 100 and len({a['instance_id'] for a in geometries}) == 100
    for layer in ('D2-S', 'D2-O'):
        rows = [a for a in geometries if a['layer'] == layer]
        matched = [m for a in rows for m in a['matched']]
        errors = [error for m in matched for error in (m['start_error_s'], m['end_error_s'])]
        integer_errors = [abs(c-f) for m in matched if m['coarse_discrete'] and m['fine_discrete']
                          for c, f in zip(m['coarse_discrete'], m['fine_discrete'])]
        aggregate_audits[layer] = {'base_instances': len(rows),
            'coarse_physical_windows': sum(a['coarse_physical_windows'] for a in rows),
            'fine_physical_windows': sum(a['fine_physical_windows'] for a in rows),
            'missed_physical_windows': sum(len(a['missed_at_5s']) for a in rows),
            'extra_physical_windows': sum(len(a['extra_at_5s']) for a in rows),
            'missed_retained_windows': sum(a['missed_retained_at_5s'] for a in rows),
            'retention_disagreements': sum(a['retention_disagreements'] for a in rows),
            'discrete_window_disagreements': sum(a['discrete_disagreements'] for a in rows),
            'max_discrete_endpoint_error_s': max(integer_errors, default=0),
            'boundary_error_mean_s': float(np.mean(errors)), 'boundary_error_p95_s': float(np.quantile(errors,.95)),
            'boundary_error_max_s': max(errors, default=0)}
    result = {'passed': True, 'stage': 'P1', 'audited_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_hashes_verified': len(manifest['source_sha256']), 'artifact_hashes_verified': len(manifest['artifact_sha256']),
        'snapshot_hashes_verified': 2, 'instances_revalidated': 150, 'task_calendar_seed_reproductions': 150,
        'synthetic_contact_seed_reproductions': 50, 'orbital_geometry_audits_recomputed': 100,
        'counts': {f'{layer}:{split}': count for (layer,split),count in counts.items()},
        'group_instance_counts': {':'.join(key): count for key,count in groups_used.items()},
        'test_instances_or_performance_accessed': False, 'window_summary': aggregate_audits,
        'audit_script_sha256': sha(Path(__file__))}
    return result, entries, geometries, instances


def figures(run, entries, audits):
    colors = ['#3366a2', '#d78b2a', '#359172']
    layers = ['D1','D2-S','D2-O']
    plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.8), layout='constrained')
    specs = [('scheduled_count','Tasks in reference plan',1),
             ('window_only_feasible_fraction','Task-window + contact feasible (%)',100),
             ('single_task_calendar_feasible_fraction','Also calendar feasible, alone (%)',100),
             ('background_actual_occupancy','Actual background terminal load (%)',100),
             ('scheduled_terminal_occupancy','Reference task terminal load (%)',100),
             ('max_sender_share','Largest sender demand share (%)',100)]
    for ax,(key,title,scale) in zip(axes.flat,specs):
        values = [[r[key]*scale for r in entries if r['layer']==layer] for layer in layers]
        plots=ax.boxplot(values,tick_labels=layers,patch_artist=True,medianprops={'color':'#18232e'})
        for patch,color in zip(plots['boxes'],colors):
            patch.set_facecolor(color); patch.set_alpha(.6)
        ax.set_title(title); ax.grid(axis='y',alpha=.2)
        if key=='scheduled_count': ax.axhline(10,color='#aa3333',ls='--',lw=1,label='Sparse-count threshold')
    fig.suptitle('P1 pilot distributions | 50 base instances per layer | 25 train + 25 validation',fontsize=14)
    fig.savefig(run/'pilot_distributions.png',dpi=180); plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13.5,4),layout='constrained')
    for layer,color in zip(('D2-S','D2-O'),colors[1:]):
        matches=[m for a in audits if a['layer']==layer for m in a['matched']]
        errors=[e for m in matches for e in (m['start_error_s'],m['end_error_s'])]
        values,cnt=np.unique(errors,return_counts=True)
        axes[0].step(values,np.cumsum(cnt)/sum(cnt),where='post',label=layer,color=color)
    axes[0].set(xlabel='Absolute boundary difference (s)',ylabel='Empirical CDF',title='5 s vs 1 s scans, both refined to 0.1 s')
    axes[0].legend(); axes[0].grid(alpha=.2)
    for layer,color in zip(layers,colors):
        lengths=[v for row in entries if row['layer']==layer for v in row['contact_lengths_s']]
        axes[1].hist(lengths,bins=40,histtype='step',density=True,label=layer,color=color)
    axes[1].set(xlabel='Integer contact duration (s)',ylabel='Density',title='Undirected usable contact windows')
    axes[1].legend(); axes[1].grid(alpha=.2)
    values=[]
    for layer in ('D2-S','D2-O'):
        rows=[a for a in audits if a['layer']==layer]
        values.append(sum(a['discrete_disagreements'] for a in rows)/sum(len(a['matched']) for a in rows)*100)
    axes[2].bar(['D2-S','D2-O'],values,color=colors[1:])
    axes[2].set(ylabel='Matched windows with changed integer endpoint (%)',title='Integer inward rounding can differ by 1 s')
    for i,value in enumerate(values): axes[2].text(i,value+.08,f'{value:.2f}%',ha='center')
    axes[2].set_ylim(0,max(values)*1.2); axes[2].grid(axis='y',alpha=.2)
    fig.savefig(run/'window_audit.png',dpi=180); plt.close(fig)


def licensing(run):
    raw=ROOT/'data/raw/p1_snapshot_20261105'
    records=[load(path) for path in sorted(raw.glob('*.fetch.json'))]
    packages=[]
    for name in ('sgp4','skyfield','numpy','matplotlib'):
        info=package_metadata(name)
        license_text=info.get('License') or ''
        packages.append({'name':name,'version':info['Version'], 'license_expression':info.get('License-Expression'),
                         'license_metadata_sha256':hashlib.sha256(license_text.encode()).hexdigest(),
                         'license_metadata_first_line':license_text.splitlines()[0] if license_text else None})
    value={'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'source':'CelesTrak GP',
        'usage_policy_url':'https://celestrak.org/usage-policy.php',
        'usage_policy_sha256':next(r['sha256'] for r in records if r['name']=='usage_policy'),
        'policy_updated_on_page':'2026-05-22',
        'policy_evidence_quotes':[
            'Only download the data you need, when you are going to use it, and only download data once per update.',
            'For GP data, updates are once every 2 hours.',
            'M2M (machine-to-machine) software should immediately stop querying when it receives any non-HTTP 200 responses and report the results to a human for investigation.'],
        'raw_GP_explicit_redistribution_license_found_in_reviewed_pages':False,
        'access_policy_is_not_an_open_data_license':True,
        'raw_GP_and_raw_HTML_uploaded_to_GitHub':False,
        'raw_GP_local_directory':'experiment_runs/data/raw/p1_snapshot_20261105',
        'published_bundle_content':'Derived integer contacts; synthetic demands and calendars; computed reference plans and metadata; geometric audit. No original GP/OMM records.',
        'source_records':records,'software_metadata':packages,
        'new_code_or_third_party_data_relicensed':False}
    save_json(run/'source_and_license_registry.json',value)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('run_directory',type=Path)
    parser.add_argument('--previous-run',type=Path)
    args=parser.parse_args(); run=args.run_directory.resolve()
    result,entries,audits,instances=audit(run)
    if args.previous_run:
        old={}
        with zipfile.ZipFile(args.previous_run/'pilot_derived_instances.zip') as bundle:
            for name in bundle.namelist():
                if not name.endswith('.audit.json'):
                    value=json.loads(bundle.read(name)); old[value['instance']['id']]=value
        relabelled=[]
        for iid,value in instances.items():
            previous=old[iid]
            current_instance,previous_instance=value['instance'],previous['instance']
            assert {k:v for k,v in current_instance.items() if k!='contacts'} == {k:v for k,v in previous_instance.items() if k!='contacts'},iid
            assert len(current_instance['contacts'])==len(previous_instance['contacts'])
            for current_contact,previous_contact in zip(current_instance['contacts'],previous_instance['contacts']):
                assert {k:v for k,v in current_contact.items() if k!='id'} == {k:v for k,v in previous_contact.items() if k!='id'},iid
                if current_contact['id']!=previous_contact['id']:
                    relabelled.append({'instance_id':iid,'previous_id':previous_contact['id'],'current_id':current_contact['id']})
            assert value['reference']==previous['reference'],iid
            assert value['metadata']==previous['metadata'],iid
        result['previous_run_same_150_semantic_instances_references_metadata']=True
        result['previous_run_contact_id_relabels']=relabelled
        result['previous_run_id']=args.previous_run.name
        result['correction']='Remove zero-duration endpoint markers from physical-window audit; no demand/calendar/contact-geometry/reference/protocol change. Local contact sequence IDs may renumber.'
    save_json(run/'independent_audit.json',result)
    licensing(run); figures(run,entries,audits)
    keys=['instance_id','layer','split','seed','group_id','scheduled_count','window_only_feasible_fraction',
          'single_task_calendar_feasible_fraction','scheduled_terminal_occupancy','background_actual_occupancy',
          'combined_terminal_occupancy','max_sender_share','max_receiver_share','reference_construction_ms','sha256']
    with (run/'per_instance_distribution.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys); writer.writeheader()
        writer.writerows({key:row[key] for key in keys} for row in entries)
    freeze={'status':'frozen_after_P1_pilot','generator_version':'1.0-pilot','pipeline_version':'0.1.1',
        'run_id':run.name,'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'protocol_revision_for_load':False,'reason':'No layer triggered >80% references with <10 tasks.',
        'test_instances_generated':0,'test_performance_read':False,'next_stage_authorized':False,
        'config_sha256':sha(ROOT/'configs/p1.json'),'generation_contract_sha256':sha(ROOT/'protocol/P1_GENERATION_CONTRACT.md'),
        'groups_sha256':{name:sha(ROOT/f'reports/p1/{name}_groups.json') for name in ('starlink','oneweb')},
        'snapshot_sha256':load(run/'manifest.json')['snapshot_sha256'],
        'derived_archive_sha256':sha(run/'pilot_derived_instances.zip'),
        'evidence_sha256':{path.name:sha(path) for path in sorted(run.iterdir()) if path.is_file()},
        'finalizer_script_sha256':sha(Path(__file__))}
    save_json(run/'protocol_freeze.json',freeze)
    print(json.dumps({'audit_passed':result['passed'],'window_summary':result['window_summary'],
                      'frozen_protocol':str(run/'protocol_freeze.json')},ensure_ascii=False))


if __name__=='__main__': main()
