"""Incremental independent replay of sealed P5 raw shards, outside online timing."""
import gzip,csv,time,os
from collections import Counter
from p5_common import *
from isl.models import Item,canonical_json,case_from_dict,case_to_dict
from isl.p5.data import cases
from isl.validation import validate
from isl.metrics import raw_metrics

PHASES=['ablations','calibration','mechanisms','simulations','upgrades','single_factor','windows','anomalies','references','transfer','continuous']

def read_gzip(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)

def get_cases(phase,ident,meta):
    if meta.get('input_path'):
        d=read_gzip(ROOT/meta['input_path'])
        return [case_from_dict(x['case']) for x in d['cases']] if 'cases' in d else [c for _,c in cases(d)]
    return [c for _,c in cases(base_data(ident,P3 if phase=='calibration' else P4))]

def verify(phase,path):
    ident=path.name.removesuffix('.json.gz');receipt=load(path.with_suffix('.receipt.json'))
    output=OUT/'audit'/phase/(ident+'.json');flat=output.with_suffix('.csv.gz')
    if output.exists():
        prior=load(output);assert prior['raw_sha256']==receipt['sha256'];return False
    assert sha(path)==receipt['sha256']
    freeze=OUT/phase/'source_freeze.json';assert sha(freeze)==receipt['freeze']
    for name,h in load(freeze)['sources'].items():assert sha(ROOT/name)==h,('frozen source changed',name)
    seen=set();counts=Counter();rows=[];cs=None
    with gzip.open(path,'rt') as f:
        for line in f:
            record=json.loads(line);r=record['result'];m=r['metrics'];spec=record['spec'];meta=record.get('metadata',{})
            if phase=='continuous':c=case_from_dict(record['case']);scenario=record['step']
            else:
                if cs is None:cs=get_cases(phase,ident,meta)
                scenario=record['scenario'];c=cs[scenario]
                assert record['input_sha256']==hashlib.sha256(canonical_json(case_to_dict(c)).encode()).hexdigest()
            key=(scenario,canonical_json(spec));assert key not in seen;seen.add(key)
            plan=tuple(Item(**p) for p in r['plan']);forced=r.get('forced_removed',[])
            raw=raw_metrics(c,plan,forced)
            for k,v in raw.items():assert m[k]==v,(phase,ident,spec,k,m[k],v)
            physical=validate(c.effective_instance(),plan,frozen=c.frozen,cancelled=c.event.cancelled)
            if r['validated']:
                check=validate(c.effective_instance(),plan,frozen=c.frozen,cancelled=c.event.cancelled,
                    original_ids={p.task_id for p in c.reference},budget=r['B'],admissions=r['admissions_cumulative'],
                    initial=tuple(Item(**p) for p in r['initial_plan']),trace=r['trace'],
                    unchanged=tuple(Item(**p) for p in r['unchanged_outside_E']))
                assert check.feasible,(phase,ident,spec,check.errors);counts['validated_replays']+=1
            feasible=bool(r['validated']);service=feasible and (not c.event.urgent or any(p.task_id==c.event.urgent.id for p in plan));ontime=r['total_ns']<=r['budget_ms']*1e6
            assert m['strict_feasible']==feasible and m['service_success']==service
            assert m['online_success']==bool(c.event.applicable and service and ontime)
            assert m['valid_output']==bool(c.event.applicable and feasible and ontime)
            assert m['U_exec']==(raw['U_raw'] if c.event.applicable and feasible and ontime else 0)
            assert r['B']<=5 and (not feasible or r['admissions_cumulative']<=r['B'])
            cfg={k:v for k,v in spec.items() if k not in ('seed','spec_id')}
            label=spec['name']
            if 'budget_ms' in spec:label+='@'+str(spec['budget_ms'])+'ms'
            if 'simulations' in spec:label+='@sim'+str(spec['simulations'])
            root=meta.get('root_id',ident)
            row=dict(phase=phase,base_id=ident,root_id=root,layer=record['layer'],scenario=scenario,kind=c.event.kind,
                FR=record.get('FR',''),q=record.get('q',''),method=spec['name'],config=canonical_json(cfg),label=label,
                seed=spec.get('seed',11),spec_id=spec.get('spec_id',''),factor=meta.get('factor',''),value=meta.get('value',''),
                variant=meta.get('variant',meta.get('type','')),budget_ms=r['budget_ms'],w=r.get('w',''),B=r['B'],
                status=r['status'],validated=int(feasible),physical_plan_feasible=int(physical.feasible),
                physical_window_violations=len(physical.window_ids),physical_resource_pairs=len(physical.resource_pairs),
                physical_frozen_violations=physical.frozen_violations,total_ms=r['total_ns']/1e6,
                kernel_ms=r.get('kernel_total_ns',r['total_ns'])/1e6,timeout=int(not ontime),
                **{k:int(m[k]) for k in ('applicable','strict_feasible','service_success','online_success','valid_output')},
                **{k:m[k] for k in raw},
                upgrade_triggered=int(r.get('upgrade_triggered',False)),first_phase_ms=r.get('first_phase_ns',0)/1e6,
                first_phase_over_10ms=int(r.get('first_phase_over_10ms',False)),search_phase_started=int(r.get('search_phase_started',False)),
                reference_count=len(c.reference),reference_utility=sum(c.effective_instance().task_map[p.task_id].utility for p in c.reference if p.task_id not in c.event.cancelled),
                task_count=len(c.base.tasks),frozen_count=c.frozen_count,
                U_exec=m['U_exec'],U_conditional=m['U_raw'] if m['valid_output'] else '')
            for field in ('simulations','iterations','completed_simulations','simulations_completed','cooperative_deadline_reached'):
                row['search_'+field]=r.get('search_stats',{}).get(field,r.get(field,''))
            rows.append(row);counts['calls']+=1;counts['applicable']+=m['applicable'];counts['online_success']+=m['online_success'];counts['timeouts']+=not ontime
    assert counts['calls']==receipt['calls']
    output.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(flat,'wt',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    save(output,dict(raw_sha256=receipt['sha256'],freeze=receipt['freeze'],flat_sha256=sha(flat),counts=counts,independent_checker='original isl.validation, including full trace for validated outputs'))
    return True

def main():
    watch=os.environ.get('P5_AUDIT_WATCH')=='1';total=0
    worker=int(os.environ.get('P5_AUDIT_WORKER','0'));workers=int(os.environ.get('P5_AUDIT_WORKERS','1'))
    while True:
        added=0
        for phase in PHASES:
            for receipt in sorted((OUT/phase).glob('*.receipt.json')):
                bucket=int.from_bytes(hashlib.sha256((phase+receipt.name).encode()).digest()[:8],'little')%workers
                if bucket!=worker:continue
                path=receipt.with_name(receipt.name.removesuffix('.receipt.json')+'.gz')
                added+=verify(phase,path)
        total+=added
        print(json.dumps(dict(audit_new_shards=added,audited_this_session=total)),flush=True)
        done=(OUT/'pipeline/COMPLETE.json').exists()
        if done or not watch:break
        time.sleep(30)
    counts={}
    for phase in PHASES:
        c=Counter()
        for p in (OUT/'audit'/phase).glob('*.json'):c.update(load(p)['counts'])
        counts[phase]=dict(c)
    name='final-replay-progress.json' if os.environ.get('P5_AUDIT_FINAL')=='1' else 'progress-worker'+str(worker)+'.json'
    save(OUT/'audit'/name,dict(phases=counts,pipeline_complete=done,worker=worker,workers=workers))

if __name__=='__main__':main()
