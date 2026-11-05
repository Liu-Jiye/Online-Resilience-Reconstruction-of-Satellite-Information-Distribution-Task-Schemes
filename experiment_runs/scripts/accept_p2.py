"""Freeze or check supplemental P2 acceptance evidence; never overwrite."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args();run=args.run_directory.resolve()
    inputs=ROOT/'reports/p2/P2-inputs-v1';target=run/'acceptance_manifest.json'
    for manifest,directory in ((load(run/'manifest.json'),run),(load(inputs/'manifest.json'),inputs)):
        for name,expected in manifest['artifact_sha256'].items():assert sha(directory/name)==expected,name
        for name,expected in manifest['source_sha256'].items():assert sha(REPO/name)==expected,name
    audit=load(run/'independent_audit.json')
    assert audit['passed'] and audit['native_models_replayed']==264
    assert sha(ROOT/'scripts/verify_p2.py')==audit['verifier_script_sha256']
    analysis=load(run/'analysis.json')
    assert sha(ROOT/'scripts/summarize_p2.py')==analysis['summary_script_sha256']
    suites=ET.parse(run/'pytest.xml').getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in suites)==140
    assert not any(int(s.attrib.get(k,0)) for s in suites for k in ('errors','failures','skipped'))
    assert '140 passed' in (run/'pytest.txt').read_text(encoding='utf-8')
    baseline='f8cd6afd8a8a33d43c9f178ae186bf42f9de18dc'
    outside=subprocess.check_output(['git','diff','--name-only',baseline,'--','.',':(exclude)experiment_runs'],cwd=REPO,text=True).splitlines()
    assert not outside
    protected=['experiment_runs/src/isl','experiment_runs/tests/test_constraints.py','experiment_runs/tests/test_p1.py',
               'experiment_runs/tests/test_repair.py','experiment_runs/reports/p0','experiment_runs/reports/p1',
               'experiment_runs/reports/P0_REPORT.md','experiment_runs/reports/P1_REPORT.md',
               'experiment_runs/configs/p0.json','experiment_runs/configs/p1.json',
               'experiment_runs/environment/requirements-p0.lock.txt','experiment_runs/environment/requirements-p1.lock.txt']
    changed=subprocess.check_output(['git','diff','--name-only',baseline,'--',*protected],cwd=REPO,text=True).splitlines()
    assert not any(p not in ['experiment_runs/src/isl/p2_exact.py','experiment_runs/src/isl/p2_generation.py'] for p in changed),changed
    files=[p for directory in (inputs,run) for p in directory.iterdir() if p.is_file() and p!=target]
    files+=list((ROOT/'src').rglob('*.py'))+list((ROOT/'tests').glob('*.py'))+list((ROOT/'scripts').glob('*.py'))
    files += [ROOT/p for p in ('configs/p2.json','protocol/P2_EXACT_CONTRACT.md','environment/requirements-p2.lock.txt',
                               'reports/P2_REPORT.md','README.md','STAGES.md','status.json','.gitattributes')]
    hashes={p.relative_to(REPO).as_posix():sha(p) for p in sorted(set(files))}
    value={'passed':True,'stage':'P2','run_id':run.name,'accepted_at_utc':datetime.now(timezone.utc).isoformat(),
           'unit_tests_passed':140,'independent_audit_passed':True,'native_models_replayed':264,
           'outside_experiment_runs_changes':outside,'P0_P1_existing_code_data_evidence_modified':False,
           'baseline_commit':baseline,'test_instances_generated':0,'next_stage':'P3','next_stage_authorized':False,
           'file_sha256':hashes}
    if args.write:
        assert not target.exists(),'Refuse to overwrite acceptance manifest'
        target.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    else:
        recorded=load(target)
        for name,expected in recorded['file_sha256'].items():assert sha(REPO/name)==expected,name
    print(json.dumps({'passed':True,'stage':'P2','files_hashed':len(hashes),'unit_tests_passed':140,
                      'native_models_replayed':264,'next_stage_authorized':False},indent=2))


if __name__=='__main__':main()
