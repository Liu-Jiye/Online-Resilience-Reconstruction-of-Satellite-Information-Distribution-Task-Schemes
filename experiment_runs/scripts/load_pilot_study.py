"""Training/validation load pilot, frozen diagnostics and no repair calls."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import argparse
from collections import Counter
from dataclasses import asdict,replace
from datetime import datetime,timezone
import csv,hashlib,json,platform,subprocess,sys,time,zipfile
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import Instance,Task,Contact,Busy,Item,canonical_json,frozen_count
from isl.load_pilot import demand_family,transform_family,indexed_reference,Diagnostics,context_statistics,group_means,select_train,validate_selection,rng_for
from isl.load_pilot_independent import BitAudit
from isl.events import generate_event
from isl.validation import validate


def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def instance_from(data):return Instance(data['id'],tuple(data['satellites']),tuple(Task(**t) for t in data['tasks']),tuple(Contact(**c) for c in data['contacts']),tuple(Busy(**b) for b in data['calendar']),data['horizon'])
def source_files():return sorted(set(list((ROOT/'src').rglob('*.py'))+[Path(__file__),ROOT/'configs/load_pilot_v1.json',ROOT/'protocol/LOAD_PILOT_V1_CONTRACT.md',ROOT/'tests/test_load_pilot.py']))
def old_evidence():
    records=[]
    # Original P1 progress documents have an explicit accepted P1->P2 transition.
    for p in sorted((ROOT/'reports/p2').glob('*/acceptance_manifest.json')):
        m=load(p)
        for n,h in m['file_sha256'].items():assert sha(REPO/n)==h,n
        records.append({'path':p.relative_to(REPO).as_posix(),'sha256':sha(p)})
    p=ROOT/'reports/p1/P1-current-entry-fix-v1/acceptance_manifest.json'
    for n,h in load(p)['file_sha256'].items():assert sha(REPO/n)==h,n
    records.append({'path':p.relative_to(REPO).as_posix(),'sha256':sha(p)})
    return records


def opportunity_tasks(base,family,config,independent=False):
    inspector=BitAudit(base,()) if independent else Diagnostics(base,())
    accepted=[];attempts=[]
    for t in family[500:500+config['opportunity_attempt_cap']]:
        label=inspector.inspect(t)
        attempts.append({'task_id':t.id,'accepted':label['calendar_feasible'],'reason':'accepted' if label['calendar_feasible'] else label['category']})
        if label['calendar_feasible']:accepted.append(t)
        if len(accepted)==config['opportunity_probes_per_context']:break
    return accepted,attempts


def probes_for(ins,ref,source_seed,opportunities,config,independent=False):
    inspector=BitAudit(ins,ref) if independent else Diagnostics(ins,ref)
    natural=[]
    for i in range(config['natural_probes_per_context']):
        seed=int(np.random.SeedSequence([source_seed,config['natural_probe_seed_tag'],i]).generate_state(1,dtype=np.uint64)[0])
        natural.append(generate_event(ins,ref,'urgent_insertion',0.,.2 if i%2==0 else .8,seed).urgent)
    records={};labels={}
    for kind,tasks in [('natural',natural),('opportunity',opportunities)]:
        records[kind]=[];labels[kind]={f'FR{fr}':[] for fr in config['FR_diagnostics']}
        for t in tasks:
            byfr={f'FR{fr}':inspector.inspect(t,frozen_count(ref,fr)) for fr in config['FR_diagnostics']}
            records[kind].append({'task':asdict(t),'labels':byfr})
            for key,label in byfr.items():labels[kind][key].append(label)
    return records,labels


def generate():
    config=load(ROOT/'configs/load_pilot_v1.json');source=ROOT/'reports/p1'/config['source_run'];archive=source/'pilot_derived_instances.zip'
    assert sha(archive)==config['source_archive_sha256'];prior=old_evidence()
    out=ROOT/'reports/p1'/datetime.now(timezone.utc).strftime('LOAD-pilot-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    save(out/'config.json',config);save(out/'prior_acceptance.json',prior)
    save(out/'environment.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,'os':platform.platform(),'thread_environment':{k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},'purpose':'offline load generation and diagnostics only',
        'pip_freeze':subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),'GPU_used':False,'repair_methods_run':[]})
    entries=sorted(load(source/'distributions.json'),key=lambda r:(config['splits'].index(r['split']),config['layers'].index(r['layer']),r['instance_id']))
    assert len(entries)==150 and all(r['split'] in ('train','validation') for r in entries)
    rows=[];training=None;start=time.perf_counter_ns()
    with zipfile.ZipFile(archive) as originals,zipfile.ZipFile(out/'contexts.zip','w',zipfile.ZIP_DEFLATED) as contexts,zipfile.ZipFile(out/'diagnostics.zip','w',zipfile.ZIP_DEFLATED) as diagnostics:
        for bi,source_row in enumerate(entries):
            if source_row['split']=='validation' and training is None:
                training=select_train(rows,config);save(out/'training_selection.json',training)
                print(json.dumps({'training_selection_frozen_before_validation':training['selected_from_train']}),flush=True)
            payload=originals.read(source_row['instance_id']+'.json');original=json.loads(payload);base=instance_from(original['instance'])
            ref0=tuple(Item(**p) for p in original['reference']);seed=original['metadata']['instance_seed']
            assert hashlib.sha256(payload).hexdigest()==source_row['sha256']
            raw,details=demand_family(base,original['metadata']['component_seeds']['tasks'],config)
            for h in config['hot_probabilities']:
                try:family,hot,sampling=transform_family(base,raw,details,seed,h,config);opps,attempts=opportunity_tasks(base,family,config)
                except Exception as error:
                    for N in config['task_counts']:rows.append({'source_instance_id':base.id,'split':source_row['split'],'layer':source_row['layer'],'N':N,'h':h,'status':'generation_failed','reason':repr(error)})
                    continue
                for N in config['task_counts']:
                    began=time.perf_counter_ns();entry=f'{base.id}-N{N}-h{h:.1f}.json';ins=replace(base,id='LOAD-'+entry[:-5],tasks=family[:N]);ref=indexed_reference(ins)
                    baseline_match=None
                    if N==100 and h==0.:
                        assert ins.tasks==base.tasks and ref==ref0;baseline_match=True
                    inspector=Diagnostics(ins,ref);task_labels=[inspector.inspect(t) for t in ins.tasks]
                    probe_records,probe_labels=probes_for(ins,ref,seed,opps,config)
                    metrics=context_statistics(ins,ref,hot,sampling,task_labels,probe_labels)
                    data={'instance':asdict(ins),'reference':[asdict(p) for p in ref],
                          'metadata':{'source_instance_id':base.id,'source_sha256':source_row['sha256'],'source_seed':seed,'split':source_row['split'],'layer':source_row['layer'],'N':N,'h':h,'hot_satellites':hot,'sampling':sampling[:N]}}
                    encoded=canonical_json(data).encode();contexts.writestr(entry,encoded)
                    detail={'task_labels':task_labels,'probes':probe_records,'opportunity_attempts':attempts}
                    diagnostics.writestr(entry,canonical_json(detail))
                    rows.append({'entry':entry,'source_instance_id':base.id,'split':source_row['split'],'layer':source_row['layer'],'N':N,'h':h,'status':'valid',
                                 'case_sha256':hashlib.sha256(encoded).hexdigest(),'default_exactly_reproduced':baseline_match,
                                 'generation_diagnostics_ns':time.perf_counter_ns()-began,**metrics})
            if (bi+1)%5==0:print(json.dumps({'base_scenarios':bi+1,'contexts':len(rows),'split':source_row['split']}),flush=True)
    if training is None:training=select_train(rows,config);save(out/'training_selection.json',training)
    final=validate_selection(rows,training,config);save(out/'frozen_load_protocol.json',{'version':'1.0','source_config_sha256':sha(ROOT/'configs/load_pilot_v1.json'),**final})
    save(out/'context_rows.json',rows);means=group_means(rows)
    save(out/'group_means.json',{'|'.join(map(str,k)):v for k,v in means.items()})
    numeric=[k for k,v in rows[0].items() if not isinstance(v,dict)]
    with (out/'per_context.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=numeric,extrasaction='ignore');w.writeheader();w.writerows(rows)
    summary={'base_scenarios':150,'attempted_contexts':len(rows),'valid_contexts':sum(r['status']=='valid' for r in rows),'failed_contexts':sum(r['status']!='valid' for r in rows),
             'default_reproduced':sum(r.get('default_exactly_reproduced') is True for r in rows),'train_validation_counts':dict(Counter(r['split'] for r in rows)),
             'offline_generation_diagnostics_wall_s':(time.perf_counter_ns()-start)/1e9,'selection':final,'P3_started':False,'test_instances':0,'repair_methods_run':[]}
    save(out/'summary.json',summary)
    save(out/'manifest.json',{'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'source_archive_sha256':sha(archive),
             'source_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in source_files()},'artifact_sha256':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}})
    print(str(out));print(json.dumps(summary,ensure_ascii=False,indent=2))


def audit(out):
    config=load(out/'config.json');manifest=load(out/'manifest.json')
    for n,h in manifest['source_sha256'].items():assert sha(REPO/n)==h,n
    for n,h in manifest['artifact_sha256'].items():assert sha(out/n)==h,n
    prior=old_evidence();source=ROOT/'reports/p1'/config['source_run'];archive=source/'pilot_derived_instances.zip';assert sha(archive)==manifest['source_archive_sha256']
    rows=load(out/'context_rows.json');valid=[r for r in rows if r['status']=='valid'];replayed=[];checks=Counter();cache={}
    with zipfile.ZipFile(archive) as originals,zipfile.ZipFile(out/'contexts.zip') as contexts,zipfile.ZipFile(out/'diagnostics.zip') as diagnoses:
        assert len(contexts.namelist())==len(diagnoses.namelist())==len(valid)
        for ri,row in enumerate(rows):
            iid=row['source_instance_id']
            if cache.get('id')!=iid:
                original=json.loads(originals.read(iid+'.json'));base=instance_from(original['instance']);seed=original['metadata']['instance_seed']
                raw,details=demand_family(base,original['metadata']['component_seeds']['tasks'],config);cache={'id':iid,'base':base,'original':original,'seed':seed,'raw':raw,'details':details,'families':{}}
            base=cache['base'];seed=cache['seed'];h=row['h'];N=row['N']
            if h not in cache['families']:
                try:
                    family,hot,sampling=transform_family(base,cache['raw'],cache['details'],seed,h,config)
                    opps,attempts=opportunity_tasks(base,family,config,independent=True)
                    cache['families'][h]=(family,hot,sampling,opps,attempts)
                except Exception as e:cache['families'][h]=e
            derived=cache['families'][h]
            if isinstance(derived,Exception):
                assert row['status']=='generation_failed' and row['reason']==repr(derived);replayed.append(row);checks['generation_failures']+=1;continue
            assert row['status']=='valid';family,hot,sampling,opps,attempts=derived
            payload=contexts.read(row['entry']);assert hashlib.sha256(payload).hexdigest()==row['case_sha256']
            data=json.loads(payload);ins=instance_from(data['instance']);ref=tuple(Item(**p) for p in data['reference']);detail=json.loads(diagnoses.read(row['entry']))
            assert ins==replace(base,id='LOAD-'+row['entry'][:-5],tasks=family[:N]);assert data['metadata']['sampling']==sampling[:N] and data['metadata']['hot_satellites']==list(hot)
            bit=BitAudit(ins,ref);assert validate(ins,ref).feasible and bit.reference_plan()==ref
            if N==100 and h==0.:
                assert ins.tasks==base.tasks and list(map(asdict,ref))==cache['original']['reference'];checks['default_reproductions']+=1
            labels=[bit.inspect(t) for t in ins.tasks];assert labels==detail['task_labels'];checks['candidate_diagnostics']+=len(labels)
            records,probe_labels=probes_for(ins,ref,seed,opps,config,independent=True)
            assert records==detail['probes'] and attempts==detail['opportunity_attempts'];checks['probe_tasks_FR_checks']+=sum(len(v)*2 for v in records.values())
            stats=context_statistics(ins,ref,hot,sampling,labels,probe_labels)
            assert all(stats[k]==row[k] for k in stats)
            replayed.append(row);checks['contexts_rebuilt']+=1;checks['reference_decisions_replayed']+=len(ins.tasks)
            if (ri+1)%45==0:print(json.dumps({'audited_contexts':ri+1,'total':len(rows)}),flush=True)
    expected_train=select_train(replayed,config);assert expected_train==load(out/'training_selection.json')
    final=validate_selection(replayed,expected_train,config);frozen=load(out/'frozen_load_protocol.json');assert all(frozen[k]==v for k,v in final.items())
    means={'|'.join(map(str,k)):v for k,v in group_means(replayed).items()};assert means==load(out/'group_means.json')
    result={'passed':True,'verification_utc':datetime.now(timezone.utc).isoformat(),'counts':dict(checks),'contexts_attempted':len(rows),'base_scenarios':150,
            'independent_method':'integer bitsets for feasible starts, greedy reference decisions and fixed-reference blocker census',
            'selection_recomputed':True,'prior_acceptance':prior,'repair_methods_run':[],'CP_SAT_run':False,'P3_started':False,'test_instances':0}
    assert not (out/'independent_audit.json').exists();save(out/'independent_audit.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['generate','audit']);p.add_argument('folder',nargs='?');a=p.parse_args()
    if a.action=='generate':generate()
    else:audit(Path(a.folder))
