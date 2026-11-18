"""Unprofiled training-only timing; Windows runs are development evidence only."""
from collections import defaultdict
import gzip,hashlib,json,platform,sys,time,zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count
from isl.p3.repair_runtime import run_method as old
from isl.p3r.repair_runtime import run_method as revised
P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112'

def main():
    ids=json.loads((OUT/'training_diagnostic_ids.json').read_text())
    manifest=json.loads((P3/'data/manifest.json').read_text())
    rows=[r for r in manifest['instances'] if r['id'] in ids]
    assert len(rows)==60 and all(r['split']=='train' for r in rows)
    formal=platform.system()=='Linux'
    target=OUT/('training_gate_linux' if formal else 'training_gate_windows_development')
    records=[];groups=defaultdict(list);eq=0
    # Whole-run wall and every component retained; no profiler is active.
    for bi,row in enumerate(rows):
        with zipfile.ZipFile(P3/'data'/(row['id']+'.zip')) as z:
            for load in ('default','N500-h0.8'):
                d=json.loads(z.read(load+'.json'))
                for e in d['events']:
                    case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    for w,B in ((3,0),(5,2)):
                        if bi%10==0:
                            a=old(case,w=w,B=B,clock=lambda:0);b=revised(case,w=w,B=B,clock=lambda:0)
                            for k in a:
                                if k!='version': assert a[k]==b[k],(row['id'],load,e['scenario_index'],k)
                            eq+=1
                        rng=np.random.Generator(np.random.PCG64(row['seed']+e['scenario_index']+B))
                        for name in rng.permutation(['old','revised']):
                            start=time.perf_counter_ns();r=(old if name=='old' else revised)(case,w=w,B=B)
                            wall=time.perf_counter_ns()-start
                            record=dict(base_id=row['id'],load=load,scenario=e['scenario_index'],method=str(name),B=B,w=w,
                                        total_ns=r['total_ns'],call_wall_ns=wall,timings_ns=r['timings_ns'],status=r['status'])
                            records.append(record);groups[str(name),load,B].append(record)
        if bi%5==0: print('training timing',bi+1,'/60',flush=True)
    with gzip.open(target.with_suffix('.json.gz'),'wt') as f:
        for r in records:f.write(json.dumps(r)+'\n')
    result=dict(environment=dict(system=platform.system(),python=sys.version),formal_linux_gate=formal,
                profiled=False,training_bases=60,calls=len(records),exact_behavior_checks=eq,
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/isl/p3r').glob('*.py')},groups={})
    for (name,load,B),rs in groups.items():
        result['groups'][f'{name}/{load}/B{B}']=dict(n=len(rs),timeouts=sum(r['status']=='timeout' for r in rs),
            response_p50_p95_p99_ms=(np.percentile([r['total_ns'] for r in rs],[50,95,99])/1e6).tolist(),
            baseline_p99_ms=float(np.percentile([r['timings_ns']['input_and_baseline_ns']+r['timings_ns']['accepted_validation_ns'] for r in rs],99)/1e6))
    target.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
