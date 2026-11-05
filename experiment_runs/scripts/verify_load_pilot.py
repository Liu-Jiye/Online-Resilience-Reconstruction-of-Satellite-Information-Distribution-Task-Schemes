"""Read-only acceptance checks; optional full replay uses a temporary copy."""
import argparse,hashlib,json,shutil,tempfile
from pathlib import Path
import load_pilot_study as study


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--full',action='store_true');args=parser.parse_args()
    out=Path(args.folder).resolve();acceptance=study.load(out/'acceptance_manifest.json')
    for name,expected in acceptance['file_sha256'].items():
        assert study.sha(study.REPO/name)==expected,name
    manifest=study.load(out/'manifest.json')
    for name,expected in manifest['source_sha256'].items():assert study.sha(study.REPO/name)==expected,name
    for name,expected in manifest['artifact_sha256'].items():assert study.sha(out/name)==expected,name
    assert study.old_evidence()==study.load(out/'prior_acceptance.json')
    receipt=study.load(out/'independent_audit.json');assert receipt['passed']
    summary=study.load(out/'summary.json');assert summary['selection']==acceptance['selection']
    assert summary['attempted_contexts']==1350 and summary['default_reproduced']==150
    if args.full:
        # All mutations are confined to this automatically cleaned work copy.
        with tempfile.TemporaryDirectory(prefix='load-pilot-replay-',dir=study.REPO.parent) as temporary:
            target=Path(temporary)
            for name in manifest['artifact_sha256']:shutil.copy2(out/name,target/name)
            shutil.copy2(out/'manifest.json',target/'manifest.json')
            study.audit(target)
            replay=study.load(target/'independent_audit.json')
            assert replay['counts']==receipt['counts']
    print(json.dumps({'passed':True,'full_replay':args.full,'file_hashes_checked':len(acceptance['file_sha256']),
        'counts':receipt['counts'],'selection':summary['selection'],'P3_started':False,'test_instances':0},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
