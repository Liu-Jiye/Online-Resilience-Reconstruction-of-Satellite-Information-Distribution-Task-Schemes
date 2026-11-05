"""Execute only P2: 200 frozen small events and offline exact references."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,canonical_json,Item
from isl.p1_sources import save_json
from isl.p2_exact import solve_exact,context,witness
from isl.repair import run_method
from isl.metrics import selection_key
from run_p0 import environment


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_process():
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.GetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.c_size_t]
        process=kernel.GetCurrentProcess()
        original,system=ctypes.c_size_t(),ctypes.c_size_t()
        assert kernel.GetProcessAffinityMask(process,ctypes.byref(original),ctypes.byref(system))
        chosen=original.value & -original.value
        assert kernel.SetProcessAffinityMask(process,chosen)
        actual=ctypes.c_size_t()
        assert kernel.GetProcessAffinityMask(process,ctypes.byref(actual),ctypes.byref(system))
        assert actual.value==chosen
        return {'original_mask':original.value,'actual_mask':actual.value,'logical_processor':chosen.bit_length()-1}
    original=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{original[0]})
    return {'original_processors':original,'actual_processors':sorted(os.sched_getaffinity(0))}


def main():
    config=json.loads((ROOT/'configs/p2.json').read_text(encoding='utf-8'))
    inputs=ROOT/'reports/p2/P2-inputs-v1'
    input_manifest=json.loads((inputs/'manifest.json').read_text(encoding='utf-8'))
    for name,expected in input_manifest['source_sha256'].items():assert sha(REPO/name)==expected,name
    for name,expected in input_manifest['artifact_sha256'].items():assert sha(inputs/name)==expected,name
    output=ROOT/'reports/p2'/datetime.now(timezone.utc).strftime('P2-%Y%m%dT%H%M%SZ')
    output.mkdir(exist_ok=False)
    affinity=pin_process()
    env=environment();env.update(scope='P2 offline exact alignment; not main online benchmark',affinity_pinned=True,
        actual_affinity=affinity,threading_note='Process affinity restricted to one logical processor; CP-SAT one search worker; BLAS/OpenMP env limits 1',
        native_thread_environment={k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
    save_json(output/'environment.json',env)
    save_json(output/'config.json',config)
    rows=[]
    started=perf_counter_ns()
    events=json.loads((inputs/'selected_events.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(inputs/'event_cases.zip') as cases, \
         zipfile.ZipFile(output/'solver_artifacts.zip','w',compression=zipfile.ZIP_DEFLATED) as artifacts, \
         (output/'results.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for spec in events:
            ordinal=spec['event_ordinal'];name=f'event-{ordinal:03d}.json'
            payload=cases.read(name)
            assert hashlib.sha256(payload).hexdigest()==input_manifest['case_entry_sha256'][name]
            case=case_from_dict(json.loads(payload))
            try:
                online=run_method(case,'Fixed-PALR',w=config['w'],B=config['B'],budget_ms=config['heuristic_online_budget_ms'])
                alignment=run_method(case,'Fixed-PALR',w=config['w'],B=config['B'],budget_ms=config['heuristic_alignment_budget_ms'])
                exact,proofs=solve_exact(case,w=config['w'],B=config['B'],limit_s=config['exact_total_limit_s'],seed=config['exact_solver_seed'])
                ctx=context(case,config['w'],config['B'])
                comparisons={}
                for label,heuristic in [('online_50ms',online),('offline_alignment_30s',alignment)]:
                    assert heuristic['editable_indices']==list(ctx['indices'])
                    assert heuristic['center_index']==ctx['center']
                    assert heuristic['candidate_spans']==list(ctx['spans'])
                    if heuristic['validation'] and heuristic['validation']['feasible']:
                        plan=tuple(Item(**p) for p in heuristic['plan'])
                        witness(case,ctx,plan)
                        if exact['proven_infeasible']:raise AssertionError('Solver INFEASIBLE contradicts validated heuristic')
                        key=selection_key(case,plan)
                        if exact['proven_optimal']:assert tuple(exact['selection_key'])<=key
                        same_service=exact['selection_key'] is not None and exact['selection_key'][0]==key[0]
                        comparisons[label]={'heuristic_selection_key':list(key),
                            'exact_proven_optimal':exact['proven_optimal'],'same_service_tier':same_service,
                            'matches_proven_lexicographic_optimum':list(key)==exact['selection_key'] if exact['proven_optimal'] else None,
                            'utility_gap_to_proven_optimum':exact['metrics']['U_raw']-heuristic['metrics']['U_raw'] if exact['proven_optimal'] and same_service else None}
                    else:
                        comparisons[label]={'heuristic_selection_key':None,'reason':'no independently valid heuristic plan'}
                for i,proof in enumerate(proofs):
                    for key,value in proof.items():
                        artifacts.writestr(f'event-{ordinal:03d}/phase-{i}/{key}.txt',value)
                row={'event_spec':spec,'case_sha256':hashlib.sha256(payload).hexdigest(),
                     'exact':exact,'heuristic_50ms':online,'heuristic_30s':alignment,'comparisons':comparisons}
                stream.write(canonical_json(row)+'\n');stream.flush();rows.append(row)
            except Exception as error:
                save_json(output/'execution_failure.json',{'event_ordinal':ordinal,'event_spec':spec,'type':type(error).__name__,'message':str(error)})
                raise
            if (ordinal+1)%10==0:
                print(json.dumps({'completed':ordinal+1,'of':200,'statuses':dict(Counter(r['exact']['status'] for r in rows))}),flush=True)
    assert len(rows)==200
    summary={'stage':'P2','event_count':len(rows),'base_instances_generated':300,
        'exact_statuses':dict(Counter(r['exact']['status'] for r in rows)),
        'urgent_certificates':dict(Counter(r['exact']['urgent_certificate'] for r in rows)),
        'exact_total_over_30s_count':sum(r['exact']['actual_total_exceeds_30s'] for r in rows),
        'events_not_applicable':sum(not r['heuristic_50ms']['metrics']['applicable'] for r in rows),
        'run_wall_s':(perf_counter_ns()-started)/1e9,'test_instances_generated':0,'next_stages_executed':[]}
    for key in ('heuristic_50ms','heuristic_30s'):
        comparison_key='online_50ms' if key=='heuristic_50ms' else 'offline_alignment_30s'
        summary[key]={'statuses':dict(Counter(r[key]['status'] for r in rows)),
            'valid_plans':sum(bool(r[key]['validation'] and r[key]['validation']['feasible']) for r in rows),
            'service_success':sum(r[key]['metrics']['service_success'] for r in rows),
            'online_success':sum(r[key]['metrics']['online_success'] for r in rows),
            'matches_proven_lexicographic_optimum':sum(r['comparisons'][comparison_key].get('matches_proven_lexicographic_optimum') is True for r in rows)}
    save_json(output/'summary.json',summary)
    sources=list((ROOT/'src').rglob('*.py'))+list((ROOT/'tests').glob('*.py'))+list((ROOT/'scripts').glob('*.py'))
    sources += [ROOT/'configs/p2.json',ROOT/'protocol/P2_EXACT_CONTRACT.md',ROOT/'environment/requirements-p2.lock.txt']
    save_json(output/'manifest.json',{'run_id':output.name,'stage':'P2',
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in sorted(set(sources))},
        'input_manifest_sha256':sha(inputs/'manifest.json'),
        'artifact_sha256':{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        'finished_at_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'output':str(output),'summary':summary},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
