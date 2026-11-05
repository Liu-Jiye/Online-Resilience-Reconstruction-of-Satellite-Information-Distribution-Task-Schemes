"""Strict, explicit P1 -> P2 progress-document compatibility checks."""
import hashlib
import json
from pathlib import Path
import subprocess

PROGRESS_PATHS=frozenset({'experiment_runs/README.md','experiment_runs/STAGES.md','experiment_runs/status.json'})


def digest(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def check_paths(repo,p1_hashes,p2_hashes,historical_read):
    """Only registered progress paths can transition; every other byte is strict."""
    transitions=[];immutable=0
    for name,expected in p1_hashes.items():
        current=digest((repo/name).read_bytes())
        if name in PROGRESS_PATHS:
            assert name in p2_hashes,f'Missing P2 progress hash: {name}'
            assert digest(historical_read('P1',name))==expected,f'P1 historical blob mismatch: {name}'
            assert current==p2_hashes[name],f'Current progress file differs from frozen P2: {name}'
            assert digest(historical_read('P2',name))==current,f'P2 historical blob mismatch: {name}'
            transitions.append({'path':name,'P1_sha256':expected,'current_P2_sha256':current,'changed_since_P1':current!=expected,
                                'P1_historical_blob_verified':True,'P2_historical_blob_verified':True})
        else:
            assert current==expected,f'Immutable P1 acceptance file changed: {name}'
            immutable+=1
    assert {x['path'] for x in transitions}==PROGRESS_PATHS,'Missing required progress paths in P1 acceptance'
    return {'immutable_P1_acceptance_files_verified':immutable,'progress_files_verified':len(transitions),'progress_transitions':transitions}


def verify_compatibility(repo,run,config_path):
    config=load(config_path)
    assert set(config['progress_paths'])==PROGRESS_PATHS,'Progress allowlist cannot be expanded'
    assert run.name==config['P1_run_id']
    p1_path=run/'acceptance_manifest.json';p2_path=repo/config['P2_acceptance_path']
    assert digest(p1_path.read_bytes())==config['P1_acceptance_sha256'],'P1 historical acceptance modified'
    assert digest(p2_path.read_bytes())==config['P2_acceptance_sha256'],'P2 historical acceptance modified'
    def historical_read(stage,name):
        commit=config[stage+'_historical_commit']
        return subprocess.check_output(['git','show',commit+':'+name],cwd=repo)
    receipt=check_paths(repo,load(p1_path)['file_sha256'],load(p2_path)['file_sha256'],historical_read)
    receipt.update(version=config['version'],P1_historical_commit=config['P1_historical_commit'],P2_historical_commit=config['P2_historical_commit'],
                   P1_acceptance_sha256=config['P1_acceptance_sha256'],P2_acceptance_sha256=config['P2_acceptance_sha256'],
                   compatibility_config_sha256=digest(config_path.read_bytes()))
    return receipt
