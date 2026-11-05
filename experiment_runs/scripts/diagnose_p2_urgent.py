"""Layered enumeration and paired exact probes on all 67 frozen P2 urgent events.

No old evidence or runtime code is edited. Counterfactual urgent eligibility
exists only inside this diagnostic script, never in the production solver.
"""
from collections import Counter
from dataclasses import asdict,replace
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from time import perf_counter_ns
from ortools.sat.python import cp_model

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import Item,case_from_dict,ordered
from isl.p1_sources import save_json
from isl.p2_exact import context,build_model
from isl.validation import validate
from run_p0 import environment
from run_p2 import pin_process


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def enumerate_layers(case,ctx):
    instance=ctx['instance'];task=case.event.urgent
    frozen_ids={p.task_id for p in case.frozen}
    exterior=tuple(p for p in ctx['unchanged'] if p.task_id not in frozen_ids)
    universe=list(range(task.release,task.deadline-task.duration+1))
    names=['physical','physical_and_calendar','physical_calendar_frozen',
           'physical_calendar_all_immutable','physical_calendar_full_reference',
           'frozen_without_calendar','E_exterior_without_frozen_or_calendar']
    starts={name:[] for name in names};samples={}
    # Deliberately recompute duration and per-window coverage; do not call
    # placement.opportunities or infer physical feasibility from pool membership.
    duration=1+(task.data_bits+task.rate_bps-1)//task.rate_bps
    assert duration==task.duration
    def overlap(item,start,end):return start<item.end and item.start<end
    for start in universe:
        end=start+duration
        physical=any(c.sender==task.sender and c.receiver==task.receiver and
                     c.start<=start and end<=c.end for c in instance.contacts)
        if not physical:continue
        item=Item(task.id,task.sender,task.receiver,start,end)
        endpoints={task.sender,task.receiver}
        calendar=any(b.resource in endpoints and overlap(b,start,end) for b in instance.calendar)
        frozen=any(endpoints & {p.sender,p.receiver} and overlap(p,start,end) for p in case.frozen)
        outside=any(endpoints & {p.sender,p.receiver} and overlap(p,start,end) for p in exterior)
        full=any(endpoints & {p.sender,p.receiver} and overlap(p,start,end) for p in case.reference)
        flags={'physical':True,'physical_and_calendar':not calendar,
               'physical_calendar_frozen':not calendar and not frozen,
               'physical_calendar_all_immutable':not calendar and not frozen and not outside,
               'physical_calendar_full_reference':not calendar and not full,
               'frozen_without_calendar':not frozen,
               'E_exterior_without_frozen_or_calendar':not outside}
        plans={'physical':(replace(instance,calendar=()),()),
               'physical_and_calendar':(instance,()),
               'physical_calendar_frozen':(instance,case.frozen),
               'physical_calendar_all_immutable':(instance,ctx['unchanged']),
               'physical_calendar_full_reference':(instance,case.reference),
               'frozen_without_calendar':(replace(instance,calendar=()),case.frozen),
               'E_exterior_without_frozen_or_calendar':(replace(instance,calendar=()),exterior)}
        for name,flag in flags.items():
            # Check every enumerated claim through the independent full-plan checker.
            ins,retained=plans[name]
            plan=ordered(retained+(item,))
            assert validate(ins,plan).feasible==flag,(case.event.id,start,name)
            if flag:
                starts[name].append(start)
                if name not in samples:samples[name]=[asdict(p) for p in plan]
    nested=names[:5]
    assert all(set(starts[b])<=set(starts[a]) for a,b in zip(nested,nested[1:]))
    return {'integer_start_universe':universe,'feasible_starts':starts,
            'feasible_start_counts':{k:len(v) for k,v in starts.items()},
            'first_feasible_plan_by_layer':samples,
            'blocking_reservations':{'calendar':[asdict(b) for b in instance.calendar if b.resource in (task.sender,task.receiver)],
                                     'frozen':[asdict(p) for p in case.frozen if {p.sender,p.receiver}&{task.sender,task.receiver}],
                                     'E_exterior':[asdict(p) for p in exterior if {p.sender,p.receiver}&{task.sender,task.receiver}]}}


