"""Audit P2 frozen inputs, plans, domain, integer objectives and native evidence."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np
from ortools.sat.python import cp_model,cp_model_helper

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import Item,case_from_dict,case_to_dict,canonical_json,ordered
from isl.p2_generation import generate_base,select_events,make_case
from isl.p2_exact import build_model,context,witness
from isl.validation import validate
from isl.metrics import selection_key,raw_metrics
from isl.p1_sources import save_json


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    parser.add_argument('--replay-solvers',action='store_true')
    parser.add_argument('--write-audit',action='store_true')
    args=parser.parse_args();run=args.run_directory.resolve()
    config=load(run/'config.json');inputs=ROOT/'reports/p2/P2-inputs-v1'
    manifest,input_manifest=load(run/'manifest.json'),load(inputs/'manifest.json')
    assert sha(inputs/'manifest.json')==manifest['input_manifest_sha256']
    for record,directory in ((manifest,run),(input_manifest,inputs)):
        for name,expected in record['artifact_sha256'].items():assert sha(directory/name)==expected,name
        for name,expected in record['source_sha256'].items():assert sha(REPO/name)==expected,name
    attempts=load(inputs/'generation_attempts.json');events=load(inputs/'selected_events.json')
    valid=[[] for _ in range(6)];bases={}
    with zipfile.ZipFile(inputs/'base_instances.zip') as bundle:
        assert len(bundle.namelist())==300
        for record in attempts:
            ci=record['combination_index'];n,s=config['combination_order'][ci]
            regenerated,data=generate_base(ci,n,s,record['attempt'],config)
            assert regenerated==record
            if data:
                name=record['instance_id']+'.json';payload=bundle.read(name)
                assert hashlib.sha256(payload).hexdigest()==input_manifest['base_entry_sha256'][name]
                original=json.loads(payload)
                # Reference-construction clock readings are the only nondeterministic field.
                original_meta=original['metadata']['reference_metadata'].copy()
                regenerated_meta=data['metadata']['reference_metadata'].copy()
                original_meta.pop('construction_ns');regenerated_meta.pop('construction_ns')
                assert canonical_json(original_meta)==canonical_json(regenerated_meta)
                data['metadata']['reference_metadata']=original['metadata']['reference_metadata']
                assert canonical_json(data)==canonical_json(original)
                bases[record['instance_id']]=original;valid[ci].append(record)
    assert all(len(v)==50 for v in valid)
    assert select_events(valid,config)==events
    rows=[json.loads(line) for line in (run/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==len(events)==200
    assert len({e['instance_id'] for e in events})==200
    assert manifest['source_commit']!=input_manifest['source_commit']
    # Input-freeze commit must be an ancestor of the execution commit.
    subprocess.run(['git','merge-base','--is-ancestor',input_manifest['source_commit'],manifest['source_commit']],cwd=REPO,check=True)
    phase_counts=Counter();replayed=0;service_checks=[];model_count=0
    with zipfile.ZipFile(inputs/'event_cases.zip') as cases,zipfile.ZipFile(run/'solver_artifacts.zip') as proofs:
        for spec,row in zip(events,rows):
            ordinal=spec['event_ordinal'];name=f'event-{ordinal:03d}.json'
            payload=cases.read(name)
            assert hashlib.sha256(payload).hexdigest()==row['case_sha256']==input_manifest['case_entry_sha256'][name]
            regenerated=make_case(bases[spec['instance_id']],spec)
            assert canonical_json(case_to_dict(regenerated))==payload.decode('utf-8')
            case=case_from_dict(json.loads(payload));ctx=context(case,config['w'],config['B'])
            assert spec==row['event_spec']
            exact=row['exact'];assert exact['event_id']==case.event.id
            assert exact['num_search_workers']==1 and exact['limit_s']==30
            assert exact['editable_indices']==list(ctx['indices'])
            assert exact['allowed_task_ids']==sorted(ctx['allowed'])
            for phase_index,phase in enumerate(exact['phases']):
                prefix=f'event-{ordinal:03d}/phase-{phase_index}/'
                pbtxt=proofs.read(prefix+'model_pbtxt.txt').decode('utf-8')
                model,present,starts,ends,weights,alternatives=build_model(case,ctx,phase['require_urgent'])
                assert str(model.proto)==pbtxt
                assert weights==phase['weights'] and alternatives==phase['model_alternatives']
                native=cp_model_helper.CpSolverResponse()
                text=proofs.read(prefix+'response_pbtxt.txt').decode('utf-8')
                if text!='not_solved':
                    assert native.parse_text_format(text)
                    assert cp_model.CpSolver().status_name(native.status)==phase['status']
                    if phase['status'] in ('OPTIMAL','FEASIBLE'):
                        native_plan=ordered(Item(t.id,t.sender,t.receiver,native.solution[starts[t.id].index],native.solution[ends[t.id].index])
                                            for t in ctx['instance'].tasks if native.solution[present[t.id].index])
                        witness(case,ctx,native_plan)
                        m=raw_metrics(case,native_plan)
                        objective=-m['U_raw']*weights['U']+m['N_drop']*weights['N_drop']+m['N_add']*weights['N_add']+m['M_all']
                        assert objective==native.objective_value==phase['objective']
                        if phase['status']=='OPTIMAL':assert objective==native.best_objective_bound==phase['best_bound']
                if args.replay_solvers:
                    replay_model=cp_model.CpModel()
                    assert replay_model.proto.parse_text_format(pbtxt)
                    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
                    solver.parameters.random_seed=config['exact_solver_seed'];solver.parameters.max_time_in_seconds=30
                    solver.parameters.relative_gap_limit=0;solver.parameters.absolute_gap_limit=0
                    status=solver.solve(replay_model)
                    assert solver.status_name(status)==phase['status'],(ordinal,phase_index,solver.status_name(status))
                    if phase['status']=='OPTIMAL':assert solver.objective_value==phase['objective']
                    replayed+=1
                phase_counts[phase['status']]+=1;model_count+=1
            if exact['plan'] is not None:
                plan=tuple(Item(**p) for p in exact['plan'])
                assert canonical_json(witness(case,ctx,plan))==canonical_json(exact['certificate'])
                assert raw_metrics(case,plan)==exact['metrics']
                assert list(selection_key(case,plan))==exact['selection_key']
            for label in ('heuristic_50ms','heuristic_30s'):
                result=row[label]
                assert result['w']==config['w'] and result['B']==config['B']
                assert result['event_id']==case.event.id
                assert result['editable_indices']==list(ctx['indices'])
                plan=tuple(Item(**p) for p in result['plan'])
                if result['validation'] and result['validation']['feasible']:
                    witness(case,ctx,plan)
                    check=validate(ctx['instance'],plan,frozen=case.frozen,cancelled=case.event.cancelled,
                                   unchanged=ctx['unchanged'],original_ids=ctx['original'],budget=config['B'],
                                   admissions=result['admissions_cumulative'],
                                   initial=tuple(Item(**p) for p in result['initial_plan']),trace=result['trace'])
                    assert check.feasible
                    if exact['proven_optimal']:assert tuple(exact['selection_key'])<=selection_key(case,plan)
                    if exact['proven_infeasible']:raise AssertionError('valid heuristic contradicts INFEASIBLE')
            if case.event.urgent:
                # Independent exhaustive start enumeration: dropping every E
                # original leaves only immutable reservations. With B>=1, urgent
                # eligibility + one feasible start is necessary and sufficient.
                t=case.event.urgent;starts_feasible=[]
                if t.id in ctx['allowed'] and config['B']>=1:
                    for start in range(t.release,t.deadline-t.duration+1):
                        p=Item(t.id,t.sender,t.receiver,start,start+t.duration)
                        plan=ordered(ctx['unchanged']+(p,))
                        if validate(ctx['instance'],plan,frozen=case.frozen,cancelled=case.event.cancelled,
                                    unchanged=ctx['unchanged']).feasible:starts_feasible.append(start)
                predicted='service_feasible' if starts_feasible else 'service_proven_infeasible'
                assert exact['urgent_certificate']==predicted
                service_checks.append({'event_ordinal':ordinal,'certificate':predicted,
                                       'eligible':t.id in ctx['allowed'],'integer_start_count':len(starts_feasible),
                                       'first_feasible_start':starts_feasible[0] if starts_feasible else None})
    assert model_count==sum(len(r['exact']['phases']) for r in rows)
    assert len(proofs.namelist())==3*model_count
    baseline='f8cd6afd8a8a33d43c9f178ae186bf42f9de18dc'
    outside=subprocess.check_output(['git','diff','--name-only',baseline,'--','.',':(exclude)experiment_runs'],cwd=REPO,text=True).splitlines()
    assert not outside
    timing={}
    for label in ('exact','heuristic_50ms','heuristic_30s'):
        times=np.array([r[label]['total_ns']/1e6 for r in rows])
        timing[label]={'mean_ms':float(np.mean(times)),'p50_ms':float(np.quantile(times,.5)),
                       'p95_ms':float(np.quantile(times,.95)),'p99_ms':float(np.quantile(times,.99)),'max_ms':float(max(times))}
    output={'passed':True,'stage':'P2','run_id':run.name,'audited_at_utc':datetime.now(timezone.utc).isoformat(),
            'attempts_reproduced':len(attempts),'valid_bases_reproduced':300,'events_reproduced':200,
            'exact_plans_checked':sum(r['exact']['plan'] is not None for r in rows),
            'heuristic_plans_checked':400,'native_models_and_responses_checked':model_count,
            'native_phase_statuses':dict(phase_counts),'native_models_replayed':replayed,
            'urgent_exhaustive_integer_start_checks':service_checks,'timing':timing,
            'outside_experiment_runs_changes':outside,'source_baseline_commit':baseline,
            'verifier_script_sha256':sha(Path(__file__)),'test_instances_generated':0,'next_stages_executed':[]}
    if args.write_audit:
        assert not (run/'independent_audit.json').exists()
        save_json(run/'independent_audit.json',output)
    print(json.dumps({k:v for k,v in output.items() if k!='urgent_exhaustive_integer_start_checks'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
