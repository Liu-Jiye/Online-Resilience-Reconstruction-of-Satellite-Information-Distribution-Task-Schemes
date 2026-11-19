"""P6 independent raw deadline/metric/failure audit, with transparent replay scope."""
import gzip,zipfile
from collections import Counter
import pandas as pd
from p6_common import *
from isl.models import Item,case_from_dict,frozen_count,canonical_json
from isl.metrics import raw_metrics
from isl.validation import validate

def cases_for(name,ident,record):
    if name=='continuous':return None
    custom=record.get('metadata',{}).get('input_path')
    if custom:
        with gzip.open(SOURCE/custom,'rt',encoding='utf-8') as f:d=json.load(f)
        if 'cases' in d:return [case_from_dict(x['case']) for x in d['cases']]
    else:
        stage=SOURCE/'reports/p3/P3-20261110' if name=='calibration' else P4
        with zipfile.ZipFile(stage/'data'/(ident+'.zip')) as z:d=json.loads(z.read('default.json'))
    return [case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR']))) for e in d['events']]

def audit(name,partition=None,partitions=4):
    directory=P4/'main' if name=='P4' else P5/name
    output=OUT/'raw_audit'/name;output.mkdir(parents=True,exist_ok=True)
    expected=192000 if name=='P4' else load(P5/name/'COMPLETE.json')['calls']
    paths=sorted(directory.glob('*.json.gz'))
    if partition is not None:
        paths=paths[partition::partitions]
        expected=sum(load(p.parent/(p.name.removesuffix('.json.gz')+('.receipt.json' if name=='P4' else '.json.receipt.json')))['calls'] for p in paths)
    totals=Counter();shards={};examples=[]
    for bi,path in enumerate(paths):
        ident=path.name.removesuffix('.json.gz');receipt=load(path.parent/(ident+('.receipt.json' if name=='P4' else '.json.receipt.json')))
        assert sha(path)==receipt['sha256'],path
        shards[path.relative_to(SOURCE).as_posix()]=receipt['sha256']
        cs=None;seen=set();counts=Counter();failure_rows=[];sampled=set()
        with gzip.open(path,'rt',encoding='utf-8') as f:
            for line in f:
                rec=json.loads(line);r=rec['result'];m=r['metrics'];spec=rec.get('spec',{})
                scenario=rec.get('scenario',rec.get('step'))
                method=rec.get('method',spec.get('name'));seed=rec.get('search_seed',spec.get('seed',11))
                label=method
                if 'budget_ms' in spec:label+='@'+str(spec['budget_ms'])+'ms'
                if 'simulations' in spec:label+='@sim'+str(spec['simulations'])
                key=(scenario,canonical_json(spec),method,seed);assert key not in seen;seen.add(key)
                if name=='continuous':c=case_from_dict(rec['case'])
                else:
                    if cs is None:cs=cases_for(name,ident,rec)
                    c=cs[scenario]
                plan=tuple(Item(**x) for x in r['plan']);raw=raw_metrics(c,plan,r.get('forced_removed',[]))
                for k,v in raw.items():assert m[k]==v,(name,ident,key,k,m[k],v)
                app=bool(c.event.applicable);feasible=bool(r['validated']);service=feasible and (not c.event.urgent or any(p.task_id==c.event.urgent.id for p in plan))
                ontime=r['total_ns']<=r['budget_ms']*1e6;online=app and service and ontime;valid=app and feasible and ontime
                for k,v in dict(applicable=app,strict_feasible=feasible,service_success=service,online_success=online,valid_output=valid,U_exec=raw['U_raw'] if valid else 0).items():assert m[k]==v,(name,ident,key,k)
                physical=None;errors=[]
                sampled_valid=feasible and (label,seed) not in sampled
                if not feasible or sampled_valid:
                    physical=validate(c.effective_instance(),plan,frozen=c.frozen,cancelled=c.event.cancelled)
                    counts['physical_plans_newly_checked']+=1
                    if sampled_valid:
                        full=validate(c.effective_instance(),plan,frozen=c.frozen,cancelled=c.event.cancelled,
                            original_ids={p.task_id for p in c.reference},budget=r['B'],admissions=r['admissions_cumulative'],
                            initial=tuple(Item(**x) for x in r['initial_plan']),trace=r['trace'],
                            unchanged=tuple(Item(**x) for x in r.get('unchanged_outside_E',[])))
                        assert full.feasible,(name,ident,key,full.errors)
                        sampled.add((label,seed));counts['validated_trace_samples_checked']+=1
                    errors=list(physical.errors)
                counts.update(calls=1,applicable=app,online_success=online,timeouts=app and not ontime,not_validated=app and not feasible,unserved=app and feasible and not service)
                counts['metric_fields_recomputed']+=len(raw)+6
                if app and not online:
                    primary='timeout' if not ontime else 'not_validated' if not feasible else 'urgent_unserved'
                    counts['exclusive_'+primary]+=1
                kind=c.event.kind
                row=dict(base_id=ident,root_id=rec.get('metadata',{}).get('root_id',ident),layer=rec['layer'],scenario=scenario,label=label,seed=seed,
                    kind=kind,applicable=int(app),online_success=int(online),strict_feasible=int(feasible),valid_output=int(valid),
                    timeout=int(not ontime),service_success=int(service),total_ms=r['total_ns']/1e6,status=r['status'],
                    input_sha256=rec.get('input_sha256','trajectory-owned-input'),U_exec=m['U_exec'],U_raw=raw['U_raw'],
                    physical_rechecked=physical is not None,physical_feasible=physical.feasible if physical else '',errors='|'.join(errors),
                    primary_failure='' if online or not app else primary,
                    witness_service_plan=int(feasible and service and kind=='urgent_insertion'),
                    N_drop=raw['N_drop'],N_add=raw['N_add'],M_all=raw['M_all'])
                failure_rows.append(row)
                category='cancellation_success' if kind=='cancellation' and online else 'urgent_failure' if kind=='urgent_insertion' and app and not online else 'window_or_receiver_counterexample' if physical and (physical.window_ids or physical.resource_pairs) else None
                if category and category not in {x['category'] for x in examples}:
                    from dataclasses import asdict
                    examples.append(dict(category=category,phase=name,source=path.relative_to(SOURCE).as_posix(),row=row,
                        case=asdict(c),result=r,new_check=None if physical is None else physical.to_dict()))
        assert counts['calls']==receipt['calls']
        pd.DataFrame(failure_rows).to_csv(output/(ident+'.csv.gz'),index=False,compression='gzip')
        totals.update(counts)
        if bi%50==0:print(json.dumps(dict(audit_phase=name,shards=bi+1,calls=totals['calls'])),flush=True)
    assert totals['calls']==expected,(name,totals['calls'],expected)
    assert sum(totals['exclusive_'+x] for x in ['timeout','not_validated','urgent_unserved'])==totals['applicable']-totals['online_success']
    suffix='' if partition is None else '.part-'+str(partition)
    save(output/('COMPLETE'+suffix+'.json'),dict(passed=True,counts=dict(totals),raw_sha256=shards,
        recheck_scope='All raw metrics and scoring recomputed; every unvalidated plan and first validated output per method/seed/base newly checked; prior full original-checker replay reused with immutable hashes.'))
    save(output/('examples'+suffix+'.json'),examples)
    print(json.dumps(dict(phase_complete=name,**dict(totals))),flush=True)

def main():
    for name in ['P4']+PHASES:
        if os.environ.get('P6_SKIP_PHASE')==name:continue
        if not (OUT/'raw_audit'/name/'COMPLETE.json').exists():audit(name)
    if all((OUT/'raw_audit'/n/'COMPLETE.json').exists() for n in ['P4']+PHASES):
        save(OUT/'raw_audit/COMPLETE.json',dict(passed=True,phases={n:load(OUT/'raw_audit'/n/'COMPLETE.json')['counts'] for n in ['P4']+PHASES}))

if __name__=='__main__':main()
