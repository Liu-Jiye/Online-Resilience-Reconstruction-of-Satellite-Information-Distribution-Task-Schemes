"""Run approved v1/v2 paired P2 urgent supplement, with cohorts kept separate."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import Item,canonical_json,case_from_dict
from isl.metrics import selection_key
from isl.p1_sources import save_json
from isl import repair,repair_v2,p2_exact,p2_exact_v2
from isl.urgent_supplement import pressure_label
from run_p2 import pin_process
from run_p0 import environment


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    inputs=ROOT/'reports/p2/P2-urgent-supplement-inputs-v1';config=load(inputs/'config.json')
    manifest=load(inputs/'manifest.json')
    for name,expected in manifest['source_sha256'].items():assert sha(REPO/name)==expected,name
    for name,expected in manifest['artifact_sha256'].items():assert sha(inputs/name)==expected,name
    old_run=ROOT/'reports/p2/P2-20261105T114327Z';old_inputs=ROOT/'reports/p2/P2-inputs-v1'
    old_rows=[json.loads(l) for l in (old_run/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    for name,expected in load(old_run/'acceptance_manifest.json')['file_sha256'].items():assert sha(REPO/name)==expected,name
    output=ROOT/'reports/p2'/datetime.now(timezone.utc).strftime('P2-urgent-supplement-%Y%m%dT%H%M%SZ')
    output.mkdir(exist_ok=False)
    affinity=pin_process();env=environment()
    env.update(scope='P2 urgent supplemental paired diagnostic/confirmation only',affinity_pinned=True,actual_affinity=affinity)
    save_json(output/'environment.json',env);save_json(output/'config.json',config)
    selected=load(inputs/'selected_events.json');work=[]
    with zipfile.ZipFile(old_inputs/'event_cases.zip') as bundle:
        for row in old_rows:
            if row['event_spec']['kind']=='urgent_insertion':
                ordinal=row['event_spec']['event_ordinal'];payload=bundle.read(f'event-{ordinal:03d}.json')
                work.append(({'cohort':'old_replay','entry':f'old-{ordinal:03d}.json','original_spec':row['event_spec']},payload,row))
    with zipfile.ZipFile(inputs/'event_cases.zip') as bundle:
        for spec in selected:
            payload=bundle.read(spec['entry'])
            assert hashlib.sha256(payload).hexdigest()==manifest['case_entry_sha256'][spec['entry']]
            work.append((spec,payload,None))
    rng=np.random.Generator(np.random.PCG64(162000));rows=[]
    with (output/'results.jsonl').open('w',encoding='utf-8',newline='\n') as stream, \
         zipfile.ZipFile(output/'solver_artifacts.zip','w',compression=zipfile.ZIP_DEFLATED) as proofs:
        for index,(spec,payload,old) in enumerate(work):
            case=case_from_dict(json.loads(payload));results={}
            methods=['v1_PALR','v1_exact','v2_PALR','v2_exact']
            order=[methods[i] for i in rng.permutation(4)]
            try:
                for method in order:
                    if method.endswith('PALR'):
                        module=repair if method.startswith('v1') else repair_v2
                        results[method]=module.run_method(case,w=config['w'],B=config['B'],budget_ms=config['heuristic_budget_ms'])
                    else:
                        module=p2_exact if method.startswith('v1') else p2_exact_v2
                        results[method],artifacts=module.solve_exact(case,w=config['w'],B=config['B'],limit_s=config['exact_limit_s'],seed=config['solver_seed'])
                        for pi,artifact in enumerate(artifacts):
                            for name,value in artifact.items():proofs.writestr(f'{spec["entry"]}/{method}/phase-{pi}/{name}.txt',value)
                comparisons={}
                for version,module in [('v1',p2_exact),('v2',p2_exact_v2)]:
                    h,e=results[version+'_PALR'],results[version+'_exact'];ctx=module.context(case,config['w'],config['B'])
                    assert h['center_index']==ctx['center'] and h['editable_indices']==list(ctx['indices'])
                    if h['validation'] and h['validation']['feasible']:
                        plan=tuple(Item(**p) for p in h['plan']);module.witness(case,ctx,plan)
                        key=selection_key(case,plan)
                        if e['proven_optimal']:assert tuple(e['selection_key'])<=key
                        assert not e['proven_infeasible']
                        comparisons[version]={'full_optimum_match':list(key)==e['selection_key'] if e['proven_optimal'] else None,
                                              'same_service_tier':list(key)[0]==e['selection_key'][0] if e['selection_key'] else None}
                label=pressure_label(case,full=spec['cohort']=='pressure')
                if spec['cohort']=='pressure':assert label['category']==spec['category']
                if label['category']=='outside_neighborhood' and spec['cohort']=='pressure':
                    wide,artifacts=p2_exact_v2.solve_exact(case,w=config['pressure']['wide_w_for_diagnostic'],B=config['B'],limit_s=30,seed=11)
                    results['v2_exact_w20_diagnostic']=wide
                    assert wide['urgent_certificate']=='service_feasible'
                    for pi,artifact in enumerate(artifacts):
                        for name,value in artifact.items():proofs.writestr(f'{spec["entry"]}/v2_exact_w20_diagnostic/phase-{pi}/{name}.txt',value)
                if old and results['v1_PALR']['status']!='timeout':assert results['v1_PALR']['plan']==old['heuristic_50ms']['plan']
                row={'event_spec':spec,'case_sha256':hashlib.sha256(payload).hexdigest(),'execution_order':order,
                     'results':results,'comparisons':comparisons,'independent_urgent_label':label}
                stream.write(canonical_json(row)+'\n');stream.flush();rows.append(row)
            except Exception as error:
                save_json(output/'failure.json',{'event_index':index,'event_spec':spec,'type':type(error).__name__,'message':str(error)})
                raise
            if (index+1)%10==0:print(json.dumps({'completed':index+1,'total':len(work),'cohort':spec['cohort']}),flush=True)
    cohorts={}
    for cohort in ('old_replay','natural','pressure'):
        subset=[r for r in rows if r['event_spec']['cohort']==cohort]
        info={'events':len(subset)}
        for version in ('v1','v2'):
            hs=[r['results'][version+'_PALR'] for r in subset];es=[r['results'][version+'_exact'] for r in subset]
            info[version]={'PALR_service_success':sum(h['metrics']['service_success'] for h in hs),
                           'PALR_online_service_success':sum(h['metrics']['online_success'] for h in hs),
                           'PALR_timeouts':sum(h['status']=='timeout' for h in hs),
                           'exact_service_feasible':sum(e['urgent_certificate']=='service_feasible' for e in es),
                           'exact_statuses':dict(Counter(e['status'] for e in es)),
                           'exact_service_certificates':dict(Counter(e['urgent_certificate'] for e in es))}
        info['paired_PALR_service_gains']=sum(not r['results']['v1_PALR']['metrics']['service_success'] and r['results']['v2_PALR']['metrics']['service_success'] for r in subset)
        info['paired_PALR_service_losses']=sum(r['results']['v1_PALR']['metrics']['service_success'] and not r['results']['v2_PALR']['metrics']['service_success'] for r in subset)
        cohorts[cohort]=info
    summary={'study':config['study'],'run_id':output.name,'cohorts':cohorts,'input_summary':load(inputs/'summary.json'),
             'P3_started':False,'old_results_overwritten':False}
    save_json(output/'summary.json',summary)
    sources=list((ROOT/'src').rglob('*.py'))+list((ROOT/'scripts').glob('*supplement*.py'))+list((ROOT/'tests').glob('*.py'))
    sources += [ROOT/'configs/p2_urgent_supplement.json',ROOT/'protocol/P2_URGENT_SUPPLEMENT_CONTRACT.md',ROOT/'environment/requirements-p2.lock.txt']
    save_json(output/'manifest.json',{'study':config['study'],'run_id':output.name,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in sorted(set(sources))},
        'input_manifest_sha256':sha(inputs/'manifest.json'),
        'artifact_sha256':{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        'finished_at_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
