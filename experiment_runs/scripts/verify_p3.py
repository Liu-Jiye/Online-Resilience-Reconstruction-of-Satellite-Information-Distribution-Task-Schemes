"""Read-only public P3 integrity entry. Full metric replay: audit_p3_results.py."""
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
RUN=ROOT/'reports/p3/P3-20261110'

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    acceptance=load(RUN/'acceptance_manifest.json')
    assert acceptance['passed'] and acceptance['stage']=='P3'
    for name,digest in acceptance['file_sha256'].items():
        path=(REPO/name).resolve();assert path.is_relative_to(REPO.resolve())
        assert sha(path)==digest,name
    manifest=load(RUN/'data/manifest.json')
    assert manifest['complete'] and manifest['base_scenes']==5000 and manifest['paired_variants']==10000
    assert manifest['test_scenes_generated']==0
    for row in manifest['instances']:
        path=RUN/'data'/(row['id']+'.zip');assert sha(path)==row['archive_sha256']
        with zipfile.ZipFile(path) as archive:
            for name,digest in row['entries_sha256'].items():
                assert hashlib.sha256(archive.read(name)).hexdigest()==digest
    expected=dict(labels=(4000,80000),grid=(1000,600000),rules=(1000,72000),et=(1000,144000),search=(1000,96000))
    for mode,(bases,calls) in expected.items():
        folder=RUN/mode;receipts=list(folder.glob('*.receipt.json'))
        assert len(receipts)==bases
        assert len(list(folder.glob('*.json.gz')))==bases
        assert sum(load(path)['calls'] for path in receipts)==calls
        for path in receipts:
            data=path.with_name(path.name.removesuffix('.receipt.json')+'.gz')
            assert sha(data)==load(path)['sha256'],str(data)
        for name,digest in load(folder/'source_freeze.json').items():
            assert sha(ROOT/name)==digest,name
    audit=load(RUN/'final_audit.json')
    assert audit['passed'] and audit['total_records']==992000 and audit['additional_sample_replays']==10000
    parameters=load(RUN/'frozen_parameters.json')
    assert parameters['test_instances']==0 and not parameters['P4_started']
    assert parameters['rule_adjustment_rounds']==1
    print(json.dumps(dict(passed=True,base_scenes=5000,paired_variants=10000,records=992000,
                         acceptance_files=len(acceptance['file_sha256']),test_instances=0,P4_started=False)))

if __name__=='__main__':main()
