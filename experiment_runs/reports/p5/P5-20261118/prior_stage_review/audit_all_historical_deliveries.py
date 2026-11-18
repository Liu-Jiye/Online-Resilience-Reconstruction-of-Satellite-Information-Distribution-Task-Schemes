import collections
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

BASE = Path(__file__).resolve().parents[1]
REPO = BASE / 'work/repository'
EXP = REPO / 'experiment_runs'
SOURCE = Path(r'C:\Users\25735\Documents\Codex\2026-11-05\https-github-com-liu-jiye-online-2\work\repository')
COMMIT = 'a7eaff69672891c1ae3ea01df8ba80c1aa431134'
SLUG = 'Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def git_blob(path):
    h = hashlib.sha1(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


remote_head = subprocess.check_output(['git','ls-remote','origin','refs/heads/main'],cwd=REPO,text=True).split()[0]
assert remote_head == COMMIT
root_tree = subprocess.check_output(['git','rev-parse',COMMIT+'^{tree}'],cwd=REPO,text=True).strip()
tree = json.loads(subprocess.check_output(['gh','api',f'repos/{SLUG}/git/trees/{root_tree}?recursive=1']))
assert not tree['truncated'] and tree['sha'] == root_tree
remote = {row['path']:row['sha'] for row in tree['tree'] if row['type']=='blob'}

checked_git = set()


def remote_exact(path):
    name = path.relative_to(REPO).as_posix()
    assert name in remote, ('Missing from remote',name)
    if name not in checked_git:
        assert git_blob(path) == remote[name], ('Git byte mismatch',name)
        checked_git.add(name)


catalog = json.loads((EXP/'deliveries/catalog.json').read_text(encoding='utf8'))
lookup = {(e['source_date'],e['source_workspace'],e['original_name']):e for e in catalog['files']}
seen = set()
details = []
scope = []
for day in ['2026-11-05','2026-11-12']:
    date_root = Path(r'C:\Users\25735\Documents\Codex')/day
    for workspace in sorted(date_root.iterdir()):
        if not workspace.is_dir():
            continue
        if not workspace.name.startswith('https-github-com-liu-jiye-online'):
            scope.append(dict(date=day,workspace=workspace.name,in_scope=False,reason='Unrelated LM324 project'))
            continue
        files = sorted(p for p in (workspace/'outputs').rglob('*') if p.is_file())
        scope.append(dict(date=day,workspace=workspace.name,in_scope=True,output_files=len(files)))
        for src in files:
            name = src.relative_to(workspace/'outputs').as_posix()
            key = day,workspace.name,name
            assert key in lookup, ('Uncatalogued local deliverable',str(src))
            entry = lookup[key]
            assert src.stat().st_size == entry['bytes'] and sha(src) == entry['sha256'], str(src)
            if entry['storage']=='file':
                dst = EXP/entry['path']
                assert sha(dst) == entry['sha256']
                remote_exact(dst)
                locations = ['experiment_runs/'+entry['path']]
            else:
                h = hashlib.sha256()
                locations = []
                for part in entry['parts']:
                    dst = EXP/part['path']
                    assert dst.stat().st_size==part['bytes'] and sha(dst)==part['sha256']
                    remote_exact(dst)
                    locations.append('experiment_runs/'+part['path'])
                    with dst.open('rb') as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):
                            h.update(block)
                assert h.hexdigest()==entry['sha256']
            seen.add(key)
            details.append(dict(source_date=day,name=name,storage=entry['storage'],sha256=entry['sha256'],passed=True,remote_paths=locations))
assert seen == set(lookup), ('Catalog/source difference', set(lookup)-seen)
print('All current source outputs matched:',len(details),flush=True)

untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=SOURCE).decode('utf8').split('\0')
new_source_files = 0
for name in untracked:
    if not name:
        continue
    assert name.startswith('experiment_runs/')
    src,dst = SOURCE/name,REPO/name
    assert dst.is_file() and sha(src)==sha(dst), ('Untracked source not delivered',name)
    remote_exact(dst)
    new_source_files += 1
print('Original untracked experimental files matched:',new_source_files,flush=True)

derived = []
for run in ['P1-20261105T110133Z','P1-20261105T110427Z']:
    archive = EXP/'reports/p1'/run/'pilot_derived_instances.zip'
    remote_exact(archive)
    with zipfile.ZipFile(archive) as z:
        by_name = {row.filename:row for row in z.infolist()}
        for src in sorted((SOURCE/'experiment_runs/data/processed/p1'/run).rglob('*')):
            if not src.is_file():
                continue
            names = [n for n in by_name if n==src.name or n.endswith('/'+src.name)]
            assert len(names)==1, (src,names)
            member = names[0]
            assert hashlib.sha256(z.read(member)).hexdigest()==sha(src), str(src)
            derived.append(dict(source=str(src.relative_to(SOURCE)),archive=str(archive.relative_to(REPO)),member=member,passed=True))
assert len(derived)==500
for constellation in ['oneweb','starlink']:
    rel = f'experiment_runs/data/processed/p1/{constellation}_eligible.json'
    assert sha(SOURCE/rel)==sha(REPO/rel)
    remote_exact(REPO/rel)

pipeline = []
package = BASE/'work/restored_packages/2026-11-12/P3R_reproducibility_package.zip'
package_entry = next(e for e in catalog['files'] if e['original_name']==package.name)
assert sha(package)==package_entry['sha256']
with zipfile.ZipFile(package) as z:
    for src in sorted((SOURCE/'experiment_runs/reports/p3r/P3R-20261112/pipeline').glob('*.log')):
        member=src.relative_to(SOURCE/'experiment_runs').as_posix()
        assert hashlib.sha256(z.read(member)).hexdigest()==sha(src)
        pipeline.append(dict(name=src.name,archive=package.name,member=member,passed=True))
assert len(pipeline)==3

old_tree={}
for row in subprocess.check_output(['git','ls-tree','-rz','HEAD'],cwd=SOURCE).decode('utf8').split('\0'):
    if row:
        meta,name=row.split('\t',1)
        old_tree[name]=meta.split()[2]
removed=[n for n in old_tree if n not in remote]
assert not removed, removed
changed=[n for n,h in old_tree.items() if remote[n]!=h]
expected={'experiment_runs/.gitattributes','experiment_runs/README.md','experiment_runs/STAGES.md','experiment_runs/scripts/accept_p3_runtime.py','experiment_runs/status.json'}
assert set(changed)==expected,changed

result=dict(date='2026-11-18',passed=True,commit=COMMIT,remote_main=remote_head,
            scope='Satellite project delivery materials in the two specified date directories; excludes unrelated projects, caches, scratch workspace files and original third-party raw orbit snapshot retained locally by prior protocol.',
            source_workspace_inventory=scope,current_output_files=len(details),outputs_by_date=dict(collections.Counter(e['source_date'] for e in details)),
            missing_output_files=0,mismatched_output_files=0,original_untracked_experimental_files_verified=new_source_files,
            original_tracked_files_retained=len(old_tree),original_tracked_files_missing=0,expected_updated_navigation_or_byte_preservation_files=changed,
            p1_derived_json_verified_inside_git_zip=len(derived),p1_eligible_files_verified=2,p3r_logs_verified_inside_delivered_zip=pipeline,
            remote_git_objects_compared_with_local_original_bytes=len(checked_git),deliverable_files=details,p1_zip_members=derived)
(BASE/'outputs/两日期目录交付完整性复核.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
summary={k:v for k,v in result.items() if k not in ('deliverable_files','p1_zip_members')}
print(json.dumps(summary,ensure_ascii=False,indent=2))
