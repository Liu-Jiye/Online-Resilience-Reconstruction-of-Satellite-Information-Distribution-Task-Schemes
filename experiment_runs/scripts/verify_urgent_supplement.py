"""Independent bit-mask pressure classification, paired plan and solver audit."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import numpy as np
from ortools.sat.python import cp_model,cp_model_helper

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import Item,case_from_dict,case_to_dict,canonical_json
from isl.p1_sources import save_json
from isl import p2_exact,p2_exact_v2
from isl.metrics import raw_metrics,selection_key
from isl.urgent_supplement import base_attempt,case_for,pressure_event_seed


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def independent_label(case):
    """Use integer bit sets of legal starts, separately from pressure_label loops."""
    task=case.event.urgent;duration=1+(task.data_bits+task.rate_bps-1)//task.rate_bps
    last=task.deadline-duration
    def interval(a,b):
        a=max(task.release,a);b=min(last,b)
        return ((1<<(b-a+1))-1)<<a if a<=b else 0
    mask=0
    for c in case.base.contacts:
        if (c.sender,c.receiver)==(task.sender,task.receiver):mask|=interval(c.start,c.end-duration)
    physical=mask.bit_count()
    for b in case.base.calendar:
        if b.resource in (task.sender,task.receiver):mask &= ~interval(b.start-duration+1,b.end-1)
    calendar=mask.bit_count();conflicts={}
    for p in case.reference:
        conflicts[p.task_id]=interval(p.start-duration+1,p.end-1) if {p.sender,p.receiver}&{task.sender,task.receiver} else 0
    for p in case.frozen:mask &= ~conflicts[p.task_id]
    frozen=mask.bit_count();minima=[]
    for w in (5,20):
        ctx=p2_exact_v2.context(case,w,2);editable={case.reference[i].task_id for i in ctx['indices']}
        allowed=mask
        for p in case.reference:
            if p.task_id not in editable:allowed &= ~conflicts[p.task_id]
        minimum=None
        while allowed:
            bit=allowed & -allowed
            count=sum(bool(conflicts[t]&bit) for t in editable)
            minimum=count if minimum is None else min(minimum,count)
            allowed-=bit
        minima.append(minimum)
    a,b=minima
    if a==0:category='direct_insert'
    elif a==1:category='one_removal'
    elif a is not None:category='multiple_removals'
    elif b is not None:category='outside_neighborhood'
    elif not physical:category='no_physical_opportunity'
    elif not calendar:category='calendar_blocks_all'
    elif not frozen:category='frozen_blocks_remaining'
    else:category='outside_wide_neighborhood'
    return {'category':category,'physical_start_count':physical,'calendar_start_count':calendar,
            'frozen_start_count':frozen,'min_removals_w5':a,'min_removals_w20':b}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--replay-solvers',action='store_true');parser.add_argument('--write-audit',action='store_true')
    args=parser.parse_args();run=args.directory.resolve();inputs=ROOT/'reports/p2/P2-urgent-supplement-inputs-v1'
    config=load(inputs/'config.json');im=load(inputs/'manifest.json');m=load(run/'manifest.json')
    assert sha(inputs/'manifest.json')==m['input_manifest_sha256']
    for manifest,directory in ((im,inputs),(m,run)):
        for name,expected in manifest['artifact_sha256'].items():assert sha(directory/name)==expected,name
        for name,expected in manifest['source_sha256'].items():assert sha(REPO/name)==expected,name
    old=ROOT/'reports/p2/P2-20261105T114327Z';old_inputs=ROOT/'reports/p2/P2-inputs-v1'
    for name,expected in load(old/'acceptance_manifest.json')['file_sha256'].items():assert sha(REPO/name)==expected,name
    attempts=load(inputs/'natural_generation_attempts.json');valid=[[] for _ in range(6)]
    with zipfile.ZipFile(inputs/'natural_bases.zip') as bundle:
        for record in attempts:
            ci=record['combination_index'];n,s=config['natural']['combination_order'][ci]
            regenerated,data=base_attempt(ci,n,s,record['attempt'],150000,1000,f'P2U-natural-c{ci}')
            assert regenerated==record
            if data:
                name=record['instance_id']+'.json';payload=bundle.read(name)
                assert hashlib.sha256(payload).hexdigest()==im['base_entry_sha256'][name]
                saved=json.loads(payload)
                data['metadata']['reference_metadata']['construction_ns']=saved['metadata']['reference_metadata']['construction_ns']
                assert canonical_json(data)==canonical_json(saved)
                valid[ci].append(record)
    assert [len(v) for v in valid]==[50]*6
    events=load(inputs/'selected_events.json');natural=[e for e in events if e['cohort']=='natural']
    rng=np.random.Generator(np.random.PCG64(160000));selection=[]
    for ci,records in enumerate(valid):
        selection += [records[i]['instance_id'] for i in rng.permutation(50).tolist()[:config['natural']['event_counts_per_combination'][ci]]]
    assert selection==[e['instance_id'] for e in natural] and len(natural)==200
    pressure_attempts=load(inputs/'pressure_generation_attempts.json');sampled=0;pressure_accepted=0
    sample_rng=np.random.Generator(np.random.PCG64(162001))
    for gi,target in enumerate(config['pressure']['category_order']):
        records=[a for a in pressure_attempts if a['target_category']==target]
        assert [a['attempt'] for a in records]==list(range(len(records)))
        accepted=[a for a in records if a['accepted']]
        assert len(accepted)<=25 and len(records)<=5000
        assert len(accepted)==25 or len(records)==5000
        expected_ids=[a['instance_id'] for a in accepted]
        assert expected_ids==[e['instance_id'] for e in events if e['cohort']=='pressure' and e['category']==target]
        # Regenerate every accepted and up to 100 deterministically selected
        # rejected attempts per group; all other attempt records remain public.
        rejected=[i for i,a in enumerate(records) if not a['accepted']]
        sample=set(sample_rng.choice(rejected,min(100,len(rejected)),replace=False).tolist())
        sample.update(i for i,a in enumerate(records) if a['accepted'])
        for index in sorted(sample):
            a=records[index]
            regenerated,data=base_attempt(gi,30,8,index,170000,5000,f'P2U-pressure-g{gi}')
            assert regenerated['seed']==a['seed'] and regenerated['status']==a['status']
            if data:
                case=case_for(data,a['FR'],a['q'],pressure_event_seed(a['seed']))
                label=independent_label(case)
                assert all(label[k]==a['label'][k] for k in label)
                assert a['accepted']==(label['category']==target)
            else:assert regenerated['reason']==a['reason']
            sampled+=not a['accepted'];pressure_accepted+=a['accepted']
    rows=[json.loads(l) for l in (run/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    original=[json.loads(l) for l in (old/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    expected_specs=[{'cohort':'old_replay','entry':f'old-{r["event_spec"]["event_ordinal"]:03d}.json','original_spec':r['event_spec']}
                    for r in original if r['event_spec']['kind']=='urgent_insertion']+events
    assert [r['event_spec'] for r in rows]==expected_specs
    models=responses=replayed=plans=0;phase_statuses=Counter();cohort_counts=Counter()
    with zipfile.ZipFile(inputs/'event_cases.zip') as cases,zipfile.ZipFile(old_inputs/'event_cases.zip') as old_cases,zipfile.ZipFile(run/'solver_artifacts.zip') as proofs,zipfile.ZipFile(inputs/'natural_bases.zip') as bases:
        for index,row in enumerate(rows):
            spec=row['event_spec'];cohort_counts[spec['cohort']]+=1
            if spec['cohort']=='old_replay':payload=old_cases.read(f'event-{spec["original_spec"]["event_ordinal"]:03d}.json')
            else:
                payload=cases.read(spec['entry']);assert hashlib.sha256(payload).hexdigest()==im['case_entry_sha256'][spec['entry']]
            assert hashlib.sha256(payload).hexdigest()==row['case_sha256']
            case=case_from_dict(json.loads(payload));label=independent_label(case)
            assert all(label[k]==row['independent_urgent_label'][k] for k in label)
            if spec['cohort']=='natural':
                data=json.loads(bases.read(spec['instance_id']+'.json'))
                assert canonical_json(case_to_dict(case_for(data,spec['FR'],spec['q'],spec['event_seed'])))==payload.decode()
            contexts={v:module.context(case,5,2) for v,module in [('v1',p2_exact),('v2',p2_exact_v2)]}
            assert all(contexts['v1'][k]==contexts['v2'][k] for k in contexts['v1'] if k!='allowed')
            assert contexts['v2']['allowed']-contexts['v1']['allowed'] <= {case.event.urgent.id}
            for key,result in row['results'].items():
                module=p2_exact if key.startswith('v1') else p2_exact_v2
                w=20 if key=='v2_exact_w20_diagnostic' else 5;ctx=module.context(case,w,2)
                if key.endswith('PALR'):
                    if result['validation'] and result['validation']['feasible']:
                        plan=tuple(Item(**p) for p in result['plan']);module.witness(case,ctx,plan);plans+=1
                    continue
                for pi,phase in enumerate(result['phases']):
                    model,present,starts,ends,weights,alts=module.build_model(case,ctx,phase['require_urgent'])
                    prefix=f'{spec["entry"]}/{key}/phase-{pi}/'
                    assert str(model.proto)==proofs.read(prefix+'model_pbtxt.txt').decode('utf-8')
                    native=cp_model_helper.CpSolverResponse();assert native.parse_text_format(proofs.read(prefix+'response_pbtxt.txt').decode('utf-8'))
                    assert cp_model.CpSolver().status_name(native.status)==phase['status']
                    if phase['status'] in ('OPTIMAL','FEASIBLE'):
                        assert native.objective_value==phase['objective']
                        if phase['status']=='OPTIMAL':assert native.objective_value==native.best_objective_bound
                    if args.replay_solvers:
                        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=11
                        solver.parameters.max_time_in_seconds=30;solver.parameters.absolute_gap_limit=0;solver.parameters.relative_gap_limit=0
                        status=solver.solve(model);assert solver.status_name(status)==phase['status']
                        if phase['status']=='OPTIMAL':assert solver.objective_value==phase['objective']
                        replayed+=1
                    models+=1;responses+=1;phase_statuses[phase['status']]+=1
                if result['plan'] is not None:
                    plan=tuple(Item(**p) for p in result['plan']);module.witness(case,ctx,plan);plans+=1
                    assert raw_metrics(case,plan)==result['metrics']
                    assert list(selection_key(case,plan))==result['selection_key']
                if result['urgent_certificate']!='service_unknown':
                    can=label['min_removals_w20' if w==20 else 'min_removals_w5'] is not None and case.event.urgent.id in ctx['allowed']
                    assert (result['urgent_certificate']=='service_feasible')==can
            if (index+1)%50==0:print(json.dumps({'audit_events':index+1,'total':len(rows),'models':models}),flush=True)
        assert len(proofs.namelist())==models*3
    result={'passed':True,'verified_at_utc':datetime.now(timezone.utc).isoformat(),'cohorts':dict(cohort_counts),
            'all_natural_attempts_regenerated':len(attempts),'natural_valid_bases_regenerated':300,
            'pressure_accepted_attempts_regenerated':pressure_accepted,'pressure_rejected_attempts_sampled':sampled,
            'pressure_attempt_metadata_all_checked':len(pressure_attempts),'all_event_labels_independently_recomputed':len(rows),
            'plans_validated':plans,'models_and_responses_checked':models,'models_replayed':replayed,
            'phase_statuses':dict(phase_statuses),'old_P2_accepted_files_unchanged':True,
            'verifier_sha256':sha(Path(__file__)),'P3_started':False}
    if args.write_audit:
        assert not (run/'independent_audit.json').exists();save_json(run/'independent_audit.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