def exact_probe(case,ctx,exempt,config):
    diagnostic_ctx={**ctx,'allowed':set(ctx['allowed'])}
    if exempt:diagnostic_ctx['allowed'].add(case.event.urgent.id)
    started=perf_counter_ns()
    model,present,starts,ends,weights,alternatives=build_model(case,diagnostic_ctx,True)
    pbtxt=str(model.proto).encode('utf-8')
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=config['CP_SAT_seed']
    solver.parameters.max_time_in_seconds=config['CP_SAT_limit_s_per_probe']
    solver.parameters.absolute_gap_limit=0;solver.parameters.relative_gap_limit=0
    status=solver.solve(model);name=solver.status_name(status)
    assert name in ('OPTIMAL','INFEASIBLE','FEASIBLE','UNKNOWN'),solver.response_stats()
    feasible=status in (cp_model.OPTIMAL,cp_model.FEASIBLE)
    plan=ordered(Item(t.id,t.sender,t.receiver,solver.value(starts[t.id]),solver.value(ends[t.id]))
                 for t in ctx['instance'].tasks if solver.value(present[t.id])) if feasible else None
    evidence=None
    if plan is not None:
        assert case.event.urgent.id in {p.task_id for p in plan}
        before={p.task_id:p for p in ctx['initial']};after={p.task_id:p for p in plan}
        removed=sorted(t for t,p in before.items() if after.get(t)!=p)
        added=[asdict(p) for t,p in sorted(after.items()) if before.get(t)!=p]
        trace=([{'removed':removed,'added':[]}] if removed else [])+[{'removed':[],'added':[p]} for p in added]
        admissions=sum(p['task_id'] not in ctx['original'] for p in added)
        check=validate(ctx['instance'],plan,frozen=case.frozen,cancelled=case.event.cancelled,
                       unchanged=ctx['unchanged'],original_ids=ctx['original'],budget=ctx['B'],
                       admissions=admissions,initial=ctx['initial'],trace=trace)
        assert check.feasible,check.errors
        assert all(p.task_id in diagnostic_ctx['allowed'] for p in plan)
        evidence={'validation':check.to_dict(),'trace':trace,'admissions':admissions}
    return {'eligibility_exemption':exempt,'status':name,'objective':solver.objective_value if feasible else None,
            'best_bound':solver.best_objective_bound,'solver_parameters':str(solver.parameters),
            'solver_wall_s':solver.wall_time,'total_ns':perf_counter_ns()-started,
            'plan':[asdict(p) for p in plan] if plan is not None else None,'evidence':evidence}, {
                'model.pbtxt':pbtxt,'response.pbtxt':str(solver.response_proto).encode('utf-8'),
                'stats.txt':solver.response_stats().encode('utf-8')}


