"""Full feature and single-head controller timing on fixed training events only."""
from collections import defaultdict
import gzip,json,platform,sys,zipfile
from pathlib import Path
import joblib,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count
from isl.p3r.sparse_control import controlled
from train_p3r import replay,sha,load
P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112'
def main():
    assert platform.system()=='Linux'
    ids=load(OUT/'training_diagnostic_ids.json');frozen=load(P3/'frozen_parameters.json')['parameters']
    models={m:joblib.load(OUT/'models'/(m+'.joblib')) for m in ('action','deviation')}
    records=[];groups=defaultdict(list)
    for bi,id in enumerate(ids):
        with zipfile.ZipFile(P3/'data'/(id+'.zip')) as z:
            for label in ('default','N500-h0.8'):
                d=json.loads(z.read(label+'.json'))
                for e in d['events']:
                    case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    for mode in ('action','deviation'):
                        r=controlled(case,frozen[label]['rule'],models[mode],mode);replay(case,r)
                        record=dict(base_id=id,load=label,mode=mode,scenario=e['scenario_index'],
                           control_ns=r['timings_ns']['control_ns'],total_ns=r['total_ns'],invoked=r['controller_invoked'],timeout=r['status']=='timeout')
                        records.append(record);groups[label,mode].append(record)
        if bi%10==0:print('controller training gate',bi+1,'/60',flush=True)
    with gzip.open(OUT/'controller_training_gate.json.gz','wt') as f:
        for r in records:f.write(json.dumps(r)+'\n')
    report=dict(training_bases=60,calls=len(records),source_sha256={p.name:sha(p) for p in (ROOT/'src/isl/p3r').glob('*.py')},groups={})
    for (label,mode),rs in groups.items():
        p95=float(np.percentile([r['control_ns'] for r in rs],95)/1e6)
        report['groups'][label+'/'+mode]=dict(n=len(rs),control_p95_ms=p95,control_target_pass=p95<=3,
            invoked=sum(r['invoked'] for r in rs),timeouts=sum(r['timeout'] for r in rs),total_p95_ms=float(np.percentile([r['total_ns'] for r in rs],95)/1e6))
    (OUT/'controller_training_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
if __name__=='__main__':main()
