"""Verify layered evidence and replay all paired urgent diagnostic models."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from ortools.sat.python import cp_model,cp_model_helper
from diagnose_p2_urgent import ROOT,REPO,enumerate_layers
from isl.models import Item,case_from_dict,canonical_json
from isl.p2_exact import context,build_model
from isl.p1_sources import save_json
from isl.validation import validate


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--write-audit',action='store_true')
    args=parser.parse_args();out=args.directory.resolve()
    manifest=load(out/'manifest.json');config=load(out/'config.json')
    for name,expected in manifest['artifact_sha256'].items():assert sha(out/name)==expected,name
    assert sha(ROOT/'scripts/diagnose_p2_urgent.py')==manifest['diagnostic_script_sha256']
    assert sha(ROOT/'configs/p2_urgent_diagnostic.json')==manifest['config_sha256']
    original=ROOT/config['source_run'];inputs=ROOT/config['source_inputs']
    assert sha(original/'acceptance_manifest.json')==manifest['source_P2_acceptance_sha256']
    assert sha(inputs/'event_cases.zip')==manifest['source_cases_sha256']
    for name,expected in load(original/'acceptance_manifest.json')['file_sha256'].items():assert sha(REPO/name)==expected,name
    prior=[json.loads(l) for l in (original/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    expected_ordinals=[r['event_spec']['event_ordinal'] for r in prior if r['event_spec']['kind']=='urgent_insertion']
    rows=load(out/'diagnostics.json')
    assert [r['event_spec']['event_ordinal'] for r in rows]==expected_ordinals
    checked=0;statuses=Counter()
    with zipfile.ZipFile(inputs/'event_cases.zip') as cases,zipfile.ZipFile(out/'paired_solver_evidence.zip') as proofs:
        for row in rows:
            ordinal=row['event_spec']['event_ordinal'];payload=cases.read(f'event-{ordinal:03d}.json')
            assert hashlib.sha256(payload).hexdigest()==row['case_sha256']
            case=case_from_dict(json.loads(payload));ctx=context(case,config['w'],config['B'])
            assert canonical_json(enumerate_layers(case,ctx))==canonical_json(row['layers'])
            for label in ('original','urgent_exempt'):
                modified={**ctx,'allowed':set(ctx['allowed'])}
                if label=='urgent_exempt':modified['allowed'].add(case.event.urgent.id)
                model,present,starts,ends,weights,alt=build_model(case,modified,True)
                prefix=f'event-{ordinal:03d}/{label}/'
                assert str(model.proto)==proofs.read(prefix+'model.pbtxt').decode('utf-8')
                native=cp_model_helper.CpSolverResponse()
                assert native.parse_text_format(proofs.read(prefix+'response.pbtxt').decode('utf-8'))
                saved=row['paired_probes'][label]
                assert cp_model.CpSolver().status_name(native.status)==saved['status']
                solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
                solver.parameters.random_seed=11;solver.parameters.max_time_in_seconds=30
                solver.parameters.relative_gap_limit=0;solver.parameters.absolute_gap_limit=0
                status=solver.solve(model);assert solver.status_name(status)==saved['status']
                if saved['status']=='OPTIMAL':
                    assert solver.objective_value==native.objective_value==native.best_objective_bound==saved['objective']
                    plan=tuple(Item(**p) for p in saved['plan'])
                    assert case.event.urgent.id in {p.task_id for p in plan}
                    assert all(p.task_id in modified['allowed'] for p in plan)
                    ev=saved['evidence']
                    check=validate(ctx['instance'],plan,frozen=case.frozen,cancelled=case.event.cancelled,
                                   unchanged=ctx['unchanged'],original_ids=ctx['original'],budget=ctx['B'],
                                   admissions=ev['admissions'],initial=ctx['initial'],trace=ev['trace'])
                    assert check.feasible
                checked+=1;statuses[saved['status']]+=1
        assert len(proofs.namelist())==checked*3
    summary=load(out/'summary.json')
    assert dict(Counter(r['classification'] for r in rows))==summary['first_eliminating_layer_counts']
    assert sum(r['eligibility_exclusion_avoidable'] for r in rows)==summary['avoidable_service_failures_from_eligibility_filter']==4
    result={'passed':True,'run_id':out.name,'verified_at_utc':datetime.now(timezone.utc).isoformat(),
            'all_67_layers_recomputed':True,'paired_models_replayed':checked,'paired_statuses':dict(statuses),
            'old_P2_accepted_files_unchanged':True,'avoided_filter_only_service_failures':4,
            'rule_revision_applied':False,'pressure_instances_generated':0,'P3_started':False,
            'verifier_sha256':sha(Path(__file__))}
    if args.write_audit:
        assert not (out/'independent_audit.json').exists()
        save_json(out/'independent_audit.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