def main():
    config_path=ROOT/'configs/p2_urgent_diagnostic.json';config=load(config_path)
    source=ROOT/config['source_run'];inputs=ROOT/config['source_inputs']
    # Verify the entire previously accepted P2 evidence before diagnosing it.
    accepted=load(source/'acceptance_manifest.json')
    for name,expected in accepted['file_sha256'].items():assert sha(REPO/name)==expected,name
    old=[json.loads(l) for l in (source/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    selected=[r for r in old if r['event_spec']['kind']=='urgent_insertion'];assert len(selected)==67
    out=ROOT/'reports/p2'/datetime.now(timezone.utc).strftime('P2-urgent-diagnostic-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    save_json(out/'config.json',config)
    affinity=pin_process();env=environment()
    env.update(scope='P2 diagnostic only; no rule revision or new-stage experiment',affinity_pinned=True,actual_affinity=affinity)
    save_json(out/'environment.json',env)
    rows=[]
    with zipfile.ZipFile(inputs/'event_cases.zip') as cases,zipfile.ZipFile(out/'paired_solver_evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as proofs:
        for prior in selected:
            spec=prior['event_spec'];ordinal=spec['event_ordinal'];payload=cases.read(f'event-{ordinal:03d}.json')
            assert hashlib.sha256(payload).hexdigest()==prior['case_sha256']
            case=case_from_dict(json.loads(payload));ctx=context(case,config['w'],config['B'])
            layers=enumerate_layers(case,ctx);counts=layers['feasible_start_counts']
            eligible=case.event.urgent.id in ctx['allowed'];local=bool(counts['physical_calendar_all_immutable'])
            probes={}
            for label,exempt in [('original',False),('urgent_exempt',True)]:
                result,artifacts=exact_probe(case,ctx,exempt,config)
                expected=local and (eligible or exempt)
                assert result['status']==('OPTIMAL' if expected else 'INFEASIBLE')
                probes[label]=result
                for name,content in artifacts.items():proofs.writestr(f'event-{ordinal:03d}/{label}/{name}',content)
            assert probes['original']['status']==prior['exact']['phases'][0]['status']
            service=prior['heuristic_50ms']['metrics']['service_success']
            if not counts['physical']:category='no_physical_opportunity'
            elif not counts['physical_and_calendar']:category='calendar_blocks_all'
            elif not counts['physical_calendar_frozen']:category='frozen_blocks_remaining'
            elif not local:category='E_exterior_blocks_remaining'
            elif not eligible:category='eligibility_only_exclusion'
            elif not service:category='PALR_service_search_failure'
            else:category='original_PALR_service_success'
            rows.append({'event_spec':spec,'case_sha256':prior['case_sha256'],'urgent_task':asdict(case.event.urgent),
                         'original_eligible':eligible,'center_index':ctx['center'],'editable_indices':list(ctx['indices']),
                         'candidate_spans':list(ctx['spans']),'layers':layers,'classification':category,
                         'eligibility_exclusion_avoidable':local and not eligible,
                         'original_PALR_service_success':service,'paired_probes':probes})
    save_json(out/'diagnostics.json',rows)
    summary={'diagnosed_events':67,'original_eligibility_excluded':sum(not r['original_eligible'] for r in rows),
             'first_eliminating_layer_counts':dict(Counter(r['classification'] for r in rows)),
             'nonexclusive_layer_feasible_event_counts':{k:sum(bool(r['layers']['feasible_start_counts'][k]) for r in rows) for k in rows[0]['layers']['feasible_start_counts']},
             'original_excluded_by_first_eliminating_layer':dict(Counter(r['classification'] for r in rows if not r['original_eligible'])),
             'avoidable_service_failures_from_eligibility_filter':sum(r['eligibility_exclusion_avoidable'] for r in rows),
             'paired_original_statuses':dict(Counter(r['paired_probes']['original']['status'] for r in rows)),
             'paired_exempt_statuses':dict(Counter(r['paired_probes']['urgent_exempt']['status'] for r in rows)),
             'conditional_cases_needing_E_edits':sum(bool(r['layers']['feasible_start_counts']['physical_calendar_all_immutable']) and not r['layers']['feasible_start_counts']['physical_calendar_full_reference'] for r in rows),
             'conclusion_scope':'Existing 67 P2 events only; eligibility exclusion association is not causal evidence',
             'rule_revision_applied':False,'pressure_instances_generated':0,'P3_started':False}
    save_json(out/'summary.json',summary)
    flat=[]
    for r in rows:
        flat.append({**r['event_spec'],'original_eligible':r['original_eligible'],
                     **r['layers']['feasible_start_counts'],'classification':r['classification'],
                     'avoidable_filter_failure':r['eligibility_exclusion_avoidable'],
                     'original_CP_status':r['paired_probes']['original']['status'],
                     'exempt_CP_status':r['paired_probes']['urgent_exempt']['status']})
    with (out/'per_event_diagnosis.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    save_json(out/'manifest.json',{'study':config['study'],'run_id':out.name,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_P2_acceptance_sha256':sha(source/'acceptance_manifest.json'),
        'source_cases_sha256':sha(inputs/'event_cases.zip'),
        'diagnostic_script_sha256':sha(Path(__file__)),'config_sha256':sha(config_path),
        'artifact_sha256':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()},
        'all_61_exclusions_checked_not_selected_by_outcome':True})
    print(json.dumps({'directory':str(out),'summary':summary},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
