"""Additive P2-C preparation, execution, independent audit and reporting."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np
from ortools.sat.python import cp_model,cp_model_helper

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_to_dict,case_from_dict,canonical_json,Item
from isl.p2c import construct,GROUPS
from isl import repair,repair_v2,p2_exact,p2_exact_v2
from isl.metrics import raw_metrics
from isl.validation import validate
from run_p2 import pin_process
from run_p0 import environment

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def sources():
    return sorted(set(list((ROOT/'src').rglob('*.py'))+list((ROOT/'tests').glob('*.py'))+[Path(__file__),ROOT/'scripts/run_p0.py',ROOT/'scripts/run_p2.py',ROOT/'protocol/P2C_CONTRACT.md',ROOT/'environment/requirements-p2.lock.txt']))
def freeze(folder,extra=None):
    save(folder/'manifest.json',{'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in sources()},
        'artifact_sha256':{p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name!='manifest.json'},**(extra or {})})
def check_manifest(folder):
    m=load(folder/'manifest.json')
    for name,h in m['source_sha256'].items():assert sha(REPO/name)==h,name
    for name,h in m['artifact_sha256'].items():assert sha(folder/name)==h,name
    return m
def old_hashes():
    accepted=[]
    for name in ('P2-20261105T114327Z','P2-urgent-diagnostic-20261105T122345Z','P2-urgent-supplement-20261105T123731Z'):
        p=ROOT/'reports/p2'/name/'acceptance_manifest.json'
        for rel,h in load(p)['file_sha256'].items():assert sha(REPO/rel)==h,rel
        accepted.append({'path':p.relative_to(REPO).as_posix(),'sha256':sha(p)})
    return accepted

def independent_starts(case,w):
    """Integer enumeration independent of the CP construction and generator."""
    ctx=p2_exact_v2.context(case,w,2);ins=case.effective_instance();u=case.event.urgent
    fixed_ids={p.task_id for p in ctx['unchanged']}|{p.task_id for p in case.frozen}
    physical=set()
    for c in ins.contacts:
        if (c.sender,c.receiver)==(u.sender,u.receiver):
            physical.update(range(max(u.release,c.start),min(u.deadline,c.end)-u.duration+1))
    calendar=[];fixed=[];usable=[]
    for a in sorted(physical):
        b=a+u.duration
        if any(z.resource in (u.sender,u.receiver) and a<z.end and z.start<b for z in ins.calendar):calendar.append(a);continue
        conflicts={p.task_id for p in case.reference if {p.sender,p.receiver}&{u.sender,u.receiver} and a<p.end and p.start<b}
        if conflicts&fixed_ids:fixed.append(a);continue
        usable.append({'start':a,'drop_ids':sorted(conflicts)})
    return {'physical_starts':sorted(physical),'calendar_blocked':calendar,'fixed_blocked':fixed,'usable':usable,
            'min_drops':min((len(z['drop_ids']) for z in usable),default=None)}

def probe_model(case,w,cap):
    ctx=p2_exact_v2.context(case,w,2)
    model,present,starts,ends,weights,alts=p2_exact_v2.build_model(case,ctx,True)
    if cap is not None:model.add(sum(1-present[p.task_id] for p in case.reference)<=cap)
    # Satisfiability probe: no optimization is needed to certify the category.
    model.clear_objective()
    return model,present,starts,ends,ctx

def probe(case,w,cap):
    model,present,starts,ends,ctx=probe_model(case,w,cap)
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.max_time_in_seconds=30;solver.parameters.random_seed=11
    status=solver.solve(model);name=solver.status_name(status)
    plan=None
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        plan=sorted([asdict(Item(t.id,t.sender,t.receiver,solver.value(starts[t.id]),solver.value(ends[t.id]))) for t in ctx['instance'].tasks if solver.value(present[t.id])],key=lambda p:(p['start'],p['task_id']))
        p2_exact_v2.witness(case,ctx,tuple(Item(**p) for p in plan))
    return {'w':w,'cap':cap,'status':name,'plan':plan,'solver_wall_s':solver.wall_time,'parameters':str(solver.parameters)}, {'model_pbtxt':str(model.proto),'response_pbtxt':str(solver.response_proto)}

def put(z,prefix,artifacts):
    for k,v in artifacts.items():z.writestr(prefix+k+'.txt',v)

def prepare():
    folder=ROOT/'reports/p2/P2C-inputs-v1';folder.mkdir(exist_ok=False)
    save(folder/'prior_acceptance.json',old_hashes())
    env=environment();env.update(actual_affinity=pin_process(),scope='P2C category certification');save(folder/'environment.json',env)
    attempts=[];entries=[];idx=0
    with zipfile.ZipFile(folder/'cases.zip','w',zipfile.ZIP_DEFLATED) as cases,zipfile.ZipFile(folder/'category_models.zip','w',zipfile.ZIP_DEFLATED) as proofs:
        for group,n in GROUPS:
            for ordinal in range(n):
                meta={'index':idx,'group':group,'ordinal':ordinal,'seed':210000+idx}
                try:
                    case,meta=construct(idx,group,ordinal);entry=f'case-{idx:03d}.json';labels={str(w):independent_starts(case,w) for w in (5,20)}
                    expected={'direct':0,'single':1,'double':2,'triple':3,'outside':None,'hard':None}[group]
                    assert labels['5']['min_drops']==expected
                    if group=='outside':assert labels['20']['min_drops']==1
                    if group=='hard':assert labels['20']['min_drops'] is None
                    specs=([(5,0,True)] if group=='direct' else
                           [(5,expected-1,False),(5,expected,True)] if group in ('single','double','triple') else
                           [(5,None,False),(20,0,False),(20,1,True)] if group=='outside' else [(20,None,False)])
                    certified=[]
                    for pi,(w,cap,feasible) in enumerate(specs):
                        result,artifact=probe(case,w,cap);put(proofs,f'{entry}/probe-{pi}/',artifact)
                        assert result['status'] in ('OPTIMAL','FEASIBLE') if feasible else result['status']=='INFEASIBLE'
                        certified.append(result)
                    payload=canonical_json(case_to_dict(case)).encode();cases.writestr(entry,payload)
                    meta.update(entry=entry,case_sha256=hashlib.sha256(payload).hexdigest(),labels=labels,probes=certified,status='certified')
                    entries.append(meta)
                except Exception as error:
                    meta.update(status='failed',error=repr(error));attempts.append(meta);save(folder/'attempts.json',attempts);raise
                attempts.append(meta);idx+=1
            print(json.dumps({'certified':idx,'group':group}),flush=True)
    save(folder/'attempts.json',attempts);save(folder/'selected.json',entries)
    save(folder/'summary.json',{'total':200,'core':150,'groups':dict(GROUPS),'failed':0,'replacements':0,'P3_started':False})
    freeze(folder)
    print(str(folder))

def run():
    inputs=ROOT/'reports/p2/P2C-inputs-v1';check_manifest(inputs);old_hashes()
    out=ROOT/'reports/p2'/datetime.now(timezone.utc).strftime('P2C-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    env=environment();env.update(actual_affinity=pin_process(),affinity_pinned=True,scope='P2C controlled paired study',thread_environment={k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
    env['threading_note']='One logical processor affinity; numerical thread environment set to 1; CP-SAT workers 1.';save(out/'environment.json',env)
    save(out/'config.json',{'B':2,'w':5,'wide_w':20,'heuristic_ms':50,'exact_s':30,'seed':220000,'P3_started':False})
    rng=np.random.Generator(np.random.PCG64(220000));rows=[]
    with zipfile.ZipFile(inputs/'cases.zip') as cases,zipfile.ZipFile(out/'solver_artifacts.zip','w',zipfile.ZIP_DEFLATED) as proofs,(out/'results.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for spec in load(inputs/'selected.json'):
            case=case_from_dict(json.loads(cases.read(spec['entry'])));results={}
            methods=['v1_PALR_w5','v1_exact_w5','v2_PALR_w5','v2_exact_w5']
            if spec['group']=='outside':methods+=['v2_PALR_w20','v2_exact_w20']
            order=[methods[i] for i in rng.permutation(len(methods))]
            for method in order:
                version,kind,width=method.split('_');w=int(width[1:])
                if kind=='PALR':
                    module=repair if version=='v1' else repair_v2
                    result=module.run_method(case,w=w,B=2,budget_ms=50)
                else:
                    module=p2_exact if version=='v1' else p2_exact_v2
                    result,artifacts=module.solve_exact(case,w=w,B=2,limit_s=30,seed=11)
                    for pi,artifact in enumerate(artifacts):put(proofs,f'{spec["entry"]}/{method}/phase-{pi}/',artifact)
                results[method]=result
            row={'entry':spec['entry'],'group':spec['group'],'index':spec['index'],'case_sha256':spec['case_sha256'],'execution_order':order,'results':results}
            stream.write(canonical_json(row)+'\n');stream.flush();rows.append(row)
            if len(rows)%25==0:print(json.dumps({'completed':len(rows),'total':200}),flush=True)
    freeze(out,{'input_manifest_sha256':sha(inputs/'manifest.json')})
    print(str(out))

def audit(out):
    inputs=ROOT/'reports/p2/P2C-inputs-v1';check_manifest(inputs);m=check_manifest(out)
    assert m['input_manifest_sha256']==sha(inputs/'manifest.json');prior=old_hashes()
    specs=load(inputs/'selected.json');rows=[json.loads(x) for x in (out/'results.jsonl').read_text().splitlines()]
    assert len(specs)==len(rows)==200
    phase_counts=Counter();category_counts=Counter();plans=0;models=0
    with zipfile.ZipFile(inputs/'cases.zip') as cases,zipfile.ZipFile(inputs/'category_models.zip') as categories,zipfile.ZipFile(out/'solver_artifacts.zip') as proofs:
        for spec,row in zip(specs,rows):
            payload=cases.read(spec['entry']);assert hashlib.sha256(payload).hexdigest()==spec['case_sha256']==row['case_sha256']
            case=case_from_dict(json.loads(payload));regen,meta=construct(spec['index'],spec['group'],spec['ordinal'])
            assert canonical_json(case_to_dict(regen)).encode()==payload
            assert validate(case.base,case.reference).feasible
            for w in (5,20):assert independent_starts(case,w)==spec['labels'][str(w)]
            for pi,result in enumerate(spec['probes']):
                model,present,starts,ends,ctx=probe_model(case,result['w'],result['cap'])
                prefix=f'{spec["entry"]}/probe-{pi}/'
                replay(model,categories,prefix,result['status']);models+=1;category_counts[result['status']]+=1
                if result['plan']:
                    plan=tuple(Item(**p) for p in result['plan']);p2_exact_v2.witness(case,ctx,plan)
                    assert any(p.task_id=='urgent' for p in plan)
                    if result['cap'] is not None:assert sum(p.task_id not in {x.task_id for x in plan} for p in case.reference)<=result['cap']
            for method,result in row['results'].items():
                version,kind,width=method.split('_');w=int(width[1:]);module=p2_exact if version=='v1' else p2_exact_v2;ctx=module.context(case,w,2)
                assert result['editable_indices']==list(ctx['indices'])
                if result['plan'] is not None:
                    plan=tuple(Item(**p) for p in result['plan']);module.witness(case,ctx,plan);plans+=1
                    raw=raw_metrics(case,plan)
                    for k,v in raw.items():assert result['metrics'][k]==v,(method,k)
                if kind=='exact':
                    for pi,phase in enumerate(result['phases']):
                        model,*_=module.build_model(case,ctx,phase['require_urgent'])
                        prefix=f'{spec["entry"]}/{method}/phase-{pi}/'
                        replay(model,proofs,prefix,phase['status'],phase['objective']);models+=1;phase_counts[phase['status']]+=1
                if kind=='PALR' and result['validation']:assert result['validation']['feasible']
            if (spec['index']+1)%25==0:print(json.dumps({'audited':spec['index']+1,'models_replayed':models}),flush=True)
    result={'passed':True,'events_regenerated':200,'core':150,'all_labels_recomputed':200,'plans_validated':plans,'all_models_replayed':models,
            'category_statuses':dict(category_counts),'method_phase_statuses':dict(phase_counts),'prior_acceptance':prior,'P3_started':False}
    assert not (out/'independent_audit.json').exists();save(out/'independent_audit.json',result);print(json.dumps(result,indent=2))

def replay(model,bundle,prefix,expected,objective=None):
    assert str(model.proto)==bundle.read(prefix+'model_pbtxt.txt').decode()
    response=cp_model_helper.CpSolverResponse();assert response.parse_text_format(bundle.read(prefix+'response_pbtxt.txt').decode())
    assert cp_model.CpSolver().status_name(response.status)==expected
    if objective is not None:
        assert response.objective_value==objective
        if expected=='OPTIMAL':assert response.best_objective_bound==objective
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=11;solver.parameters.max_time_in_seconds=30
    solver.parameters.absolute_gap_limit=0;solver.parameters.relative_gap_limit=0
    status=solver.solve(model);assert solver.status_name(status)==expected
    if objective is not None:assert solver.objective_value==objective

def summarize(out):
    rows=[json.loads(x) for x in (out/'results.jsonl').read_text().splitlines()];summary={};records=[]
    for group,n in GROUPS:
        subset=[r for r in rows if r['group']==group];assert len(subset)==n
        info={'events':n,'methods':{}}
        for key in subset[0]['results']:
            rr=[r['results'][key] for r in subset]
            info['methods'][key]={'service_success':sum(any(p['task_id']=='urgent' for p in (r['plan'] or [])) for r in rr),'timeouts':sum(r['status']=='timeout' for r in rr),
                'statuses':dict(Counter(r['status'] for r in rr)),'valid_plans':sum((r.get('validation') or r.get('certificate',{}).get('validation') or {}).get('feasible',False) for r in rr),
                'mean_ms':float(np.mean([r.get('total_ns',r.get('elapsed_ns',0))/1e6 for r in rr])),
                'metrics_means':{k:float(np.mean([r['metrics'][k] for r in rr])) for k in ('U_raw','N_drop','N_add','M_all')}}
        summary[group]=info
    for row in rows:
        for method,r in row['results'].items():
            records.append({'entry':row['entry'],'group':row['group'],'method':method,'status':r['status'],**r['metrics']})
    keys=list(dict.fromkeys(k for r in records for k in r))
    with (out/'per_event.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(records)
    save(out/'summary.json',{'groups':summary,'events':200,'core':150,'P3_started':False})
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run','audit','summarize']);parser.add_argument('folder',nargs='?');args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='run':run()
    else:globals()[args.action](Path(args.folder))
