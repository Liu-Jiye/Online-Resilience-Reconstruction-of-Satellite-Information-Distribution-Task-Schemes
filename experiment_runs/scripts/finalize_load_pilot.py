"""Seal additive load-pilot evidence after successful scientific checks."""
import argparse,json,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
import load_pilot_study as study


def main():
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args();out=Path(args.folder).resolve()
    assert not (out/'acceptance_manifest.json').exists()
    manifest=study.load(out/'manifest.json')
    for name,h in manifest['source_sha256'].items():assert study.sha(study.REPO/name)==h,name
    for name,h in manifest['artifact_sha256'].items():assert study.sha(out/name)==h,name
    assert study.old_evidence()==study.load(out/'prior_acceptance.json')
    audit=study.load(out/'independent_audit.json');assert audit['passed'] and audit['counts']['contexts_rebuilt']==1350
    tests=ET.parse(out/'pytest.xml').getroot().findall('testsuite')
    assert sum(int(t.attrib['tests']) for t in tests)==188
    assert all(int(t.attrib['failures'])==int(t.attrib['errors'])==int(t.attrib['skipped'])==0 for t in tests)
    p1=study.load(out/'p1_current_verification.json');assert p1['instances_revalidated']==150
    files=set(out.iterdir())|set(study.source_files())|{
        study.ROOT/'scripts/load_pilot_analysis.py',study.ROOT/'scripts/verify_load_pilot.py',
        Path(__file__).resolve(),study.ROOT/'load_pilot_status.json',study.ROOT/'reports/LOAD_PILOT_REPORT.md'}
    baseline='d7e8f2c7796e7296db7ebfed7b3331259cdbd6b0'
    changes=subprocess.check_output(['git','diff','--name-only',baseline,'HEAD'],cwd=study.REPO,text=True).splitlines()
    assert all(name.startswith('experiment_runs/') for name in changes)
    study.save(out/'acceptance_manifest.json',{
        'study':'P1-training-validation-load-supplement-v1','accepted_utc':datetime.now(timezone.utc).isoformat(),
        'protocol_source_commit':manifest['source_commit'],'data_freeze_commit':'478aba8',
        'prestudy_commit':baseline,'selection':study.load(out/'summary.json')['selection'],
        'pytest_passed':188,'independent_audit_counts':audit['counts'],'old_acceptance_unchanged':True,
        'P1_current_entry_revalidated':True,'test_instances_accessed':0,'repair_methods_run':[],
        'CP_SAT_run':False,'P3_started':False,'outside_experiment_runs_changed':[],
        'file_sha256':{f.relative_to(study.REPO).as_posix():study.sha(f) for f in sorted(files) if f.is_file()}})
    print(str(out/'acceptance_manifest.json'))


if __name__=='__main__':main()
