"""Read-only public P3-R evidence verifier; never fits or reruns validation."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/p3r/P3R-20261112'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    manifest=load(OUT/'acceptance_manifest.json');assert manifest['passed']
    for name,h in manifest['files'].items():assert sha(ROOT/name)==h,name
    freeze=load(OUT/'validation_freeze.json')
    for name,h in freeze['sha256'].items():assert sha(ROOT/name)==h,name
    bases=0;records=0
    for p in sorted((OUT/'validation').glob('*.json.gz')):
        receipt=load(p.with_suffix('.receipt.json'));assert sha(p)==receipt['sha256']
        with gzip.open(p,'rt') as f:
            rows=[json.loads(l) for l in f]
        assert len(rows)==receipt['calls']==168
        assert len({(r['load'],r['scenario'],r['method']) for r in rows})==168
        assert all(r['base_id'].startswith('P3-validation-') for r in rows)
        for row in rows:
            result=row['result'];m=result['metrics'];ontime=result['total_ns']<=50_000_000
            assert m['within_budget']==ontime
            assert m['online_success']==bool(m['applicable'] and m['service_success'] and ontime)
            assert m['U_exec']==(m['U_raw'] if m['applicable'] and m['strict_feasible'] and ontime else 0)
        bases+=1;records+=len(rows)
    assert bases==1000 and records==168000
    audit=load(OUT/'final_audit.json');assert audit['passed']
    print(json.dumps(dict(passed=True,bases=bases,records=records,files=len(manifest['files']),
        test_instances=0,note='hashes and recorded metric boundaries verified; independent replay was performed by collector')))
if __name__=='__main__':main()
