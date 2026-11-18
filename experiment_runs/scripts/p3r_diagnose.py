"""Frozen training-only P3-R diagnostic, exact checker and behavior comparison."""
from collections import defaultdict
from dataclasses import replace
import cProfile,gzip,hashlib,json,pstats,sys,time,zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count
from isl.p3.repair_runtime import run_method as old
from isl.p3r.repair_runtime import run_method as new
from isl.p3.validation_indexed import validate as old_check
from isl.p3r.validation_indexed import validate as new_check
P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112';OUT.mkdir(parents=True,exist_ok=True)

def load(p):return json.loads(p.read_text())
def main():
    rows=[]
    for layer in ('D1','D2-S','D2-O'):
        rows += [r for r in load(P3/'data/manifest.json')['instances'] if r['split']=='train' and r['layer']==layer][:20]
    (OUT/'training_diagnostic_ids.json').write_text(json.dumps([r['id'] for r in rows],indent=2)+'\n')
    groups=defaultdict(list);records=[];equivalence=0;checks=0;prof=cProfile.Profile()
    for bi,row in enumerate(rows):
        with zipfile.ZipFile(P3/'data'/(row['id']+'.zip')) as z:
            for label in ('default','N500-h0.8'):
                d=json.loads(z.read(label+'.json'))
                for e in d['events']:
                    case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    # Valid and malformed cases compare every diagnostic field.
                    plans=[case.reference,tuple(reversed(case.reference)),case.reference+case.reference[:1]]
                    if case.reference:plans += [(replace(case.reference[0],end=case.reference[0].end+1),)+case.reference[1:]]
                    for plan in plans:
                        a=old_check(case.base,plan,frozen=case.frozen);b=new_check(case.base,plan,frozen=case.frozen)
                        assert a.to_dict()==b.to_dict();checks+=1
                    if bi%10==0:
                        a=old(case,w=5,B=2,clock=lambda:0);b=new(case,w=5,B=2,clock=lambda:0)
                        for key in ('plan','initial_plan','trace','admissions_cumulative','forced_removed','validation','editable_indices','candidate_spans'):
                            assert a[key]==b[key],(row['id'],label,e['scenario_index'],key)
                        equivalence+=1
                    # Profile only training and retain both failures and late calls.
                    for name,method in (('old',old),('revised',new)):
                        if name=='revised':prof.enable()
                        r=method(case,w=5,B=2)
                        if name=='revised':prof.disable()
                        # Profile overhead is not used for formal 50ms selection.
                        records.append(dict(base=row['id'],load=label,scenario=e['scenario_index'],method=name,total_ns=r['total_ns'],timings_ns=r['timings_ns'],status=r['status']))
                        groups[name,label].append(r)
        print('training diagnostic',bi+1,'/60',flush=True)
    prof.dump_stats(str(OUT/'training_profile.prof'))
    with (OUT/'training_profile.txt').open('w') as f:pstats.Stats(prof,stream=f).sort_stats('cumtime').print_stats(35)
    with gzip.open(OUT/'training_diagnostic.json.gz','wt') as f:
        for r in records:f.write(json.dumps(r)+'\n')
    report=dict(training_bases=60,checker_field_equivalence_checks=checks,no_deadline_behavior_cases=equivalence,passed=True,profile_overhead_in_revised=True,
                groups={name+'/'+label:dict(n=len(rs),timeouts=sum(r['status']=='timeout' for r in rs),p50_p95_p99_ms=(np.percentile([r['total_ns'] for r in rs],[50,95,99])/1e6).tolist()) for (name,label),rs in groups.items()})
    (OUT/'diagnostic_acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
if __name__=='__main__':main()
