"""One frozen revision validation; resumable receipts and independent replay."""
import gzip,hashlib,json,platform,sys,time,zipfile
from pathlib import Path
import joblib,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count,canonical_json
from isl.p3r.repair_runtime import run_method
from isl.p3r.control_timed import controlled
from isl.p3r.sparse_control import controlled as sparse
from isl.p3r.model_io import load_model
from isl.p3r.search import run_puct,run_alns
from train_p3r import replay,load,sha
P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112'

def files_to_freeze():
    return sorted((ROOT/'src/isl').glob('*.py'))+sorted((ROOT/'src/isl/p3r').glob('*.py'))+sorted((OUT/'models').glob('*'))+[
        ROOT/'protocol/P3R_EXECUTION_V1.md',ROOT/'scripts/p3r_validate.py',ROOT/'scripts/train_p3r.py',
        OUT/'supplement_budget.json',OUT/'training_gate_linux.json',OUT/'controller_training_gate.json',
        P3/'data/manifest.json',P3/'frozen_parameters.json',P3/'search_training_statistics.json']

def main():
    assert platform.system()=='Linux'
    frozen=load(P3/'frozen_parameters.json')['parameters'];stats=load(P3/'search_training_statistics.json')
    source={p.relative_to(ROOT).as_posix():sha(p) for p in files_to_freeze()}
    freeze=OUT/'validation_freeze.json'
    if freeze.exists():assert load(freeze)['sha256']==source,'Never mix validation revisions'
    else:
        assert not (OUT/'validation').exists()
        freeze.write_text(json.dumps(dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),sha256=source,
          models=['action','deviation'],gate='difficult and remaining>=35ms; control<=3ms practical acceptance',
          selection='macro success gain >=0.005; control p95<=3ms; timeout increase<=0.005; otherwise rule',
          validation_bases=1000,events_per_base=24,methods=7,calls=168000,test_accessed=0),indent=2)+'\n')
    out=OUT/'validation';out.mkdir(exist_ok=True)
    model=load_model(P3/'models');models={m:joblib.load(OUT/'models'/(m+'.joblib')) for m in ('action','deviation')}
    rows=[r for r in load(P3/'data/manifest.json')['instances'] if r['split']=='validation']
    begun=time.perf_counter();warm=0
    for bi,row in enumerate(rows):
        dest=out/(row['id']+'.json.gz');receipt=dest.with_suffix('.receipt.json')
        if receipt.exists():assert sha(dest)==load(receipt)['sha256'];continue
        jobs=[];records=[]
        with zipfile.ZipFile(P3/'data'/(row['id']+'.zip')) as z:
            for label in ('default','N500-h0.8'):
                d=json.loads(z.read(label+'.json'))
                for e in d['events']:
                    case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    ins=case.effective_instance();tm=ins.task_map
                    baseline=sum(tm[p.task_id].utility for p in case.reference if p.task_id not in case.event.cancelled)
                    for name in ('fixed','rule','et_original','puct','alns','action','deviation'):jobs.append((label,e,case,name,baseline))
        order=np.random.Generator(np.random.PCG64(np.random.SeedSequence([row['seed'],94112]))).permutation(len(jobs))
        def execute(label,case,name):
            cfg=frozen[label]
            if name=='fixed':return run_method(case,**cfg['fixed'])
            if name=='rule':return controlled(case,cfg['rule'])
            if name=='et_original':return controlled(case,cfg['rule'],model,threshold=cfg['ET']['probability'],time_ratio=cfg['ET']['time_safety_ratio'])
            if name=='puct':return run_puct(case,temperature=cfg['PUCT']['temperature'],density_mean=stats['mean'],density_std=stats['std'])
            if name=='alns':return run_alns(case)
            return sparse(case,cfg['rule'],models[name],name)
        for j in order:
            label,e,case,name,baseline=jobs[int(j)]
            if warm<21:
                execute(label,case,name);warm+=1
            start=time.perf_counter_ns();r=execute(label,case,name);wall=time.perf_counter_ns()-start
            replay(case,r)
            records.append(dict(base_id=row['id'],layer=row['layer'],load=label,scenario=e['scenario_index'],kind=case.event.kind,
               method=name,reference_utility=baseline,result=r,call_wall_ns=wall))
        temp=dest.with_suffix('.tmp')
        with gzip.open(temp,'wt') as f:
            for r in records:f.write(canonical_json(r)+'\n')
        temp.replace(dest);receipt.write_text(json.dumps(dict(sha256=sha(dest),calls=len(records)))+'\n')
        if bi%5==0:print(json.dumps(dict(base_completed=bi+1,total=1000,new_elapsed_s=time.perf_counter()-begun)),flush=True)
    (out/'COMPLETE.json').write_text(json.dumps(dict(bases=1000,calls=168000,freeze_sha256=sha(freeze)))+'\n')
if __name__=='__main__':main()
