"""Shared P5 collection. Independent replay is outside online clocks."""
import gzip,os,platform,time
import numpy as np
from p5_common import *
from isl.models import Item,canonical_json,case_to_dict
from isl.validation import validate
from isl.p5.online import execute
from isl.p5.data import cases

def audit(c,r):
    if r['validated']:
        check=validate(c.effective_instance(),tuple(Item(**p) for p in r['plan']),frozen=c.frozen,cancelled=c.event.cancelled,
            original_ids={p.task_id for p in c.reference},budget=r['B'],admissions=r['admissions_cumulative'],
            initial=tuple(Item(**p) for p in r['initial_plan']),trace=r['trace'],unchanged=tuple(Item(**p) for p in r['unchanged_outside_E']))
        assert check.feasible,check.errors
    m=r['metrics'];assert not m['online_success'] or (r['validated'] and m['service_success'] and r['total_ns']<=r['budget_ms']*1e6)
    if r['total_ns']>r['budget_ms']*1e6:assert not m['online_success'] and m['U_exec']==0

def frozen_phase(phase,extra=None):
    assert platform.system()=='Linux' and sorted(os.sched_getaffinity(0))==[0]
    sources=source_hashes()
    for p in (OUT/'subsets.json',P3/'frozen_parameters.json',P3/'search_training_statistics.json'):
        sources[p.relative_to(ROOT).as_posix()]=sha(p)
    value=dict(sources=sources,extra=extra or {},phase=phase)
    path=OUT/phase/'source_freeze.json'
    if path.exists():
        frozen=load(path);assert frozen['extra']==value['extra']
        for name,h in frozen['sources'].items():assert sha(ROOT/name)==h,('frozen source changed',name)
    else:save(path,value)
    return sha(OUT/phase/'source_freeze.json')

def warm(specs,rule,stats,phase):
    training=load(P3/'data/manifest.json')['instances'][0];cs=cases(base_data(training['id'],P3))
    records=[]
    for spec in specs:
        for i in range(20):
            c=cs[i%12][1];r=execute(c,spec,rule,stats);audit(c,r)
            records.append(dict(spec=spec,iteration=i,total_ns=r['total_ns']))
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    save(OUT/phase/'sessions'/(stamp+'.json'),dict(warmups=records,affinity=sorted(os.sched_getaffinity(0)),python=platform.python_version()))
    return stamp

def collect(phase,ident,layer,cs,specs,rule,stats,freeze,session,metadata=None):
    dest=OUT/phase/(ident+'.json.gz');receipt=dest.with_suffix('.receipt.json')
    if receipt.exists():
        old=load(receipt);assert old['sha256']==sha(dest) and old['freeze']==freeze;return old['calls']
    jobs=[(i,j) for i in range(len(cs)) for j in range(len(specs))]
    seed=int.from_bytes(__import__('hashlib').sha256((phase+ident).encode()).digest()[:8],'little')
    order=np.random.Generator(np.random.PCG64(seed)).permutation(len(jobs));temp=dest.with_suffix('.tmp')
    with gzip.open(temp,'wt',encoding='utf-8') as f:
        for k in order:
            i,j=jobs[int(k)];e,c=cs[i];spec=specs[j]
            r=execute(c,spec,rule,stats);audit(c,r)
            record=dict(base_id=ident,layer=layer,scenario=i,FR=e.get('FR'),q=e.get('q'),kind=c.event.kind,
                spec=spec,phase=phase,result=r,metadata=metadata or {},
                input_sha256=__import__('hashlib').sha256(canonical_json(case_to_dict(c)).encode()).hexdigest())
            f.write(canonical_json(record)+'\n')
    temp.replace(dest);save(receipt,dict(sha256=sha(dest),calls=len(jobs),freeze=freeze,session=session))
    return len(jobs)

def config():return load(P3/'frozen_parameters.json')['parameters']['default']['rule'],load(P3/'search_training_statistics.json')
