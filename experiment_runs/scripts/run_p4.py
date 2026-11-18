"""Single frozen P4 test pass and separately recorded timing repetitions."""
import gzip,json,os,platform,time,zipfile
import numpy as np
from p4_common import *
from isl.models import case_from_dict,frozen_count,canonical_json
from isl.p3r.repair_runtime import run_method
from isl.p3r.control_timed import controlled
from isl.p3r.search import run_puct,run_alns
from isl.p4.online import enforce_wall,run_cp
from train_p3r import replay

def cases(d):
    return [(e,case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))) for e in d['events']]
def main():
    assert platform.system()=='Linux' and list(os.sched_getaffinity(0))==[0]
    assert load(OUT/'training_preflight.json')['passed']
    assert load(OUT/'historical_integrity.json')['all_unchanged']
    for p,h in load(OUT/'data/manifest.json')['source_sha256'].items():assert sha(ROOT/p)==h,('generation changed',p)
    cfg=load(P3/'frozen_parameters.json')['parameters']['default'];stats=load(P3/'search_training_statistics.json')
    source=sources();source['protocol/P4_STATISTICS_V1.md']=sha(ROOT/'protocol/P4_STATISTICS_V1.md')
    source['reports/p4/P4-20261117/data/manifest.json']=sha(OUT/'data/manifest.json')
    source['reports/p4/P4-20261117/data/timing_subset.json']=sha(OUT/'data/timing_subset.json')
    for name in ('training_preflight.json','historical_integrity.json','environment.json'):
        source[(OUT/name).relative_to(ROOT).as_posix()]=sha(OUT/name)
    freeze=OUT/'test_freeze.json'
    if freeze.exists():assert load(freeze)['sha256']==source,'STOP: test source changed'
    else:save(freeze,dict(sha256=source,created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),methods=METHODS,main_calls=192000,timing_calls=384000))
    def execute(c,name,seed):
        start=time.perf_counter_ns()
        if name in ('Minimal-Repair','Frozen-Greedy','Fixed-PALR'):r=run_method(c,method=name)
        elif name=='Validation-Best-Fixed':r=run_method(c,**cfg['fixed'])
        elif name=='Rule-PALR':r=controlled(c,cfg['rule'])
        elif name=='PUCT-ISL':r=run_puct(c,temperature=cfg['PUCT']['temperature'],density_mean=stats['mean'],density_std=stats['std'],seed=seed)
        elif name=='ALNS-ISL':r=run_alns(c,seed=seed)
        else:r=run_cp(c,seed=seed)
        wall=time.perf_counter_ns()-start
        return enforce_wall(r,wall)
    jobspec=[(m,s) for m in METHODS for s in (SEEDS if m in ('PUCT-ISL','ALNS-ISL') else [11])]
    # Every adapter/seed gets 20 warmups on training input, before any formal test.
    training=load(P3/'data/manifest.json')['instances'][0]
    with zipfile.ZipFile(P3/'data'/(training['id']+'.zip')) as z:td=json.loads(z.read('default.json'))
    train_cases=cases(td);warm=[]
    for m,s in jobspec:
        for i in range(20):
            r=execute(train_cases[i%12][1],m,s);warm.append(dict(method=m,seed=s,iteration=i,total_ns=r['total_ns']))
    session=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());save(OUT/'sessions'/f'{session}.json',dict(warmups=warm,affinity=sorted(os.sched_getaffinity(0)),python=platform.python_version(),freeze_sha256=sha(freeze)))
    manifest=load(OUT/'data/manifest.json');subset=set(load(OUT/'data/timing_subset.json')['base_ids'])
    for phase in ('main','timing'):
        out=OUT/phase;out.mkdir(exist_ok=True);start_phase=time.perf_counter()
        rows=[r for r in manifest['instances'] if phase=='main' or r['id'] in subset]
        for bi,row in enumerate(rows):
            dest=out/(row['id']+'.json.gz');receipt=out/(row['id']+'.receipt.json')
            if receipt.exists():assert sha(dest)==load(receipt)['sha256'];continue
            path=OUT/'data'/(row['id']+'.zip');assert sha(path)==row['archive_sha256']
            with zipfile.ZipFile(path) as z:d=json.loads(z.read('default.json'))
            cs=cases(d);jobs=[(i,m,s,rep) for rep in range(1 if phase=='main' else 20) for i in range(12) for m,s in jobspec]
            rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([row['seed'],94017,phase=='timing'])))
            order=rng.permutation(len(jobs));temp=dest.with_suffix('.tmp');counts=0
            with gzip.open(temp,'wt',encoding='utf-8') as f:
                for j in order:
                    i,m,s,rep=jobs[int(j)];e,c=cs[i]
                    r=execute(c,m,s);replay(c,r)
                    record=dict(base_id=row['id'],layer=row['layer'],load='default',scenario=i,kind=c.event.kind,
                                FR=e['FR'],q=e['q'],method=m,search_seed=s,repeat=rep,phase=phase,
                                input_sha256=row['payload_sha256'],result=r)
                    f.write(canonical_json(record)+'\n');counts+=1
            temp.replace(dest);save(receipt,dict(sha256=sha(dest),calls=counts,freeze_sha256=sha(freeze),session=session))
            if bi%5==0:print(json.dumps(dict(phase=phase,completed=bi+1,total=len(rows),elapsed_s=time.perf_counter()-start_phase)),flush=True)
        save(out/'COMPLETE.json',dict(bases=len(rows),calls=len(rows)*192*(1 if phase=='main' else 20),freeze_sha256=sha(freeze)))
    print('P4 formal and timing runs complete',flush=True)
if __name__=='__main__':main()
